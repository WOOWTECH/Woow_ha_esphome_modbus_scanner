"""Migration away from legacy bridge v1, observed through HA's Repairs and the services.

Each Gateway still on legacy bridge v1 gets one Repairs issue asking for a reflash with
the vendor-neutral scanner component; the issue goes away once the Gateway is enrolled
as bridge v2. The former vendor register map ships only as an importable example
Device Profile.
"""

import asyncio
from pathlib import Path

from homeassistant.core import Context
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import issue_registry as ir
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.woow_esphome_modbus_scanner import async_setup_entry
from custom_components.woow_esphome_modbus_scanner.const import DATA_COORDINATOR, DOMAIN
from custom_components.woow_esphome_modbus_scanner.modbus_scan.bridge_v2 import (
    provider as v2_provider,
)
from custom_components.woow_esphome_modbus_scanner.modbus_scan.legacy_v1 import (
    provider as legacy_provider,
)
from tests.services.test_bridge_v2 import GATEWAY_ID as V2_GATEWAY_ID
from tests.services.test_bridge_v2 import FakeClient, FakeV2Gateway
from tests.services.test_bridge_v2 import _setup as setup_v2
from tests.services.test_legacy_v1_adapter import IN_D17_REGISTERS, FakeLegacyClient

EXAMPLE = Path(__file__).parents[2] / "examples" / "device_profiles" / "guanjie-ind17.json"
LEGACY_GATEWAY_ID = "esphome:aabbccddeeff"
LEGACY_A = {"host": "192.0.2.1", "mac": "AA:BB:CC:DD:EE:FF", "name": "dryer-a"}
LEGACY_B = {"host": "192.0.2.2", "mac": "AA:BB:CC:DD:EE:FE", "name": "dryer-b", "bridge": "v1"}
GENERIC = {"host": "192.0.2.10", "mac": "AA:BB:CC:DD:EE:01", "name": "pump", "bridge": "v2"}


@pytest.fixture(autouse=True)
def bypass_panel_registration(monkeypatch):
    """Repairs do not depend on the sidebar panel."""

    async def register_panel(_hass):
        return None

    monkeypatch.setattr(
        "custom_components.woow_esphome_modbus_scanner._async_register_panel", register_panel
    )


def legacy_issues(hass):
    """Legacy-bridge Repairs issues of this integration, by Gateway name."""
    return {
        issue.translation_placeholders["name"]: issue
        for (domain, _), issue in ir.async_get(hass).issues.items()
        if domain == DOMAIN and issue.translation_key == "legacy_bridge"
    }


async def _setup(hass, gateways):
    entry = MockConfigEntry(domain=DOMAIN, data={"gateways": gateways})
    entry.add_to_hass(hass)
    assert await async_setup_entry(hass, entry)
    return entry


async def test_each_legacy_gateway_gets_one_repairs_issue(hass):
    await _setup(hass, [LEGACY_A, LEGACY_B, GENERIC])

    issues = legacy_issues(hass)
    assert set(issues) == {"dryer-a", "dryer-b"}
    issue = issues["dryer-a"]
    assert issue.translation_placeholders == {
        "name": "dryer-a",
        "host": "192.0.2.1",
        "mac": "AA:BB:CC:DD:EE:FF",
    }
    assert issue.severity is ir.IssueSeverity.WARNING
    assert not issue.is_fixable


async def test_a_legacy_gateway_keeps_scanning_within_legacy_limits_meanwhile(
    hass, monkeypatch
):
    FakeLegacyClient.instances = []
    monkeypatch.setattr(legacy_provider, "APIClient", FakeLegacyClient)
    await _setup(hass, [LEGACY_A])
    user = await hass.auth.async_create_user("legacy operator")

    async def call(service, data):
        return await hass.services.async_call(
            DOMAIN, service, data, blocking=True, return_response=True,
            context=Context(user_id=user.id),
        )

    target = {"provider": "esphome", "gateway_id": LEGACY_GATEWAY_ID}
    with pytest.raises(ServiceValidationError, match="A Legacy Gateway supports slave IDs 1"):
        await call("test_address", {**target, "address": 33})
    started = await call("test_address", {**target, "address": 1})
    await asyncio.gather(*hass.data[DOMAIN][DATA_COORDINATOR]._tasks.values())

    results = await call("get_scan_results", {"scan_id": started["scan_id"]})
    assert results["status"] == "completed"
    assert [(r["address"], r["raw_value"]) for r in results["responders"]] == [(1, 1234)]
    assert set(legacy_issues(hass)) == {"dryer-a"}


