"""Provider-contract tests for the deterministic mock adapter."""

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.woow_esphome_modbus_scanner.modbus_scan.mock_provider import (
    MockGatewayProvider,
)
from custom_components.woow_esphome_modbus_scanner.modbus_scan.models import ScanRequest
from custom_components.woow_esphome_modbus_scanner.modbus_scan.provider import (
    GatewayProviderError,
)


async def _outcomes(profile: str, start: int = 1, end: int = 12):
    provider = MockGatewayProvider(step_delay_ms=0)
    request = ScanRequest.mock(start_id=start, end_id=end, profile=profile)
    outcomes = []
    await provider.run_scan(request, outcomes.append, lambda: False)
    return outcomes


async def test_default_profile_reports_known_responders():
    outcomes = await _outcomes("found_default")
    assert [(item.address, item.outcome.value) for item in outcomes if item.is_responder] == [
        (1, "identified"),
        (3, "responded"),
        (5, "modbus_exception"),
        (12, "identified"),
    ]


async def test_gateway_metadata_advertises_profiles_and_read_only_probes():
    gateway = MockGatewayProvider().list_gateways()[0]
    assert gateway.gateway_id == "mock:rs485-gateway"
    assert gateway.provider == "mock"
    assert "found_default" in gateway.mock_profiles
    assert "holding_register" in gateway.capabilities


async def test_all_offline_is_all_timeouts():
    outcomes = await _outcomes("all_offline", 1, 4)
    assert [item.outcome.value for item in outcomes] == ["timeout"] * 4
    assert not any(item.is_responder for item in outcomes)


@pytest.mark.parametrize(
    ("profile", "end", "expected"),
    [
        ("partial_timeout", 42, [2, 7, 11, 21, 42]),
        ("modbus_exception", 17, [4, 9, 17]),
    ],
)
async def test_profile_responder_addresses_are_stable(profile, end, expected):
    outcomes = await _outcomes(profile, 1, end)
    assert [item.address for item in outcomes if item.is_responder] == expected


async def test_collision_is_reported_without_claiming_uniqueness():
    outcomes = await _outcomes("possible_collision", 6, 8)
    collision = next(item for item in outcomes if item.address == 7)
    assert collision.outcome.value == "possible_collision"
    assert "duplicate" in collision.detail


async def test_disconnect_raises_provider_error_at_a_stable_address():
    with pytest.raises(GatewayProviderError, match="disconnected") as raised:
        await _outcomes("gateway_disconnect", 1, 12)
    assert raised.value.address == 4


async def test_cancellation_is_observed_between_addresses():
    provider = MockGatewayProvider(step_delay_ms=0)
    request = ScanRequest.mock(start_id=1, end_id=20)
    outcomes = []

    def cancelled():
        return len(outcomes) == 3

    await provider.run_scan(request, outcomes.append, cancelled)
    assert [item.address for item in outcomes] == [1, 2, 3]


async def test_single_address_has_no_inter_request_delay():
    provider = MockGatewayProvider(step_delay_ms=0)
    request = ScanRequest.mock(
        start_id=3,
        end_id=3,
        inter_request_delay_ms=5_000,
    )
    sleep = AsyncMock()

    with patch(
        "custom_components.woow_esphome_modbus_scanner.modbus_scan.mock_provider.asyncio.sleep",
        sleep,
    ):
        outcomes = []
        await provider.run_scan(request, outcomes.append, lambda: False)

    assert [item.address for item in outcomes] == [3]
    sleep.assert_not_awaited()


async def test_mock_specific_profile_validation_lives_in_mock_provider():
    provider = MockGatewayProvider(step_delay_ms=0)
    request = ScanRequest.mock(profile="not-a-profile")

    with pytest.raises(ValueError, match="mock_profile"):
        await provider.run_scan(request, lambda _result: None, lambda: False)
