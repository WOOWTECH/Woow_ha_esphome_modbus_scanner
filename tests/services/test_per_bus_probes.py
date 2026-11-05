"""Buses of one Gateway probe independently on firmware with per-Bus sensors (ADR 0010).

Current firmware gives every Bus its own result and lease text sensor and names them in its
info entry. HA then keeps one Probe in flight per Bus. On any other v2 firmware, or when a
name does not resolve, the whole Gateway keeps one shared Probe Slot (test_multi_bus).
"""

import asyncio
import json

from aioesphomeapi import TextSensorInfo
from homeassistant.exceptions import HomeAssistantError
import pytest
from test_bridge_v2 import (
    GATEWAY_ID,
    LEASE,
    RESULT_KEY,
    FakeClient,
    FakeV2Gateway,
    _settle,
    _setup,
)

from custom_components.woow_esphome_modbus_scanner.const import DOMAIN
from custom_components.woow_esphome_modbus_scanner.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.woow_esphome_modbus_scanner.modbus_scan.bridge_v2 import (
    provider as v2_provider,
)
from custom_components.woow_esphome_modbus_scanner.probe_slot_modes import (
    STORAGE_KEY,
    ProbeSlotModes,
    async_probe_slot_modes,
)


def _node(**options):
    return FakeV2Gateway(
        buses=("line_a", "line_b"),
        devices={("line_a", 3): [11], ("line_b", 3): [22]},
        pollers={"line_a": [("meter", 1)], "line_b": [("pump", 4)]},
        **options,
    )


@pytest.fixture
def gateway(monkeypatch):
    node = _node(per_bus_sensors=True)
    FakeClient.gateway = node
    FakeClient.instances = []
    monkeypatch.setattr(v2_provider, "APIClient", FakeClient)
    return node


def _listed(gateways):
    return next(g for g in gateways["gateways"] if g["gateway_id"] == GATEWAY_ID)


async def _diagnosed_probe_slots(hass):
    """The Probe Slot mode HA's diagnostics download reports for the one v2 Gateway."""
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    diagnostics = json.loads(json.dumps(await async_get_config_entry_diagnostics(hass, entry)))
    assert GATEWAY_ID not in json.dumps(diagnostics)  # still no Gateway identity
    [gateway] = [g for g in diagnostics["gateways"] if g["provider"] == "esphome"]
    return gateway["probe_slots"]


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


async def _until(predicate, what):
    for _ in range(1000):
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"timed out waiting for {what}")


def _hold_first_probe_of_line_a(gateway):
    """line_a's first Probe gets no result until the test publishes it (or never)."""
    held = []

    def hold(data):
        if data["bus"] == "line_a" and not held:
            held.append(data)
            return None
        return gateway.firmware_result(data)

    gateway.result_override = hold
    return held


async def test_check_reports_per_bus_probe_slots_and_no_concurrent_wait_limit(hass, gateway):
    call = await _setup(hass)
    before = _listed(await call("list_gateways"))
    # Diagnostics report the mode of the last info read, not the assumed one: none yet.
    assert await _diagnosed_probe_slots(hass) is None
    checked = await call("check_gateway", {"gateway_id": GATEWAY_ID})
    after = _listed(await call("list_gateways"))

    # Until a Gateway is checked HA assumes the shared slot, the safe side.
    assert before["limits"]["probes_take_turns"] is True
    assert checked["health"]["probe_slots"] == "per_bus"
    assert after["limits"]["probes_take_turns"] is False
    assert await _diagnosed_probe_slots(hass) == "per_bus"


async def test_after_a_restart_concurrent_scans_are_admitted_under_the_stored_mode(
    hass, hass_storage, gateway
):
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "key": STORAGE_KEY,
        "data": {"modes": {GATEWAY_ID: "per_bus", "esphome:000000000000": "bogus"}},
    }
    modes = await async_probe_slot_modes(hass)
    assert modes.get("esphome:000000000000") is None  # an unreadable entry is dropped
    call = await _setup(hass)
    assert _listed(await call("list_gateways"))["limits"]["probes_take_turns"] is False

    # No check and no info read yet: with the shared slot's limits B would be refused.
    first = await _start(
        call, bus="line_a", start_id=2, end_id=3, inter_request_delay_ms=3000, timeout_ms=2000
    )
    second = await _start(call, bus="line_b", timeout_ms=2000)
    await _settle(hass)
    for scan in (first, second):
        status = await call("get_scan_status", {"scan_id": scan["scan_id"]})
        assert status["status"] == "completed", status["error_info"]


