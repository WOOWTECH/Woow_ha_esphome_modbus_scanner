"""Choosing which Pausable Pollers a Scan pauses, through the HA service seam.

The v2 Gateway is the fake from ``test_bridge_v2`` (built from the shared contract file).
The selection is kept per Gateway and Bus in the integration's config entry.
"""

from homeassistant.core import Context
from homeassistant.exceptions import (
    HomeAssistantError,
    ServiceValidationError,
    Unauthorized,
)
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from test_bridge_v2 import GATEWAY_ID, MAC, FakeClient, FakeV2Gateway, _settle, _setup
import voluptuous as vol

from custom_components.woow_esphome_modbus_scanner import (
    async_setup_entry,
    async_unload_entry,
)
from custom_components.woow_esphome_modbus_scanner.const import DOMAIN
from custom_components.woow_esphome_modbus_scanner.modbus_scan.bridge_v2 import (
    provider as v2_provider,
)
from custom_components.woow_esphome_modbus_scanner.modbus_scan.models import ONE_BUS_PER_GATEWAY
from custom_components.woow_esphome_modbus_scanner.poller_selection import PollerSelectionStore

INTEGRATION = "custom_components.woow_esphome_modbus_scanner"

POLLERS = [("meter", 1), ("inverter", 2), ("chiller", 5)]


def _row(index, paused=True):
    name, address = POLLERS[index]
    return {"index": index, "name": name, "address": address, "paused": paused}


@pytest.fixture
def gateway(monkeypatch):
    node = FakeV2Gateway(pollers={"rs485": list(POLLERS)})
    FakeClient.gateway = node
    FakeClient.instances = []
    monkeypatch.setattr(v2_provider, "APIClient", FakeClient)
    return node


def _listed(gateways):
    return next(g for g in gateways["gateways"] if g["gateway_id"] == GATEWAY_ID)


async def test_checked_gateway_lists_its_pollers_all_paused_by_default(hass, gateway):
    call = await _setup(hass)
    checked = await call("check_gateway", {"gateway_id": GATEWAY_ID})

    assert checked["poller_selection"] == {"rs485": [_row(0), _row(1), _row(2)]}
    assert checked["removed_pollers"] == {"rs485": []}
    listed = _listed(await call("list_gateways"))
    assert listed["poller_selection"] == {"rs485": [_row(0), _row(1), _row(2)]}


async def _scan(hass, call, **fields):
    started = await call(
        "start_scan",
        {
            "provider": "esphome",
            "gateway_id": GATEWAY_ID,
            "start_id": 8,
            "end_id": 9,
            "inter_request_delay_ms": 0,
            "safety_confirmed": True,
            **fields,
        },
    )
    await _settle(hass)
    return await call("get_scan_status", {"scan_id": started["scan_id"]})


async def _choose(call, indices):
    return await call(
        "set_pausable_pollers",
        {"gateway_id": GATEWAY_ID, "bus": "rs485", "pause_pollers": indices},
    )


async def test_saved_selection_pauses_only_the_chosen_pollers(hass, gateway):
    call = await _setup(hass)
    await call("check_gateway", {"gateway_id": GATEWAY_ID})

    saved = await _choose(call, [0, 2])
    assert saved["poller_selection"] == {"rs485": [_row(0), _row(1, False), _row(2)]}
    status = await _scan(hass, call)

    assert [probe["pause_pollers"] for probe in gateway.probes] == ["0,2", "0,2"]
    assert status["paused_pollers"] == [
        {"index": 0, "name": "meter", "address": 1},
        {"index": 2, "name": "chiller", "address": 5},
    ]
    assert status["lease_status"] == "ended"


