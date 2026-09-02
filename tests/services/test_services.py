"""Public Home Assistant service-seam tests."""

import asyncio
from pathlib import Path
import time

from homeassistant.exceptions import HomeAssistantError
import pytest
import voluptuous as vol
import yaml

from custom_components.woow_esphome_modbus_scanner.const import (
    DATA_COORDINATOR,
    DOMAIN,
    PUBLIC_SERVICES,
)
from custom_components.woow_esphome_modbus_scanner.modbus_scan.models import ProbeType
from custom_components.woow_esphome_modbus_scanner.services import async_register_services


async def _call(hass, service, data=None):
    return await hass.services.async_call(
        DOMAIN,
        service,
        data or {},
        blocking=True,
        return_response=True,
    )


async def _start(hass, **changes):
    data = {
        "start_id": 1,
        "end_id": 12,
        "safety_confirmed": True,
        "inter_request_delay_ms": 0,
    }
    data.update(changes)
    return await _call(hass, "start_scan", data)


async def _wait_for_terminal(hass, scan_id):
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        status = await _call(hass, "get_scan_status", {"scan_id": scan_id})
        if status["status"] != "running":
            return status
        await asyncio.sleep(0.01)
    pytest.fail(f"scan {scan_id} did not finish")


async def test_exactly_six_public_services_are_registered(hass):
    async_register_services(hass)
    assert set(hass.services.async_services()[DOMAIN]) == set(PUBLIC_SERVICES)


async def test_list_gateways_returns_mock_capabilities(hass):
    async_register_services(hass)
    response = await _call(hass, "list_gateways")
    gateway = response["gateways"][0]
    assert gateway["gateway_id"] == "mock:rs485-gateway"
    assert gateway["simulated"] is True
    assert gateway["provider"] == "mock"


async def test_start_status_and_results_have_normalized_public_shapes(hass):
    async_register_services(hass)
    started = await _start(hass)
    assert started["status"] == "running"
    done = await _wait_for_terminal(hass, started["scan_id"])
    assert done["status"] == "completed"
    results = await _call(hass, "get_scan_results", {"scan_id": started["scan_id"]})
    assert [item["address"] for item in results["responders"]] == [1, 3, 5, 12]
    assert results["outcome_counts"]["timeout"] == 8
    assert results["best_effort"] is True
    assert results["uniqueness_guaranteed"] is False


async def test_test_address_is_one_id_and_accepts_reserved_device_selector(hass):
    async_register_services(hass)
    started = await _call(
        hass,
        "test_address",
        {
            "address": 3,
            "inter_request_delay_ms": 0,
            "esphome_device_id": "reserved-future-device",
        },
    )
    done = await _wait_for_terminal(hass, started["scan_id"])
    assert done["total_addresses"] == 1
    result = await _call(hass, "get_scan_results", {"scan_id": started["scan_id"]})
    assert [item["address"] for item in result["responders"]] == [3]


async def test_cancel_requests_terminal_cancelled_state(hass):
    async_register_services(hass)
    started = await _start(hass, end_id=100, inter_request_delay_ms=100)
    requested = await _call(hass, "cancel_scan", {"scan_id": started["scan_id"]})
    assert requested["cancellation_requested"] is True
    assert (await _wait_for_terminal(hass, started["scan_id"]))["status"] == "cancelled"


async def test_invalid_range_is_rejected_before_scheduling(hass):
    async_register_services(hass)
    with pytest.raises(HomeAssistantError, match="start_id"):
        await _start(hass, start_id=12, end_id=1)


async def test_missing_safety_confirmation_is_rejected(hass):
    async_register_services(hass)
    with pytest.raises(Exception, match="safety_confirmed"):
        await _call(hass, "start_scan", {"start_id": 1, "end_id": 2})


@pytest.mark.parametrize("value", [1, 1.0, "true", "True", False])
async def test_safety_confirmation_requires_exact_boolean_true(hass, value):
    async_register_services(hass)
    with pytest.raises(vol.Invalid):
        await _start(hass, safety_confirmed=value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("start_id", 1.9),
        ("end_id", True),
        ("register_address", 1.1),
        ("register_count", False),
        ("timeout_ms", 500.5),
        ("retries", True),
        ("inter_request_delay_ms", 0.1),
    ],
)
async def test_numeric_schema_rejects_floats_and_booleans(hass, field, value):
    async_register_services(hass)
    with pytest.raises(vol.Invalid):
        await _start(hass, **{field: value})


