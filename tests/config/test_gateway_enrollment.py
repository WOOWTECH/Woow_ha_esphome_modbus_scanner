"""Gateway enrollment through the config flow, from HA's ESPHome devices or manually.

The node behind the selected device is the contract-built fake v2 Gateway at the
aioesphomeapi client boundary, so enrollment verifies a real-shaped MAC and v2 signature.
"""

from types import SimpleNamespace
from unittest.mock import patch

from homeassistant import config_entries, data_entry_flow
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.woow_esphome_modbus_scanner.const import DOMAIN
from custom_components.woow_esphome_modbus_scanner.modbus_scan.bridge_v2 import (
    provider as v2_provider,
)
from custom_components.woow_esphome_modbus_scanner.modbus_scan.legacy_v1 import (
    provider as legacy_provider,
)
from tests.services.test_bridge_v2 import FakeClient, FakeV2Gateway
from tests.services.test_legacy_v1_adapter import FakeLegacyClient

MAC = "AA:BB:CC:DD:EE:01"
KEY = "A" * 43 + "="
OTHER_KEY = "B" * 43 + "="


class RecordingClient(FakeClient):
    """Remembers how each API connection was opened."""

    opened: list = []

    def __init__(self, host, port, password, **kwargs):
        super().__init__(host, port, password, **kwargs)
        RecordingClient.opened.append({"host": host, "port": port, **kwargs})

    async def connect(self, **kwargs):
        if hook := getattr(self.gateway, "connect", None):  # e.g. an unreachable node
            await hook(**kwargs)
        await super().connect(**kwargs)


@pytest.fixture(autouse=True)
def dependency_setup_is_outside_flow_unit_scope(hass):
    hass.config.components.update({"frontend", "panel_custom", "esphome"})


@pytest.fixture(autouse=True)
def no_entry_setup():
    with patch(
        "custom_components.woow_esphome_modbus_scanner.async_setup_entry", return_value=True
    ):
        yield


@pytest.fixture
def node(monkeypatch):
    gateway = FakeV2Gateway(mac=MAC)
    FakeClient.gateway = gateway
    FakeClient.instances = []
    RecordingClient.opened = []
    monkeypatch.setattr(v2_provider, "APIClient", RecordingClient)
    return gateway


@pytest.fixture
def legacy_nodes(monkeypatch):
    """Legacy Gateways on bridge v1 firmware; maps each host to the MAC it reports."""
    macs: dict[str, str] = {}

    class Client(FakeLegacyClient):
        def __init__(self, host, port, password, **kwargs):
            super().__init__(host, port, password, **kwargs)
            self.host = host

        async def device_info(self):
            return SimpleNamespace(mac_address=macs.get(self.host, "00:00:00:00:00:00"))

    monkeypatch.setattr(legacy_provider, "APIClient", Client)
    return macs


def esphome_device(hass, *, mac=MAC, title="pump-room", host="192.0.2.10", key=KEY, **kw):
    """A node already added to HA's ESPHome integration."""
    data = {"host": host, "port": 6053, "password": "", "device_name": title}
    if key is not None:
        data["noise_psk"] = key
    entry = MockConfigEntry(
        domain="esphome", title=title, unique_id=mac.lower(), data=data, **kw
    )
    entry.add_to_hass(hass)
    return entry


async def start_user(hass):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def step(hass, result, user_input):
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input)
    await hass.async_block_till_done()  # let a reconfigure's entry reload finish
    return result


def device_options(form):
    field = next(key for key in form["data_schema"].schema if str(key) == "device")
    selector = form["data_schema"].schema[field]
    return [option["value"] for option in selector.config["options"]]