async def test_selection_survives_a_restart(hass, gateway, monkeypatch):
    async def no_panel(_hass):
        return None

    monkeypatch.setattr(f"{INTEGRATION}._async_register_panel", no_panel)
    monkeypatch.setattr(f"{INTEGRATION}.frontend.async_remove_panel", lambda *_a, **_k: None)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"gateways": [{"host": "192.0.2.10", "mac": MAC, "bridge": "v2"}]},
    )
    entry.add_to_hass(hass)
    assert await async_setup_entry(hass, entry)

    async def call(service, data=None):
        return await hass.services.async_call(
            DOMAIN, service, data or {}, blocking=True, return_response=True
        )

    await call("check_gateway", {"gateway_id": GATEWAY_ID})
    await _choose(call, [1])

    # Restart: the entry is torn down and set up again from what HA stored for it.
    assert await async_unload_entry(hass, entry)
    assert await async_setup_entry(hass, entry)

    # A fresh coordinator has not talked to the Gateway yet: the saved checklist shows.
    listed = _listed(await call("list_gateways"))
    assert listed["poller_selection"] == {"rs485": [_row(0, False), _row(1), _row(2, False)]}
    await _scan(hass, call)
    assert {probe["pause_pollers"] for probe in gateway.probes} == {"1"}


async def _restarted(hass, monkeypatch):
    """Set up from a stored entry, check, save [1], then restart: (call, options)."""

    async def no_panel(_hass):
        return None

    monkeypatch.setattr(f"{INTEGRATION}._async_register_panel", no_panel)
    monkeypatch.setattr(f"{INTEGRATION}.frontend.async_remove_panel", lambda *_a, **_k: None)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"gateways": [{"host": "192.0.2.10", "mac": MAC, "bridge": "v2"}]},
    )
    entry.add_to_hass(hass)
    assert await async_setup_entry(hass, entry)

    async def call(service, data=None):
        return await hass.services.async_call(
            DOMAIN, service, data or {}, blocking=True, return_response=True
        )

    await call("check_gateway", {"gateway_id": GATEWAY_ID})
    await _choose(call, [1])
    assert await async_unload_entry(hass, entry)
    assert await async_setup_entry(hass, entry)
    return call


async def test_saving_after_a_restart_uses_the_saved_checklist(hass, gateway, monkeypatch):
    # No check since the restart: the panel shows the saved checklist, and saving from it
    # works against that checklist, the Bus given or omitted.
    call = await _restarted(hass, monkeypatch)

    saved = await _choose(call, [0, 2])
    assert saved["bus"] == "rs485"
    assert saved["poller_selection"] == {"rs485": [_row(0), _row(1, False), _row(2)]}
    omitted = await call(
        "set_pausable_pollers", {"gateway_id": GATEWAY_ID, "pause_pollers": [2]}
    )
    assert omitted["poller_selection"] == {"rs485": [_row(0, False), _row(1, False), _row(2)]}
    assert _options(hass) == {GATEWAY_ID: omitted["poller_selection"]}
    with pytest.raises(ServiceValidationError, match="no Pausable Poller with index \\[3\\]"):
        await _choose(call, [3])

    await _scan(hass, call)
    assert {probe["pause_pollers"] for probe in gateway.probes} == {"2"}


async def test_saving_another_bus_after_a_restart_is_refused(hass, gateway, monkeypatch):
    call = await _restarted(hass, monkeypatch)
    before = _options(hass)
    with pytest.raises(ServiceValidationError, match="check the Gateway first"):
        await call(
            "set_pausable_pollers",
            {"gateway_id": GATEWAY_ID, "bus": "rs485_b", "pause_pollers": [0]},
        )
    assert _options(hass) == before


async def _refused_for_two_buses(hass, gateway):
    """Check, save [0], then reflash with a second Bus and check again: (call, options)."""
    call = await _setup(hass)
    await call("check_gateway", {"gateway_id": GATEWAY_ID})
    await _choose(call, [0])
    kept = _options(hass)
    # Reflashed with a second modbus_scanner entry: HA forgets the Bus.
    gateway.buses = ["rs485", "rs485_b"]
    with pytest.raises(HomeAssistantError, match="exactly one Bus"):
        await call("check_gateway", {"gateway_id": GATEWAY_ID})
    return call, kept


