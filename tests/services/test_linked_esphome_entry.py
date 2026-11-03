"""A Gateway enrolled from HA's ESPHome integration follows that entry's host, port and key.

The scanner keeps a copy taken at Enrollment only as a fallback: when the ESPHome entry is
later changed (new IP after DHCP, rotated API key), the next connection uses its values.
"""

from homeassistant.core import Context
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from test_bridge_v2 import GATEWAY_ID, MAC, FakeClient, FakeV2Gateway, _test_address

from custom_components.woow_esphome_modbus_scanner.const import DOMAIN
from custom_components.woow_esphome_modbus_scanner.modbus_scan.bridge_v2 import (
    provider as v2_provider,
)
from custom_components.woow_esphome_modbus_scanner.services import async_register_services

OLD_KEY = "A" * 43 + "="
NEW_KEY = "B" * 43 + "="


@pytest.fixture(autouse=True)
def esphome_integration_is_outside_scope(hass):
    """Updating an ESPHome entry must not try to load the real ESPHome integration."""
    hass.config.components.add("esphome")


class RecordingClient(FakeClient):
    """Remembers how each API connection was opened."""

    opened: list = []

    def __init__(self, host, port, password, **kwargs):
        super().__init__(host, port, password, **kwargs)
        RecordingClient.opened.append((host, port, kwargs.get("noise_psk")))


async def _setup(hass, monkeypatch, *, linked=True, link_to=None):
    FakeClient.gateway = FakeV2Gateway(devices={("rs485", 7): [1]})
    FakeClient.instances = []
    RecordingClient.opened = []
    monkeypatch.setattr(v2_provider, "APIClient", RecordingClient)
    esphome = MockConfigEntry(
        domain="esphome",
        title="pump-room",
        unique_id=MAC.lower(),
        data={"host": "192.0.2.10", "port": 6053, "password": "", "noise_psk": OLD_KEY},
    )
    esphome.add_to_hass(hass)
    gateway = {"host": "192.0.2.10", "port": 6053, "mac": MAC, "bridge": "v2"}
    gateway["noise_psk"] = OLD_KEY
    if linked:
        gateway["esphome_entry_id"] = link_to or esphome.entry_id
    entry = MockConfigEntry(domain=DOMAIN, data={"gateways": [gateway]})
    entry.add_to_hass(hass)
    user = await hass.auth.async_create_user("operator")
    async_register_services(hass, entry.entry_id)
    context = Context(user_id=user.id)

    async def call(service, data=None):
        return await hass.services.async_call(
            DOMAIN, service, data or {}, blocking=True, return_response=True, context=context
        )

    return call, esphome


async def test_scan_uses_the_linked_esphome_entrys_current_host_and_key(hass, monkeypatch):
    call, esphome = await _setup(hass, monkeypatch)
    assert (await _test_address(hass, call, address=7))["status"] == "completed"

    hass.config_entries.async_update_entry(
        esphome, data={**esphome.data, "host": "192.0.2.77", "port": 6054, "noise_psk": NEW_KEY}
    )
    assert (await _test_address(hass, call, address=7))["status"] == "completed"
    checked = await call("check_gateway", {"gateway_id": GATEWAY_ID})

    assert RecordingClient.opened == [
        ("192.0.2.10", 6053, OLD_KEY),
        ("192.0.2.77", 6054, NEW_KEY),
        ("192.0.2.77", 6054, NEW_KEY),
    ]
    assert checked["health"]["encrypted"] is True


async def test_key_removed_from_the_esphome_entry_connects_without_encryption(hass, monkeypatch):
    call, esphome = await _setup(hass, monkeypatch)
    hass.config_entries.async_update_entry(
        esphome, data={k: v for k, v in esphome.data.items() if k != "noise_psk"}
    )
    await _test_address(hass, call, address=7)
    assert RecordingClient.opened == [("192.0.2.10", 6053, None)]


async def test_without_the_esphome_entry_the_enrolment_copy_is_used(hass, monkeypatch):
    call, _esphome = await _setup(hass, monkeypatch, link_to="removed-esphome-entry")
    await _test_address(hass, call, address=7)
    assert RecordingClient.opened == [("192.0.2.10", 6053, OLD_KEY)]


async def test_manually_enrolled_gateway_uses_its_stored_host_and_key(hass, monkeypatch):
    call, esphome = await _setup(hass, monkeypatch, linked=False)
    hass.config_entries.async_update_entry(esphome, data={**esphome.data, "host": "192.0.2.77"})
    await _test_address(hass, call, address=7)
    assert RecordingClient.opened == [("192.0.2.10", 6053, OLD_KEY)]
