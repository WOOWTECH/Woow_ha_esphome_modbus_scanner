"""One Gateway with several Buses, through the HA service seam.

The v2 Gateway is the fake from ``test_bridge_v2`` (built from the shared contract file).
A Scan targets Gateway + Bus, and only one Scan at a time may run on each Bus.
"""

import asyncio

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
import pytest
from test_bridge_v2 import GATEWAY_ID, RESULT_KEY, FakeClient, FakeV2Gateway, _settle, _setup
import voluptuous as vol

from custom_components.woow_esphome_modbus_scanner.const import DOMAIN
from custom_components.woow_esphome_modbus_scanner.modbus_scan.bridge_v2 import (
    provider as v2_provider,
)
from custom_components.woow_esphome_modbus_scanner.services import async_register_services

SERIAL_A = {"baud_rate": 9600, "parity": "NONE", "stop_bits": 1}
SERIAL_B = {"baud_rate": 19200, "parity": "EVEN", "stop_bits": 2}


@pytest.fixture
def gateway(monkeypatch):
    node = FakeV2Gateway(
        buses=("line_a", "line_b"),
        devices={("line_a", 3): [11], ("line_b", 3): [22]},
        pollers={"line_a": [("meter", 1)], "line_b": [("pump", 4), ("fan", 5)]},
        serial={"line_a": SERIAL_A, "line_b": SERIAL_B},
    )
    FakeClient.gateway = node
    FakeClient.instances = []
    monkeypatch.setattr(v2_provider, "APIClient", FakeClient)
    return node


def _listed(gateways):
    return next(g for g in gateways["gateways"] if g["gateway_id"] == GATEWAY_ID)


async def _start(call, **fields):
    return await call(
        "start_scan",
        {
            "provider": "esphome",
            "gateway_id": GATEWAY_ID,
            "start_id": 2,
            "end_id": 4,
            "inter_request_delay_ms": 0,
            "safety_confirmed": True,
            **fields,
        },
    )


async def test_gateway_lists_each_bus_with_its_serial_parameters(hass, gateway):
    call = await _setup(hass)
    assert _listed(await call("list_gateways"))["buses"] == []  # unknown until checked
    checked = await call("check_gateway", {"gateway_id": GATEWAY_ID})

    listed = _listed(await call("list_gateways"))

    expected = [{"bus": "line_a", "serial": SERIAL_A}, {"bus": "line_b", "serial": SERIAL_B}]
    assert listed["buses"] == checked["buses"] == expected
    assert gateway.probes == []  # learning the Buses sends no Modbus frame


async def test_a_bus_without_reported_serial_parameters_is_still_listed(hass, gateway):
    gateway.serial = {"line_a": SERIAL_A}
    call = await _setup(hass)
    checked = await call("check_gateway", {"gateway_id": GATEWAY_ID})
    assert checked["buses"][1] == {"bus": "line_b", "serial": None}


@pytest.mark.parametrize(
    "serial",
    [
        {"baud_rate": 0, "parity": "NONE", "stop_bits": 1},
        {"baud_rate": 9600, "parity": "MARK", "stop_bits": 1},
        {"baud_rate": 9600, "parity": "NONE", "stop_bits": 3},
        {"baud_rate": "9600", "parity": "NONE", "stop_bits": 1},
        {"parity": "NONE", "stop_bits": 1},
    ],
)
async def test_malformed_serial_parameters_are_incompatible_bridge_info(hass, gateway, serial):
    gateway.serial = {"line_a": serial}
    call = await _setup(hass)
    with pytest.raises(HomeAssistantError, match="incompatible bridge info"):
        await call("check_gateway", {"gateway_id": GATEWAY_ID})


async def test_duplicate_bus_names_are_incompatible_bridge_info(hass, gateway):
    gateway.buses = ["line_a", "line_a"]
    call = await _setup(hass)
    with pytest.raises(HomeAssistantError, match="incompatible bridge info"):
        await call("check_gateway", {"gateway_id": GATEWAY_ID})


async def test_scan_targets_the_chosen_bus(hass, gateway):
    call = await _setup(hass)

    started = await _start(call, bus="line_b", pause_normal_polling=False)
    await _settle(hass)
    results = await call("get_scan_results", {"scan_id": started["scan_id"]})

    assert started["bus"] == "line_b"
    assert results["status"] == "completed"
    assert results["bus"] == "line_b"
    assert {probe["bus"] for probe in gateway.probes} == {"line_b"}
    assert [r["raw_values"] for r in results["responders"]] == [[22]]


