"""Asynchronous lifecycle coordinator for provider-backed Modbus scans."""

from __future__ import annotations

import asyncio
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from homeassistant.core import HomeAssistant

from .models import ProbeResult, ScanOutcome, ScanPhase, ScanRequest
from .provider import GatewayProvider, GatewayProviderError


class ScanNotFoundError(LookupError):
    """The requested scan is not retained in memory."""


class GatewayBusyError(RuntimeError):
    """A scan already owns the provider/gateway concurrency key."""

    def __init__(self, provider: str, gateway_id: str, scan_id: str) -> None:
        super().__init__(
            f"Gateway {provider}/{gateway_id} is busy with active scan {scan_id}"
        )
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


class ModbusScanCoordinator:
    """Own scan validation, concurrency, snapshots, tasks, and bounded history."""

    def __init__(
        self,
        hass: HomeAssistant,
        providers: list[GatewayProvider],
        *,
        max_history: int = 20,
    ) -> None:
        self._hass = hass
        self._providers = {provider.provider_id: provider for provider in providers}
        self._max_history = max_history
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
        return self.status(scan_id)

    def status(self, scan_id: str) -> dict[str, Any]:
        """Return a serializable lifecycle snapshot."""
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
            "cancellation_requested": state.cancellation_requested,
            "error": state.error,
        }

    def results(self, scan_id: str) -> dict[str, Any]:
        """Return bounded responder details and complete outcome counts."""
        state = self._get(scan_id)
        return {
            "scan_id": state.scan_id,
            "provider": state.request.provider,
            "gateway_id": state.request.gateway_id,
            "status": state.phase.value,
            "phase": state.phase.value,
            "responders": [
                result.as_dict()
                for result in state.retained_results
                if result.is_responder
            ],
            "outcome_counts": self._serialized_counts(state),
            "completed_addresses": state.completed_addresses,
            "total_addresses": state.request.address_count,
            "best_effort": True,
            "uniqueness_guaranteed": False,
            "error": state.error,
        }

    async def cancel(self, scan_id: str) -> dict[str, Any]:
        """Request cooperative cancellation after the current mock transaction."""
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
        """Cancel and await every active task during config-entry unload."""
        self._shutting_down = True
        active_scans: list[tuple[str, asyncio.Task[None]]] = []
        for scan_id, task in tuple(self._tasks.items()):
            state = self._scans.get(scan_id)
            if state is not None and state.phase == ScanPhase.RUNNING:
                state.cancellation_requested = True
                task.cancel()
                active_scans.append((scan_id, task))
        if active_scans:
            await asyncio.gather(
                *(task for _scan_id, task in active_scans), return_exceptions=True
            )
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

        try:
            await provider.run_scan(
                state.request, emit, lambda: state.cancellation_requested
            )
            if state.cancellation_requested:
                state.phase = ScanPhase.CANCELLED
            else:
                requested_addresses = set(
                    range(state.request.start_id, state.request.end_id + 1)
                )
                missing = sorted(requested_addresses - state.emitted_addresses)
                if missing:
                    raise GatewayProviderError(
                        "Provider contract violation: a non-cancelled scan must "
                        f"emit exactly one outcome per requested address; missing {missing}",
                        address=missing[0],
                    )
                state.phase = ScanPhase.COMPLETED
        except GatewayProviderError as err:
            self._record_gateway_error(state, str(err), err.address)
        except asyncio.CancelledError:
            state.cancellation_requested = True
            state.phase = ScanPhase.CANCELLED
            raise
        except Exception as err:  # noqa: BLE001 - isolates provider failures per scan
            self._record_gateway_error(state, f"Provider failure: {err}", None)
        finally:
            state.finished_at = _utc_now()
            if self._active.get(state.request.gateway_key) == state.scan_id:
                self._active.pop(state.request.gateway_key, None)
            self._record_terminal(state.scan_id)
            self._tasks.pop(state.scan_id, None)

    def _record_gateway_error(
        self, state: _ScanState, message: str, address: int | None
    ) -> None:
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
            type(result.exception_code) is not int
            or not 0 <= result.exception_code <= 255
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
        return ProbeResult(
            address=result.address,
            outcome=result.outcome,
            latency_ms=result.latency_ms,
            detail=result.detail,
            exception_code=result.exception_code,
            identity=dict(identity) if identity is not None else None,
        )

    def _record_terminal(self, scan_id: str) -> None:
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