async def _assert_refused(hass, call, kept):
    listed = _listed(await call("list_gateways"))
    assert (listed["poller_selection"], listed["removed_pollers"]) == ({}, {})
    assert listed["health"]["multiple_buses"] is True
    for bus in ({"bus": "rs485"}, {}):
        with pytest.raises(ServiceValidationError) as refused:
            await call(
                "set_pausable_pollers", {"gateway_id": GATEWAY_ID, "pause_pollers": [1], **bus}
            )
        # The one-Bus rule, not advice to check a Gateway that was just checked.
        assert str(refused.value) == (
            f"Gateway {GATEWAY_ID} reports more than one Bus, but {ONE_BUS_PER_GATEWAY}"
        )
    assert _options(hass) == kept


async def test_a_gateway_refused_for_two_buses_offers_no_checklist_until_it_passes(
    hass, gateway
):
    call, kept = await _refused_for_two_buses(hass, gateway)
    await _assert_refused(hass, call, kept)

    # Reflashed back to one Bus: the saved checklist is offered again.
    gateway.buses = ["rs485"]
    checked = await call("check_gateway", {"gateway_id": GATEWAY_ID})
    assert checked["health"]["multiple_buses"] is False
    assert checked["poller_selection"] == {"rs485": [_row(0), _row(1, False), _row(2, False)]}
    saved = await _choose(call, [1])
    assert saved["poller_selection"] == {"rs485": [_row(0, False), _row(1), _row(2, False)]}


async def _offline(_self, **_kwargs):
    raise ConnectionRefusedError("node offline")


async def test_a_later_connect_failure_keeps_the_two_bus_refusal(hass, gateway, monkeypatch):
    call, kept = await _refused_for_two_buses(hass, gateway)
    # The node goes offline: a failed check proves nothing about its Buses.
    online = FakeClient.connect
    monkeypatch.setattr(FakeClient, "connect", _offline)
    with pytest.raises(HomeAssistantError):
        await call("check_gateway", {"gateway_id": GATEWAY_ID})
    listed = _listed(await call("list_gateways"))
    assert listed["health"]["error_info"]["code"] == "API_TRANSPORT_ERROR"
    await _assert_refused(hass, call, kept)

    # A Scan that cannot connect does not lift it either.
    status = await _scan(hass, call)
    assert status["error_info"]["code"] == "API_TRANSPORT_ERROR"
    await _assert_refused(hass, call, kept)

    # Back online with one Bus: a passing check lifts the refusal.
    monkeypatch.setattr(FakeClient, "connect", online)
    gateway.buses = ["rs485"]
    checked = await call("check_gateway", {"gateway_id": GATEWAY_ID})
    assert checked["poller_selection"] == {"rs485": [_row(0), _row(1, False), _row(2, False)]}


async def test_check_drops_saved_pollers_the_firmware_no_longer_has(hass, gateway):
    call = await _setup(hass)
    await call("check_gateway", {"gateway_id": GATEWAY_ID})
    await _choose(call, [0])
    # Recompiled firmware: the chiller is gone and a pump is new.
    gateway.pollers = {"rs485": [("meter", 1), ("inverter", 2), ("pump", 9)]}

    checked = await call("check_gateway", {"gateway_id": GATEWAY_ID})

    assert checked["removed_pollers"] == {"rs485": [{"index": 2, "name": "chiller", "address": 5}]}
    assert checked["poller_selection"] == {
        "rs485": [
            _row(0),
            _row(1, False),
            {"index": 2, "name": "pump", "address": 9, "paused": True},
        ]
    }
    again = await call("check_gateway", {"gateway_id": GATEWAY_ID})
    assert again["removed_pollers"] == {"rs485": []}
    assert again["poller_selection"] == checked["poller_selection"]


async def test_scan_revalidates_the_saved_selection_and_reports_removals(hass, gateway):
    call = await _setup(hass)
    await call("check_gateway", {"gateway_id": GATEWAY_ID})
    await _choose(call, [1, 2])
    gateway.pollers = {"rs485": [("meter", 1), ("inverter", 2)]}

    status = await _scan(hass, call)

    assert {probe["pause_pollers"] for probe in gateway.probes} == {"1"}
    assert status["removed_pollers"] == [{"index": 2, "name": "chiller", "address": 5}]
    listed = _listed(await call("list_gateways"))
    assert listed["poller_selection"] == {"rs485": [_row(0, False), _row(1)]}
    assert listed["removed_pollers"] == {"rs485": []}


