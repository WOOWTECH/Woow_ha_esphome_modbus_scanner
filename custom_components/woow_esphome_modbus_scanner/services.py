"""All-user Home Assistant service seam for Modbus scanning."""

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
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError, Unauthorized
import voluptuous as vol

from .const import (
    DATA_COORDINATOR,
    DATA_COORDINATOR_OWNER,
    DATA_DEVICE_PROFILES,
    DATA_PROBE_SLOT_MODES,
    DATA_SERVICE_OWNER,
    DATA_SERVICES_AVAILABLE,
    DOMAIN,
    PUBLIC_SERVICES,
    SERVICE_CANCEL_SCAN,
    SERVICE_DELETE_DEVICE_PROFILE,
    SERVICE_EXPORT_DEVICE_PROFILE,
    SERVICE_GET_SCAN_RESULTS,
    SERVICE_GET_SCAN_STATUS,
    SERVICE_IMPORT_DEVICE_PROFILE,
    SERVICE_LIST_DEVICE_PROFILES,
    SERVICE_LIST_GATEWAYS,
    SERVICE_SET_PAUSABLE_POLLERS,
    SERVICE_START_SCAN,
    SERVICE_TEST_ADDRESS,
)
from .device_profile_store import DeviceProfileNotFoundError, DeviceProfileStore
from .issues import report_gateway_issue
from .modbus_scan.adapters import build_physical_provider, physical_gateway_id
from .modbus_scan.coordinator import (
    GatewayBusyError,
    ModbusScanCoordinator,
    ScanNotFoundError,
)
from .modbus_scan.device_profile import GENERIC_PROFILE_ID, DeviceProfile, DeviceProfileError
from .modbus_scan.mock_provider import MOCK_GATEWAY_ID, MockGatewayProvider
from .modbus_scan.models import (
    BUS_NAME_PATTERN,
    LARGE_RANGE_THRESHOLD,
    MAX_INTER_REQUEST_DELAY_MS,
    MAX_REGISTER_ADDRESS,
    MAX_REGISTER_COUNT,
    MAX_RETRIES,
    MAX_SLAVE_ID,
    MAX_TIMEOUT_MS,
    MIN_SLAVE_ID,
    MIN_TIMEOUT_MS,
    MockScenario,
    ProbeType,
    ScanRequest,
)
from .modbus_scan.provider import GatewayProviderError
from .poller_selection import PollerSelectionStore


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


_POLLER_INDICES = vol.All(
    [vol.All(_exact_int, vol.Range(min=0, max=255))], vol.Unique(), vol.Coerce(tuple)
)

_PROVIDER_FIELDS = {
    vol.Optional("provider", default="mock"): vol.In(["mock", "esphome"]),
    vol.Optional("gateway_id", default=MOCK_GATEWAY_ID): str,
    # The Bus to scan; may be omitted when the Gateway has only one.
    vol.Optional("bus"): vol.All(str, vol.Match(rf"\A{BUS_NAME_PATTERN}\Z")),
    # Reserved UI bridge for a future adapter. Mock mode accepts and records no
    # dependency on an ESPHome device or integration.
    vol.Optional("esphome_device_id"): str,
}
_PROBE_FIELDS = {
    vol.Optional("device_profile_id", default=GENERIC_PROFILE_ID): str,
    vol.Optional("probe_type"): _probe_type,
    vol.Optional("register_address"): vol.All(
        _exact_int, vol.Range(min=0, max=MAX_REGISTER_ADDRESS)
    ),
    vol.Optional("register_count"): vol.All(_exact_int, vol.Range(min=1, max=MAX_REGISTER_COUNT)),
    vol.Optional("timeout_ms"): vol.All(
        _exact_int, vol.Range(min=MIN_TIMEOUT_MS, max=MAX_TIMEOUT_MS)
    ),
    vol.Optional("retries"): vol.All(_exact_int, vol.Range(min=0, max=MAX_RETRIES)),
    vol.Optional("inter_request_delay_ms"): vol.All(
        _exact_int, vol.Range(min=0, max=MAX_INTER_REQUEST_DELAY_MS)
    ),
    vol.Optional("pause_normal_polling"): bool,
    # Explicit Pausable Poller indices; absent means the Bus's saved selection.
    vol.Optional("pause_pollers"): _POLLER_INDICES,
    vol.Optional("mock_scenario"): vol.In([item.value for item in MockScenario]),
    # Deprecated alias of mock_scenario, kept so existing scripts keep working.
    vol.Optional("mock_profile"): vol.In([item.value for item in MockScenario]),
}


