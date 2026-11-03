"""Asynchronous lifecycle coordinator for provider-backed Modbus scans."""

from __future__ import annotations

import asyncio
from collections import Counter, deque
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from time import monotonic
from typing import Any
from uuid import uuid4

from homeassistant.core import HomeAssistant

from .device_profile import GENERIC_DEVICE_PROFILE, DeviceProfile
from .models import GatewayInfo, ProbeResult, ProbeType, ScanOutcome, ScanPhase, ScanRequest
from .pollers import choose
from .provider import GatewayProvider, GatewayProviderError

SHUTDOWN_GRACE_SECONDS = 35
GENERIC_REQUEST_DEFAULTS: dict[str, Any] = {
    "probe_type": ProbeType.DEVICE_IDENTIFICATION,
    "register_address": 0,
    "register_count": 1,
    "timeout_ms": 500,
    "retries": 1,
    "inter_request_delay_ms": 100,
    "pause_normal_polling": False,
}


class ScanNotFoundError(LookupError):
    """The requested scan is not retained in memory."""


class GatewayBusyError(RuntimeError):
    """A scan already owns the Bus (or the whole Gateway) this request needs."""

    def __init__(
        self, provider: str, gateway_id: str, scan_id: str, bus: str | None = None
    ) -> None:
        target = f"Bus {bus} of gateway" if bus is not None else "Gateway"
        super().__init__(f"{target} {provider}/{gateway_id} is busy with active scan {scan_id}")
        self.scan_id = scan_id
        self.bus = bus


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class _ScanState:
    scan_id: str
    request: ScanRequest
    # The Bus scanned: the request's, else the one the provider resolved on connect.
    bus: str | None = None
    device_profile: dict[str, Any] = field(default_factory=GENERIC_DEVICE_PROFILE.summary)
    phase: ScanPhase = ScanPhase.RUNNING
    started_at: str = field(default_factory=_utc_now)
    finished_at: str | None = None
    current_address: int | None = None
    completed_addresses: int = 0
    counts: Counter[str] = field(default_factory=Counter)
    retained_results: list[ProbeResult] = field(default_factory=list)
    emitted_addresses: set[int] = field(default_factory=set)
    cancellation_requested: bool = False
    error: str | None = None
    error_info: dict[str, Any] | None = None
    operation_phase: str = "scheduled"
    attempt: int | None = None
    recovery_status: str = "unknown"
    recovery_error_code: str | None = None
    cleanup_status: str = "unknown"
    # Scan Lease as reported by the Gateway: none, active, ended or unconfirmed.
    lease_status: str = "none"
    lease_end_reason: str | None = None
    paused_pollers: list[dict[str, Any]] = field(default_factory=list)
    # Chosen pollers the Gateway's current table no longer has; they were not paused.
    removed_pollers: list[dict[str, Any]] = field(default_factory=list)
    started_clock: float = field(default_factory=monotonic)
    elapsed_ms: int = 0
    events: deque = field(default_factory=lambda: deque(maxlen=32))