async def test_picking_an_esphome_device_enrolls_it_with_its_host_and_key(hass, node):
    device = esphome_device(hass)

    menu = await start_user(hass)
    assert menu["type"] is data_entry_flow.FlowResultType.MENU
    form = await step(hass, menu, {"next_step_id": "esphome_device"})
    created = await step(hass, form, {"device": device.entry_id})

    assert created["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert created["data"]["gateways"] == [
        {
            "host": "192.0.2.10",
            "port": 6053,
            "mac": MAC,
            "name": "pump-room",
            "bridge": "v2",
            "noise_psk": KEY,
            "esphome_entry_id": device.entry_id,
        }
    ]
    # Verified over the API with the ESPHome integration's key; no Modbus frame sent.
    assert RecordingClient.opened == [{"host": "192.0.2.10", "port": 6053, "noise_psk": KEY}]
    assert node.probes == []


async def test_the_device_list_only_offers_esphome_nodes_with_a_known_mac(hass, node):
    device = esphome_device(hass)
    esphome_device(hass, mac="AA:BB:CC:DD:EE:02", source=config_entries.SOURCE_IGNORE)
    MockConfigEntry(
        domain="esphome", title="no mac yet", data={"host": "192.0.2.12"}
    ).add_to_hass(hass)
    MockConfigEntry(domain="mqtt", title="broker", data={"host": "192.0.2.13"}).add_to_hass(hass)

    form = await step(hass, await start_user(hass), {"next_step_id": "esphome_device"})

    assert device_options(form) == [device.entry_id]


async def test_without_esphome_devices_the_device_path_explains_why(hass, node):
    result = await step(hass, await start_user(hass), {"next_step_id": "esphome_device"})
    assert result["type"] is data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "no_esphome_devices"


def _plain_node(gateway):
    gateway.services = []
    gateway.entities = []


def _old_signature(gateway):
    gateway.services[0].args.pop()


def _other_bridge_version(gateway):
    gateway.info = lambda: {"v": 1, "bridge": 3, "buses": []}


def _reused_ip(gateway):
    gateway.mac = "AA:BB:CC:DD:EE:99"


def _offline(gateway):
    async def unreachable(**kwargs):
        raise TimeoutError

    gateway.connect = unreachable


@pytest.mark.parametrize(
    "node_change,error",
    [
        (_offline, "cannot_connect"),
        (_plain_node, "scanner_missing"),
        (_old_signature, "bridge_mismatch"),
        (_other_bridge_version, "bridge_mismatch"),
        (_reused_ip, "identity_mismatch"),
    ],
)
async def test_a_node_that_fails_verification_is_not_enrolled(hass, node, node_change, error):
    device = esphome_device(hass)
    node_change(node)

    form = await step(hass, await start_user(hass), {"next_step_id": "esphome_device"})
    result = await step(hass, form, {"device": device.entry_id})

    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": error}
    assert not hass.config_entries.async_entries(DOMAIN)
    assert node.probes == []


LEGACY = [
    # Two nodes enrolled with the old two-slot manual form, before bridge v2 existed.
    {"host": "192.0.2.1", "mac": "AA:BB:CC:00:00:01", "name": "Legacy 1", "noise_psk": KEY},
    {"host": "192.0.2.2", "mac": "AA:BB:CC:00:00:02", "name": "Legacy 2"},
]


def scanner_entry(hass, gateways):
    entry = MockConfigEntry(
        domain=DOMAIN, data={"gateways": [dict(g) for g in gateways]}, options={"kept": True}
    )
    entry.add_to_hass(hass)
    return entry


async def start_reconfigure(hass, entry):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )


async def test_a_third_gateway_joins_existing_legacy_gateways_unchanged(hass, node):
    entry = scanner_entry(hass, LEGACY)
    device = esphome_device(hass)

    menu = await start_reconfigure(hass, entry)
    form = await step(hass, menu, {"next_step_id": "esphome_device"})
    done = await step(hass, form, {"device": device.entry_id})

    assert done["reason"] == "reconfigure_successful"
    assert entry.data["gateways"][:2] == LEGACY
    assert [g["mac"] for g in entry.data["gateways"]] == [
        "AA:BB:CC:00:00:01",
        "AA:BB:CC:00:00:02",
        MAC,
    ]
    assert entry.options == {"kept": True}