@pytest.fixture
def reflashed_node(hass, monkeypatch):
    """dryer-a after its reflash: now a bridge v2 node in HA's ESPHome integration."""
    hass.config.components.update({"frontend", "panel_custom", "esphome"})
    monkeypatch.setattr(
        "custom_components.woow_esphome_modbus_scanner.frontend.async_remove_panel",
        lambda *_args, **_kwargs: None,
    )
    node = FakeV2Gateway(mac=LEGACY_A["mac"])
    FakeClient.gateway = node
    FakeClient.instances = []
    monkeypatch.setattr(v2_provider, "APIClient", FakeClient)
    device = MockConfigEntry(
        domain="esphome",
        title="dryer-a",
        unique_id=LEGACY_A["mac"].lower(),
        data={"host": LEGACY_A["host"], "port": 6053, "password": ""},
    )
    device.add_to_hass(hass)
    return device


async def _reconfigure(hass, entry, menu_choice, user_input):
    menu = await entry.start_reconfigure_flow(hass)
    form = await hass.config_entries.flow.async_configure(
        menu["flow_id"], {"next_step_id": menu_choice}
    )
    result = await hass.config_entries.flow.async_configure(form["flow_id"], user_input)
    await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"


async def test_reenrolling_a_reflashed_gateway_as_v2_clears_its_issue(hass, reflashed_node):
    entry = MockConfigEntry(domain=DOMAIN, data={"gateways": [LEGACY_A, LEGACY_B]})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert set(legacy_issues(hass)) == {"dryer-a", "dryer-b"}

    await _reconfigure(hass, entry, "esphome_device", {"device": reflashed_node.entry_id})

    assert set(legacy_issues(hass)) == {"dryer-b"}
    assert reflashed_node.entry_id in {
        g.get("esphome_entry_id") for g in entry.data["gateways"] if g.get("bridge") == "v2"
    }


async def test_removing_a_legacy_gateway_clears_its_issue(hass, reflashed_node):
    entry = MockConfigEntry(domain=DOMAIN, data={"gateways": [LEGACY_A, LEGACY_B]})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)

    await _reconfigure(hass, entry, "remove_gateway", {"gateways": [LEGACY_B["mac"]]})

    assert set(legacy_issues(hass)) == {"dryer-a"}


async def test_vendor_example_profile_imports_and_scans_a_v2_gateway(hass, monkeypatch):
    node = FakeV2Gateway(devices={("rs485", 2): [1]})
    FakeClient.gateway = node
    FakeClient.instances = []
    monkeypatch.setattr(v2_provider, "APIClient", FakeClient)
    call = await setup_v2(hass)

    # Uploaded the way the sidebar does it: the file's JSON text.
    imported = await call("import_device_profile", {"profile": EXAMPLE.read_text("utf-8")})
    profile_id = imported["profile"]["id"]
    listed = next(
        p for p in (await call("list_device_profiles"))["profiles"] if p["id"] == profile_id
    )
    assert listed["function_codes"] == [3]
    assert listed["allowed_registers"] == IN_D17_REGISTERS
    assert listed["deletable"] is True

    started = await call(
        "start_scan",
        {
            "provider": "esphome",
            "gateway_id": V2_GATEWAY_ID,
            "device_profile_id": profile_id,
            "safety_confirmed": True,
        },
    )
    await asyncio.gather(*hass.data[DOMAIN][DATA_COORDINATOR]._tasks.values())

    assert [p["slave"] for p in node.probes] == [1, 2, 3]
    assert {
        (p["function_code"], p["register"], p["count"], p["timeout_ms"]) for p in node.probes
    } == {(3, 0x6201, 1, 700)}
    results = await call("get_scan_results", {"scan_id": started["scan_id"]})
    assert results["device_profile"]["id"] == profile_id
    assert [(r["address"], r["raw_values"]) for r in results["responders"]] == [(2, [1])]


async def test_removing_the_integration_clears_legacy_issues(hass, reflashed_node):
    entry = MockConfigEntry(domain=DOMAIN, data={"gateways": [LEGACY_A]})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)

    await hass.config_entries.async_remove(entry.entry_id)

    assert legacy_issues(hass) == {}
