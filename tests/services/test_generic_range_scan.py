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


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"register_address": 65534, "register_count": 3}, ServiceValidationError),
        ({"register_count": 5}, ServiceValidationError),
        ({"timeout_ms": 2001}, ServiceValidationError),
        ({"probe_type": "device_identification"}, ServiceValidationError),
        ({"retries": 6}, vol.Invalid),
        ({"start_id": 0}, vol.Invalid),
        ({"end_id": 248}, vol.Invalid),
    ],
)
async def test_generic_limits_are_enforced_before_any_bus_traffic(hass, gateway, changes, error):
    call = await _setup(hass)
    with pytest.raises(error):
        await _start_scan(call, **{"start_id": 1, "end_id": 10, **changes})
    assert FakeClient.instances == []


async def test_highest_register_block_ending_at_65535_is_accepted(hass, gateway):
    call = await _setup(hass)
    started = await _start_scan(
        call, start_id=1, end_id=1, register_address=65532, register_count=4
    )
    await _settle(hass)
    [probe] = gateway.probes
    assert (probe["register"], probe["count"]) == (65532, 4)
    status = await call("get_scan_status", {"scan_id": started["scan_id"]})
    assert status["status"] == "completed"