async def test_a_failing_selection_store_never_changes_a_finished_scan(
    hass, gateway, monkeypatch
):
    call = await _setup(hass)
    await call("check_gateway", {"gateway_id": GATEWAY_ID})
    await _choose(call, [1, 2])
    gateway.pollers = {"rs485": [("meter", 1), ("inverter", 2)]}

    def broken_save(*_args, **_kwargs):
        raise RuntimeError("config entry options could not be written")

    # The end-of-Scan prune of the removed chiller is the only write left.
    monkeypatch.setattr(PollerSelectionStore, "save", broken_save)
    status = await _scan(hass, call)

    assert (status["status"], status["error"]) == ("completed", None)
    assert status["removed_pollers"] == [{"index": 2, "name": "chiller", "address": 5}]
    results = await call("get_scan_results", {"scan_id": status["scan_id"]})
    assert (results["status"], results["completed_addresses"]) == ("completed", 2)
    history = await call("get_history")
    assert [(scan["scan_id"], scan["status"]) for scan in history["scans"]] == [
        (status["scan_id"], "completed")
    ]


async def test_unchecking_every_poller_scans_without_a_lease(hass, gateway):
    call = await _setup(hass)
    await call("check_gateway", {"gateway_id": GATEWAY_ID})
    await _choose(call, [])

    status = await _scan(hass, call)

    assert status["status"] == "completed"
    assert [probe["pause_pollers"] for probe in gateway.probes] == ["", ""]
    assert gateway.releases == []
    assert (status["lease_status"], status["paused_pollers"]) == ("none", [])


async def test_scan_accepts_an_explicit_selection_over_the_saved_one(hass, gateway):
    call = await _setup(hass)
    await call("check_gateway", {"gateway_id": GATEWAY_ID})
    await _choose(call, [0, 1, 2])

    status = await _scan(hass, call, pause_pollers=[1, 7])

    assert {probe["pause_pollers"] for probe in gateway.probes} == {"1"}
    assert status["paused_pollers"] == [{"index": 1, "name": "inverter", "address": 2}]
    # An index the firmware does not have is never sent; it is reported instead.
    assert status["removed_pollers"] == [{"index": 7, "name": None, "address": None}]
    # The explicit choice is for this Scan only.
    listed = _listed(await call("list_gateways"))
    assert listed["poller_selection"] == {"rs485": [_row(0), _row(1), _row(2)]}


async def test_explicit_empty_selection_pauses_nothing(hass, gateway):
    call = await _setup(hass)
    status = await _scan(hass, call, pause_pollers=[])
    assert {probe["pause_pollers"] for probe in gateway.probes} == {""}
    assert status["lease_status"] == "none"


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"bus": "rs485", "pause_pollers": [3]}, "no Pausable Poller with index \\[3\\]"),
        # A Gateway serves exactly one Bus (ADR 0011): a selection never names another.
        ({"bus": "other", "pause_pollers": [0]}, "has no Bus other; its Bus is rs485"),
        (
            {"gateway_id": "mock:rs485-gateway", "bus": "rs485", "pause_pollers": []},
            "needs an enrolled Gateway with Scan Lease support",
        ),
    ],
)
async def test_saving_a_selection_is_validated_against_the_known_table(
    hass, gateway, data, message
):
    call = await _setup(hass)
    await call("check_gateway", {"gateway_id": GATEWAY_ID})
    with pytest.raises(ServiceValidationError, match=message):
        await call("set_pausable_pollers", {"gateway_id": GATEWAY_ID, **data})


async def test_saving_before_the_poller_table_is_known_is_refused(hass, gateway):
    call = await _setup(hass)
    with pytest.raises(ServiceValidationError, match="check the Gateway first"):
        await _choose(call, [0])
    assert _listed(await call("list_gateways"))["poller_selection"] == {}


