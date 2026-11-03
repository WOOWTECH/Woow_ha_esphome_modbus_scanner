"""Range Scans with the Generic Device Profile through the HA service seam.

The v2 Gateway is the fake from ``test_bridge_v2`` (built from the shared contract file).
"""

from homeassistant.exceptions import ServiceValidationError
import pytest
from test_bridge_v2 import (  # noqa: F401 - gateway is a fixture
    GATEWAY_ID,
    FakeClient,
    _settle,
    _setup,
    gateway,
)
import voluptuous as vol


async def _start_scan(call, **fields):
    return await call(
        "start_scan",
        {
            "provider": "esphome",
            "gateway_id": GATEWAY_ID,
            "inter_request_delay_ms": 0,
            # The fake's responder at ID 7 answers with two registers.
            "register_count": 2,
            "safety_confirmed": True,
            **fields,
        },
    )


async def test_range_above_32_ids_needs_the_large_range_confirmation(hass, gateway):
    call = await _setup(hass)
    with pytest.raises(ServiceValidationError, match="large_range_confirmed"):
        await _start_scan(call, start_id=1, end_id=33)
    assert FakeClient.instances == []


@pytest.mark.parametrize("value", [1, "true", False])
async def test_large_range_confirmation_requires_exact_boolean_true(hass, gateway, value):
    call = await _setup(hass)
    with pytest.raises(vol.Invalid):
        await _start_scan(call, start_id=1, end_id=33, large_range_confirmed=value)
    assert FakeClient.instances == []


async def test_range_of_32_ids_needs_only_safety_confirmation(hass, gateway):
    call = await _setup(hass)
    started = await _start_scan(call, start_id=1, end_id=32)
    await _settle(hass)
    status = await call("get_scan_status", {"scan_id": started["scan_id"]})
    assert (status["status"], status["total_addresses"], status["error"]) == ("completed", 32, None)
