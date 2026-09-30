"""New public seams under real HA core with a fake physical provider."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.core import Context
from homeassistant.exceptions import ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.woow_esphome_modbus_scanner.const import DATA_COORDINATOR, DOMAIN
from custom_components.woow_esphome_modbus_scanner.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.woow_esphome_modbus_scanner.modbus_scan.esphome_provider import (
    ESPHomeGatewayProvider,
)
from custom_components.woow_esphome_modbus_scanner.modbus_scan.models import (
    ProbeResult,
    ScanOutcome,
)
from custom_components.woow_esphome_modbus_scanner.services import async_register_services


async def test_physical_defaults_progress_history_and_check_service(hass, monkeypatch):
    entry = MockConfigEntry(
        domain=DOMAIN, data={"gateways": [{"host": "192.0.2.1", "mac": "AA:BB:CC:DD:EE:FF"}]}
    )
    entry.add_to_hass(hass)
    user = await hass.auth.async_create_user("isolated owner")
    context = Context(user_id=user.id)
    requests = []

    async def fake_run(self, request, emit, cancelled, *, progress):
        requests.append(request)
        progress({"operation_phase": "probe", "current_address": 1, "attempt": 1})
        emit(
            ProbeResult(
                1,
                ScanOutcome.RESPONDED,
                10,
                "synthetic",
                register_address=0x6201,
                raw_value=0,
                attempts=1,
            )
        )
        progress({"recovery_status": "verified", "cleanup_status": "closed"})

    monkeypatch.setattr(ESPHomeGatewayProvider, "run_scan", fake_run)
    monkeypatch.setattr(
        ESPHomeGatewayProvider, "check_gateway", AsyncMock(return_value={"api_status": "verified"})
    )
    async_register_services(hass, entry.entry_id)

    async def call(service, data=None):
        return await hass.services.async_call(
            DOMAIN, service, data or {}, blocking=True, return_response=True, context=context
        )

    gateways = await call("list_gateways")
    assert gateways["gateways"][1]["can_operate"]
    selected = {"provider": "esphome", "gateway_id": "esphome:aabbccddeeff"}
    started = await call("test_address", {**selected, "address": 1})
    coordinator = hass.data[DOMAIN][DATA_COORDINATOR]
    await asyncio.gather(*coordinator._tasks.values())
    request = requests[0]
    assert request.register_address == 0x6201 and request.timeout_ms == 700
    assert request.pause_normal_polling and request.retries == 0
    status = await call("get_scan_status", {"scan_id": started["scan_id"]})
    assert status["recovery_status"] == "verified" and status["attempt"] == 1
    assert (await call("get_history"))["scans"]
    assert (await call("check_gateway", {"gateway_id": selected["gateway_id"]}))["health"][
        "api_status"
    ] == "verified"
    with pytest.raises(ServiceValidationError):
        await call("test_address", {**selected, "address": 1, "register_count": 2})


async def test_diagnostics_omit_identity_keys_and_raw_error_details(hass):
    secret = "PRIVATE_DIAGNOSTIC_MARKER"
    entry = MockConfigEntry(domain=DOMAIN, data={"noise_psk": secret})
    gateway = {
        "gateway_id": secret,
        "host": secret,
        "name": secret,
        "provider": "esphome",
        "health": {
            "encrypted": True,
            "error_info": {"code": "API_AUTH_FAILED", "message": secret},
            "firmware_state": {"raw": secret},
        },
        "profile": {"profile_hash": "a" * 64},
    }
    fake = SimpleNamespace(list_gateways=lambda: {"gateways": [gateway]})
    history = SimpleNamespace(
        load_error=False,
        summaries=lambda: [
            {"status": "failed", "error": secret, "gateway_id": secret, "responders": [secret]}
        ],
    )
    hass.data[DOMAIN] = {DATA_COORDINATOR: fake, "history": history}
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert secret not in json.dumps(diagnostics)
    assert diagnostics["gateways"][0]["error_code"] == "API_AUTH_FAILED"
    assert diagnostics["gateways"][0]["encrypted"] is True