def _resolve_mock_scenario(data):
    """Fold the deprecated mock_profile alias into mock_scenario."""
    if "mock_scenario" in data and "mock_profile" in data:
        raise vol.Invalid(
            "mock_profile is a deprecated alias of mock_scenario; provide only mock_scenario"
        )
    data["mock_scenario"] = data.pop(
        "mock_profile", data.get("mock_scenario", MockScenario.FOUND_DEFAULT.value)
    )
    return data


def _with_gateway_defaults(
    coordinator: ModbusScanCoordinator, data, profile: DeviceProfile
) -> dict[str, Any]:
    """Only absent fields get Device Profile/gateway defaults; explicit values stay validated."""
    data = dict(data)
    defaults = coordinator.request_defaults(data["provider"], data["gateway_id"], profile)
    for key, value in defaults.items():
        data.setdefault(key, value)
    data["probe_type"] = ProbeType(data["probe_type"])
    if data["provider"] == "esphome":
        data["pause_checklists"] = coordinator.saved_poller_selection(data["gateway_id"])
    return data


def _require_range(data) -> None:
    if "start_id" not in data or "end_id" not in data:
        raise ValueError(
            "start_id and end_id are required unless the Device Profile defines a default "
            "slave range"
        )


_START_SCAN_SCHEMA = vol.Schema(
    {
        **_PROVIDER_FIELDS,
        vol.Optional("start_id"): vol.All(
            _exact_int, vol.Range(min=MIN_SLAVE_ID, max=MAX_SLAVE_ID)
        ),
        vol.Optional("end_id"): vol.All(_exact_int, vol.Range(min=MIN_SLAVE_ID, max=MAX_SLAVE_ID)),
        **_PROBE_FIELDS,
        vol.Required("safety_confirmed"): _exact_true,
        vol.Optional("large_range_confirmed"): _exact_true,
    }
)
_SCAN_ID_SCHEMA = vol.Schema({vol.Required("scan_id"): _canonical_uuid})
_TEST_ADDRESS_SCHEMA = vol.Schema(
    {
        **_PROVIDER_FIELDS,
        vol.Required("address"): vol.All(_exact_int, vol.Range(min=MIN_SLAVE_ID, max=MAX_SLAVE_ID)),
        **_PROBE_FIELDS,
    }
)
_LIST_GATEWAYS_SCHEMA = vol.Schema({})
_PROFILE_ID_SCHEMA = vol.Schema({vol.Required("profile_id"): str})
_IMPORT_PROFILE_SCHEMA = vol.Schema(
    # Any value: the Device Profile parser reports what is wrong with it field by field.
    {vol.Required("profile"): object}
)
_START_SCAN_SCHEMA = vol.All(_START_SCAN_SCHEMA, _resolve_mock_scenario)
_TEST_ADDRESS_SCHEMA = vol.All(_TEST_ADDRESS_SCHEMA, _resolve_mock_scenario)


_Owner = tuple[str, int]


async def _profile_store(hass: HomeAssistant, owner: _Owner) -> DeviceProfileStore:
    """The shared Device Profile store, loaded from HA storage on first use."""
    _coordinator(hass, owner)  # fail closed once this generation no longer owns services
    domain_data = hass.data[DOMAIN]
    store = domain_data.get(DATA_DEVICE_PROFILES)
    if store is None:
        store = domain_data[DATA_DEVICE_PROFILES] = DeviceProfileStore(hass)
    await store.async_load()
    return store


async def _selected_profile(hass: HomeAssistant, owner: _Owner, data) -> DeviceProfile:
    try:
        return (await _profile_store(hass, owner)).get(data["device_profile_id"])
    except DeviceProfileNotFoundError as err:
        raise ValueError(str(err)) from err


