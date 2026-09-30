"""HA-framework tests; isolated users/storage, not production HA login tests."""

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock

from homeassistant.auth.const import GROUP_ID_ADMIN, GROUP_ID_USER
from homeassistant.core import Context, ServiceCall
from homeassistant.exceptions import Unauthorized
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.woow_esphome_modbus_scanner.config_flow import gateway_input, gateway_schema
from custom_components.woow_esphome_modbus_scanner.const import DOMAIN
from custom_components.woow_esphome_modbus_scanner.history import ScanHistory
from custom_components.woow_esphome_modbus_scanner.modbus_scan.coordinator import (
    ModbusScanCoordinator,
)
from custom_components.woow_esphome_modbus_scanner.modbus_scan.mock_provider import (
    MockGatewayProvider,
)
from custom_components.woow_esphome_modbus_scanner.modbus_scan.models import ScanRequest
from custom_components.woow_esphome_modbus_scanner.services import (
    _authorize_physical,
    _handle_test_address,
)


@pytest.mark.parametrize(
    "admin,active,automation,has_user,allowed",
    [
        (True, True, False, True, True),
        (False, True, False, True, True),
        (True, False, False, True, False),
        (False, True, True, True, True),
        (False, True, False, False, True),
        (False, True, True, False, True),
    ],
)
async def test_backend_physical_permissions(hass, admin, active, automation, has_user, allowed):
    entry = MockConfigEntry(domain=DOMAIN, data={"allow_physical_automation": automation})
    entry.add_to_hass(hass)
    await hass.auth.async_create_user("isolated owner")
    user = await hass.auth.async_create_user(
        "isolated scanner test", group_ids=[GROUP_ID_ADMIN if admin else GROUP_ID_USER]
    )
    await hass.auth.async_update_user(user, is_active=active)
    call = ServiceCall(
        hass,
        DOMAIN,
        "test_address",
        {"provider": "esphome"},
        context=Context(user_id=user.id if has_user else None),
    )
    if allowed:
        await _authorize_physical(call, (entry.entry_id, 1), "esphome")
    else:
        with pytest.raises(Unauthorized):
            await _handle_test_address(call, (entry.entry_id, 1))
        assert DOMAIN not in hass.data  # Rejected before coordinator/transport construction.
    await _authorize_physical(call, (entry.entry_id, 1), "mock")


def test_secret_retention_is_by_mac_and_never_rendered():
    key = "A" * 43 + "="
    existing = [{"host": "192.0.2.1", "mac": "AA:BB:CC:DD:EE:FF", "noise_psk": key}]
    data = {"host": "192.0.2.2", "mac": existing[0]["mac"]}
    gateways, error = gateway_input(data, existing)
    assert error is None and gateways[0]["noise_psk"] == key
    defaults = {
        str(field): field.default()
        for field in gateway_schema(existing).schema
        if callable(getattr(field, "default", None))
    }
    assert key not in repr(defaults)
    gateways, error = gateway_input({**data, "clear_psk": True}, existing)
    assert error is None and "noise_psk" not in gateways[0]
    assert (
        gateway_input({**data, "noise_psk": key, "clear_psk": True}, existing)[1]
        == "conflicting_psk"
    )
    assert gateway_input({**data, "noise_psk": "not-a-key"}, existing)[1] == "invalid_psk"
    gateways, error = gateway_input({**data, "mac": "AA:BB:CC:DD:EE:00"}, existing)
    assert error is None and "noise_psk" not in gateways[0]


def history(hass):
    value = ScanHistory(hass)
    value.store = MagicMock()
    value.store.async_load = AsyncMock(return_value=None)
    value.store.async_save = AsyncMock()
    return value


