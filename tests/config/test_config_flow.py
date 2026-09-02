"""Config flow tests for the singleton public integration."""

from homeassistant import config_entries, data_entry_flow
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.woow_esphome_modbus_scanner.const import DOMAIN, NAME


async def test_user_flow_creates_singleton_entry(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"

    created = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert created["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert created["title"] == NAME
    assert created["data"] == {}


async def test_second_entry_aborts_as_already_configured(hass):
    MockConfigEntry(domain=DOMAIN, title=NAME, data={}).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"
