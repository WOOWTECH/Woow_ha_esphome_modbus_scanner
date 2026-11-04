"""Range Scans with the Generic Device Profile through the HA service seam.

The v2 Gateway is the fake from ``test_bridge_v2`` (built from the shared contract file).
"""

from homeassistant.exceptions import ServiceValidationError
import pytest
from test_bridge_v2 import GATEWAY_ID, FakeClient, FakeV2Gateway, _settle, _setup
import voluptuous as vol

from custom_components.woow_esphome_modbus_scanner.modbus_scan.bridge_v2 import (
    provider as v2_provider,
)


@pytest.fixture
def gateway(monkeypatch):
    node = FakeV2Gateway(devices={("rs485", 7): [1234, 65535], ("rs485", 9): 2})
    FakeClient.gateway = node
    FakeClient.instances = []
    monkeypatch.setattr(v2_provider, "APIClient", FakeClient)
    return node


async def _start_scan(call, **fields):
    return await call(
        "start_scan",
        {
            "provider": "esphome",
            "gateway_id": GATEWAY_ID,
            "inter_request_delay_ms": 0,
            # The fake's responder at ID 7 answers with two registers.
            "register_count": 2,
            "safety_confirmed": True,
            **fields,
        },
    )


async def test_range_above_32_ids_needs_the_large_range_confirmation(hass, gateway):
    call = await _setup(hass)
    with pytest.raises(ServiceValidationError, match="large_range_confirmed"):
        await _start_scan(call, start_id=1, end_id=33)
    assert FakeClient.instances == []


@pytest.mark.parametrize("value", [1, "true", False])
async def test_large_range_confirmation_requires_exact_boolean_true(hass, gateway, value):
    call = await _setup(hass)
    with pytest.raises(vol.Invalid):
        await _start_scan(call, start_id=1, end_id=33, large_range_confirmed=value)
    assert FakeClient.instances == []


async def test_range_of_32_ids_needs_only_safety_confirmation(hass, gateway):
    call = await _setup(hass)
    started = await _start_scan(call, start_id=1, end_id=32)
    await _settle(hass)
    status = await call("get_scan_status", {"scan_id": started["scan_id"]})
    assert (status["status"], status["total_addresses"], status["error"]) == ("completed", 32, None)


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"register_address": 65534, "register_count": 3}, ServiceValidationError),
        ({"register_count": 5}, ServiceValidationError),
        ({"timeout_ms": 2001}, ServiceValidationError),
        ({"probe_type": "device_identification"}, vol.Invalid),
        ({"retries": 6}, vol.Invalid),
        ({"start_id": 0}, vol.Invalid),
        ({"end_id": 248}, vol.Invalid),
    ],
)
async def test_generic_limits_are_enforced_before_any_bus_traffic(hass, gateway, changes, error):
    call = await _setup(hass)
    with pytest.raises(error):
        await _start_scan(call, **{"start_id": 1, "end_id": 10, **changes})
    assert FakeClient.instances == []


async def test_highest_register_block_ending_at_65535_is_accepted(hass, gateway):
    call = await _setup(hass)
    started = await _start_scan(
        call, start_id=1, end_id=1, register_address=65532, register_count=4
    )
    await _settle(hass)
    [probe] = gateway.probes
    assert (probe["register"], probe["count"]) == (65532, 4)
    status = await call("get_scan_status", {"scan_id": started["scan_id"]})
    assert status["status"] == "completed"


async def test_full_range_fc04_scan_reads_four_registers_from_every_responder(hass, gateway):
    gateway.devices = {
        ("rs485", 7): [1, 2, 3, 4],
        ("rs485", 100): 2,
        ("rs485", 247): [0xFFFF, 0, 0x1234, 9],
    }
    call = await _setup(hass)
    started = await _start_scan(
        call,
        start_id=1,
        end_id=247,
        probe_type="input_register",
        register_address=0x0010,
        register_count=4,
        timeout_ms=100,
        large_range_confirmed=True,
    )
    await _settle(hass)
    results = await call("get_scan_results", {"scan_id": started["scan_id"]})

    assert (results["status"], results["total_addresses"]) == ("completed", 247)
    assert results["outcome_counts"]["timeout"] == 244
    assert [(row["address"], row["outcome"]) for row in results["responders"]] == [
        (7, "responded"),
        (100, "modbus_exception"),
        (247, "responded"),
    ]
    assert results["responders"][2]["raw_values"] == [65535, 0, 4660, 9]
    assert {(p["function_code"], p["register"], p["count"]) for p in gateway.probes} == {
        (4, 0x0010, 4)
    }
    assert [p["slave"] for p in gateway.probes] == list(range(1, 248))


async def test_timeouts_are_retried_up_to_the_requested_retries(hass, gateway):
    call = await _setup(hass)
    started = await _start_scan(call, start_id=6, end_id=7, retries=5)
    await _settle(hass)
    assert [p["slave"] for p in gateway.probes] == [6] * 6 + [7]
    results = await call("get_scan_results", {"scan_id": started["scan_id"]})
    assert results["responders"][0]["attempts"] == 1