async def test_bus_is_required_once_the_gateway_is_known_to_have_several(hass, gateway):
    call = await _setup(hass)
    await call("check_gateway", {"gateway_id": GATEWAY_ID})
    connections = len(FakeClient.instances)

    with pytest.raises(ServiceValidationError, match=r"2 Buses \(line_a, line_b\)"):
        await _start(call)
    with pytest.raises(ServiceValidationError, match="has no Bus line_c"):
        await _start(call, bus="line_c")

    assert len(FakeClient.instances) == connections  # rejected before connecting
    assert gateway.probes == []


async def test_unknown_bus_on_an_unchecked_gateway_fails_without_probing(hass, gateway):
    call = await _setup(hass)

    started = await _start(call, bus="line_c")
    await _settle(hass)
    status = await call("get_scan_status", {"scan_id": started["scan_id"]})

    assert status["status"] == "failed"
    assert status["error_info"]["code"] == "UNKNOWN_BUS"
    assert gateway.probes == []


@pytest.mark.parametrize("bus", ["", "x" * 33, "line a", "line\n"])
async def test_malformed_bus_names_are_rejected(hass, gateway, bus):
    call = await _setup(hass)
    with pytest.raises(vol.Invalid):
        await _start(call, bus=bus)


async def _first_probe_on(gateway, bus):
    for _ in range(500):
        if any(probe["bus"] == bus for probe in gateway.probes):
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"no probe reached {bus}")


async def test_two_buses_of_one_gateway_scan_at_the_same_time(hass, gateway):
    call = await _setup(hass)
    held = []

    def hold_line_a(data):
        if data["bus"] == "line_a" and not held:
            held.append(data)  # line_a's first probe stays on the wire
            return None
        return gateway.firmware_result(data)

    gateway.result_override = hold_line_a
    scan_a = await _start(call, bus="line_a")
    await _first_probe_on(gateway, "line_a")

    scan_b = await _start(call, bus="line_b")
    with pytest.raises(HomeAssistantError, match="Bus line_a .* is busy"):
        await _start(call, bus="line_a")
    with pytest.raises(HomeAssistantError, match="busy"):
        await call("check_gateway", {"gateway_id": GATEWAY_ID})

    gateway.publish(RESULT_KEY, gateway.firmware_result(held[0]))
    await _settle(hass)
    a = await call("get_scan_results", {"scan_id": scan_a["scan_id"]})
    b = await call("get_scan_results", {"scan_id": scan_b["scan_id"]})

    assert (a["status"], a["bus"]) == ("completed", "line_a")
    assert (b["status"], b["bus"]) == ("completed", "line_b")
    assert [r["raw_values"] for r in a["responders"]] == [[11]]
    assert [r["raw_values"] for r in b["responders"]] == [[22]]
    assert sorted((p["bus"], p["slave"]) for p in gateway.probes) == [
        ("line_a", 2),
        ("line_a", 3),
        ("line_a", 4),
        ("line_b", 2),
        ("line_b", 3),
        ("line_b", 4),
    ]
    # Each Bus held and released its own Scan Lease over its own pollers.
    assert {(r["bus"], r["scan_id"]) for r in gateway.releases} == {
        ("line_a", gateway.probes[0]["scan_id"]),
        ("line_b", next(p["scan_id"] for p in gateway.probes if p["bus"] == "line_b")),
    }
    assert a["paused_pollers"] == [{"index": 0, "name": "meter", "address": 1}]
    assert [p["name"] for p in b["paused_pollers"]] == ["pump", "fan"]
    assert gateway.paused == set()


async def test_pause_choices_apply_to_the_scanned_bus(hass, gateway):
    call = await _setup(hass)
    await call("check_gateway", {"gateway_id": GATEWAY_ID})
    await call(
        "set_pausable_pollers", {"gateway_id": GATEWAY_ID, "bus": "line_b", "pause_pollers": [1]}
    )

    saved = await _start(call, bus="line_b")
    await _settle(hass)
    explicit = await _start(call, bus="line_b", pause_pollers=[0])
    await _settle(hass)
    other = await _start(call, bus="line_a")
    await _settle(hass)

    by_scan = {}
    for probe in gateway.probes:
        by_scan.setdefault(probe["scan_id"], set()).add((probe["bus"], probe["pause_pollers"]))
    assert list(by_scan.values()) == [{("line_b", "1")}, {("line_b", "0")}, {("line_a", "0")}]
    status = await call("get_scan_status", {"scan_id": saved["scan_id"]})
    assert status["paused_pollers"] == [{"index": 1, "name": "fan", "address": 5}]
    status = await call("get_scan_status", {"scan_id": explicit["scan_id"]})
    assert status["paused_pollers"] == [{"index": 0, "name": "pump", "address": 4}]
    status = await call("get_scan_status", {"scan_id": other["scan_id"]})
    assert status["paused_pollers"] == [{"index": 0, "name": "meter", "address": 1}]