async def test_inactive_user_cannot_change_the_selection(hass, gateway):
    call = await _setup(hass)
    await call("check_gateway", {"gateway_id": GATEWAY_ID})
    user = await hass.auth.async_create_user("deactivated operator")
    await hass.auth.async_update_user(user, is_active=False)
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN,
            "set_pausable_pollers",
            {"gateway_id": GATEWAY_ID, "bus": "rs485", "pause_pollers": []},
            blocking=True,
            return_response=True,
            context=Context(user_id=user.id),
        )
    listed = _listed(await call("list_gateways"))
    assert listed["poller_selection"] == {"rs485": [_row(0), _row(1), _row(2)]}


async def test_explicit_selection_is_refused_for_gateways_that_cannot_choose(hass, gateway):
    call = await _setup(hass)
    with pytest.raises(
        ServiceValidationError, match="pause_pollers needs a Gateway with Scan Lease support"
    ):
        await call("test_address", {"provider": "mock", "address": 1, "pause_pollers": [0]})


def _options(hass):
    [entry] = hass.config_entries.async_entries(DOMAIN)
    return entry.options.get("pausable_poller_selection", {})


def _seed(hass, checklists):
    [entry] = hass.config_entries.async_entries(DOMAIN)
    hass.config_entries.async_update_entry(
        entry, options={"pausable_poller_selection": {GATEWAY_ID: checklists}}
    )


# Checklists a 0.5.0.dev2 multi-Bus Gateway left behind: one with rows, one empty.
STALE = {"rs485_b": [{"index": 0, "name": "meter", "address": 1, "paused": False}], "x": []}


async def test_check_drops_saved_checklists_of_buses_the_gateway_does_not_report(hass, gateway):
    call = await _setup(hass)
    _seed(hass, {"rs485": [_row(0, False), _row(1), _row(2)], **STALE})

    checked = await call("check_gateway", {"gateway_id": GATEWAY_ID})

    assert checked["poller_selection"] == {"rs485": [_row(0, False), _row(1), _row(2)]}
    assert _options(hass) == {GATEWAY_ID: {"rs485": [_row(0, False), _row(1), _row(2)]}}


async def test_check_drops_an_empty_stale_checklist_too(hass, gateway):
    call = await _setup(hass)
    _seed(hass, {"rs485": [_row(0), _row(1), _row(2)], "x": []})

    await call("check_gateway", {"gateway_id": GATEWAY_ID})

    assert _options(hass) == {GATEWAY_ID: {"rs485": [_row(0), _row(1), _row(2)]}}


async def test_saving_drops_saved_checklists_of_buses_the_gateway_does_not_report(
    hass, gateway
):
    call = await _setup(hass)
    await call("check_gateway", {"gateway_id": GATEWAY_ID})
    _seed(hass, STALE)

    saved = await _choose(call, [1])

    assert saved["poller_selection"] == {"rs485": [_row(0, False), _row(1), _row(2, False)]}
    assert _options(hass) == {GATEWAY_ID: {"rs485": [_row(0, False), _row(1), _row(2, False)]}}


async def test_saving_a_stale_bus_before_the_table_is_known_is_refused(hass, gateway):
    call = await _setup(hass)
    _seed(hass, STALE)
    with pytest.raises(ServiceValidationError, match="check the Gateway first"):
        await call(
            "set_pausable_pollers",
            {"gateway_id": GATEWAY_ID, "bus": "rs485_b", "pause_pollers": [0]},
        )
    assert _options(hass) == {GATEWAY_ID: STALE}


@pytest.mark.parametrize("bus", ["", "x y", "a" * 33])
async def test_a_malformed_bus_name_is_a_schema_error(hass, gateway, bus):
    call = await _setup(hass)
    await call("check_gateway", {"gateway_id": GATEWAY_ID})
    with pytest.raises(vol.Invalid):
        await call(
            "set_pausable_pollers", {"gateway_id": GATEWAY_ID, "bus": bus, "pause_pollers": []}
        )
