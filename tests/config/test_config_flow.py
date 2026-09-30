"""Config flow tests for the singleton public integration."""

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries, data_entry_flow
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.woow_esphome_modbus_scanner.const import DOMAIN, NAME


@pytest.fixture(autouse=True)
def dependency_setup_is_outside_flow_unit_scope(hass):
    # These flow tests exercise this integration's form/schema, not native HA
    # Bluetooth, assist-pipeline or frontend startup. Live HA tests cover those.
    hass.config.components.update({"frontend", "panel_custom", "esphome"})


async def test_user_flow_creates_singleton_entry(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"

    created = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert created["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert created["title"] == NAME
    assert created["data"] == {"gateways": []}


async def test_second_entry_aborts_as_already_configured(hass):
    MockConfigEntry(domain=DOMAIN, title=NAME, data={}).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize("failure", [None, "auth", "network"])
async def test_reauth_verifies_api_before_saving(hass, failure):
    from custom_components.woow_esphome_modbus_scanner.modbus_scan.esphome_provider import (
        ESPHomeGatewayProvider,
    )
    from custom_components.woow_esphome_modbus_scanner.modbus_scan.provider import (
        GatewayProviderError,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "gateways": [
                {"host": "192.0.2.1", "mac": "AA:BB:CC:DD:EE:FF", "noise_psk": "A" * 43 + "="}
            ],
            "allow_physical_automation": True,
        },
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )
    assert result["step_id"] == "reauth_confirm"
    with (
        patch.object(ESPHomeGatewayProvider, "check_gateway", new_callable=AsyncMock) as check,
        patch("custom_components.woow_esphome_modbus_scanner.async_setup_entry", return_value=True),
    ):
        if failure == "auth":
            check.side_effect = GatewayProviderError("PRIVATE", code="API_AUTH_FAILED")
        elif failure:
            check.side_effect = RuntimeError("PRIVATE")
        updated = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"noise_psk": "B" * 43 + "="}
        )
        check.assert_awaited_once()
    if failure:
        assert updated["errors"]["base"] == (
            "invalid_auth" if failure == "auth" else "cannot_connect"
        )
        assert entry.data["gateways"][0]["noise_psk"] == "A" * 43 + "="
    else:
        assert updated["reason"] == "reauth_successful"
        assert entry.data["gateways"][0]["noise_psk"] == "B" * 43 + "="
        assert entry.data["allow_physical_automation"] is True


async def test_reconfigure_preserves_secret_without_automation_gate(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "gateways": [
                {"host": "192.0.2.1", "mac": "AA:BB:CC:DD:EE:FF", "noise_psk": "A" * 43 + "="}
            ]
        },
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    bad = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "192.0.2.2", "mac": ""}
    )
    assert bad["errors"]["base"] == "gateway_pair_required"
    with patch(
        "custom_components.woow_esphome_modbus_scanner.async_setup_entry", return_value=True
    ):
        updated = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"host": "192.0.2.2", "mac": "AA:BB:CC:DD:EE:FF"},
        )
    assert updated["reason"] == "reconfigure_successful"
    assert entry.data["gateways"][0]["noise_psk"] == "A" * 43 + "="
    assert "allow_physical_automation" not in entry.data