async def test_cancelled_v2_range_scan_stops_and_appears_in_history(hass, gateway):
    call = await _setup(hass)
    started = await _start_scan(
        call, start_id=1, end_id=247, inter_request_delay_ms=200, large_range_confirmed=True
    )
    requested = await call("cancel_scan", {"scan_id": started["scan_id"]})
    assert requested["cancellation_requested"] is True
    await _settle(hass)

    status = await call("get_scan_status", {"scan_id": started["scan_id"]})
    assert (status["status"], status["gateway_id"]) == ("cancelled", GATEWAY_ID)
    assert status["completed_addresses"] < 247
    assert len(gateway.probes) == status["completed_addresses"]
    results = await call("get_scan_results", {"scan_id": started["scan_id"]})
    assert results["status"] == "cancelled"
    history = await call("get_history")
    assert [scan["scan_id"] for scan in history["scans"]] == [started["scan_id"]]


async def test_mock_gateway_reads_input_register_blocks_across_1_to_247(hass, gateway):
    call = await _setup(hass)
    started = await call(
        "start_scan",
        {
            "start_id": 1,
            "end_id": 247,
            "probe_type": "input_register",
            "register_address": 0x0010,
            "register_count": 3,
            "inter_request_delay_ms": 0,
            "mock_scenario": "partial_timeout",
            "safety_confirmed": True,
            "large_range_confirmed": True,
        },
    )
    await _settle(hass)
    results = await call("get_scan_results", {"scan_id": started["scan_id"]})

    assert (results["status"], results["total_addresses"]) == ("completed", 247)
    rows = {row["address"]: row for row in results["responders"]}
    assert sorted(rows) == [2, 7, 11, 21, 42]
    # A register read never claims a device identity; it returns raw register evidence.
    assert {row["outcome"] for row in rows.values()} == {"responded"}
    assert rows[42]["register_address"] == 0x0010
    assert rows[42]["raw_values"] == [0x2A10, 0x2A11, 0x2A12]
    assert rows[42]["raw_value"] == 0x2A10
    assert "identity" not in rows[7]


@pytest.mark.parametrize(
    ("service", "fields"),
    [
        ("start_scan", {"start_id": 1, "end_id": 3, "safety_confirmed": True}),
        ("test_address", {"address": 1}),
    ],
)
async def test_device_identification_is_not_a_probe_type_on_the_mock_gateway(
    hass, gateway, service, fields
):
    # FC43/14 device identification is out of scope for 0.5.0: the service schema
    # rejects it as an invalid value, before any Device Profile or Gateway check.
    call = await _setup(hass)
    with pytest.raises(vol.Invalid, match="probe type"):
        await call(
            service,
            {**fields, "probe_type": "device_identification", "inter_request_delay_ms": 0},
        )
    history = await call("get_history")
    assert history["scans"] == []


async def test_mock_scan_without_probe_type_reads_holding_registers(hass, gateway):
    call = await _setup(hass)
    started = await call(
        "start_scan",
        {
            "start_id": 1,
            "end_id": 12,
            "inter_request_delay_ms": 0,
            "mock_scenario": "found_default",
            "safety_confirmed": True,
        },
    )
    await _settle(hass)
    results = await call("get_scan_results", {"scan_id": started["scan_id"]})

    assert results["status"] == "completed"
    rows = {row["address"]: row for row in results["responders"]}
    # Responders answer with raw holding-register (FC03) values, never a device identity.
    assert {rows[a]["outcome"] for a in (1, 3, 12)} == {"responded"}
    assert results["outcome_counts"].get("identified", 0) == 0
    assert all(rows[a]["raw_values"] for a in (1, 3, 12))
    assert "FC03" in rows[3]["detail"]


# Story 52: the only outcomes a 0.5.0 Scan reports.
SPEC_OUTCOMES = {"responded", "modbus_exception", "timeout", "possible_collision", "gateway_error"}


@pytest.mark.parametrize(
    "scenario",
    [
        "found_default",
        "all_offline",
        "partial_timeout",
        "modbus_exception",
        "possible_collision",
        "gateway_disconnect",
    ],
)
@pytest.mark.parametrize("probe_type", ["holding_register", "input_register"])
async def test_mock_scenarios_report_only_spec_outcomes(hass, gateway, scenario, probe_type):
    call = await _setup(hass)
    started = await call(
        "start_scan",
        {
            "start_id": 1,
            "end_id": 42,
            "probe_type": probe_type,
            "register_count": 3,
            "inter_request_delay_ms": 0,
            "mock_scenario": scenario,
            "large_range_confirmed": True,
            "safety_confirmed": True,
        },
    )
    await _settle(hass)
    results = await call("get_scan_results", {"scan_id": started["scan_id"]})

    assert set(results["outcome_counts"]) == SPEC_OUTCOMES
    assert {row["outcome"] for row in results["responders"]} <= SPEC_OUTCOMES
    for row in results["responders"]:
        assert "identity" not in row
        if row["outcome"] == "responded":
            assert len(row["raw_values"]) == 3