async def test_reselecting_an_enrolled_gateway_takes_its_new_host_and_key(hass, node):
    entry = scanner_entry(
        hass,
        [{"host": "192.0.2.10", "mac": MAC, "name": "pump-room", "bridge": "v2", "noise_psk": KEY}],
    )
    device = esphome_device(hass, host="192.0.2.50", key=OTHER_KEY)

    menu = await start_reconfigure(hass, entry)
    form = await step(hass, menu, {"next_step_id": "esphome_device"})
    await step(hass, form, {"device": device.entry_id})

    [gateway] = entry.data["gateways"]
    assert (gateway["host"], gateway["noise_psk"]) == ("192.0.2.50", OTHER_KEY)


async def test_a_gateway_can_be_removed_without_touching_the_others(hass, node):
    entry = scanner_entry(hass, LEGACY)

    menu = await start_reconfigure(hass, entry)
    assert "remove_gateway" in menu["menu_options"]
    form = await step(hass, menu, {"next_step_id": "remove_gateway"})
    done = await step(hass, form, {"gateways": ["AA:BB:CC:00:00:01"]})

    assert done["reason"] == "reconfigure_successful"
    assert entry.data["gateways"] == LEGACY[1:]


async def test_removing_a_gateway_forgets_its_saved_pausable_poller_selection(hass, node):
    entry = scanner_entry(hass, LEGACY)
    selection = {
        "esphome:aabbcc000001": {"rs485": [{"index": 0, "name": "meter", "paused": False}]},
        "esphome:aabbcc000002": {"rs485": [{"index": 0, "name": "pump", "paused": True}]},
    }
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, "pausable_poller_selection": selection}
    )

    menu = await start_reconfigure(hass, entry)
    form = await step(hass, menu, {"next_step_id": "remove_gateway"})
    await step(hass, form, {"gateways": ["AA:BB:CC:00:00:01"]})

    assert entry.options == {
        "kept": True,
        "pausable_poller_selection": {"esphome:aabbcc000002": selection["esphome:aabbcc000002"]},
    }


async def test_manual_mode_enrolls_a_gateway_outside_the_esphome_integration(
    hass, node, legacy_nodes
):
    legacy_nodes["192.0.2.20"] = "AA:BB:CC:DD:EE:20"
    form = await step(hass, await start_user(hass), {"next_step_id": "manual"})
    created = await step(
        hass, form, {"host": "192.0.2.20", "mac": "aa:bb:cc:dd:ee:20", "bridge": "v1"}
    )

    assert created["data"]["gateways"] == [
        {"host": "192.0.2.20", "mac": "AA:BB:CC:DD:EE:20", "name": "ESPHome Modbus DDEE20",
         "bridge": "v1"}
    ]


