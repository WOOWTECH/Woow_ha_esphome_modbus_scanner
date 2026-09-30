"""Experimental FC03 bridge for explicitly configured Guanjie firmware v1.

Never reinterpret cached entity telemetry as a probe. Each result must carry
our unpredictable request ID and the exact slave/register sent to the firmware.
The firmware owns UART arbitration, CRC validation, and automatic resumption.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import inspect
import json
from uuid import uuid4

from aioesphomeapi import APIClient, TextSensorInfo, UserServiceArgType

from .models import GatewayInfo, ProbeResult, ProbeType, ScanOutcome
from .provider import GatewayProviderError

SERVICE = "modbus_scanner_probe_v1"
REGISTERS = frozenset(
    (
        0x6201,
        0x6202,
        0x6203,
        0x6205,
        0x6206,
        0x6105,
        0x6101,
        0x6102,
        0x6103,
        0x6104,
        0x6106,
        0x6111,
        0x6112,
    )
)


@dataclass(frozen=True)
class ESPHomeGateway:
    host: str
    mac: str
    name: str = "Guanjie read-only scanner"
    port: int = 6053
    device_id: str | None = None

    @property
    def gateway_id(self):
        return "esphome:" + self.mac.replace(":", "").lower()


class ESPHomeGatewayProvider:
    provider_id = "esphome"

    def __init__(self, gateways, *, client_factory=APIClient):
        self.gateways = {g.gateway_id: g for g in gateways}
        self.client_factory = client_factory
        self._locks = {key: asyncio.Lock() for key in self.gateways}

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
            )
            for g in self.gateways.values()
        ]

    def validate_request(self, request):
        request.validate()
        if request.provider != self.provider_id or request.gateway_id not in self.gateways:
            raise ValueError("Unknown physical gateway")
        if request.end_id > 32:
            raise ValueError("Guanjie bridge supports slave IDs 1–32 only")
        if request.probe_type != ProbeType.HOLDING_REGISTER or request.register_count != 1:
            raise ValueError("Bridge v1 supports FC03 single-register reads only")
        if request.register_address not in REGISTERS:
            raise ValueError("Register is not in the verified IN-D17 read allowlist")
        if request.timeout_ms != 700:
            raise ValueError("Bridge v1 uses the existing fixed 700 ms bus timeout")
        if not request.pause_normal_polling:
            raise ValueError("Physical reads require pause_normal_polling=true")

    async def run_scan(self, request, emit, cancelled):
        self.validate_request(request)
        async with self._locks[request.gateway_id]:
            if cancelled():
                return
            await self._run(request, emit, cancelled)

    async def _run(self, request, emit, cancelled):
        gateway = self.gateways[request.gateway_id]
        client = self.client_factory(gateway.host, gateway.port, "")
        pending = None
        expected = None
        sensor_key = None

        def on_state(state):
            if pending is None or pending.done() or state.key != sensor_key:
                return
            try:
                payload = json.loads(state.state)
                if not isinstance(payload, dict) or payload.get("id") != expected[0]:
                    return  # Initial cached result / another client is not evidence.
                for key, value in (("v", 1), ("slave", expected[1]), ("reg", expected[2])):
                    if type(payload.get(key)) is not int or payload[key] != value:
                        raise ValueError("Mismatched correlated response")
                if (
                    type(payload.get("latency_ms")) is not int
                    or not 0 <= payload["latency_ms"] <= 10000
                ):
                    raise ValueError("Invalid response latency")
                outcome = ScanOutcome(payload["outcome"])
                if outcome not in (
                    ScanOutcome.RESPONDED,
                    ScanOutcome.TIMEOUT,
                    ScanOutcome.MODBUS_EXCEPTION,
                    ScanOutcome.GATEWAY_ERROR,
                ):
                    raise ValueError("Unsupported firmware result")
                if outcome == ScanOutcome.RESPONDED:
                    if type(payload.get("value")) is not int or not 0 <= payload["value"] <= 65535:
                        raise ValueError("Invalid register data")
                if outcome == ScanOutcome.MODBUS_EXCEPTION:
                    if (
                        type(payload.get("exception")) is not int
                        or not 1 <= payload["exception"] <= 255
                    ):
                        raise ValueError("Invalid Modbus exception")
                pending.set_result(payload)
            except (ValueError, TypeError, KeyError, AttributeError):
                pending.set_exception(GatewayProviderError("Invalid firmware response"))

        async def on_stop(expected_disconnect):
            if pending is not None and not pending.done():
                pending.set_exception(GatewayProviderError("ESPHome connection lost"))

        try:
            await asyncio.wait_for(client.connect(login=True, on_stop=on_stop), 15)
            info = await asyncio.wait_for(client.device_info(), 10)
            if info.mac_address.upper() != gateway.mac.upper():
                raise GatewayProviderError("Gateway identity mismatch; no probe sent")
            entities, services = await asyncio.wait_for(client.list_entities_services(), 10)
            matches = [s for s in services if s.name == SERVICE]
            sensors = [
                e
                for e in entities
                if isinstance(e, TextSensorInfo) and e.name == "Modbus Scanner Result"
            ]
            if len(matches) != 1 or len(sensors) != 1:
                raise GatewayProviderError(
                    "Required read-only scanner firmware v1 is not installed"
                )
            service = matches[0]
            if {a.name: a.type for a in service.args} != {
                "request_id": UserServiceArgType.STRING,
                "slave": UserServiceArgType.INT,
                "reg": UserServiceArgType.INT,
            } or len(service.args) != 3:
                raise GatewayProviderError("Unexpected scanner service signature")
            sensor_key = sensors[0].key
            client.subscribe_states(on_state)
            for slave in range(request.start_id, request.end_id + 1):
                payload = None
                for _attempt in range(request.retries + 1):
                    if cancelled():
                        return
                    expected = (uuid4().hex, slave, request.register_address)
                    pending = asyncio.get_running_loop().create_future()
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
                    # Drain <=700ms, pre/post quiet 1000ms each, read <=700ms,
                    # plus API delivery margin. API timeout != Modbus timeout.
                    payload = await asyncio.wait_for(pending, 6)
                    if payload["outcome"] != "timeout":
                        break
                if payload["outcome"] == "gateway_error":
                    raise GatewayProviderError(
                        "Firmware rejected probe or transport failed", address=slave
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
                emit(
                    ProbeResult(
                        slave,
                        outcome,
                        payload["latency_ms"],
                        detail,
                        exception_code=payload["exception"]
                        if outcome == ScanOutcome.MODBUS_EXCEPTION
                        else None,
                    )
                )
                if slave < request.end_id and not cancelled():
                    await asyncio.sleep(request.inter_request_delay_ms / 1000)
        except GatewayProviderError:
            raise
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - sanitize transport-library exceptions
            # Do not leak host, credentials, library frames or registry data.
            raise GatewayProviderError(
                "ESPHome transport failed or response deadline exceeded"
            ) from None
        finally:
            if pending is not None and not pending.done():
                pending.cancel()
            await client.disconnect()
            # Firmware restores polling without a client message, even on loss
            # of Wi-Fi/API. Never send a second master request or address change.