async def test_numeric_schema_accepts_exact_integer_strings(hass):
    async_register_services(hass)
    started = await _start(
        hass,
        start_id="1",
        end_id="1",
        register_address="0",
        register_count="1",
        timeout_ms="500",
        retries="1",
        inter_request_delay_ms="0",
    )
    assert (await _wait_for_terminal(hass, started["scan_id"]))["status"] == "completed"


@pytest.mark.parametrize("value", ["١", "１", "１２"])
async def test_numeric_schema_rejects_non_ascii_integer_strings(hass, value):
    async_register_services(hass)
    with pytest.raises(vol.Invalid, match="integer"):
        await _start(hass, start_id=value)


async def test_service_schema_passes_typed_probe_to_coordinator(hass):
    async_register_services(hass)
    started = await _start(hass, start_id=1, end_id=1, probe_type="holding_register")
    coordinator = hass.data[DOMAIN][DATA_COORDINATOR]

    assert coordinator._scans[started["scan_id"]].request.probe_type is ProbeType.HOLDING_REGISTER
    assert (await _wait_for_terminal(hass, started["scan_id"]))["status"] == "completed"


async def test_unknown_canonical_scan_id_is_clear_service_error(hass):
    async_register_services(hass)
    unknown_id = "00000000-0000-0000-0000-000000000000"
    with pytest.raises(HomeAssistantError, match="Unknown Modbus scan ID"):
        await _call(hass, "get_scan_status", {"scan_id": unknown_id})


@pytest.mark.parametrize(
    "scan_id",
    [
        "missing",
        "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA",
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "{aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa}",
    ],
)
async def test_malformed_or_noncanonical_scan_id_is_schema_rejected(hass, scan_id):
    async_register_services(hass)
    with pytest.raises(vol.Invalid, match="canonical UUID"):
        await _call(hass, "get_scan_status", {"scan_id": scan_id})


@pytest.mark.parametrize(
    ("service", "expected"),
    [
        (
            "start_scan",
            {
                "provider",
                "gateway_id",
                "esphome_device_id",
                "start_id",
                "end_id",
                "probe_type",
                "register_address",
                "register_count",
                "timeout_ms",
                "retries",
                "inter_request_delay_ms",
                "pause_normal_polling",
                "mock_profile",
                "safety_confirmed",
            },
        ),
        (
            "test_address",
            {
                "provider",
                "gateway_id",
                "esphome_device_id",
                "address",
                "probe_type",
                "register_address",
                "register_count",
                "timeout_ms",
                "retries",
                "inter_request_delay_ms",
                "pause_normal_polling",
                "mock_profile",
            },
        ),
        ("get_scan_status", {"scan_id"}),
        ("get_scan_results", {"scan_id"}),
        ("cancel_scan", {"scan_id"}),
    ],
)
def test_service_metadata_has_selector_for_every_parameter(service, expected):
    metadata = yaml.safe_load(
        Path("custom_components/woow_esphome_modbus_scanner/services.yaml").read_text()
    )
    fields = metadata[service]["fields"]
    assert set(fields) == expected
    assert all("selector" in fields[field] for field in expected)


def test_reserved_esphome_selector_is_optional_and_filtered():
    metadata = yaml.safe_load(
        Path("custom_components/woow_esphome_modbus_scanner/services.yaml").read_text()
    )
    for service in ("start_scan", "test_address"):
        field = metadata[service]["fields"]["esphome_device_id"]
        assert field.get("required", False) is False
        assert field["selector"]["device"]["filter"] == [{"integration": "esphome"}]


def test_mock_provider_and_gateway_selectors_are_fixed_to_implemented_values():
    metadata = yaml.safe_load(
        Path("custom_components/woow_esphome_modbus_scanner/services.yaml").read_text()
    )
    for service in ("start_scan", "test_address"):
        fields = metadata[service]["fields"]
        provider = fields["provider"]["selector"]["select"]
        gateway = fields["gateway_id"]["selector"]["select"]
        assert provider["options"] == [{"label": "Mock (simulated)", "value": "mock"}]
        assert gateway["options"] == [
            {
                "label": "Simulated RS-485 Gateway",
                "value": "mock:rs485-gateway",
            }
        ]
        assert provider.get("custom_value", False) is False
        assert gateway.get("custom_value", False) is False
