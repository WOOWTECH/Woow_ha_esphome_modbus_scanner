"""Asynchronous lifecycle coordinator for provider-backed Modbus scans."""

from __future__ import annotations

import asyncio
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import monotonic
from typing import Any
from uuid import uuid4

from homeassistant.core import HomeAssistant

from .models import ProbeResult, ScanOutcome, ScanPhase, ScanRequest
from .provider import GatewayProvider, GatewayProviderError

SHUTDOWN_GRACE_SECONDS = 35


class ScanNotFoundError(LookupError):
    """The requested scan is not retained in memory."""


class GatewayBusyError(RuntimeError):
    """A scan already owns the provider/gateway concurrency key."""

    def __init__(self, provider: str, gateway_id: str, scan_id: str) -> None:
        super().__init__(f"Gateway {provider}/{gateway_id} is busy with active scan {scan_id}")
        self.scan_id = scan_id


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class _ScanState:
    scan_id: str
    request: ScanRequest
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
    ) -> None:
        self._hass = hass
        self._providers = {provider.provider_id: provider for provider in providers}
        self._max_history = max_history
        self._history = history
        self._issue_callback = issue_callback
        self._issues_failed = False
        self._scans: dict[str, _ScanState] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._active: dict[tuple[str, str], str] = {}
        self._terminal_order: deque[str] = deque()
        self._shutting_down = False

    def list_gateways(self) -> dict[str, Any]:
        """Return every provider gateway in a stable service response."""
        gateways = [
            gateway.as_dict()
            for provider in self._providers.values()
            for gateway in provider.list_gateways()
        ]
        return {"gateways": gateways}

    async def start(self, request: ScanRequest) -> dict[str, Any]:
        """Validate and schedule a scan without awaiting its address loop."""
        if self._shutting_down:
            raise RuntimeError("Modbus scan coordinator is shutting down")
        request.validate()
        provider = self._providers.get(request.provider)
        if provider is None:
            raise ValueError(f"Unsupported Modbus scan provider: {request.provider}")
        if validator := getattr(provider, "validate_request", None):
            validator(request)
        available_ids = {item.gateway_id for item in provider.list_gateways()}
        if request.gateway_id not in available_ids:
            raise ValueError(f"Unknown Modbus gateway: {request.gateway_id}")
        if existing := self._active.get(request.gateway_key):
            raise GatewayBusyError(request.provider, request.gateway_id, existing)

        scan_id = str(uuid4())
        state = _ScanState(scan_id=scan_id, request=request)
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
            "error": state.error,
            "error_info": state.error_info,
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
            self._record_terminal(state.scan_id)
            self._tasks.pop(state.scan_id, None)

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
        if existing := self._active.get(("esphome", gateway_id)):
            raise GatewayBusyError("esphome", gateway_id, existing)
        return {"gateway_id": gateway_id, "health": await provider.check_gateway(gateway_id)}

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