async def test_explicit_poller_index_unknown_on_the_scanned_bus_is_not_paused(hass, gateway):
    call = await _setup(hass)
    started = await _start(call, bus="line_a", pause_pollers=[0, 1])
    await _settle(hass)
    status = await call("get_scan_status", {"scan_id": started["scan_id"]})

    assert {probe["pause_pollers"] for probe in gateway.probes} == {"0"}
    assert status["removed_pollers"] == [{"index": 1, "name": None, "address": None}]


async def test_concurrent_buses_lose_no_result_to_esphome_state_batching(
    hass, gateway, monkeypatch
):
    # The node has one result sensor for all Buses, and the ESPHome API sends only the
    # latest state of an entity per batch: results of two Buses must not share a batch.
    monkeypatch.setattr(FakeClient, "batch_delay", 0.02)
    monkeypatch.setattr(v2_provider, "_RESULT_MARGIN_S", 0.5)
    call = await _setup(hass)

    scans = [await _start(call, bus=bus, start_id=1, end_id=6) for bus in ("line_a", "line_b")]
    await _settle(hass)

    for scan in scans:
        status = await call("get_scan_status", {"scan_id": scan["scan_id"]})
        assert status["status"] == "completed", status["error_info"]
        assert (status["lease_status"], status["lease_end_reason"]) == ("ended", "released")
    assert len(gateway.probes) == 12


# ---- Concurrent Scans and the Scan Lease idle limit ----
# Probes of a Gateway's Buses take turns, so between two Probes a Scan waits its own
# inter-request delay plus one Probe of every other Scan. The contract caps that wait at
# lease.inter_request_delay_max_ms (3000 ms of the 5000 ms idle time), so a Scan whose
# waits would pass it is refused before any Probe.


def _hold_first_probe_of_line_a(gateway):
    """Keep line_a's first Probe on the wire; every other Scan waits for the Probe Slot."""
    held = []

    def hold(data):
        if data["bus"] == "line_a" and not held:
            held.append(data)
            return None
        return gateway.firmware_result(data)

    gateway.result_override = hold
    return held


async def _release_held(hass, gateway, held):
    gateway.publish(RESULT_KEY, gateway.firmware_result(held[0]))
    await _settle(hass)


async def test_a_scan_whose_waits_would_end_a_running_scans_lease_is_refused(hass, gateway):
    call = await _setup(hass)
    held = _hold_first_probe_of_line_a(gateway)
    scan_a = await _start(call, bus="line_a", inter_request_delay_ms=3000, timeout_ms=2000)
    await _first_probe_on(gateway, "line_a")

    # Scan A would wait its 3000 ms delay plus a 2000 ms line_b Probe between Probes.
    with pytest.raises(ServiceValidationError, match="Scan Lease idle limit"):
        await _start(call, bus="line_b", timeout_ms=2000)

    await _release_held(hass, gateway, held)
    a = await call("get_scan_results", {"scan_id": scan_a["scan_id"]})
    assert a["status"] == "completed"
    assert (a["lease_status"], a["lease_end_reason"]) == ("ended", "released")
    assert {probe["bus"] for probe in gateway.probes} == {"line_a"}


async def test_a_scan_whose_own_waits_would_end_its_lease_is_refused(hass, gateway):
    call = await _setup(hass)
    held = _hold_first_probe_of_line_a(gateway)
    scan_a = await _start(call, bus="line_a", inter_request_delay_ms=100)
    await _first_probe_on(gateway, "line_a")

    # The new Scan would wait 2500 ms plus a 1000 ms line_a Probe between its Probes.
    with pytest.raises(ServiceValidationError, match="Scan Lease idle limit"):
        await _start(call, bus="line_b", inter_request_delay_ms=2500)

    await _release_held(hass, gateway, held)
    a = await call("get_scan_status", {"scan_id": scan_a["scan_id"]})
    assert a["status"] == "completed"
    assert {probe["bus"] for probe in gateway.probes} == {"line_a"}


async def test_test_address_is_refused_like_start_scan(hass, gateway):
    call = await _setup(hass)
    held = _hold_first_probe_of_line_a(gateway)
    await _start(call, bus="line_a", inter_request_delay_ms=3000, timeout_ms=2000)
    await _first_probe_on(gateway, "line_a")

    with pytest.raises(ServiceValidationError, match="Scan Lease idle limit"):
        await call(
            "test_address",
            {"provider": "esphome", "gateway_id": GATEWAY_ID, "bus": "line_b", "address": 3},
        )

    await _release_held(hass, gateway, held)
    assert {probe["bus"] for probe in gateway.probes} == {"line_a"}


