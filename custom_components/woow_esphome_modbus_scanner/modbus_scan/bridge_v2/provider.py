"""Bridge v2 adapter: Gateways running the vendor-neutral ``modbus_scanner`` ESPHome component.

Every protocol detail (action signature, sensor names, result schema, hard limits) comes
from the shared contract file. Cached sensor states are never treated as Probe evidence:
a result only counts when it echoes the request id of the Probe just sent.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
import inspect
import json
import re
from typing import Any
from uuid import uuid4

from aioesphomeapi import (
    APIClient,
    EncryptionPlaintextAPIError,
    InvalidAuthAPIError,
    InvalidEncryptionKeyAPIError,
    RequiresEncryptionAPIError,
    TextSensorInfo,
    UserServiceArgType,
)

from ..limits import ProbeLimits, ScanTiming
from ..models import (
    BUS_NAME_PATTERN,
    GatewayInfo,
    ProbeResult,
    ProbeType,
    ScanOutcome,
    ScanRequest,
)
from ..pollers import choose, paused_pollers, reconcile
from ..provider import GatewayProviderError
from .contract import (
    BRIDGE_VERSION,
    ERROR_CODES,
    HARD_LIMITS,
    INFO_BUS_FIELDS,
    INFO_FIELDS,
    INFO_POLLER_FIELDS,
    INFO_SCHEMA_VERSION,
    INFO_SENSOR,
    INFO_SERIAL_FIELDS,
    LEASE_END_REASONS,
    LEASE_SCHEMA_VERSION,
    LEASE_SENSOR,
    LEASE_STATES,
    OUTCOMES,
    PROBE_ACTION,
    PROBE_ARGS,
    RELEASE_ACTION,
    RELEASE_ARGS,
    RESULT_COMMON_FIELDS,
    RESULT_OUTCOME_FIELDS,
    RESULT_SCHEMA_VERSION,
    RESULT_SENSOR,
    SERIAL_PARITIES,
)

_ARG_TYPES = {"string": UserServiceArgType.STRING, "int": UserServiceArgType.INT}
_FUNCTION_CODES = {ProbeType.HOLDING_REGISTER: 3, ProbeType.INPUT_REGISTER: 4}
# Margin over the per-probe timeout for API round trips and the hub's turnaround delay.
_RESULT_MARGIN_S = 5
# How long cleanup waits for the Gateway to answer a lease release. Without an answer the
# Gateway still resumes Normal Polling by itself after the contract's idle time.
_RELEASE_ANSWER_S = 1.0

LIMITS = ProbeLimits(
    "Bridge v2",
    slave_min=HARD_LIMITS["slave_min"],
    slave_max=HARD_LIMITS["slave_max"],
    probe_types=tuple(
        probe for probe, code in _FUNCTION_CODES.items() if code in HARD_LIMITS["function_codes"]
    ),
    register_count_max=HARD_LIMITS["count_max"],
    timeout_ms_min=HARD_LIMITS["timeout_ms_min"],
    timeout_ms_max=HARD_LIMITS["timeout_ms_max"],
    defaults={
        "probe_type": ProbeType.HOLDING_REGISTER,
        "register_address": 0,
        "register_count": 1,
        "timeout_ms": 1000,
        "retries": 0,
        "inter_request_delay_ms": 100,
        # A Scan pauses every Pausable Poller on its Bus under one Scan Lease.
        "pause_normal_polling": True,
    },
    timing=ScanTiming(
        # The probe action and its result's way back over the API; the Gateway applies the
        # timeout itself and needs no drain or quiet periods (the lease holds the pollers).
        attempt_overhead_ms=300,
        # Connect 15 s, device info 10 s, entity list 10 s, bridge info 5 s.
        setup_ms=40_000,
        # The probe action call (5 s) plus the result margin over the timeout (5 s).
        attempt_budget_ms=10_000,
        # Lease release answer (1 s) and disconnect (up to 3 s).
        cleanup_ms=4_000,
    ),
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


class _Cancelled(Exception):
    """Cooperative cancellation before a Probe is transmitted."""


async def _bounded(awaitable, timeout, cancelled=None):
    """Interrupt connect/discovery waits; never interrupt an already-sent Probe."""
    task = asyncio.ensure_future(awaitable)
    try:
        async with asyncio.timeout(timeout):
            while not task.done():
                if cancelled and cancelled():
                    raise _Cancelled
                await asyncio.wait({task}, timeout=0.05)
            return task.result()
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@dataclass(frozen=True)
class V2Gateway:
    host: str
    mac: str
    name: str | None = None
    port: int = 6053
    noise_psk: str | None = field(default=None, repr=False)

    @property
    def gateway_id(self) -> str:
        return "esphome:" + self.mac.replace(":", "").lower()

    @property
    def display_name(self) -> str:
        return self.name or "ESPHome Modbus " + self.mac.replace(":", "")[-6:].upper()


@dataclass(slots=True)
class _Session:
    """One verified API connection: the probe action, sensor keys and bus table."""

    service: Any
    release_service: Any
    info_key: int
    result_key: int
    lease_key: int
    info: asyncio.Future
    buses: list[dict[str, Any]] = field(default_factory=list)


def _int(value: Any) -> bool:
    return type(value) is int


def _valid_poller_table(pollers: Any) -> bool:
    """The Pausable Poller table: stable indices 0..n-1, names, slave addresses 0..247."""
    return isinstance(pollers, list) and all(
        isinstance(poller, dict)
        and all(key in poller for key in INFO_POLLER_FIELDS)
        and _int(poller["index"])
        and poller["index"] == position
        and isinstance(poller["name"], str)
        and _int(poller["address"])
        and 0 <= poller["address"] <= 247
        for position, poller in enumerate(pollers)
    )


def _valid_serial(serial: Any) -> bool:
    """The optional serial parameters of a Bus's hub UART."""
    return (
        isinstance(serial, dict)
        and all(key in serial for key in INFO_SERIAL_FIELDS)
        and _int(serial["baud_rate"])
        and serial["baud_rate"] >= 1
        and serial["parity"] in SERIAL_PARITIES
        and serial["stop_bits"] in (1, 2)
        and _int(serial["stop_bits"])
    )