async def test_an_info_read_saves_a_changed_mode(hass, hass_storage, gateway):
    modes = await async_probe_slot_modes(hass)
    call = await _setup(hass)
    await call("check_gateway", {"gateway_id": GATEWAY_ID})
    assert modes.get(GATEWAY_ID) == "per_bus"

    gateway.per_bus_sensors = False  # reflashed to older firmware
    await call("check_gateway", {"gateway_id": GATEWAY_ID})
    assert modes.get(GATEWAY_ID) == "shared_slot_fallback"
    await modes._store._async_handle_write_data()
    assert hass_storage[STORAGE_KEY]["data"] == {"modes": {GATEWAY_ID: "shared_slot_fallback"}}

    # The next HA run reads it back before any check or Scan.
    restarted = ProbeSlotModes(hass)
    await restarted.async_load()
    assert restarted.get(GATEWAY_ID) == "shared_slot_fallback"


async def test_two_buses_each_have_a_probe_in_flight_and_lose_no_result_to_batching(
    hass, gateway, monkeypatch
):
    # The ESPHome API sends only the latest state of an entity per batch. Each Bus's results
    # come on its own sensor, so they never share an entity; the shared mirror drops some.
    monkeypatch.setattr(FakeClient, "batch_delay", 0.02)
    monkeypatch.setattr(v2_provider, "_RESULT_MARGIN_S", 0.5)
    call = await _setup(hass)

    scans = [await _start(call, bus=bus, start_id=1, end_id=6) for bus in ("line_a", "line_b")]
    await _settle(hass)

    for scan in scans:
        status = await call("get_scan_status", {"scan_id": scan["scan_id"]})
        assert status["status"] == "completed", status["error_info"]
        assert (status["lease_status"], status["lease_end_reason"]) == ("ended", "released")
    results = [await call("get_scan_results", {"scan_id": s["scan_id"]}) for s in scans]
    assert [[r["raw_values"] for r in result["responders"]] for result in results] == [
        [[11]],
        [[22]],
    ]
    assert len(gateway.probes) == 12
    assert gateway.max_outstanding == 2  # the Buses probed at the same time


async def test_concurrent_scans_are_not_limited_by_the_shared_slot_wait(hass, gateway):
    call = await _setup(hass)
    held = _hold_first_probe_of_line_a(gateway)
    # With one shared slot this pair is refused: A would wait 3000 ms plus a 2000 ms Probe.
    scan_a = await _start(
        call, bus="line_a", start_id=2, end_id=3, inter_request_delay_ms=3000, timeout_ms=2000
    )
    await _until(lambda: held, "line_a's first probe")

    scan_b = await _start(call, bus="line_b", timeout_ms=2000)
    await _until(lambda: sum(p["bus"] == "line_b" for p in gateway.probes) == 3, "line_b's probes")

    # line_b finished all its Probes while line_a's first one is still on the wire.
    b = await call("get_scan_status", {"scan_id": scan_b["scan_id"]})
    assert b["status"] == "completed", b["error_info"]
    assert (await call("get_scan_status", {"scan_id": scan_a["scan_id"]}))["status"] == "running"
    gateway.publish_result(gateway.firmware_result(held[0]))
    await _settle(hass)
    a = await call("get_scan_status", {"scan_id": scan_a["scan_id"]})
    assert a["status"] == "completed", a["error_info"]


async def test_a_lost_result_on_one_bus_never_holds_the_other_bus_past_its_lease_idle(
    hass, gateway, monkeypatch
):
    monkeypatch.setattr(v2_provider, "_RESULT_MARGIN_S", 1)
    call = await _setup(hass)
    _hold_first_probe_of_line_a(gateway)  # this result is lost: it never arrives
    scan_a = await _start(call, bus="line_a", timeout_ms=100)
    await _until(lambda: gateway.probes, "line_a's first probe")

    scan_b = await _start(call, bus="line_b", start_id=1, end_id=8, inter_request_delay_ms=50)
    await _until(lambda: sum(p["bus"] == "line_b" for p in gateway.probes) == 8, "line_b")

    times = [
        t for p, t in zip(gateway.probes, gateway.probe_times, strict=True) if p["bus"] == "line_b"
    ]
    gaps = [later - earlier for earlier, later in zip(times, times[1:], strict=False)]
    # Far below the Gateway's idle time, and below the lost Probe's own wait (1.1 s).
    assert max(gaps) < 1.0 < LEASE["idle_ms"] / 1000
    b = await call("get_scan_status", {"scan_id": scan_b["scan_id"]})
    assert b["status"] == "completed", b["error_info"]
    assert (b["lease_status"], b["lease_end_reason"]) == ("ended", "released")

    await _settle(hass)
    a = await call("get_scan_status", {"scan_id": scan_a["scan_id"]})
    assert a["status"] == "failed"  # the lost result is the line_a Scan's own failure