class ModbusScanCoordinator:
    """Own scan validation, concurrency, snapshots, tasks, and bounded history."""

    def __init__(
        self,
        hass: HomeAssistant,
        providers: list[GatewayProvider],
        *,
        max_history: int = 20,
        history=None,
        issue_callback=None,
        selection_store=None,
    ) -> None:
        self._hass = hass
        self._providers = {provider.provider_id: provider for provider in providers}
        self._max_history = max_history
        self._history = history
        self._issue_callback = issue_callback
        # Saved Pausable Poller checklists (PollerSelectionStore), revalidated here.
        self._selection_store = selection_store
        self._issues_failed = False
        self._scans: dict[str, _ScanState] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        # (provider, gateway_id, bus) -> running scan id; a None bus holds the whole Gateway.
        self._active: dict[tuple[str, str, str | None], str] = {}
        self._terminal_order: deque[str] = deque()
        self._shutting_down = False

    def list_gateways(self) -> dict[str, Any]:
        """Return every provider gateway in a stable service response."""
        gateways = [
            {**gateway.as_dict(), **self._poller_selection(gateway, prune=False)}
            for provider in self._providers.values()
            for gateway in provider.list_gateways()
        ]
        return {"gateways": gateways}

    def _poller_selection(self, gateway: GatewayInfo, *, prune: bool) -> dict[str, Any]:
        """Pausable Poller checklist per Bus of a bridge v2 Gateway, revalidated if known."""
        if self._selection_store is None or "bridge_v2" not in gateway.capabilities:
            return {}
        tables = (gateway.health or {}).get("pausable_pollers")
        selection, removed = self._selection_store.report(gateway.gateway_id, tables, prune=prune)
        return {"poller_selection": selection, "removed_pollers": removed}

    def _gateway(self, provider_id: str, gateway_id: str) -> GatewayInfo | None:
        provider = self._providers.get(provider_id)
        if provider is None:
            return None
        return next(
            (item for item in provider.list_gateways() if item.gateway_id == gateway_id), None
        )

    def saved_poller_selection(self, gateway_id: str) -> dict[str, list[dict[str, Any]]]:
        """Saved Pausable Poller checklist per Bus of one Gateway, for a Scan request."""
        return self._selection_store.saved(gateway_id) if self._selection_store else {}

    def save_poller_selection(self, gateway_id: str, bus: str, indices) -> dict[str, Any]:
        """Save which Pausable Pollers of one Bus a Scan pauses (indices of its table)."""
        gateway = self._gateway("esphome", gateway_id)
        if (
            gateway is None
            or self._selection_store is None
            or "bridge_v2" not in gateway.capabilities
        ):
            raise ValueError("Pausable Poller selection needs an enrolled bridge v2 Gateway")
        tables = (gateway.health or {}).get("pausable_pollers")
        selection, _removed = self._selection_store.report(gateway_id, tables, prune=False)
        if bus not in selection:
            raise ValueError(
                f"Bus {bus} has no known Pausable Poller table; check the Gateway first"
            )
        checklist, unknown = choose(selection[bus], indices)
        if unknown:
            raise ValueError(f"Bus {bus} has no Pausable Poller with index {unknown}")
        saved = self._selection_store.saved(gateway_id)
        saved[bus] = checklist
        self._selection_store.save(gateway_id, saved)
        return {
            "gateway_id": gateway_id,
            "bus": bus,
            **self._poller_selection(gateway, prune=False),
        }

    def request_defaults(
        self,
        provider_id: str,
        gateway_id: str,
        profile: DeviceProfile = GENERIC_DEVICE_PROFILE,
    ) -> dict[str, Any]:
        """Device Profile defaults, then the gateway adapter's, then generic defaults."""
        gateway = self._gateway(provider_id, gateway_id)
        reported = gateway.limits.defaults if gateway and gateway.limits else {}
        return {**GENERIC_REQUEST_DEFAULTS, **reported, **profile.request_defaults}

    def profile_in_use(self, profile_id: str) -> str | None:
        """The running Scan that uses this Device Profile, if any."""
        return next(
            (
                scan_id
                for scan_id in self._active.values()
                if self._scans[scan_id].device_profile["id"] == profile_id
            ),
            None,
        )

    def _running_on(self, provider: str, gateway_id: str, bus: str | None = None) -> str | None:
        """The running Scan holding this Bus; with bus None, any running Scan of the Gateway.

        A Scan whose Bus is not known yet (None) holds every Bus of its Gateway.
        """
        return next(
            (
                scan_id
                for (p, g, b), scan_id in self._active.items()
                if p == provider and g == gateway_id and (bus is None or b is None or b == bus)
            ),
            None,
        )

    @staticmethod
    def _target_bus(request: ScanRequest, gateway: GatewayInfo) -> ScanRequest:
        """Resolve and check the Scan's Bus against the Buses the Gateway reports.

        A Gateway with one known Bus needs no ``bus``. While a bridge v2 Gateway's Buses are
        not known yet (never checked), the provider resolves the Bus when it connects.
        """
        names = [row["bus"] for row in gateway.buses]
        if request.bus is not None:
            if names and request.bus not in names:
                raise ValueError(
                    f"Gateway {request.gateway_id} has no Bus {request.bus}; "
                    f"its Buses are {', '.join(names)}"
                )
            if not names and "bridge_v2" not in gateway.capabilities:
                raise ValueError(f"Gateway {request.gateway_id} does not support bus selection")
            return request
        if len(names) == 1:
            return replace(request, bus=names[0])
        if len(names) > 1:
            raise ValueError(
                f"Gateway {request.gateway_id} has {len(names)} Buses ({', '.join(names)}); "
                "choose one with bus"
            )
        return request

    async def start(
        self, request: ScanRequest, profile: DeviceProfile = GENERIC_DEVICE_PROFILE
    ) -> dict[str, Any]:
        """Validate and schedule a scan without awaiting its address loop.

        The effective limits are the gateway's limits intersected with the Device Profile's.
        """
        if self._shutting_down:
            raise RuntimeError("Modbus scan coordinator is shutting down")
        request.validate()
        provider = self._providers.get(request.provider)
        if provider is None:
            raise ValueError(f"Unsupported Modbus scan provider: {request.provider}")
        gateway = self._gateway(request.provider, request.gateway_id)
        if gateway is None:
            raise ValueError(f"Unknown Modbus gateway: {request.gateway_id}")
        if gateway.limits is not None:
            gateway.limits.validate(request)
        profile.limits.validate(request)
        if request.pause_pollers is not None and "bridge_v2" not in gateway.capabilities:
            raise ValueError("pause_pollers needs a bridge v2 Gateway with Pausable Pollers")
        request = self._target_bus(request, gateway)
        if existing := self._running_on(request.provider, request.gateway_id, request.bus):
            raise GatewayBusyError(request.provider, request.gateway_id, existing, request.bus)

        scan_id = str(uuid4())
        state = _ScanState(
            scan_id=scan_id, request=request, bus=request.bus, device_profile=profile.summary()
        )
        self._scans[scan_id] = state
        self._active[request.gateway_key] = scan_id
        run_coroutine = self._run(state, provider)
        try:
            task = self._hass.async_create_task(
                run_coroutine,
                f"Modbus scan {scan_id}",
                eager_start=False,
            )
        except BaseException:
            # Home Assistant rejected scheduling, so no task owns the coroutine
            # or the state reserved above. Close and roll back atomically.
            run_coroutine.close()
            self._scans.pop(scan_id, None)
            if self._active.get(request.gateway_key) == scan_id:
                self._active.pop(request.gateway_key, None)
            raise
        self._tasks[scan_id] = task
        if self._history:
            self._history.started(self.status(scan_id))
        return self.status(scan_id)

    def status(self, scan_id: str) -> dict[str, Any]:
        """Return a serializable lifecycle snapshot."""
        if scan_id not in self._scans and self._history and (record := self._history.get(scan_id)):
            return record["status"]
        state = self._get(scan_id)
        total = state.request.address_count
        return {
            "scan_id": state.scan_id,
            "provider": state.request.provider,
            "gateway_id": state.request.gateway_id,
            "bus": state.bus,
            "device_profile": dict(state.device_profile),
            "status": state.phase.value,
            "phase": state.phase.value,
            "current_address": state.current_address,
            "completed_addresses": state.completed_addresses,
            "total_addresses": total,
            "progress_percent": round(state.completed_addresses * 100 / total, 1),
            "responder_count": sum(
                state.counts[outcome.value]
                for outcome in (
                    ScanOutcome.IDENTIFIED,
                    ScanOutcome.RESPONDED,
                    ScanOutcome.MODBUS_EXCEPTION,
                    ScanOutcome.POSSIBLE_COLLISION,
                )
            ),
            "outcome_counts": self._serialized_counts(state),
            "started_at": state.started_at,
            "finished_at": state.finished_at,
            "estimated_worst_case_ms": state.request.estimated_worst_case_ms,
            "execution_budget_ms": state.request.execution_budget_ms,
            "elapsed_ms": int((monotonic() - state.started_clock) * 1000)
            if state.phase == ScanPhase.RUNNING
            else state.elapsed_ms,
            "operation_phase": state.operation_phase,
            "attempt": state.attempt,
            "events": [dict(event) for event in state.events],
            "recovery_status": state.recovery_status,
            "recovery_error_code": state.recovery_error_code,
            "cleanup_status": state.cleanup_status,
            **self._lease(state),
            "cancellation_requested": state.cancellation_requested,
            "error": state.error,
            "error_info": state.error_info,
        }

    def results(self, scan_id: str) -> dict[str, Any]:
        """Return bounded responder details and complete outcome counts."""
        if scan_id not in self._scans and self._history and (record := self._history.get(scan_id)):
            return record["results"]
        state = self._get(scan_id)
        return {
            "scan_id": state.scan_id,
            "provider": state.request.provider,
            "gateway_id": state.request.gateway_id,
            "bus": state.bus,
            "device_profile": dict(state.device_profile),
            "status": state.phase.value,
            "phase": state.phase.value,
            "responders": [
                result.as_dict() for result in state.retained_results if result.is_responder
            ],
            "outcome_counts": self._serialized_counts(state),
            "completed_addresses": state.completed_addresses,
            "total_addresses": state.request.address_count,
            "events": [dict(event) for event in state.events],
            "best_effort": True,
            "uniqueness_guaranteed": False,
            "recovery_status": state.recovery_status,
            "recovery_error_code": state.recovery_error_code,
            "cleanup_status": state.cleanup_status,
            **self._lease(state),
            "error": state.error,
            "error_info": state.error_info,
        }

    @staticmethod
    def _lease(state: _ScanState) -> dict[str, Any]:
        return {
            "lease_status": state.lease_status,
            "lease_end_reason": state.lease_end_reason,
            "paused_pollers": [dict(poller) for poller in state.paused_pollers],
            "removed_pollers": [dict(poller) for poller in state.removed_pollers],
        }

    async def cancel(self, scan_id: str) -> dict[str, Any]:
        """Request cooperative cancellation after the current transaction."""
        if scan_id not in self._scans:
            return self.status(scan_id)  # History is terminal; never replay it.
        state = self._get(scan_id)
        if state.phase == ScanPhase.RUNNING:
            state.cancellation_requested = True
        return self.status(scan_id)

    async def wait(self, scan_id: str) -> dict[str, Any]:
        """Wait until one retained scan reaches a terminal state."""
        self._get(scan_id)
        if task := self._tasks.get(scan_id):
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                current_task = asyncio.current_task()
                if current_task is not None and current_task.cancelling():
                    raise
        return self.status(scan_id)

    async def async_shutdown(self) -> None:
        """Allow bounded cooperative recovery before forcing task cancellation."""
        self._shutting_down = True
        active_scans: list[tuple[str, asyncio.Task[None]]] = []
        for scan_id, task in tuple(self._tasks.items()):
            state = self._scans.get(scan_id)
            if state is not None and state.phase == ScanPhase.RUNNING:
                state.cancellation_requested = True
                active_scans.append((scan_id, task))
        if active_scans:
            # Response <=6s + fresh recovery <=25s + disconnect <=3s.
            # Immediate Task.cancel() intentionally skips recovery in the
            # provider; reserve that fallback for an expired grace period.
            _, pending = await asyncio.wait(
                [task for _scan_id, task in active_scans], timeout=SHUTDOWN_GRACE_SECONDS
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*(task for _scan_id, task in active_scans), return_exceptions=True)
        for scan_id, _task in active_scans:
            state = self._scans.get(scan_id)
            if state is not None and state.phase == ScanPhase.RUNNING:
                # A non-eager task can be cancelled before its coroutine starts,
                # so its normal ``finally`` block never has a chance to run.
                state.phase = ScanPhase.CANCELLED
                state.finished_at = _utc_now()
                if self._active.get(state.request.gateway_key) == scan_id:
                    self._active.pop(state.request.gateway_key, None)
                self._record_terminal(scan_id)
                self._tasks.pop(scan_id, None)

    async def _run(self, state: _ScanState, provider: GatewayProvider) -> None:
        def emit(result: ProbeResult) -> None:
            normalized = self._normalize_result(state, result)
            state.current_address = normalized.address
            state.completed_addresses += 1
            state.counts[normalized.outcome.value] += 1
            state.emitted_addresses.add(normalized.address)
            if normalized.outcome != ScanOutcome.TIMEOUT:
                state.retained_results.append(normalized)

        def progress(update):
            for key, choices in {
                "operation_phase": {
                    "connect",
                    "verify_identity",
                    "verify_bridge",
                    "probe",
                    "inter_request_delay",
                    "recovery",
                    "finished",
                },
                "recovery_status": {"unknown", "pending", "verified", "failed"},
                "cleanup_status": {"unknown", "pending", "closed", "forced", "failed"},
                "lease_status": {"none", "active", "ended", "unconfirmed"},
            }.items():
                if update.get(key) in choices:
                    if key == "operation_phase" and update[key] != state.operation_phase:
                        state.events.append(
                            {
                                "phase": update[key],
                                "elapsed_ms": int((monotonic() - state.started_clock) * 1000),
                            }
                        )
                    setattr(state, key, update[key])
            if update.get("lease_status") == state.lease_status and update.get(
                "lease_end_reason"
            ) in {
                None,
                "released",
                "idle",
                "hard_limit",
                "superseded",
            }:
                state.lease_end_reason = update["lease_end_reason"]
            if state.bus is None and isinstance(update.get("bus"), str):
                state.bus = update["bus"]
            for key in ("paused_pollers", "removed_pollers"):
                if isinstance(update.get(key), list):
                    setattr(
                        state,
                        key,
                        [
                            {name: poller.get(name) for name in ("index", "name", "address")}
                            for poller in update[key]
                            if isinstance(poller, dict) and "index" in poller
                        ],
                    )
            if update.get("recovery_error_code") in {
                "FIRMWARE_FAULT",
                "DEVICE_RESTARTED",
                "PROFILE_MISMATCH",
                "RESTORE_UNCONFIRMED",
                "API_DISCONNECTED",
                "RESPONSE_INVALID",
            }:
                state.recovery_error_code = update["recovery_error_code"]
            if (
                type(update.get("current_address")) is int
                and state.request.start_id <= update["current_address"] <= state.request.end_id
            ):
                state.current_address = update["current_address"]
            if (
                type(update.get("attempt")) is int
                and 1 <= update["attempt"] <= state.request.retries + 1
            ):
                state.attempt = update["attempt"]

        try:
            kwargs = {"progress": progress} if getattr(provider, "supports_progress", False) else {}
            cleanup_reserve_ms = 3000 if state.request.provider == "esphome" else 0
            async with asyncio.timeout(
                (state.request.execution_budget_ms - cleanup_reserve_ms) / 1000
            ):
                await provider.run_scan(
                    state.request, emit, lambda: state.cancellation_requested, **kwargs
                )
            if state.cancellation_requested:
                state.phase = ScanPhase.CANCELLED
            else:
                requested_addresses = set(range(state.request.start_id, state.request.end_id + 1))
                missing = sorted(requested_addresses - state.emitted_addresses)
                if missing:
                    raise GatewayProviderError(
                        "Provider contract violation: a non-cancelled scan must "
                        f"emit exactly one outcome per requested address; missing {missing}",
                        address=missing[0],
                    )
                state.phase = ScanPhase.COMPLETED
                if (
                    self._issue_callback
                    and state.cleanup_status == "closed"
                    and state.recovery_status == "verified"
                ):
                    self._report_issue(state.request.gateway_id, None)
        except TimeoutError:
            state.error_info = {
                "code": "JOB_DEADLINE",
                "phase": state.operation_phase,
                "retryable": False,
            }
            self._record_gateway_error(
                state, "Scan operation deadline exceeded", state.current_address
            )
        except GatewayProviderError as err:
            state.error_info = err.as_dict()
            self._report_issue(state.request.gateway_id, err.code)
            self._record_gateway_error(state, str(err), err.address)
        except asyncio.CancelledError:
            state.cancellation_requested = True
            state.phase = ScanPhase.CANCELLED
            raise
        except Exception:  # noqa: BLE001 - never expose transport-library exception text
            state.error_info = {"code": "INTERNAL_ERROR", "phase": "provider", "retryable": False}
            self._record_gateway_error(
                state, "Unexpected provider failure; inspect redacted diagnostics", None
            )
        finally:
            state.elapsed_ms = int((monotonic() - state.started_clock) * 1000)
            state.finished_at = _utc_now()
            state.events.append({"phase": state.phase.value, "elapsed_ms": state.elapsed_ms})
            if self._active.get(state.request.gateway_key) == state.scan_id:
                self._active.pop(state.request.gateway_key, None)
            if state.recovery_error_code:
                self._report_issue(state.request.gateway_id, state.recovery_error_code)
            self._prune_poller_selection(state.request)
            self._record_terminal(state.scan_id)
            self._tasks.pop(state.scan_id, None)

    def _prune_poller_selection(self, request: ScanRequest) -> None:
        """A Scan read the Gateway's poller table: drop saved choices it no longer has."""
        gateway = self._gateway(request.provider, request.gateway_id)
        if gateway is None:
            return
        try:
            self._poller_selection(gateway, prune=True)
        except Exception:  # noqa: BLE001 - never replace the Scan's own outcome
            return

    def _report_issue(self, gateway_id, code):
        if self._issue_callback:
            try:
                self._issue_callback(gateway_id, code)
            except Exception:  # noqa: BLE001 - never replace the primary outcome
                self._issues_failed = True

    def _record_gateway_error(self, state: _ScanState, message: str, address: int | None) -> None:
        state.phase = ScanPhase.FAILED
        state.error = message
        failed_address = address
        if (
            type(failed_address) is not int
            or not state.request.start_id <= failed_address <= state.request.end_id
        ):
            failed_address = state.current_address or state.request.start_id
        state.current_address = failed_address
        if failed_address in state.emitted_addresses:
            return
        state.completed_addresses += 1
        state.counts[ScanOutcome.GATEWAY_ERROR.value] += 1
        state.emitted_addresses.add(failed_address)
        state.retained_results.append(
            ProbeResult(
                address=failed_address,
                outcome=ScanOutcome.GATEWAY_ERROR,
                latency_ms=0,
                detail=message,
            )
        )

    @staticmethod
    def _normalize_result(state: _ScanState, result: ProbeResult) -> ProbeResult:
        """Validate and copy one provider emission into a JSON-safe form."""
        if not isinstance(result, ProbeResult):
            raise GatewayProviderError("Provider emitted a non-ProbeResult value")
        if type(result.address) is not int:
            raise GatewayProviderError(
                "Provider result address must be an integer",
                address=state.current_address,
            )
        if not state.request.start_id <= result.address <= state.request.end_id:
            raise GatewayProviderError(
                f"Provider result address {result.address} is outside requested range",
                address=result.address,
            )
        if result.address in state.emitted_addresses:
            raise GatewayProviderError(
                f"Provider emitted duplicate address {result.address}",
                address=result.address,
            )
        if not isinstance(result.outcome, ScanOutcome):
            raise GatewayProviderError(
                "Provider result outcome must be a ScanOutcome",
                address=result.address,
            )
        if type(result.latency_ms) is not int or result.latency_ms < 0:
            raise GatewayProviderError(
                "Provider result latency_ms must be a non-negative integer",
                address=result.address,
            )
        if not isinstance(result.detail, str):
            raise GatewayProviderError(
                "Provider result detail must be a string",
                address=result.address,
            )
        if result.exception_code is not None and (
            type(result.exception_code) is not int or not 0 <= result.exception_code <= 255
        ):
            raise GatewayProviderError(
                "Provider result exception_code must be an integer from 0 to 255",
                address=result.address,
            )
        identity = result.identity
        if identity is not None and (
            not isinstance(identity, dict)
            or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in identity.items()
            )
        ):
            raise GatewayProviderError(
                "Provider result identity must contain only string keys and values",
                address=result.address,
            )
        if result.register_address is not None:
            if (
                type(result.register_address) is not int
                or result.register_address != state.request.register_address
            ):
                raise GatewayProviderError("Provider returned an unexpected register")
            if result.raw_value is not None and (
                result.outcome != ScanOutcome.RESPONDED
                or type(result.raw_value) is not int
                or not 0 <= result.raw_value <= 65535
            ):
                raise GatewayProviderError("Invalid typed register value")
            if result.raw_values is not None and (
                result.outcome != ScanOutcome.RESPONDED
                or len(result.raw_values) != state.request.register_count
                or any(type(v) is not int or not 0 <= v <= 65535 for v in result.raw_values)
            ):
                raise GatewayProviderError("Invalid typed register values")
            if (
                type(result.attempts) is not int
                or not 1 <= result.attempts <= state.request.retries + 1
            ):
                raise GatewayProviderError("Invalid probe attempt count")
        return ProbeResult(
            address=result.address,
            outcome=result.outcome,
            latency_ms=result.latency_ms,
            detail=result.detail,
            exception_code=result.exception_code,
            identity=dict(identity) if identity is not None else None,
            register_address=result.register_address,
            raw_value=result.raw_value,
            attempts=result.attempts,
            raw_values=tuple(result.raw_values) if result.raw_values is not None else None,
        )

    def history(self):
        return {
            "scans": self._history.summaries()
            if self._history
            else [self.status(s) for s in reversed(self._terminal_order)]
        }

    async def check_gateway(self, gateway_id):
        provider = self._providers.get("esphome")
        if provider is None or not hasattr(provider, "check_gateway"):
            raise ValueError("No physical gateways are configured")
        if existing := self._running_on("esphome", gateway_id):
            raise GatewayBusyError("esphome", gateway_id, existing)
        health = await provider.check_gateway(gateway_id)
        response = {"gateway_id": gateway_id, "health": health}
        if gateway := self._gateway("esphome", gateway_id):
            response.update(self._poller_selection(gateway, prune=True))
        return response

    def _record_terminal(self, scan_id: str) -> None:
        if self._history:
            self._history.remember(self.status(scan_id), self.results(scan_id))
        self._terminal_order.append(scan_id)
        while len(self._terminal_order) > self._max_history:
            oldest = self._terminal_order.popleft()
            self._scans.pop(oldest, None)
            self._tasks.pop(oldest, None)

    def _get(self, scan_id: str) -> _ScanState:
        try:
            return self._scans[scan_id]
        except KeyError as err:
            raise ScanNotFoundError(f"Unknown Modbus scan ID: {scan_id}") from err

    @staticmethod
    def _serialized_counts(state: _ScanState) -> dict[str, int]:
        return {outcome.value: state.counts[outcome.value] for outcome in ScanOutcome}