def _parse_info(state: str) -> dict[str, Any]:
    info = json.loads(state)
    if not isinstance(info, dict) or any(key not in info for key in INFO_FIELDS):
        raise ValueError
    if info["v"] != INFO_SCHEMA_VERSION or info["bridge"] != BRIDGE_VERSION:
        raise ValueError
    buses = info["buses"]
    if not isinstance(buses, list) or not all(
        isinstance(bus, dict)
        and all(key in bus for key in INFO_BUS_FIELDS)
        and isinstance(bus["bus"], str)
        and re.fullmatch(BUS_NAME_PATTERN, bus["bus"])
        and _valid_poller_table(bus["pollers"])
        and ("serial" not in bus or _valid_serial(bus["serial"]))
        for bus in buses
    ):
        raise ValueError
    if len({bus["bus"] for bus in buses}) != len(buses):
        raise ValueError
    return info


def _bus_rows(buses: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    """The Gateway's Buses as list_gateways reports them: name and serial parameters."""
    return tuple(
        {
            "bus": bus["bus"],
            "serial": {key: bus["serial"][key] for key in INFO_SERIAL_FIELDS}
            if "serial" in bus
            else None,
        }
        for bus in buses
    )


def _parse_lease(state: str, bus: str, scan_id: str) -> tuple[str, str | None] | None:
    """(state, end reason) of a lease message for this bus and scan; None for anything else."""
    try:
        lease = json.loads(state)
    except (ValueError, TypeError):
        return None
    if (
        not isinstance(lease, dict)
        or lease.get("v") != LEASE_SCHEMA_VERSION
        or lease.get("bus") != bus
        or lease.get("scan") != scan_id
        or lease.get("state") not in LEASE_STATES
    ):
        return None
    if lease["state"] != "ended":
        return lease["state"], None
    if lease.get("reason") not in LEASE_END_REASONS:
        return None
    return "ended", lease["reason"]


def _pause_selection(
    request: ScanRequest, bus: str, table: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(pollers this Scan pauses, chosen pollers the current table no longer has).

    The choice is revalidated against the table the Gateway reports now: explicit indices
    first, else the Bus's saved checklist, else every poller.
    """
    if not request.pause_normal_polling:
        return [], []
    if request.pause_pollers is not None:
        checklist, unknown = choose(table, request.pause_pollers)
        return paused_pollers(checklist), [{"index": index} for index in unknown]
    checklist, removed = reconcile(table, (request.pause_checklists or {}).get(bus))
    return paused_pollers(checklist), removed


def _signature(service: Any, args: dict[str, str]) -> bool:
    return len(service.args) == len(args) and {a.name: a.type for a in service.args} == {
        name: _ARG_TYPES[kind] for name, kind in args.items()
    }


def _check_result(payload: Any, expected: dict[str, Any]) -> dict[str, Any]:
    """Validate a correlated result against the contract; raise ValueError if malformed."""
    if not isinstance(payload, dict) or any(key not in payload for key in RESULT_COMMON_FIELDS):
        raise ValueError
    if payload["v"] != RESULT_SCHEMA_VERSION or payload["outcome"] not in OUTCOMES:
        raise ValueError
    for key, value in expected.items():
        if payload[key] != value or type(payload[key]) is not type(value):
            raise ValueError
    if not _int(payload["latency_ms"]) or not 0 <= payload["latency_ms"] <= 60_000:
        raise ValueError
    outcome = payload["outcome"]
    if any(key not in payload for key in RESULT_OUTCOME_FIELDS[outcome]):
        raise ValueError
    if outcome == "responded":
        values = payload["values"]
        if (
            not isinstance(values, list)
            or len(values) != expected["count"]
            or not all(_int(v) and 0 <= v <= 65535 for v in values)
        ):
            raise ValueError
    elif outcome == "modbus_exception":
        if not _int(payload["exception"]) or not 1 <= payload["exception"] <= 255:
            raise ValueError
    elif outcome == "gateway_error" and payload["error"] not in ERROR_CODES:
        raise ValueError
    return payload


class V2GatewayProvider:
    """Probes through ``modbus_scanner_v2_probe``; one API connection per Scan."""

    provider_id = "esphome"
    supports_progress = True

    def __init__(self, gateways, *, client_factory=None):
        self.gateways = {g.gateway_id: g for g in gateways}
        self.client_factory = client_factory
        # Held by a check; a Scan waits for it, a check refuses while any Scan runs.
        self._locks = {key: asyncio.Lock() for key in self.gateways}
        self._scans = dict.fromkeys(self.gateways, 0)
        # One Probe (or lease release) in flight per Gateway across all its Buses' Scans.
        # ESPHome batches text sensor states and sends only the latest state of an entity
        # per batch, so two results published close together would lose the first one.
        self._probe_slots = {key: asyncio.Lock() for key in self.gateways}
        self._buses: dict[str, tuple[dict[str, Any], ...]] = {}
        self.health = {
            key: {
                "api_status": "unchecked",
                "bus_status": "unverified",
                "recovery_status": "unknown",
                "encrypted": bool(g.noise_psk),
            }
            for key, g in self.gateways.items()
        }

    def list_gateways(self):
        return [
            GatewayInfo(
                self.provider_id,
                g.gateway_id,
                g.display_name,
                ("bridge_v2", "holding_register", "input_register", "multi_register"),
                health=deepcopy(self.health[g.gateway_id]),
                limits=LIMITS,
                buses=deepcopy(self._buses.get(g.gateway_id, ())),
            )
            for g in self.gateways.values()
        ]

    def _client(self, gateway: V2Gateway):
        options = {"noise_psk": gateway.noise_psk} if gateway.noise_psk else {}
        factory = self.client_factory or APIClient
        try:
            return factory(gateway.host, gateway.port, "", **options)
        except Exception:  # noqa: BLE001 - constructor errors may contain secrets
            raise GatewayProviderError(
                "Unable to initialize ESPHome connection",
                code="API_CONFIGURATION_ERROR",
                phase="connect",
            ) from None

    @staticmethod
    def _transport_error(exc, phase):
        # Never expose str(exc); library messages may contain host or key material.
        if isinstance(
            exc,
            (
                InvalidAuthAPIError,
                InvalidEncryptionKeyAPIError,
                RequiresEncryptionAPIError,
                EncryptionPlaintextAPIError,
            ),
        ):
            return GatewayProviderError(
                "ESPHome API authentication failed; verify the configured encryption key",
                code="API_AUTH_FAILED",
                phase=phase,
            )
        code = (
            "API_CONNECT_TIMEOUT"
            if isinstance(exc, TimeoutError) and phase == "connect"
            else "API_TRANSPORT_ERROR"
        )
        return GatewayProviderError(
            "ESPHome transport failed or response deadline exceeded",
            code=code,
            phase=phase,
            retryable=True,
        )

    async def _disconnect(self, client, gateway_id):
        try:
            await asyncio.wait_for(client.disconnect(), 2)
        except asyncio.CancelledError:
            await self._force_disconnect(client, gateway_id)
            raise
        except Exception:  # noqa: BLE001 - keep the primary failure
            await self._force_disconnect(client, gateway_id)
        else:
            self.health[gateway_id]["cleanup_status"] = "closed"

    async def _force_disconnect(self, client, gateway_id):
        try:
            await asyncio.wait_for(client.disconnect(force=True), 1)
        except Exception:  # noqa: BLE001 - no raw cleanup exception strings
            self.health[gateway_id]["cleanup_status"] = "failed"
        else:
            self.health[gateway_id]["cleanup_status"] = "forced"

    async def _discover(self, client, gateway, on_stop, cancelled, progress) -> _Session:
        """Connect, verify MAC and the v2 signature, then read the bus table."""
        phase = "connect"
        try:
            progress({"operation_phase": phase})
            await _bounded(client.connect(login=True, on_stop=on_stop), 15, cancelled)
            phase = "verify_identity"
            progress({"operation_phase": phase})
            info = await _bounded(client.device_info(), 10, cancelled)
            if info.mac_address.upper() != gateway.mac.upper():
                raise GatewayProviderError(
                    "Gateway identity mismatch; no probe sent",
                    code="IDENTITY_MISMATCH",
                    phase=phase,
                )
            phase = "verify_bridge"
            progress({"operation_phase": phase})
            entities, services = await _bounded(client.list_entities_services(), 10, cancelled)
            actions = {
                name: [s for s in services if s.name == name]
                for name in (PROBE_ACTION, RELEASE_ACTION)
            }
            sensors = {
                name: [e for e in entities if isinstance(e, TextSensorInfo) and e.name == name]
                for name in (INFO_SENSOR, RESULT_SENSOR, LEASE_SENSOR)
            }
            if any(len(found) != 1 for found in (*actions.values(), *sensors.values())):
                raise GatewayProviderError(
                    "The modbus_scanner component (bridge v2) is not installed on this node",
                    code="BRIDGE_UNSUPPORTED",
                    phase=phase,
                    reason="scanner_missing",
                )
            service = actions[PROBE_ACTION][0]
            release_service = actions[RELEASE_ACTION][0]
            if not _signature(service, PROBE_ARGS) or not _signature(release_service, RELEASE_ARGS):
                raise GatewayProviderError(
                    "Unexpected bridge v2 action signature",
                    code="BRIDGE_UNSUPPORTED",
                    phase=phase,
                    reason="bridge_mismatch",
                )
            session = _Session(
                service=service,
                release_service=release_service,
                info_key=sensors[INFO_SENSOR][0].key,
                result_key=sensors[RESULT_SENSOR][0].key,
                lease_key=sensors[LEASE_SENSOR][0].key,
                info=asyncio.get_running_loop().create_future(),
            )
            return session
        except (GatewayProviderError, _Cancelled):
            raise
        except Exception as exc:  # noqa: BLE001 - boundary sanitization
            raise self._transport_error(exc, phase) from None

    async def _read_info(self, session: _Session, gateway_id: str, cancelled) -> None:
        try:
            info = await _bounded(asyncio.shield(session.info), 5, cancelled)
        except TimeoutError:
            raise GatewayProviderError(
                "Gateway did not publish its bridge v2 info",
                code="BRIDGE_UNSUPPORTED",
                phase="verify_bridge",
                reason="bridge_mismatch",
            ) from None
        session.buses = info["buses"]
        self._buses[gateway_id] = _bus_rows(session.buses)
        self.health[gateway_id].update(
            api_status="verified",
            checked_at=_now(),
            bridge_status="v2_signature_verified",
            buses=[bus["bus"] for bus in session.buses],
            pausable_pollers={bus["bus"]: deepcopy(bus["pollers"]) for bus in session.buses},
            error_info=None,
        )

    @staticmethod
    def _accept_info(session: _Session, state) -> None:
        if session.info.done() or getattr(state, "missing_state", False):
            return
        try:
            session.info.set_result(_parse_info(state.state))
        except (ValueError, TypeError, AttributeError, KeyError):
            session.info.set_exception(
                GatewayProviderError(
                    "Gateway published an incompatible bridge info",
                    code="BRIDGE_UNSUPPORTED",
                    phase="verify_bridge",
                    reason="bridge_mismatch",
                )
            )

    def validate_request(self, request: ScanRequest) -> None:
        request.validate()
        if request.provider != self.provider_id or request.gateway_id not in self.gateways:
            raise ValueError("Unknown physical gateway")
        LIMITS.validate(request)

    async def check_gateway(self, gateway_id):
        """API-only identity/signature check. Never sends a Modbus frame."""
        if gateway_id not in self.gateways:
            raise ValueError("Unknown physical gateway")
        if self._locks[gateway_id].locked() or self._scans[gateway_id]:
            raise GatewayProviderError(
                "Gateway is busy", code="GATEWAY_BUSY", phase="preflight", retryable=True
            )
        async with self._locks[gateway_id]:
            gateway = self.gateways[gateway_id]
            client = self._client(gateway)

            async def stopped(_expected):
                return None

            try:
                session = await self._discover(
                    client, gateway, stopped, lambda: False, lambda _data: None
                )

                def on_state(state):
                    if state.key == session.info_key:
                        self._accept_info(session, state)

                client.subscribe_states(on_state)
                await self._read_info(session, gateway_id, None)
            except GatewayProviderError as exc:
                self.health[gateway_id].update(
                    api_status="failed", checked_at=_now(), error_info=exc.as_dict()
                )
                raise
            except Exception as exc:  # noqa: BLE001 - no raw library messages
                error = self._transport_error(exc, "verify_bridge")
                self.health[gateway_id].update(
                    api_status="failed", checked_at=_now(), error_info=error.as_dict()
                )
                raise error from None
            finally:
                await self._disconnect(client, gateway_id)
            return deepcopy(self.health[gateway_id])

    async def run_scan(self, request, emit, cancelled, *, progress=None):
        """Scan one Bus. The coordinator allows one Scan per Bus; Buses run side by side."""
        self.validate_request(request)
        gateway_id = request.gateway_id
        self._scans[gateway_id] += 1
        try:
            async with self._locks[gateway_id]:
                pass  # let a running check finish first
            if cancelled():
                return
            await self._run(request, emit, cancelled, progress or (lambda _data: None))
        except _Cancelled:
            return
        finally:
            self._scans[gateway_id] -= 1

    async def _run(self, request, emit, cancelled, progress):
        gateway = self.gateways[request.gateway_id]
        self.health[gateway.gateway_id].update(cleanup_status="pending")
        client = self._client(gateway)
        session: _Session | None = None
        pending: asyncio.Future | None = None
        expected: dict[str, Any] | None = None
        phase = "connect"
        bus: str | None = None
        scan_id = uuid4().hex
        # Scan Lease as last reported by the Gateway for this bus and scan.
        lease: dict[str, Any] = {"status": "none", "reason": None, "requested": False}
        lease_answer: asyncio.Future | None = None
        disconnected = False

        def report_lease(status, reason=None):
            lease.update(status=status, reason=reason)
            progress({"lease_status": status, "lease_end_reason": reason})

        def on_lease(state):
            parsed = _parse_lease(state.state, bus, scan_id) if bus is not None else None
            if parsed is None:
                return  # foreign, stale or malformed lease messages are never evidence
            report_lease(*parsed)
            if lease_answer is not None and not lease_answer.done() and parsed[0] != "active":
                lease_answer.set_result(parsed)

        def on_state(state):
            if session is None or getattr(state, "missing_state", False):
                return
            if state.key == session.info_key:
                self._accept_info(session, state)
                return
            if state.key == session.lease_key:
                on_lease(state)
                return
            if state.key != session.result_key or pending is None or pending.done():
                return
            try:
                payload = json.loads(state.state)
            except (ValueError, TypeError, AttributeError):
                return
            # Uncorrelated (stale or foreign) results are ignored, never treated as evidence.
            if not isinstance(payload, dict) or payload.get("id") != expected["id"]:
                return
            try:
                pending.set_result(_check_result(payload, expected))
            except (ValueError, TypeError, KeyError):
                pending.set_exception(
                    GatewayProviderError(
                        "Invalid firmware response", code="RESPONSE_INVALID", phase="probe"
                    )
                )

        async def on_stop(_expected_disconnect):
            nonlocal disconnected
            disconnected = True
            if pending is not None and not pending.done():
                pending.set_exception(
                    GatewayProviderError(
                        "ESPHome connection lost",
                        code="API_DISCONNECTED",
                        phase=phase,
                        retryable=True,
                    )
                )

        try:
            session = await self._discover(client, gateway, on_stop, cancelled, progress)
            phase = "verify_bridge"
            client.subscribe_states(on_state)
            await self._read_info(session, gateway.gateway_id, cancelled)
            target = self._target_bus(request, session.buses, phase)
            bus = target["bus"]
            progress({"bus": bus})
            paused, removed = _pause_selection(request, bus, target["pollers"])
            pause_pollers = ",".join(str(poller["index"]) for poller in paused)
            progress({"paused_pollers": paused, "removed_pollers": removed})
            function_code = _FUNCTION_CODES[request.probe_type]
            for slave in range(request.start_id, request.end_id + 1):
                for attempt in range(request.retries + 1):
                    if cancelled():
                        return
                    phase = "probe"
                    progress(
                        {"operation_phase": phase, "current_address": slave, "attempt": attempt + 1}
                    )
                    expected = {
                        "id": uuid4().hex,
                        "bus": bus,
                        "slave": slave,
                        "fc": function_code,
                        "reg": request.register_address,
                        "count": request.register_count,
                    }
                    async with self._probe_slots[gateway.gateway_id]:
                        if cancelled():
                            return
                        pending = asyncio.get_running_loop().create_future()
                        # From here on the Gateway may hold a lease, so cleanup releases it.
                        lease["requested"] = lease["requested"] or bool(pause_pollers)
                        result = client.execute_service(
                            session.service,
                            {
                                "request_id": expected["id"],
                                "bus": bus,
                                "slave": slave,
                                "function_code": function_code,
                                "register": request.register_address,
                                "count": request.register_count,
                                "timeout_ms": request.timeout_ms,
                                "scan_id": scan_id,
                                "pause_pollers": pause_pollers,
                            },
                        )
                        if inspect.isawaitable(result):
                            await asyncio.wait_for(result, 5)
                        payload = await asyncio.wait_for(
                            pending, request.timeout_ms / 1000 + _RESULT_MARGIN_S
                        )
                    if payload["outcome"] != "timeout":
                        break
                emit(self._probe_result(request, payload, attempt + 1))
                if slave < request.end_id:
                    phase = "inter_request_delay"
                    progress({"operation_phase": phase})
                    loop = asyncio.get_running_loop()
                    deadline = loop.time() + request.inter_request_delay_ms / 1000
                    while not cancelled() and loop.time() < deadline:
                        await asyncio.sleep(min(0.05, max(0, deadline - loop.time())))
            progress({"operation_phase": "finished"})
        except (GatewayProviderError, _Cancelled) as exc:
            if isinstance(exc, GatewayProviderError):
                self.health[gateway.gateway_id]["error_info"] = exc.as_dict()
            raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - sanitize before exposing to HA
            error = self._transport_error(exc, phase)
            self.health[gateway.gateway_id]["error_info"] = error.as_dict()
            raise error from None
        finally:
            if pending is not None and not pending.done():
                pending.cancel()
            if session is not None and not session.info.done():
                session.info.cancel()
            try:
                if lease["requested"]:
                    # Completion, cancellation and errors all release at once. When HA cannot
                    # reach the Gateway, it resumes Normal Polling by itself (idle expiry).
                    lease_answer = asyncio.get_running_loop().create_future()
                    released = False
                    if not disconnected:
                        # The answer comes on the node-wide lease sensor: keep it out of
                        # another Bus's batch like a probe result.
                        async with self._probe_slots[gateway.gateway_id]:
                            released = await self._release(
                                client, session, bus, scan_id, lease_answer
                            )
                    if not released and lease["status"] != "ended":
                        report_lease("unconfirmed")
            finally:
                await self._disconnect(client, gateway.gateway_id)
            progress({"cleanup_status": self.health[gateway.gateway_id].get("cleanup_status")})

    @staticmethod
    def _target_bus(request: ScanRequest, buses: list[dict[str, Any]], phase: str):
        """The info entry of the Bus this Scan targets, as the Gateway reports it now."""
        if request.bus is not None:
            for entry in buses:
                if entry["bus"] == request.bus:
                    return entry
            raise GatewayProviderError(
                f"Gateway reports no Bus {request.bus}; no probe sent",
                code="UNKNOWN_BUS",
                phase=phase,
            )
        if len(buses) != 1:
            # Never guess a Bus.
            raise GatewayProviderError(
                f"Gateway reports {len(buses)} Buses; choose one with bus",
                code="BUS_SELECTION_REQUIRED",
                phase=phase,
            )
        return buses[0]

    @staticmethod
    async def _release(client, session, bus, scan_id, answer: asyncio.Future) -> bool:
        """Ask the Gateway to end this scan's lease; True once it answered with the ending."""
        try:
            async with asyncio.timeout(_RELEASE_ANSWER_S):
                result = client.execute_service(
                    session.release_service, {"bus": bus, "scan_id": scan_id}
                )
                if inspect.isawaitable(result):
                    await result
                await asyncio.shield(answer)
        except Exception:  # noqa: BLE001 - cleanup never replaces the scan's own outcome
            return False
        finally:
            if not answer.done():
                answer.cancel()
        return True

    def _probe_result(self, request: ScanRequest, payload: dict, attempts: int) -> ProbeResult:
        outcome = payload["outcome"]
        slave = payload["slave"]
        if outcome == "gateway_error":
            raise GatewayProviderError(
                f"Gateway rejected the probe ({payload['error']})",
                address=slave,
                code="FIRMWARE_REJECTED",
                phase="probe",
                retryable=payload["error"] == "busy",
            )
        label = f"FC{payload['fc']:02d} register 0x{payload['reg']:04X} x{payload['count']}"
        if outcome in ("responded", "modbus_exception"):
            self.health[request.gateway_id].update(bus_status=outcome, last_bus_response_at=_now())
        values = tuple(payload["values"]) if outcome == "responded" else None
        detail = {
            "responded": f"{label} = {list(values or ())}",
            "modbus_exception": (
                f"{label}: Modbus exception {payload.get('exception')}; "
                "not proof of unique identity"
            ),
            "timeout": (
                f"No valid response within {request.timeout_ms} ms; not proof of an unused address"
            ),
            "possible_collision": f"{label}: garbled or mismatched reply; possible ID collision",
        }[outcome]
        return ProbeResult(
            slave,
            ScanOutcome(outcome),
            payload["latency_ms"],
            detail,
            exception_code=payload["exception"] if outcome == "modbus_exception" else None,
            register_address=request.register_address,
            raw_value=values[0] if values else None,
            attempts=attempts,
            raw_values=values,
        )
