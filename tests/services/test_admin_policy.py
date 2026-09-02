"""Context-aware administrator policy tests at the public service seam."""

from homeassistant.core import Context
from homeassistant.exceptions import Unauthorized
import pytest
from pytest_homeassistant_custom_component.common import MockUser

from custom_components.woow_esphome_modbus_scanner.const import DOMAIN
from custom_components.woow_esphome_modbus_scanner.services import async_register_services


async def _list(hass, context=None):
    return await hass.services.async_call(
        DOMAIN,
        "list_gateways",
        blocking=True,
        return_response=True,
        context=context,
    )


async def test_non_admin_user_is_refused(hass):
    async_register_services(hass)
    user = MockUser(groups=[])
    user.add_to_hass(hass)
    with pytest.raises(Unauthorized):
        await _list(hass, Context(user_id=user.id))


async def test_admin_user_is_allowed(hass, hass_admin_user):
    async_register_services(hass)
    assert "gateways" in await _list(hass, Context(user_id=hass_admin_user.id))


async def test_internal_call_without_user_context_is_allowed(hass):
    async_register_services(hass)
    assert "gateways" in await _list(hass)