def _esphome_endpoint(hass: HomeAssistant):
    """Resolve an ESPHome config entry id to its current host, port and API key."""

    def resolve(entry_id: str) -> dict[str, Any] | None:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != "esphome":
            return None
        return {
            "host": entry.data.get("host"),
            "port": entry.data.get("port"),
            "noise_psk": entry.data.get("noise_psk"),
        }

    return resolve


def _coordinator(
    hass: HomeAssistant, expected_owner: _Owner | None = None
) -> ModbusScanCoordinator:
    """Return the coordinator only while the calling generation still owns it."""
    domain_data = hass.data.get(DOMAIN)
    if (
        domain_data is None
        or not domain_data.get(DATA_SERVICES_AVAILABLE, False)
        or (expected_owner is not None and domain_data.get(DATA_SERVICE_OWNER) != expected_owner)
    ):
        raise HomeAssistantError("Modbus scan services are no longer available")
    owner = domain_data.get(DATA_SERVICE_OWNER)
    coordinator = domain_data.get(DATA_COORDINATOR)
    if coordinator is None:
        providers = [MockGatewayProvider()]
        entry = hass.config_entries.async_get_entry(owner[0]) if owner else None
        if entry is not None and (
            physical := build_physical_provider(
                entry.data.get("gateways", ()),
                esphome_endpoint=_esphome_endpoint(hass),
                probe_slot_memory=domain_data.get(DATA_PROBE_SLOT_MODES),
            )
        ):
            providers.append(physical)
        coordinator = ModbusScanCoordinator(
            hass,
            providers,
            history=domain_data.get("history"),
            issue_callback=lambda gateway, code: report_gateway_issue(hass, gateway, code),
            selection_store=PollerSelectionStore(hass, owner[0] if owner else None),
        )
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
        bus=data.get("bus"),
        probe_type=data["probe_type"],
        register_address=data["register_address"],
        register_count=data["register_count"],
        timeout_ms=data["timeout_ms"],
        retries=data["retries"],
        inter_request_delay_ms=data["inter_request_delay_ms"],
        pause_normal_polling=data["pause_normal_polling"],
        mock_scenario=data["mock_scenario"],
        safety_confirmed=safety_confirmed,
        pause_pollers=data.get("pause_pollers"),
        pause_checklists=data.get("pause_checklists"),
    )


def _as_home_assistant_error(err: Exception) -> HomeAssistantError:
    if isinstance(err, (ValueError, ScanNotFoundError)):
        return ServiceValidationError(
            str(err),
            translation_domain=DOMAIN,
            translation_key="invalid_request",
            translation_placeholders={"reason": str(err)},
        )
    return HomeAssistantError(str(err))


async def _is_active_user_or_automation(call: ServiceCall) -> bool:
    """All active HA users and internal automations, per the approved policy (ADR 0008)."""
    if call.context.user_id is None:
        return True
    user = await call.hass.auth.async_get_user(call.context.user_id)
    return bool(user and user.is_active)


async def _require_active_user(call: ServiceCall) -> None:
    """Refuse unknown and inactive named users; also guards Device Profile writes."""
    if not await _is_active_user_or_automation(call):
        raise Unauthorized(context=call.context)


async def _authorize_physical(call: ServiceCall, provider: str) -> None:
    if provider == "esphome":
        await _require_active_user(call)


async def _handle_list_gateways(call: ServiceCall, owner: _Owner) -> ServiceResponse:
    result = _coordinator(call.hass, owner).list_gateways()
    allowed = await _is_active_user_or_automation(call)
    for gateway in result["gateways"]:
        gateway["can_operate"] = gateway["provider"] == "mock" or allowed
    return result


def _validate_selected_device(call: ServiceCall) -> None:
    if call.data["provider"] != "esphome" or not call.data.get("esphome_device_id"):
        return
    from homeassistant.helpers import device_registry as dr

    device = dr.async_get(call.hass).async_get(call.data["esphome_device_id"])
    if device is None or not any(
        kind == dr.CONNECTION_NETWORK_MAC
        and physical_gateway_id(value) == call.data["gateway_id"]
        for kind, value in device.connections
    ):
        raise ValueError("Selected ESPHome device does not match the configured gateway")


