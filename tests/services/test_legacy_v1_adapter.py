"""Legacy bridge v1 behaviour through the HA service seam with a fake ESPHome client."""

import asyncio
import json
from types import SimpleNamespace

from aioesphomeapi import (
    TextSensorInfo,
    TextSensorState,
    UserService,
    UserServiceArg,
    UserServiceArgType,
)
from homeassistant.core import Context
from homeassistant.exceptions import ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.woow_esphome_modbus_scanner.const import DATA_COORDINATOR, DOMAIN
from custom_components.woow_esphome_modbus_scanner.modbus_scan.legacy_v1 import (
    provider as legacy_provider,
)
from custom_components.woow_esphome_modbus_scanner.services import async_register_services

GATEWAY_ID = "esphome:aabbccddeeff"
IN_D17_REGISTERS = [
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
]


class FakeLegacyClient:
    """aioesphomeapi client boundary of a node running bridge v1 firmware."""

    instances: list = []

    def __init__(self, host, port, password, **kwargs):
        self.probes = []
        FakeLegacyClient.instances.append(self)

    async def connect(self, **kwargs):
        return None

    async def device_info(self):
        return SimpleNamespace(mac_address="AA:BB:CC:DD:EE:FF")

    async def list_entities_services(self):
        return [TextSensorInfo(key=1, name="Modbus Scanner Result")], [
            UserService(
                name="modbus_scanner_probe_v1",
                key=10,
                args=[
                    UserServiceArg("request_id", UserServiceArgType.STRING),
                    UserServiceArg("slave", UserServiceArgType.INT),
                    UserServiceArg("reg", UserServiceArgType.INT),
                ],
            )
        ]

    def subscribe_states(self, callback):
        self.callback = callback

    async def execute_service(self, service, data):
        self.probes.append((data["slave"], data["reg"]))
        payload = {
            "v": 1,
            "id": data["request_id"],
            "slave": data["slave"],
            "reg": data["reg"],
            "outcome": "responded" if data["slave"] == 1 else "timeout",
            "latency_ms": 12,
            "value": 1234,
        }
        self.callback(TextSensorState(key=1, state=json.dumps(payload)))

    async def disconnect(self, force=False):
        return None


@pytest.fixture(autouse=True)
def fake_client(monkeypatch):
    FakeLegacyClient.instances = []
    monkeypatch.setattr(legacy_provider, "APIClient", FakeLegacyClient)
    return FakeLegacyClient


async def _setup(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, data={"gateways": [{"host": "192.0.2.1", "mac": "AA:BB:CC:DD:EE:FF"}]}
    )
    entry.add_to_hass(hass)
    user = await hass.auth.async_create_user("legacy operator")
    async_register_services(hass, entry.entry_id)
    context = Context(user_id=user.id)

    async def call(service, data=None):
        return await hass.services.async_call(
            DOMAIN, service, data or {}, blocking=True, return_response=True, context=context
        )

    return call


async def test_legacy_gateway_reports_its_limits_in_list_gateways(hass):
    call = await _setup(hass)
    gateway = next(
        g for g in (await call("list_gateways"))["gateways"] if g["gateway_id"] == GATEWAY_ID
    )
    assert gateway["limits"] == {
        "slave_min": 1,
        "slave_max": 32,
        "probe_types": ["holding_register"],
        "register_count_max": 1,
        "allowed_registers": IN_D17_REGISTERS,
        "timeout_ms_min": 700,
        "timeout_ms_max": 700,
        "inter_request_delay_ms_max": 5000,
        "pause_normal_polling_required": True,
        "pause_normal_polling_supported": True,
        "attempt_overhead_ms": 2700,
    }


async def test_legacy_probe_uses_reported_defaults_and_keeps_result_format(hass):
    call = await _setup(hass)
    started = await call(
        "test_address", {"provider": "esphome", "gateway_id": GATEWAY_ID, "address": 1}
    )
    await asyncio.gather(*hass.data[DOMAIN][DATA_COORDINATOR]._tasks.values())
    assert FakeLegacyClient.instances[0].probes == [(1, 0x6201)]
    # One 700 ms attempt plus the v1 firmware's 2700 ms drain and quiet periods; the budget
    # adds v1 connect, per-attempt API waits and the post-scan polling recovery check.
    assert (started["estimated_worst_case_ms"], started["execution_budget_ms"]) == (3400, 79000)
    results = await call("get_scan_results", {"scan_id": started["scan_id"]})
    assert results["status"] == "completed"
    assert results["responders"] == [
        {
            "address": 1,
            "outcome": "responded",
            "latency_ms": 12,
            "detail": "FC03 register 0x6201 = 1234; CRC validated by ESPHome",
            "register_address": 0x6201,
            "raw_value": 1234,
            "attempts": 1,
        }
    ]


async def test_legacy_gateway_keeps_its_frozen_inter_request_delay_cap(hass):
    """A Legacy Gateway has no Scan Lease, so the bridge v2 3000 ms cap does not apply."""
    call = await _setup(hass)
    started = await call(
        "test_address",
        {"provider": "esphome", "gateway_id": GATEWAY_ID, "address": 1,
         "inter_request_delay_ms": 5000},
    )
    await asyncio.gather(*hass.data[DOMAIN][DATA_COORDINATOR]._tasks.values())
    results = await call("get_scan_results", {"scan_id": started["scan_id"]})
    assert results["status"] == "completed"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"address": 33}, "Bridge v1 supports slave IDs 1–32 only"),
        ({"probe_type": "input_register"}, "Bridge v1 requires probe_type"),
        ({"register_count": 2}, "Bridge v1 requires register_count<=1"),
        ({"register_address": 0}, r"Register 0 \(0x0000\) is not in the Bridge v1 read allowlist"),
        ({"timeout_ms": 500}, "Bridge v1 requires timeout_ms=700"),
        ({"pause_normal_polling": False}, "Bridge v1 requires pause_normal_polling=true"),
        ({"bus": "rs485"}, "does not support bus selection"),
    ],
)
async def test_service_rejects_requests_outside_legacy_limits_without_bus_traffic(
    hass, changes, message
):
    call = await _setup(hass)
    with pytest.raises(ServiceValidationError, match=message):
        await call(
            "test_address",
            {"provider": "esphome", "gateway_id": GATEWAY_ID, "address": 1, **changes},
        )
    assert FakeLegacyClient.instances == []