async def test_scans_without_a_scan_lease_have_no_idle_limit_to_keep(hass, gateway):
    call = await _setup(hass)
    held = _hold_first_probe_of_line_a(gateway)
    fields = {"inter_request_delay_ms": 3000, "timeout_ms": 2000, "pause_normal_polling": False}
    scan_a = await _start(call, bus="line_a", **fields)
    await _first_probe_on(gateway, "line_a")

    scan_b = await _start(call, bus="line_b", **fields)

    assert scan_b["status"] == "running"
    await _release_held(hass, gateway, held)
    for scan in (scan_a, scan_b):
        status = await call("get_scan_status", {"scan_id": scan["scan_id"]})
        assert status["status"] == "completed"


async def test_three_buses_scan_together_at_the_defaults_and_a_fourth_is_refused(hass, gateway):
    gateway.buses = ["line_a", "line_b", "line_c", "line_d"]
    call = await _setup(hass)
    held = _hold_first_probe_of_line_a(gateway)

    # Gateway defaults: 100 ms delay and 1000 ms timeout. Three Scans wait 100 ms plus two
    # Probes of the others; a fourth would add a third Probe and pass 3000 ms.
    scans = [
        await call(
            "start_scan",
            {
                "provider": "esphome",
                "gateway_id": GATEWAY_ID,
                "bus": bus,
                "start_id": 2,
                "end_id": 3,
                "safety_confirmed": True,
            },
        )
        for bus in ("line_a", "line_b", "line_c")
    ]
    await _first_probe_on(gateway, "line_a")
    with pytest.raises(ServiceValidationError, match="Scan Lease idle limit"):
        await _start(call, bus="line_d", start_id=2, end_id=3, inter_request_delay_ms=100)

    await _release_held(hass, gateway, held)
    for scan in scans:
        status = await call("get_scan_status", {"scan_id": scan["scan_id"]})
        assert status["status"] == "completed", status["error_info"]
    assert "line_d" not in {probe["bus"] for probe in gateway.probes}


# ---- The mock provider: one single-Bus and one multi-Bus simulated Gateway ----

MOCK_MULTI = "mock:multi-bus-gateway"


async def _mock_setup(hass):
    async_register_services(hass)

    async def call(service, data=None):
        return await hass.services.async_call(
            DOMAIN, service, data or {}, blocking=True, return_response=True
        )

    return call


async def test_mock_gateways_report_their_buses(hass):
    call = await _mock_setup(hass)
    gateways = {g["gateway_id"]: g for g in (await call("list_gateways"))["gateways"]}

    assert [row["bus"] for row in gateways["mock:rs485-gateway"]["buses"]] == ["rs485"]
    assert gateways[MOCK_MULTI]["buses"] == [
        {"bus": "rs485_a", "serial": {"baud_rate": 9600, "parity": "NONE", "stop_bits": 1}},
        {"bus": "rs485_b", "serial": {"baud_rate": 19200, "parity": "EVEN", "stop_bits": 1}},
    ]
    assert gateways[MOCK_MULTI]["simulated"] is True


async def test_mock_gateways_publish_bus_selection_but_no_scan_lease_support(hass):
    call = await _mock_setup(hass)
    gateways = {g["gateway_id"]: g for g in (await call("list_gateways"))["gateways"]}

    for gateway_id in ("mock:rs485-gateway", MOCK_MULTI):
        assert gateways[gateway_id]["supports_bus_selection"] is True
        assert gateways[gateway_id]["supports_scan_lease"] is False


async def test_mock_single_bus_gateway_needs_no_bus(hass):
    call = await _mock_setup(hass)
    started = await call("start_scan", {"start_id": 1, "end_id": 3, "safety_confirmed": True})
    assert started["bus"] == "rs485"


async def test_mock_multi_bus_gateway_scans_buses_side_by_side(hass):
    call = await _mock_setup(hass)
    fields = {
        "gateway_id": MOCK_MULTI,
        "start_id": 1,
        "end_id": 12,
        "inter_request_delay_ms": 50,
        "safety_confirmed": True,
    }
    with pytest.raises(ServiceValidationError, match="choose one with bus"):
        await call("start_scan", fields)

    a = await call("start_scan", {**fields, "bus": "rs485_a"})
    b = await call("start_scan", {**fields, "bus": "rs485_b"})
    with pytest.raises(HomeAssistantError, match="Bus rs485_b .* is busy"):
        await call("start_scan", {**fields, "bus": "rs485_b"})
    assert (a["status"], b["status"]) == ("running", "running")

    await _settle(hass)
    for scan, bus in ((a, "rs485_a"), (b, "rs485_b")):
        results = await call("get_scan_results", {"scan_id": scan["scan_id"]})
        assert (results["status"], results["bus"]) == ("completed", bus)
        assert results["completed_addresses"] == 12