def _require_large_range_confirmation(data) -> None:
    """A long Scan must be confirmed explicitly, not only by safety_confirmed."""
    count = data["end_id"] - data["start_id"] + 1
    if count > LARGE_RANGE_THRESHOLD and data.get("large_range_confirmed") is not True:
        raise ValueError(
            f"Scanning {count} IDs (more than {LARGE_RANGE_THRESHOLD}) requires "
            "large_range_confirmed=true"
        )


async def _handle_start_scan(call: ServiceCall, owner: _Owner) -> ServiceResponse:
    await _authorize_physical(call, call.data["provider"])
    try:
        _validate_selected_device(call)
        coordinator = _coordinator(call.hass, owner)
        profile = await _selected_profile(call.hass, owner, call.data)
        data = _with_gateway_defaults(coordinator, call.data, profile)
        _require_range(data)
        _require_large_range_confirmation(data)
        request = _scan_request(data, safety_confirmed=call.data["safety_confirmed"])
        return await coordinator.start(request, profile)
    except (ValueError, GatewayBusyError, RuntimeError) as err:
        raise _as_home_assistant_error(err) from err


async def _handle_get_scan_status(call: ServiceCall, owner: _Owner) -> ServiceResponse:
    try:
        return _coordinator(call.hass, owner).status(call.data["scan_id"])
    except ScanNotFoundError as err:
        raise _as_home_assistant_error(err) from err


async def _handle_get_scan_results(call: ServiceCall, owner: _Owner) -> ServiceResponse:
    try:
        return _coordinator(call.hass, owner).results(call.data["scan_id"])
    except ScanNotFoundError as err:
        raise _as_home_assistant_error(err) from err


async def _handle_cancel_scan(call: ServiceCall, owner: _Owner) -> ServiceResponse:
    try:
        coordinator = _coordinator(call.hass, owner)
        state = coordinator.status(call.data["scan_id"])
        await _authorize_physical(call, state["provider"])
        return await coordinator.cancel(call.data["scan_id"])
    except ScanNotFoundError as err:
        raise _as_home_assistant_error(err) from err


async def _handle_test_address(call: ServiceCall, owner: _Owner) -> ServiceResponse:
    await _authorize_physical(call, call.data["provider"])
    try:
        _validate_selected_device(call)
        coordinator = _coordinator(call.hass, owner)
        profile = await _selected_profile(call.hass, owner, call.data)
        request = _scan_request(
            _with_gateway_defaults(coordinator, call.data, profile),
            safety_confirmed=True,
            address=call.data["address"],
        )
        return await coordinator.start(request, profile)
    except (ValueError, GatewayBusyError, RuntimeError) as err:
        raise _as_home_assistant_error(err) from err


async def _handle_check_gateway(call: ServiceCall, owner: _Owner) -> ServiceResponse:
    await _authorize_physical(call, "esphome")
    try:
        return await _coordinator(call.hass, owner).check_gateway(call.data["gateway_id"])
    except ValueError as err:
        raise _as_home_assistant_error(err) from err
    except GatewayProviderError as err:
        report_gateway_issue(call.hass, call.data["gateway_id"], err.code)
        raise HomeAssistantError(
            str(err),
            translation_domain=DOMAIN,
            translation_key="gateway_failure",
            translation_placeholders={"code": err.code},
        ) from err
    except GatewayBusyError as err:
        raise HomeAssistantError(str(err)) from err


async def _handle_set_pausable_pollers(call: ServiceCall, owner: _Owner) -> ServiceResponse:
    await _authorize_physical(call, "esphome")
    try:
        return _coordinator(call.hass, owner).save_poller_selection(
            call.data["gateway_id"], call.data["bus"], call.data["pause_pollers"]
        )
    except ValueError as err:
        raise _as_home_assistant_error(err) from err


async def _handle_get_history(call: ServiceCall, owner: _Owner) -> ServiceResponse:
    return _coordinator(call.hass, owner).history()