async def test_manual_mode_verifies_a_v2_gateway_before_saving_it(hass, node):
    form = await step(hass, await start_user(hass), {"next_step_id": "manual"})
    created = await step(hass, form, {"host": "192.0.2.30", "mac": MAC, "bridge": "v2"})

    assert created["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert RecordingClient.opened == [{"host": "192.0.2.30", "port": 6053}]
    assert node.probes == []


@pytest.mark.parametrize(
    "node_change,error",
    [
        (_offline, "cannot_connect"),
        (_plain_node, "scanner_missing"),
        (_other_bridge_version, "bridge_mismatch"),
        (_reused_ip, "identity_mismatch"),
    ],
)
async def test_manual_mode_does_not_save_a_gateway_that_fails_verification(
    hass, node, node_change, error
):
    entry = scanner_entry(hass, LEGACY)
    node_change(node)

    form = await step(hass, await start_reconfigure(hass, entry), {"next_step_id": "manual"})
    result = await step(hass, form, {"host": "192.0.2.30", "mac": MAC, "bridge": "v2"})

    assert result["errors"] == {"base": error}
    assert entry.data["gateways"] == LEGACY
    assert node.probes == []


async def test_manual_mode_refuses_a_legacy_gateway_with_another_mac(hass, legacy_nodes):
    legacy_nodes["192.0.2.20"] = "AA:BB:CC:DD:EE:99"
    form = await step(hass, await start_user(hass), {"next_step_id": "manual"})
    result = await step(
        hass, form, {"host": "192.0.2.20", "mac": "AA:BB:CC:DD:EE:20", "bridge": "v1"}
    )

    assert result["errors"] == {"base": "identity_mismatch"}
    assert not hass.config_entries.async_entries(DOMAIN)


@pytest.mark.parametrize(
    "user_input,error",
    [
        ({"host": "192.0.2.20", "mac": "not-a-mac"}, "invalid_mac"),
        ({"host": "192.0.2.20", "mac": ""}, "gateway_pair_required"),
        ({"host": "192.0.2.20", "mac": MAC, "noise_psk": "not-a-key"}, "invalid_psk"),
        ({"host": "192.0.2.20", "mac": MAC, "noise_psk": "QUJD"}, "invalid_psk"),  # 3 bytes
        (
            {"host": "192.0.2.20", "mac": MAC, "noise_psk": KEY, "clear_psk": True},
            "conflicting_psk",
        ),
        ({"host": "192.0.2.1", "mac": MAC}, "duplicate_gateway"),
    ],
)
async def test_manual_mode_keeps_its_validation(hass, node, user_input, error):
    entry = scanner_entry(hass, LEGACY)
    form = await step(hass, await start_reconfigure(hass, entry), {"next_step_id": "manual"})
    result = await step(hass, form, user_input)
    assert result["errors"] == {"base": error}
    assert entry.data["gateways"] == LEGACY


async def test_manual_edit_retains_the_key_by_mac_and_never_renders_it(
    hass, node, legacy_nodes
):
    legacy_nodes["192.0.2.9"] = "AA:BB:CC:00:00:01"
    entry = scanner_entry(hass, LEGACY)

    form = await step(hass, await start_reconfigure(hass, entry), {"next_step_id": "manual"})
    assert KEY not in repr(
        {str(k): k.default() for k in form["data_schema"].schema if callable(k.default)}
    )
    await step(hass, form, {"host": "192.0.2.9", "mac": "AA:BB:CC:00:00:01"})

    first = entry.data["gateways"][0]
    assert (first["host"], first["noise_psk"], first["name"]) == ("192.0.2.9", KEY, "Legacy 1")
    # A node enrolled before bridge v2 existed stays on the legacy bridge.
    assert first["bridge"] == "v1"

    form = await step(hass, await start_reconfigure(hass, entry), {"next_step_id": "manual"})
    await step(hass, form, {"host": "192.0.2.9", "mac": "AA:BB:CC:00:00:01", "clear_psk": True})
    assert "noise_psk" not in entry.data["gateways"][0]


async def test_reauth_rekeys_only_the_chosen_gateway_of_many(hass, node):
    v2 = {"host": "192.0.2.10", "mac": MAC, "name": "pump-room", "bridge": "v2", "noise_psk": KEY}
    entry = scanner_entry(hass, [*LEGACY, v2])
    flow = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )

    done = await step(hass, flow, {"gateway": MAC, "noise_psk": OTHER_KEY})

    assert done["reason"] == "reauth_successful"
    assert entry.data["gateways"] == [*LEGACY, {**v2, "noise_psk": OTHER_KEY}]
    assert [c["host"] for c in RecordingClient.opened] == ["192.0.2.10"]


async def test_reauth_without_physical_gateways_aborts(hass, node):
    entry = scanner_entry(hass, [])
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )
    assert result["reason"] == "no_physical_gateways"
