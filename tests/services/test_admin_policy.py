"""Permanent all-user policy tests at the six public service seams."""

from homeassistant.core import Context
import pytest
from pytest_homeassistant_custom_component.common import MockUser

from custom_components.woow_esphome_modbus_scanner.const import DOMAIN, PUBLIC_SERVICES
from custom_components.woow_esphome_modbus_scanner.services import async_register_services


@pytest.mark.parametrize("service", PUBLIC_SERVICES)
async def test_every_scanner_service_allows_non_admin_user(hass, service):
    """The sidebar and all six actions are deliberately available to every HA user."""
    async_register_services(hass)
    user = MockUser(groups=[])
    user.add_to_hass(hass)
    context = Context(user_id=user.id)

    scan_id = None
    if service in {"get_scan_status", "get_scan_results", "cancel_scan"}:
        started = await hass.services.async_call(
            DOMAIN,
            "start_scan",
            {"start_id": 1, "end_id": 1, "safety_confirmed": True},
            blocking=True,
            return_response=True,
            context=context,
        )
        scan_id = started["scan_id"]

    data = {
        "list_gateways": {},
        "start_scan": {"start_id": 1, "end_id": 1, "safety_confirmed": True},
        "get_scan_status": {"scan_id": scan_id},
        "get_scan_results": {"scan_id": scan_id},
        "cancel_scan": {"scan_id": scan_id},
        "test_address": {"address": 1},
    }[service]
    response = await hass.services.async_call(
        DOMAIN,
        service,
        data,
        blocking=True,
        return_response=True,
        context=context,
    )
    assert isinstance(response, dict)
    if service == "list_gateways":
        assert response["gateways"]
    else:
        assert response["scan_id"]


async def test_internal_call_without_user_context_is_allowed(hass):
    async_register_services(hass)
    response = await hass.services.async_call(
        DOMAIN, "list_gateways", blocking=True, return_response=True
    )
    assert "gateways" in response