async def test_per_bus_mode_ignores_results_on_the_shared_sensor(hass, gateway):
    call = await _setup(hass)
    held = _hold_first_probe_of_line_a(gateway)
    scan = await _start(call, bus="line_a", start_id=3, end_id=3)
    await _until(lambda: held, "line_a's probe")

    # Only the mirror arrives: the Bus's own sensor stays silent.
    gateway.publish(RESULT_KEY, gateway.firmware_result(held[0]))
    await asyncio.sleep(0.05)
    assert (await call("get_scan_status", {"scan_id": scan["scan_id"]}))["status"] == "running"

    gateway.publish(gateway.bus_keys("line_a")[0], gateway.firmware_result(held[0]))
    await _settle(hass)
    result = await call("get_scan_results", {"scan_id": scan["scan_id"]})
    assert [r["raw_values"] for r in result["responders"]] == [[11]]


# ---- Shared-slot fallback: all or nothing for the whole Gateway ----


def _drop_lease_sensor_of_line_b(info):
    del info["buses"][1]["lease_sensor"]


def _rename_result_sensor_of_line_a(info):
    info["buses"][0]["result_sensor"] = "Modbus Scanner v2 Result nowhere"


def _non_string_name(info):
    info["buses"][0]["lease_sensor"] = 7


def _two_buses_name_one_result_sensor(info):
    info["buses"][1]["result_sensor"] = info["buses"][0]["result_sensor"]


def _bus_names_the_shared_lease_sensor(info):
    info["buses"][0]["lease_sensor"] = "Modbus Scanner v2 Lease"


@pytest.mark.parametrize(
    ("hook", "extra"),
    [
        pytest.param(None, None, id="firmware-without-per-bus-sensors"),
        pytest.param(_drop_lease_sensor_of_line_b, None, id="one-bus-misses-a-field"),
        pytest.param(_rename_result_sensor_of_line_a, None, id="name-matches-no-entity"),
        pytest.param(_non_string_name, None, id="name-is-not-a-string"),
        pytest.param(_two_buses_name_one_result_sensor, None, id="two-buses-name-one-sensor"),
        pytest.param(_bus_names_the_shared_lease_sensor, None, id="bus-names-a-shared-sensor"),
        pytest.param(
            None,
            TextSensorInfo(key=999, name="Modbus Scanner v2 Lease line_b"),
            id="name-matches-two-entities",
        ),
    ],
)
async def test_the_whole_gateway_falls_back_to_one_shared_slot(hass, monkeypatch, hook, extra):
    node = _node(per_bus_sensors=hook is not None or extra is not None)
    node.info_hook = hook
    if extra is not None:
        node.extra_entities.append(extra)
    FakeClient.gateway = node
    FakeClient.instances = []
    monkeypatch.setattr(v2_provider, "APIClient", FakeClient)
    monkeypatch.setattr(FakeClient, "batch_delay", 0.02)
    monkeypatch.setattr(v2_provider, "_RESULT_MARGIN_S", 0.5)
    call = await _setup(hass)

    checked = await call("check_gateway", {"gateway_id": GATEWAY_ID})
    assert checked["health"]["probe_slots"] == "shared_slot_fallback"
    assert _listed(await call("list_gateways"))["limits"]["probes_take_turns"] is True
    assert await _diagnosed_probe_slots(hass) == "shared_slot_fallback"

    scans = [await _start(call, bus=bus, start_id=1, end_id=4) for bus in ("line_a", "line_b")]
    await _settle(hass)
    for scan in scans:
        status = await call("get_scan_status", {"scan_id": scan["scan_id"]})
        assert status["status"] == "completed", status["error_info"]
        assert (status["lease_status"], status["lease_end_reason"]) == ("ended", "released")
    assert node.max_outstanding == 1  # the Buses took turns


async def test_shared_sensors_are_still_required_in_per_bus_mode(hass, gateway):
    gateway.entities = [e for e in gateway.entities if e.name != "Modbus Scanner v2 Lease"]
    call = await _setup(hass)
    with pytest.raises(HomeAssistantError, match="not installed"):
        await call("check_gateway", {"gateway_id": GATEWAY_ID})


# ---- The estimate caveat: which Buses run a Scan ----


