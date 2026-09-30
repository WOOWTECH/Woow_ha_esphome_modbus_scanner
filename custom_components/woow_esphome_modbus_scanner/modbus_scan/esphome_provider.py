"""Bounded read-only bridge. Cached states are never treated as probe evidence."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
import inspect
import json
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

from .health import HealthSession
from .models import GatewayInfo, ProbeResult, ProbeType, ScanOutcome
from .profile_generated import PROFILE
from .provider import GatewayProviderError

SERVICE = "modbus_scanner_probe_v1"
REGISTERS = frozenset(PROFILE["allowed_registers"])


def _now():
    return datetime.now(UTC).isoformat()


class _Cancelled(Exception):
    """Cooperative cancellation before a transaction is transmitted."""


async def _bounded(awaitable, timeout, cancelled=None):
    """Interrupt connect/discovery waits; never interrupt an already-sent RTU frame."""
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
class ESPHomeGateway:
    host: str
    mac: str
    name: str = "Guanjie read-only scanner"
    port: int = 6053
    device_id: str | None = None
    noise_psk: str | None = field(default=None, repr=False)

    @property
    def gateway_id(self):
        return "esphome:" + self.mac.replace(":", "").lower()


class ESPHomeGatewayProvider:
    provider_id = "esphome"
    supports_progress = True

    def __init__(self, gateways, *, client_factory=APIClient):
        self.gateways = {g.gateway_id: g for g in gateways}
        self.client_factory = client_factory
        self._locks = {key: asyncio.Lock() for key in self.gateways}
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
                g.name,
                (
                    "holding_register",
                    "single_register",
                    "slave_1_32",
                    "timeout_700ms",
                    "automatic_polling_resume",
                ),
                profile=PROFILE,
                health=deepcopy(self.health[g.gateway_id]),
            )
            for g in self.gateways.values()
        ]

    def validate_request(self, request):
        request.validate()
        if request.provider != self.provider_id or request.gateway_id not in self.gateways:
            raise ValueError("Unknown physical gateway")
        if request.end_id > PROFILE["limits"]["slave_max"]:
            raise ValueError("Guanjie bridge supports slave IDs 1–32 only")
        if request.probe_type != ProbeType.HOLDING_REGISTER or request.register_count != 1:
            raise ValueError(
                "Bridge v1 requires probe_type=holding_register (FC03), register_count=1"
            )
        if request.register_address not in REGISTERS:
            raise ValueError(
                "Register is not in the verified IN-D17 read allowlist; example: 25089 (0x6201)"
            )
        if request.timeout_ms != PROFILE["limits"]["timeout_ms"]:
            raise ValueError("Bridge v1 requires timeout_ms=700")
        if not request.pause_normal_polling:
            raise ValueError("Physical reads require pause_normal_polling=true")

    def _client(self, gateway):
        options = {"noise_psk": gateway.noise_psk} if gateway.noise_psk else {}
        try:
            return self.client_factory(gateway.host, gateway.port, "", **options)
        except Exception:  # noqa: BLE001 - constructor errors may contain secrets
            raise GatewayProviderError(
                "Unable to initialize ESPHome connection",
                code="API_CONFIGURATION_ERROR",
                phase="connect",
            ) from None

    @staticmethod
    def _transport_error(exc, phase):
        # Include subclasses (e.g. EncryptionErrorAPIError for a wrong PSK).
        # Never expose str(exc), including exceptions raised during cleanup.
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
        except Exception:  # noqa: BLE001 - retain primary failure, don't leak library messages
            await self._force_disconnect(client, gateway_id)
        else:
            self.health[gateway_id]["cleanup_status"] = "closed"

    async def _force_disconnect(self, client, gateway_id):
        # Public API in the pinned aioesphomeapi 45.3.1/46.3.0 implementations.
        # Closing HA's dedicated API socket never interrupts ESP-owned UART work.
        try:
            await asyncio.wait_for(client.disconnect(force=True), 1)
        except Exception:  # noqa: BLE001 - no raw cleanup exception strings
            self.health[gateway_id]["cleanup_status"] = "failed"
        else:
            self.health[gateway_id]["cleanup_status"] = "forced"

    async def _discover(self, client, gateway, on_stop, cancelled, progress):
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
            matches = [s for s in services if s.name == SERVICE]
            sensors = [
                e
                for e in entities
                if isinstance(e, TextSensorInfo) and e.name == "Modbus Scanner Result"
            ]
            if len(matches) != 1 or len(sensors) != 1:
                raise GatewayProviderError(
                    "Required read-only scanner firmware v1 is not installed",
                    code="BRIDGE_UNSUPPORTED",
                    phase=phase,
                )
            service = matches[0]
            if {a.name: a.type for a in service.args} != {
                "request_id": UserServiceArgType.STRING,
                "slave": UserServiceArgType.INT,
                "reg": UserServiceArgType.INT,
            } or len(service.args) != 3:
                raise GatewayProviderError(
                    "Unexpected scanner service signature", code="BRIDGE_UNSUPPORTED", phase=phase
                )
            self.health[gateway.gateway_id].update(
                api_status="verified",
                checked_at=_now(),
                bridge_status="v1_signature_verified",
                error_info=None,
            )
            return service, sensors[0].key, entities, services
        except (GatewayProviderError, _Cancelled):
            raise
        except Exception as exc:  # noqa: BLE001 - boundary sanitization
            raise self._transport_error(exc, phase) from None

    async def check_gateway(self, gateway_id):
        """API-only identity/signature check. Never executes a Modbus action."""
        if gateway_id not in self.gateways:
            raise ValueError("Unknown physical gateway")
        if self._locks[gateway_id].locked():
            raise GatewayProviderError(
                "Gateway is busy", code="GATEWAY_BUSY", phase="preflight", retryable=True
            )
        async with self._locks[gateway_id]:
            client = self._client(self.gateways[gateway_id])

            async def stopped(_expected):
                return None

            try:
                _, _, entities, services = await self._discover(
                    client, self.gateways[gateway_id], stopped, lambda: False, lambda _data: None
                )
                session = HealthSession.discover(client, entities, services)
                if session:
                    client.subscribe_states(session.accept)
                    snapshot = await session.snapshot()
                    self.health[gateway_id].update(
                        bridge_status="profile_verified",
                        firmware_state={k: v for k, v in snapshot.items() if k != "id"},
                    )
            except GatewayProviderError as exc:
                self.health[gateway_id].update(
                    api_status="failed", checked_at=_now(), error_info=exc.as_dict()
                )
                raise
            except Exception as exc:  # noqa: BLE001 - no raw health/library messages
                error = self._transport_error(exc, "verify_bridge")
                self.health[gateway_id].update(
                    api_status="failed", checked_at=_now(), error_info=error.as_dict()
                )
                raise error from None
            finally:
                await self._disconnect(client, gateway_id)
            return deepcopy(self.health[gateway_id])

    async def run_scan(self, request, emit, cancelled, *, progress=None):
        self.validate_request(request)
        async with self._locks[request.gateway_id]:
            if cancelled():
                return
            try:
                await self._run(request, emit, cancelled, progress or (lambda _data: None))
            except _Cancelled:
                return

    async def _run(self, request, emit, cancelled, progress):
        gateway = self.gateways[request.gateway_id]
        self.health[gateway.gateway_id].update(
            recovery_status="unknown", recovery_error=None, cleanup_status="pending"
        )
        client = self._client(gateway)
        pending = None
        expected = None
        sensor_key = None
        health_session = None
        probe_sent = False
        phase = "connect"

        def on_state(state):
            if health_session is not None:
                health_session.accept(state)
            if (
                pending is None
                or pending.done()
                or state.key != sensor_key
                or getattr(state, "missing_state", False)
            ):
                return
            try:
                payload = json.loads(state.state)
            except (ValueError, TypeError, AttributeError):
                return
            if not isinstance(payload, dict) or payload.get("id") != expected[0]:
                return
            try:
                for key, value in (("v", 1), ("slave", expected[1]), ("reg", expected[2])):
                    if type(payload.get(key)) is not int or payload[key] != value:
                        raise ValueError
                if (
                    type(payload.get("latency_ms")) is not int
                    or not 0 <= payload["latency_ms"] <= 10000
                ):
                    raise ValueError
                outcome = ScanOutcome(payload["outcome"])
                if outcome not in (
                    ScanOutcome.RESPONDED,
                    ScanOutcome.TIMEOUT,
                    ScanOutcome.MODBUS_EXCEPTION,
                    ScanOutcome.GATEWAY_ERROR,
                ):
                    raise ValueError
                if outcome == ScanOutcome.RESPONDED and (
                    type(payload.get("value")) is not int or not 0 <= payload["value"] <= 65535
                ):
                    raise ValueError
                if outcome == ScanOutcome.MODBUS_EXCEPTION and (
                    type(payload.get("exception")) is not int
                    or not 1 <= payload["exception"] <= 255
                ):
                    raise ValueError
                pending.set_result(payload)
            except (ValueError, TypeError, KeyError, AttributeError):
                pending.set_exception(
                    GatewayProviderError(
                        "Invalid firmware response", code="RESPONSE_INVALID", phase="probe"
                    )
                )

        async def on_stop(_expected_disconnect):
            if health_session is not None:
                health_session.disconnected()
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
            service, sensor_key, entities, services = await self._discover(
                client, gateway, on_stop, cancelled, progress
            )
            phase = "verify_bridge"
            health_session = HealthSession.discover(client, entities, services)
            client.subscribe_states(on_state)
            if health_session:
                snapshot = await _bounded(health_session.snapshot(), 4, cancelled)
                if snapshot["fault"]:
                    raise GatewayProviderError(
                        "Firmware transport fault requires manual maintenance",
                        code="FIRMWARE_FAULT",
                        phase="verify_bridge",
                    )
                self.health[gateway.gateway_id].update(
                    bridge_status="profile_verified",
                    firmware_state={k: v for k, v in snapshot.items() if k != "id"},
                )
            self.health[gateway.gateway_id]["recovery_status"] = "unknown"
            for slave in range(request.start_id, request.end_id + 1):
                for attempt in range(request.retries + 1):
                    if cancelled():
                        return
                    phase = "probe"
                    progress(
                        {"operation_phase": phase, "current_address": slave, "attempt": attempt + 1}
                    )
                    expected = (uuid4().hex, slave, request.register_address)
                    pending = asyncio.get_running_loop().create_future()
                    probe_sent = True
                    result = client.execute_service(
                        service,
                        {
                            "request_id": expected[0],
                            "slave": slave,
                            "reg": request.register_address,
                        },
                    )
                    if inspect.isawaitable(result):
                        await asyncio.wait_for(result, 5)
                    payload = await asyncio.wait_for(pending, 6)
                    if payload["outcome"] != "timeout":
                        break
                if payload["outcome"] == "gateway_error":
                    raise GatewayProviderError(
                        "Firmware rejected probe or transport failed",
                        address=slave,
                        code="FIRMWARE_REJECTED",
                        phase=phase,
                    )
                outcome = ScanOutcome(payload["outcome"])
                detail = {
                    ScanOutcome.RESPONDED: (
                        f"FC03 register 0x{request.register_address:04X} = {payload.get('value')}; "
                        "CRC validated by ESPHome"
                    ),
                    ScanOutcome.TIMEOUT: (
                        "No valid response within 700 ms; not proof of an unused address"
                    ),
                    ScanOutcome.MODBUS_EXCEPTION: (
                        "CRC-valid Modbus exception; not proof of unique identity"
                    ),
                }[outcome]
                if outcome in (ScanOutcome.RESPONDED, ScanOutcome.MODBUS_EXCEPTION):
                    self.health[gateway.gateway_id].update(
                        bus_status=outcome.value, last_bus_response_at=_now()
                    )
                emit(
                    ProbeResult(
                        slave,
                        outcome,
                        payload["latency_ms"],
                        detail,
                        exception_code=payload["exception"]
                        if outcome == ScanOutcome.MODBUS_EXCEPTION
                        else None,
                        register_address=request.register_address,
                        raw_value=payload["value"] if outcome == ScanOutcome.RESPONDED else None,
                        attempts=attempt + 1,
                    )
                )
                if slave < request.end_id:
                    phase = "inter_request_delay"
                    progress({"operation_phase": phase})
                    deadline = (
                        asyncio.get_running_loop().time() + request.inter_request_delay_ms / 1000
                    )
                    while not cancelled() and asyncio.get_running_loop().time() < deadline:
                        await asyncio.sleep(
                            min(0.05, max(0, deadline - asyncio.get_running_loop().time()))
                        )
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
            try:
                await self._recover(gateway.gateway_id, health_session, probe_sent, progress)
            finally:
                await self._disconnect(client, gateway.gateway_id)
                progress(
                    {
                        "cleanup_status": self.health[gateway.gateway_id].get(
                            "cleanup_status", "unknown"
                        ),
                        "recovery_status": self.health[gateway.gateway_id]["recovery_status"],
                    }
                )

    async def _recover(self, gateway_id, session, probe_sent, progress):
        task = asyncio.current_task()
        if probe_sent and session is not None and not (task and task.cancelling()):
            progress({"operation_phase": "recovery", "recovery_status": "pending"})
            try:
                snapshot = await session.verify_recovery()
            except GatewayProviderError as exc:
                recovery = (
                    "failed"
                    if exc.code in {"FIRMWARE_FAULT", "DEVICE_RESTARTED", "PROFILE_MISMATCH"}
                    else "unknown"
                )
                self.health[gateway_id].update(
                    recovery_status=recovery, recovery_error=exc.as_dict()
                )
            except Exception:  # noqa: BLE001 - never replace the primary probe failure
                self.health[gateway_id].update(
                    recovery_status="unknown",
                    recovery_error={
                        "code": "RESTORE_UNCONFIRMED",
                        "phase": "recovery",
                        "retryable": True,
                    },
                )
            else:
                self.health[gateway_id].update(
                    recovery_status="verified",
                    recovery_error=None,
                    recovered_at=_now(),
                    firmware_state={k: v for k, v in snapshot.items() if k != "id"},
                )
        progress(
            {
                "recovery_status": self.health[gateway_id]["recovery_status"],
                "recovery_error_code": (self.health[gateway_id].get("recovery_error") or {}).get(
                    "code"
                ),
            }
        )