async def test_terminal_history_survives_new_coordinator_without_replay(hass):
    saved = history(hass)
    coordinator = ModbusScanCoordinator(hass, [MockGatewayProvider()], history=saved)
    request = ScanRequest(
        "mock", "mock:rs485-gateway", 1, 1, safety_confirmed=True, inter_request_delay_ms=0
    )
    started = await coordinator.start(request)
    await asyncio.gather(*coordinator._tasks.values())
    record = saved.get(started["scan_id"])
    assert record["status"]["status"] == "completed"
    restored = history(hass)
    restored.store.async_load.return_value = deepcopy(saved._data())
    await restored.async_load()
    replacement = ModbusScanCoordinator(hass, [MockGatewayProvider()], history=restored)
    assert replacement.status(started["scan_id"])["status"] == "completed"
    assert replacement.results(started["scan_id"])["responders"]
    assert not replacement._tasks
    assert (await replacement.cancel(started["scan_id"]))["status"] == "completed"
    record["status"]["status"] = "modified"
    assert saved.get(started["scan_id"])["status"]["status"] == "completed"


async def test_persisted_start_becomes_interrupted_not_replayed(hass):
    saved = history(hass)
    coordinator = ModbusScanCoordinator(hass, [MockGatewayProvider()], history=saved)
    started = await coordinator.start(
        ScanRequest("mock", "mock:rs485-gateway", 1, 12, safety_confirmed=True)
    )
    checkpoint = deepcopy(saved._data())
    await coordinator.async_shutdown()
    restored = history(hass)
    restored.store.async_load.return_value = checkpoint
    await restored.async_load()
    record = restored.get(started["scan_id"])
    assert record["status"]["error_info"]["code"] == "INTERRUPTED"
    assert record["status"]["progress_is_checkpoint"]
    assert not restored.pending


async def test_corrupt_history_and_disk_errors_do_not_break_live_operation(hass):
    saved = history(hass)
    saved.store.async_load.return_value = {"records": [{"status": "invalid"}]}
    await saved.async_load()
    assert saved.load_error and not saved.records
    saved.store.async_save.side_effect = OSError("private path not exposed")
    await saved.async_flush()
    assert saved.load_error


async def test_history_bounds_and_storage_faults(hass):
    saved = history(hass)
    coordinator = ModbusScanCoordinator(hass, [MockGatewayProvider()], history=saved)
    first = None
    for _ in range(21):
        started = await coordinator.start(
            ScanRequest(
                "mock", "mock:rs485-gateway", 1, 1, safety_confirmed=True, inter_request_delay_ms=0
            )
        )
        first = first or started["scan_id"]
        await asyncio.gather(*coordinator._tasks.values())
    assert len(saved.records) == 20 and saved.get(first) is None
    saved.remember({}, {})
    assert saved.load_error
    record = next(iter(saved.records.values()))
    saved.store.async_delay_save.side_effect = OSError("PRIVATE")
    saved.remember(record["status"], record["results"])
    assert saved.load_error
    restored = history(hass)
    restored.store.async_load.side_effect = OSError("PRIVATE")
    await restored.async_load()
    assert restored.load_error
    restored.store.async_load.side_effect = None
    restored.store.async_load.return_value = {"records": "invalid"}
    await restored.async_load()
    assert not restored.records


async def test_repairs_are_actionable_and_auth_triggers_reauth(hass, monkeypatch):
    from unittest.mock import Mock

    from homeassistant.helpers import issue_registry as ir

    from custom_components.woow_esphome_modbus_scanner.issues import report_gateway_issue

    entry = MockConfigEntry(
        domain=DOMAIN, data={"gateways": [{"mac": "AA:BB:CC:DD:EE:FF", "host": "192.0.2.1"}]}
    )
    entry.add_to_hass(hass)
    reauth = Mock()
    monkeypatch.setattr(type(entry), "async_start_reauth", reauth)
    report_gateway_issue(hass, "esphome:aabbccddeeff", "API_AUTH_FAILED")
    reauth.assert_called_once_with(hass)
    assert any(domain == DOMAIN for domain, _ in ir.async_get(hass).issues)
    report_gateway_issue(hass, "esphome:aabbccddeeff", None)
    assert not any(domain == DOMAIN for domain, _ in ir.async_get(hass).issues)