def _profile_error(err: Exception) -> HomeAssistantError:
    if isinstance(err, DeviceProfileNotFoundError):
        err = ValueError(str(err))
    return _as_home_assistant_error(err)


async def _handle_list_device_profiles(call: ServiceCall, owner: _Owner) -> ServiceResponse:
    store = await _profile_store(call.hass, owner)
    return {"profiles": [profile.as_dict() for profile in store.profiles()]}


async def _handle_import_device_profile(call: ServiceCall, owner: _Owner) -> ServiceResponse:
    await _require_active_user(call)
    store = await _profile_store(call.hass, owner)
    try:
        profile, replaced = await store.async_import(call.data["profile"])
    except DeviceProfileError as err:
        raise ServiceValidationError(
            str(err),
            translation_domain=DOMAIN,
            translation_key="invalid_request",
            translation_placeholders={"reason": str(err)},
        ) from err
    except ValueError as err:
        raise _profile_error(err) from err
    return {"profile": profile.as_dict(), "replaced": replaced}


async def _handle_export_device_profile(call: ServiceCall, owner: _Owner) -> ServiceResponse:
    store = await _profile_store(call.hass, owner)
    try:
        return {"profile": store.get(call.data["profile_id"]).export()}
    except DeviceProfileNotFoundError as err:
        raise _profile_error(err) from err


async def _handle_delete_device_profile(call: ServiceCall, owner: _Owner) -> ServiceResponse:
    await _require_active_user(call)
    store = await _profile_store(call.hass, owner)
    coordinator = _coordinator(call.hass, owner)

    def refuse_if_running(profile_id: str) -> None:
        if scan_id := coordinator.profile_in_use(profile_id):
            raise ValueError(
                f"Device Profile {profile_id} is used by running Scan {scan_id}; "
                "cancel the Scan or wait for it to finish first"
            )

    try:
        await store.async_delete(call.data["profile_id"], refuse_if_running)
    except (ValueError, DeviceProfileNotFoundError) as err:
        raise _profile_error(err) from err
    return {"deleted": call.data["profile_id"]}


_SERVICE_DEFINITIONS = (
    (
        SERVICE_LIST_DEVICE_PROFILES,
        _handle_list_device_profiles,
        vol.Schema({}),
        SupportsResponse.ONLY,
    ),
    (
        SERVICE_IMPORT_DEVICE_PROFILE,
        _handle_import_device_profile,
        _IMPORT_PROFILE_SCHEMA,
        SupportsResponse.OPTIONAL,
    ),
    (
        SERVICE_EXPORT_DEVICE_PROFILE,
        _handle_export_device_profile,
        _PROFILE_ID_SCHEMA,
        SupportsResponse.ONLY,
    ),
    (
        SERVICE_DELETE_DEVICE_PROFILE,
        _handle_delete_device_profile,
        _PROFILE_ID_SCHEMA,
        SupportsResponse.OPTIONAL,
    ),
    (
        "check_gateway",
        _handle_check_gateway,
        vol.Schema({vol.Required("gateway_id"): str}),
        SupportsResponse.ONLY,
    ),
    ("get_history", _handle_get_history, vol.Schema({}), SupportsResponse.ONLY),
    (
        SERVICE_SET_PAUSABLE_POLLERS,
        _handle_set_pausable_pollers,
        vol.Schema(
            {
                vol.Required("gateway_id"): str,
                vol.Required("bus"): str,
                vol.Required("pause_pollers"): _POLLER_INDICES,
            }
        ),
        SupportsResponse.OPTIONAL,
    ),
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
    """Register the public services bound to one owner generation."""
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
    expected_owner = None if entry_id is None or generation is None else (entry_id, generation)
    if expected_owner is not None and domain_data.get(DATA_SERVICE_OWNER) != expected_owner:
        return
    domain_data.pop(DATA_SERVICES_AVAILABLE, None)
    domain_data.pop(DATA_SERVICE_OWNER, None)
    for service in PUBLIC_SERVICES:
        hass.services.async_remove(DOMAIN, service)
