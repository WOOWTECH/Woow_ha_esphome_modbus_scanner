"""Admin-only Home Assistant service seam for Modbus scanning."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, Unauthorized
import voluptuous as vol

from .const import (
    DATA_COORDINATOR,
    DATA_COORDINATOR_OWNER,
    DATA_SERVICE_OWNER,
    DATA_SERVICES_AVAILABLE,
    DOMAIN,
    PUBLIC_SERVICES,
    SERVICE_CANCEL_SCAN,
    SERVICE_GET_SCAN_RESULTS,
    SERVICE_GET_SCAN_STATUS,
    SERVICE_LIST_GATEWAYS,
    SERVICE_START_SCAN,
    SERVICE_TEST_ADDRESS,
)
from .modbus_scan.coordinator import (
    GatewayBusyError,
    ModbusScanCoordinator,
    ScanNotFoundError,
)
from .modbus_scan.mock_provider import MOCK_GATEWAY_ID, MockGatewayProvider
from .modbus_scan.models import (
    MAX_INTER_REQUEST_DELAY_MS,
    MAX_REGISTER_ADDRESS,
    MAX_REGISTER_COUNT,
    MAX_RETRIES,
    MAX_SLAVE_ID,
    MAX_TIMEOUT_MS,
    MIN_SLAVE_ID,
    MIN_TIMEOUT_MS,
    MockProfile,
    ProbeType,
    ScanRequest,
)


def _exact_int(value: object) -> int:
    """Accept integers and integer strings without lossy coercion."""
    if type(value) is int:
        return value
    if isinstance(value, str) and re.fullmatch(r"[+-]?[0-9]+", value):
        return int(value)
    raise vol.Invalid("expected an integer without fractional part")


def _exact_true(value: object) -> bool:
    """Accept only the literal boolean true for the scan safety acknowledgement."""
    if type(value) is bool and value is True:
        return value
    raise vol.Invalid("expected boolean true")


def _probe_type(value: object) -> ProbeType:
    """Normalize a public probe string to the provider-facing enum."""
    try:
        return ProbeType(value)
    except (TypeError, ValueError) as err:
        raise vol.Invalid("expected a supported read-only probe type") from err


def _canonical_uuid(value: object) -> str:
    """Accept only the lowercase, hyphenated canonical UUID representation."""
    if not isinstance(value, str):
        raise vol.Invalid("expected a canonical UUID string")
    try:
        parsed = UUID(value)
    except ValueError as err:
        raise vol.Invalid("expected a canonical UUID string") from err
    if str(parsed) != value:
        raise vol.Invalid("expected a canonical UUID string")
    return value


_PROVIDER_FIELDS = {
    vol.Optional("provider", default="mock"): vol.In(["mock"]),
    vol.Optional("gateway_id", default=MOCK_GATEWAY_ID): str,
    # Reserved UI bridge for a future adapter. Mock mode accepts and records no
    # dependency on an ESPHome device or integration.
    vol.Optional("esphome_device_id"): str,
}
_PROBE_FIELDS = {
    vol.Optional("probe_type", default=ProbeType.DEVICE_IDENTIFICATION.value): _probe_type,
    vol.Optional("register_address", default=0): vol.All(
        _exact_int, vol.Range(min=0, max=MAX_REGISTER_ADDRESS)
    ),
    vol.Optional("register_count", default=1): vol.All(
        _exact_int, vol.Range(min=1, max=MAX_REGISTER_COUNT)
    ),
    vol.Optional("timeout_ms", default=500): vol.All(
        _exact_int, vol.Range(min=MIN_TIMEOUT_MS, max=MAX_TIMEOUT_MS)
    ),
    vol.Optional("retries", default=1): vol.All(
        _exact_int, vol.Range(min=0, max=MAX_RETRIES)
    ),
    vol.Optional("inter_request_delay_ms", default=100): vol.All(
        _exact_int, vol.Range(min=0, max=MAX_INTER_REQUEST_DELAY_MS)
    ),
    vol.Optional("pause_normal_polling", default=False): bool,
    vol.Optional("mock_profile", default=MockProfile.FOUND_DEFAULT.value): vol.In(
        [item.value for item in MockProfile]
    ),
}
_START_SCAN_SCHEMA = vol.Schema(
    {
        **_PROVIDER_FIELDS,
        vol.Required("start_id"): vol.All(
            _exact_int, vol.Range(min=MIN_SLAVE_ID, max=MAX_SLAVE_ID)
        ),
        vol.Required("end_id"): vol.All(
            _exact_int, vol.Range(min=MIN_SLAVE_ID, max=MAX_SLAVE_ID)
        ),
        **_PROBE_FIELDS,
        vol.Required("safety_confirmed"): _exact_true,
    }
)
_SCAN_ID_SCHEMA = vol.Schema({vol.Required("scan_id"): _canonical_uuid})
_TEST_ADDRESS_SCHEMA = vol.Schema(
    {
        **_PROVIDER_FIELDS,
        vol.Required("address"): vol.All(
            _exact_int, vol.Range(min=MIN_SLAVE_ID, max=MAX_SLAVE_ID)
        ),
        **_PROBE_FIELDS,
    }
)
_LIST_GATEWAYS_SCHEMA = vol.Schema({})


async def _async_reject_non_admin(hass: HomeAssistant, call: ServiceCall) -> None:
    """Require admin for user-context calls while allowing trusted internal calls."""
    if call.context.user_id is None:
        return
    user = await hass.auth.async_get_user(call.context.user_id)
    if user is None or not user.is_admin:
        raise Unauthorized(context=call.context)


_Owner = tuple[str, int]


def _coordinator(
    hass: HomeAssistant, expected_owner: _Owner | None = None
) -> ModbusScanCoordinator:
    """Return the coordinator only while the calling generation still owns it."""
    domain_data = hass.data.get(DOMAIN)
    if (
        domain_data is None
        or not domain_data.get(DATA_SERVICES_AVAILABLE, False)
        or (
            expected_owner is not None
            and domain_data.get(DATA_SERVICE_OWNER) != expected_owner
        )
    ):
        raise HomeAssistantError("Modbus scan services are no longer available")
    owner = domain_data.get(DATA_SERVICE_OWNER)
    coordinator = domain_data.get(DATA_COORDINATOR)
    if coordinator is None:
        coordinator = ModbusScanCoordinator(hass, [MockGatewayProvider()])
        domain_data[DATA_COORDINATOR] = coordinator
        domain_data[DATA_COORDINATOR_OWNER] = owner
    elif domain_data.get(DATA_COORDINATOR_OWNER) != owner:
        raise HomeAssistantError("Modbus scan coordinator ownership is inconsistent")
    return coordinator


def _scan_request(
    data: dict[str, Any], *, safety_confirmed: bool, address: int | None = None
) -> ScanRequest:
    """Translate a public payload into a provider-neutral request."""
    start_id = address if address is not None else data["start_id"]
    end_id = address if address is not None else data["end_id"]
    return ScanRequest(
        provider=data["provider"],
        gateway_id=data["gateway_id"],
        start_id=start_id,
        end_id=end_id,
        probe_type=data["probe_type"],
        register_address=data["register_address"],
        register_count=data["register_count"],
        timeout_ms=data["timeout_ms"],
        retries=data["retries"],
        inter_request_delay_ms=data["inter_request_delay_ms"],
        pause_normal_polling=data["pause_normal_polling"],
        mock_profile=data["mock_profile"],
        safety_confirmed=safety_confirmed,
    )


def _as_home_assistant_error(err: Exception) -> HomeAssistantError:
    return HomeAssistantError(str(err))


async def _handle_list_gateways(
    call: ServiceCall, owner: _Owner
) -> ServiceResponse:
    await _async_reject_non_admin(call.hass, call)
    return _coordinator(call.hass, owner).list_gateways()


async def _handle_start_scan(call: ServiceCall, owner: _Owner) -> ServiceResponse:
    await _async_reject_non_admin(call.hass, call)
    try:
        request = _scan_request(
            call.data, safety_confirmed=call.data["safety_confirmed"]
        )
        return await _coordinator(call.hass, owner).start(request)
    except (ValueError, GatewayBusyError, RuntimeError) as err:
        raise _as_home_assistant_error(err) from err


async def _handle_get_scan_status(
    call: ServiceCall, owner: _Owner
) -> ServiceResponse:
    await _async_reject_non_admin(call.hass, call)
    try:
        return _coordinator(call.hass, owner).status(call.data["scan_id"])
    except ScanNotFoundError as err:
        raise _as_home_assistant_error(err) from err


async def _handle_get_scan_results(
    call: ServiceCall, owner: _Owner
) -> ServiceResponse:
    await _async_reject_non_admin(call.hass, call)
    try:
        return _coordinator(call.hass, owner).results(call.data["scan_id"])
    except ScanNotFoundError as err:
        raise _as_home_assistant_error(err) from err


async def _handle_cancel_scan(call: ServiceCall, owner: _Owner) -> ServiceResponse:
    await _async_reject_non_admin(call.hass, call)
    try:
        return await _coordinator(call.hass, owner).cancel(call.data["scan_id"])
    except ScanNotFoundError as err:
        raise _as_home_assistant_error(err) from err


async def _handle_test_address(call: ServiceCall, owner: _Owner) -> ServiceResponse:
    await _async_reject_non_admin(call.hass, call)
    try:
        request = _scan_request(
            call.data, safety_confirmed=True, address=call.data["address"]
        )
        return await _coordinator(call.hass, owner).start(request)
    except (ValueError, GatewayBusyError, RuntimeError) as err:
        raise _as_home_assistant_error(err) from err


_SERVICE_DEFINITIONS = (
    (
        SERVICE_LIST_GATEWAYS,
        _handle_list_gateways,
        _LIST_GATEWAYS_SCHEMA,
        SupportsResponse.ONLY,
    ),
    (
        SERVICE_START_SCAN,
        _handle_start_scan,
        _START_SCAN_SCHEMA,
        SupportsResponse.OPTIONAL,
    ),
    (
        SERVICE_GET_SCAN_STATUS,
        _handle_get_scan_status,
        _SCAN_ID_SCHEMA,
        SupportsResponse.ONLY,
    ),
    (
        SERVICE_GET_SCAN_RESULTS,
        _handle_get_scan_results,
        _SCAN_ID_SCHEMA,
        SupportsResponse.ONLY,
    ),
    (
        SERVICE_CANCEL_SCAN,
        _handle_cancel_scan,
        _SCAN_ID_SCHEMA,
        SupportsResponse.OPTIONAL,
    ),
    (
        SERVICE_TEST_ADDRESS,
        _handle_test_address,
        _TEST_ADDRESS_SCHEMA,
        SupportsResponse.OPTIONAL,
    ),
)


def async_register_services(
    hass: HomeAssistant,
    entry_id: str = "direct-registration",
    generation: int = 0,
) -> None:
    """Register six services bound to one owner generation."""
    owner = (entry_id, generation)
    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data[DATA_SERVICE_OWNER] = owner
    domain_data[DATA_SERVICES_AVAILABLE] = True
    _coordinator(hass, owner)
    for service, handler, schema, response_mode in _SERVICE_DEFINITIONS:
        if not hass.services.has_service(DOMAIN, service):

            async def owned_handler(
                call: ServiceCall,
                _handler=handler,
                _owner=owner,
            ) -> ServiceResponse:
                return await _handler(call, _owner)

            hass.services.async_register(
                DOMAIN,
                service,
                owned_handler,
                schema=schema,
                supports_response=response_mode,
            )


def async_unregister_services(
    hass: HomeAssistant,
    entry_id: str | None = None,
    generation: int | None = None,
) -> None:
    """Make one generation's dispatched handlers fail closed, then remove them."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    expected_owner = (
        None if entry_id is None or generation is None else (entry_id, generation)
    )
    if (
        expected_owner is not None
        and domain_data.get(DATA_SERVICE_OWNER) != expected_owner
    ):
        return
    domain_data.pop(DATA_SERVICES_AVAILABLE, None)
    domain_data.pop(DATA_SERVICE_OWNER, None)
    for service in PUBLIC_SERVICES:
        hass.services.async_remove(DOMAIN, service)
