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


async def _outcomes(scenario: str, start: int = 1, end: int = 12):
    provider = MockGatewayProvider(step_delay_ms=0)
    request = ScanRequest.mock(start_id=start, end_id=end, scenario=scenario)
    outcomes = []
    await provider.run_scan(request, outcomes.append, lambda: False)
    return outcomes


async def test_default_scenario_reports_known_responders():
    # The default probe is an FC03 holding-register read, so no Responder is identified.
    outcomes = await _outcomes("found_default")
    assert [(item.address, item.outcome.value) for item in outcomes if item.is_responder] == [
        (1, "responded"),
        (3, "responded"),
        (5, "modbus_exception"),
        (12, "responded"),
    ]


async def test_gateway_metadata_advertises_scenarios_and_read_only_probes():
    gateway = MockGatewayProvider().list_gateways()[0]
    assert gateway.gateway_id == "mock:rs485-gateway"
    assert gateway.provider == "mock"
    assert "found_default" in gateway.mock_scenarios
    assert "holding_register" in gateway.capabilities


async def test_all_offline_is_all_timeouts():
    outcomes = await _outcomes("all_offline", 1, 4)
    assert [item.outcome.value for item in outcomes] == ["timeout"] * 4
    assert not any(item.is_responder for item in outcomes)


@pytest.mark.parametrize(
    ("scenario", "end", "expected"),
    [
        ("partial_timeout", 42, [2, 7, 11, 21, 42]),
        ("modbus_exception", 17, [4, 9, 17]),
    ],
)
async def test_scenario_responder_addresses_are_stable(scenario, end, expected):
    outcomes = await _outcomes(scenario, 1, end)
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
        inter_request_delay_ms=3_000,
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


async def test_mock_specific_scenario_validation_lives_in_mock_provider():
    provider = MockGatewayProvider(step_delay_ms=0)
    request = ScanRequest.mock(scenario="not-a-scenario")

    with pytest.raises(ValueError, match="mock_scenario"):
        await provider.run_scan(request, lambda _result: None, lambda: False)