async def test_list_gateways_reports_the_buses_running_a_scan(hass, gateway):
    call = await _setup(hass)
    held = _hold_first_probe_of_line_a(gateway)
    assert _listed(await call("list_gateways"))["running_buses"] == []
    scan = await _start(call, bus="line_a")
    await _until(lambda: held, "line_a's probe")

    assert _listed(await call("list_gateways"))["running_buses"] == ["line_a"]

    gateway.publish_result(gateway.firmware_result(held[0]))
    await _settle(hass)
    assert (await call("get_scan_status", {"scan_id": scan["scan_id"]}))["status"] == "completed"
    assert _listed(await call("list_gateways"))["running_buses"] == []


async def test_a_scan_started_without_a_bus_lists_its_bus_once_it_connects(
    hass, monkeypatch
):
    # A Gateway never checked: HA does not know its Bus, so the Scan names none and the
    # provider resolves it when the Scan connects.
    node = FakeV2Gateway(buses=("line_a",), per_bus_sensors=True)
    FakeClient.gateway = node
    FakeClient.instances = []
    monkeypatch.setattr(v2_provider, "APIClient", FakeClient)
    call = await _setup(hass)
    held = _hold_first_probe_of_line_a(node)
    scan = await _start(call)
    await _until(lambda: held, "line_a's probe")

    assert _listed(await call("list_gateways"))["running_buses"] == ["line_a"]

    node.publish_result(node.firmware_result(held[0]))
    await _settle(hass)
    assert (await call("get_scan_status", {"scan_id": scan["scan_id"]}))["status"] == "completed"
    assert _listed(await call("list_gateways"))["running_buses"] == []


# ---- The mode Scans are admitted under: the last info read ----


async def test_a_scan_started_while_another_bus_connects_is_not_limited_by_the_shared_slot(
    hass, gateway
):
    call = await _setup(hass)
    await call("check_gateway", {"gateway_id": GATEWAY_ID})
    gate = asyncio.Event()
    gateway.discovery_gate = gate  # line_a's Scan has not read the info yet
    # With one shared slot this pair is refused: A would wait 3000 ms plus a 2000 ms Probe.
    scan_a = await _start(
        call, bus="line_a", start_id=2, end_id=3, inter_request_delay_ms=3000, timeout_ms=2000
    )
    await _until(lambda: gateway.discovering, "line_a's Scan to connect")

    assert _listed(await call("list_gateways"))["limits"]["probes_take_turns"] is False
    scan_b = await _start(call, bus="line_b", timeout_ms=2000)

    gate.set()
    await _settle(hass)
    for scan in (scan_a, scan_b):
        status = await call("get_scan_status", {"scan_id": scan["scan_id"]})
        assert status["status"] == "completed", status["error_info"]


async def test_a_scan_that_ends_before_reading_the_info_keeps_the_per_bus_mode(hass, gateway):
    call = await _setup(hass)
    await call("check_gateway", {"gateway_id": GATEWAY_ID})
    gate = asyncio.Event()
    gateway.discovery_gate = gate
    scan = await _start(call, bus="line_a")
    await _until(lambda: gateway.discovering, "line_a's Scan to connect")

    await call("cancel_scan", {"scan_id": scan["scan_id"]})
    await _settle(hass)
    assert (await call("get_scan_status", {"scan_id": scan["scan_id"]}))["status"] == "cancelled"
    assert _listed(await call("list_gateways"))["limits"]["probes_take_turns"] is False


async def test_a_gateway_reflashed_to_older_firmware_after_a_check_still_takes_the_shared_slot(
    hass, gateway
):
    call = await _setup(hass)
    await call("check_gateway", {"gateway_id": GATEWAY_ID})
    # Reflashed with firmware without per-Bus sensors after the check.
    gateway.per_bus_sensors = False
    gate = asyncio.Event()
    gateway.discovery_gate = gate
    scans = [await _start(call, bus=bus, start_id=1, end_id=4) for bus in ("line_a", "line_b")]
    await _until(lambda: gateway.discovering == 2, "both Scans to connect")

    # Admitted under the per-Bus limits of the earlier check (ADR 0010 accepts this) ...
    gate.set()
    await _settle(hass)
    for scan in scans:
        status = await call("get_scan_status", {"scan_id": scan["scan_id"]})
        assert status["status"] == "completed", status["error_info"]
    # ... but each Scan read the info itself: the Buses took turns and no result was lost.
    assert gateway.max_outstanding == 1
    listed = _listed(await call("list_gateways"))
    assert listed["health"]["probe_slots"] == "shared_slot_fallback"
    assert listed["limits"]["probes_take_turns"] is True
    assert await _diagnosed_probe_slots(hass) == "shared_slot_fallback"
