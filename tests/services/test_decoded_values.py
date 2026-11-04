"""Responder results carry decoded values when the selected Device Profile defines fields."""

import pytest
from test_bridge_v2 import GATEWAY_ID, FakeClient, FakeV2Gateway
from test_bridge_v2 import _setup as setup_v2
from test_device_profiles import METER, _settle
from test_device_profiles import _setup as setup_mock
from test_legacy_v1_adapter import GATEWAY_ID as LEGACY_GATEWAY_ID
from test_legacy_v1_adapter import FakeLegacyClient
from test_legacy_v1_adapter import _setup as setup_legacy

from custom_components.woow_esphome_modbus_scanner.const import DOMAIN
from custom_components.woow_esphome_modbus_scanner.history import ScanHistory
from custom_components.woow_esphome_modbus_scanner.modbus_scan.bridge_v2 import (
    provider as v2_provider,
)
from custom_components.woow_esphome_modbus_scanner.modbus_scan.coordinator import (
    ModbusScanCoordinator,
)
from custom_components.woow_esphome_modbus_scanner.modbus_scan.legacy_v1 import (
    provider as legacy_provider,
)
from custom_components.woow_esphome_modbus_scanner.modbus_scan.mock_provider import (
    MockGatewayProvider,
)


async def test_profile_fields_decode_responder_values_next_to_raw_values(hass):
    call = await setup_mock(hass)
    await call("import_device_profile", {"profile": METER})
    started = await call(
        "start_scan", {"device_profile_id": "acme-meter", "safety_confirmed": True}
    )
    await _settle(hass)
    results = await call("get_scan_results", {"scan_id": started["scan_id"]})
    row = next(item for item in results["responders"] if item["outcome"] == "responded")
    # Mock ID 3 answers registers 16..17 with 0x0310, 0x0311; only 16 has a field.
    assert (row["address"], row["raw_value"], row["raw_values"]) == (3, 784, [784, 785])
    assert row["decoded"] == [{"register": 16, "name": "Voltage", "unit": "V", "value": 78.4}]


async def test_generic_device_profile_shows_only_raw_values(hass):
    call = await setup_mock(hass)
    started = await call(
        "test_address",
        {"address": 3, "probe_type": "input_register", "register_address": 16, "register_count": 2},
    )
    await _settle(hass)
    [row] = (await call("get_scan_results", {"scan_id": started["scan_id"]}))["responders"]
    assert row["raw_values"] == [784, 785]
    assert "decoded" not in row


@pytest.fixture
def v2_gateway(monkeypatch):
    node = FakeV2Gateway(devices={("rs485", 3): [2301, 7, 65400, 9], ("rs485", 4): [32768, 1]})
    FakeClient.gateway = node
    FakeClient.instances = []
    monkeypatch.setattr(v2_provider, "APIClient", FakeClient)
    return node


async def _v2_row(hass, call, **fields):
    started = await call(
        "test_address",
        {
            "provider": "esphome",
            "gateway_id": GATEWAY_ID,
            "device_profile_id": "acme-meter",
            **fields,
        },
    )
    await _settle(hass)
    [row] = (await call("get_scan_results", {"scan_id": started["scan_id"]}))["responders"]
    return row


async def test_each_field_decodes_its_own_register_of_a_multi_register_probe(hass, v2_gateway):
    call = await setup_v2(hass)
    await call("import_device_profile", {"profile": METER})
    row = await _v2_row(hass, call, address=3, register_count=4)
    assert row["raw_values"] == [2301, 7, 65400, 9]  # registers 16..19, never rewritten
    assert row["decoded"] == [
        {"register": 16, "name": "Voltage", "unit": "V", "value": 230.1},
        # s16: 65400 is -136 counts, scaled by 0.01.
        {"register": 18, "name": "Current", "unit": "A", "value": -1.36},
    ]


async def test_s16_sign_boundary_and_a_block_starting_on_a_later_field(hass, v2_gateway):
    call = await setup_v2(hass)
    profile = {
        **METER,
        "allowed_registers": [16, 17, 18, 19, 32],
        "fields": [*METER["fields"], {"register": 19, "name": "Power factor", "data_type": "u16"}],
    }
    await call("import_device_profile", {"profile": profile})
    row = await _v2_row(hass, call, address=4, register_address=18, register_count=2)
    assert row["raw_values"] == [32768, 1]
    assert row["decoded"] == [
        {"register": 18, "name": "Current", "unit": "A", "value": -327.68},
        # No scale means 1 and no unit means None; a u16 is never sign-extended.
        {"register": 19, "name": "Power factor", "unit": None, "value": 1},
    ]


async def test_a_full_range_of_decoded_responders_is_kept_in_scan_history(hass, v2_gateway):
    # Worst case for the stored record: every ID answers 4 registers and every register
    # has a field with the longest allowed name and unit.
    v2_gateway.devices = {("rs485", slave): [65535, 1, 2, 3] for slave in range(1, 248)}
    history = ScanHistory(hass)
    await history.async_load()
    hass.data[DOMAIN] = {"history": history}  # as the integration's setup provides it
    call = await setup_v2(hass)
    profile = {
        **METER,
        "allowed_registers": None,
        "defaults": {},
        "fields": [
            {
                "register": 16 + offset,
                "name": f"{offset}" * 64,
                "unit": "u" * 16,
                "scale": 0.001,
                "data_type": "s16",
            }
            for offset in range(4)
        ],
    }
    await call("import_device_profile", {"profile": profile})
    started = await call(
        "start_scan",
        {
            "provider": "esphome",
            "gateway_id": GATEWAY_ID,
            "device_profile_id": "acme-meter",
            "start_id": 1,
            "end_id": 247,
            "register_address": 16,
            "register_count": 4,
            "timeout_ms": 100,
            "retries": 0,
            "inter_request_delay_ms": 0,
            "safety_confirmed": True,
            "large_range_confirmed": True,
        },
    )
    await _settle(hass)
    await history.async_flush()

    restored = ScanHistory(hass)
    await restored.async_load()
    coordinator = ModbusScanCoordinator(hass, [MockGatewayProvider()], history=restored)
    results = coordinator.results(started["scan_id"])
    assert len(results["responders"]) == 247
    assert results["responders"][-1]["decoded"][0] == {
        "register": 16,
        "name": "0" * 64,
        "unit": "u" * 16,
        "value": -0.001,
    }


async def test_single_register_legacy_reply_is_decoded_too(hass, monkeypatch):
    FakeLegacyClient.instances = []
    monkeypatch.setattr(legacy_provider, "APIClient", FakeLegacyClient)
    call = await setup_legacy(hass)
    profile = {
        **METER,
        "function_codes": [3],
        "defaults": {"register": 0x6201, "timeout_ms": 700},
        "allowed_registers": None,
        "fields": [{"register": 0x6201, "name": "Temperature", "unit": "°C", "scale": 0.1}],
    }
    await call("import_device_profile", {"profile": profile})
    started = await call(
        "test_address",
        {
            "provider": "esphome",
            "gateway_id": LEGACY_GATEWAY_ID,
            "device_profile_id": "acme-meter",
            "address": 1,
        },
    )
    await _settle(hass)
    [row] = (await call("get_scan_results", {"scan_id": started["scan_id"]}))["responders"]
    assert row["raw_value"] == 1234
    assert row["decoded"] == [
        {"register": 0x6201, "name": "Temperature", "unit": "°C", "value": 123.4}
    ]
