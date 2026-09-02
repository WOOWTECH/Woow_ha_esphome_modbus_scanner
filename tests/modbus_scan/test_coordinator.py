"""Public coordinator lifecycle tests."""

import asyncio
import json

import pytest

from custom_components.woow_esphome_modbus_scanner.modbus_scan.coordinator import (
    GatewayBusyError,
    ModbusScanCoordinator,
    ScanNotFoundError,
)
from custom_components.woow_esphome_modbus_scanner.modbus_scan.mock_provider import (
    MockGatewayProvider,
)
from custom_components.woow_esphome_modbus_scanner.modbus_scan.models import (
    GatewayInfo,
    ProbeResult,
    ScanOutcome,
    ScanRequest,
)
from custom_components.woow_esphome_modbus_scanner.modbus_scan.provider import (
    GatewayProviderError,
)


class _FakeProvider:
    provider_id = "fake"

    def __init__(self, run):
        self._run = run

    def list_gateways(self):
        return (
            GatewayInfo(
                provider=self.provider_id,
                gateway_id="fake:gateway",
                name="Fake gateway",
                capabilities=("device_identification",),
            ),
        )

    async def run_scan(self, request, emit, cancelled):
        await self._run(request, emit, cancelled)


def _fake_request(**changes):
    values = {
        "provider": "fake",
        "gateway_id": "fake:gateway",
        "start_id": 1,
        "end_id": 2,
        "safety_confirmed": True,
        "inter_request_delay_ms": 0,
    }
    values.update(changes)
    return ScanRequest(**values)


def _coordinator(hass, *, delay=0, history=20):
    return ModbusScanCoordinator(
        hass, [MockGatewayProvider(step_delay_ms=delay)], max_history=history
    )


async def test_scan_runs_in_background_and_returns_normalized_results(hass):
    coordinator = _coordinator(hass)
    scan = await coordinator.start(ScanRequest.mock())
    assert scan["status"] == "running"
    await coordinator.wait(scan["scan_id"])
    result = coordinator.results(scan["scan_id"])
    assert [hit["address"] for hit in result["responders"]] == [1, 3, 5, 12]
    assert result["uniqueness_guaranteed"] is False


async def test_one_active_scan_per_gateway(hass):
    coordinator = _coordinator(hass, delay=20)
    first = await coordinator.start(ScanRequest.mock(end_id=20))
    with pytest.raises(GatewayBusyError, match=first["scan_id"]):
        await coordinator.start(ScanRequest.mock(end_id=2))
    await coordinator.cancel(first["scan_id"])
    await coordinator.wait(first["scan_id"])


async def test_status_tracks_progress_and_terminal_counts(hass):
    coordinator = _coordinator(hass)
    scan = await coordinator.start(ScanRequest.mock(end_id=3))
    done = await coordinator.wait(scan["scan_id"])
    assert done["status"] == "completed"
    assert done["completed_addresses"] == 3
    assert done["progress_percent"] == 100.0
    assert done["outcome_counts"]["identified"] == 1
    assert done["outcome_counts"]["timeout"] == 1


async def test_cancellation_reaches_terminal_cancelled_state(hass):
    coordinator = _coordinator(hass, delay=20)
    scan = await coordinator.start(ScanRequest.mock(end_id=30))
    requested = await coordinator.cancel(scan["scan_id"])
    assert requested["cancellation_requested"] is True
    done = await coordinator.wait(scan["scan_id"])
    assert done["status"] == "cancelled"
    assert done["completed_addresses"] < done["total_addresses"]


async def test_provider_failure_is_isolated_and_published(hass):
    coordinator = _coordinator(hass)
    scan = await coordinator.start(
        ScanRequest.mock(end_id=12, profile="gateway_disconnect")
    )
    done = await coordinator.wait(scan["scan_id"])
    assert done["status"] == "failed"
    assert done["outcome_counts"]["gateway_error"] == 1
    assert "disconnected" in done["error"]


def test_unknown_scan_id_is_clear(hass):
    coordinator = _coordinator(hass)
    with pytest.raises(ScanNotFoundError, match="unknown",):
        coordinator.status("unknown")


async def test_terminal_history_is_bounded(hass):
    coordinator = _coordinator(hass, history=2)
    ids = []
    for address in (1, 2, 3):
        scan = await coordinator.start(ScanRequest.mock(start_id=address, end_id=address))
        ids.append(scan["scan_id"])
        await coordinator.wait(scan["scan_id"])
    with pytest.raises(ScanNotFoundError):
        coordinator.status(ids[0])
    assert coordinator.status(ids[-1])["status"] == "completed"


async def test_shutdown_cancels_and_awaits_active_work(hass):
    coordinator = _coordinator(hass, delay=100)
    scan = await coordinator.start(ScanRequest.mock(end_id=100))
    await coordinator.async_shutdown()
    assert coordinator.status(scan["scan_id"])["status"] == "cancelled"


@pytest.mark.parametrize("fails", [False, True])
async def test_immediate_provider_completion_does_not_leave_a_stale_task(hass, fails):
    async def run(request, emit, _cancelled):
        if fails:
            raise RuntimeError("immediate failure")
        emit(ProbeResult(request.start_id, ScanOutcome.TIMEOUT, 1, "complete"))

    coordinator = ModbusScanCoordinator(hass, [_FakeProvider(run)])
    started = await coordinator.start(_fake_request(start_id=1, end_id=1))
    done = await coordinator.wait(started["scan_id"])

    assert done["status"] == ("failed" if fails else "completed")
    assert started["scan_id"] not in coordinator._tasks


@pytest.mark.parametrize("emitted", [(), (1,)])
async def test_provider_success_requires_one_emission_per_requested_address(
    hass, emitted
):
    async def run(_request, emit, _cancelled):
        for address in emitted:
            emit(ProbeResult(address, ScanOutcome.TIMEOUT, 1, "partial"))

    coordinator = ModbusScanCoordinator(hass, [_FakeProvider(run)])
    started = await coordinator.start(_fake_request(start_id=1, end_id=2))
    done = await coordinator.wait(started["scan_id"])

    assert done["status"] == "failed"
    assert "Provider contract violation" in done["error"]
    assert "missing" in done["error"]


async def test_task_schedule_failure_rolls_back_scan_and_gateway_reservation(
    hass, monkeypatch
):
    coordinator = ModbusScanCoordinator(hass, [_FakeProvider(lambda *_args: None)])

    def reject_task(*_args, **_kwargs):
        raise RuntimeError("scheduler rejected task")

    monkeypatch.setattr(hass, "async_create_task", reject_task)
    with pytest.raises(RuntimeError, match="scheduler rejected"):
        await coordinator.start(_fake_request())

    assert coordinator._scans == {}
    assert coordinator._tasks == {}
    assert coordinator._active == {}


async def test_wait_caller_cancellation_does_not_cancel_scan(hass):
    release = asyncio.Event()

    async def run(request, emit, _cancelled):
        await release.wait()
        emit(
            ProbeResult(
                address=request.start_id,
                outcome=ScanOutcome.RESPONDED,
                latency_ms=1,
                detail="valid",
            )
        )

    coordinator = ModbusScanCoordinator(hass, [_FakeProvider(run)])
    started = await coordinator.start(_fake_request(start_id=1, end_id=1))
    waiter = asyncio.create_task(coordinator.wait(started["scan_id"]))
    await asyncio.sleep(0)
    waiter.cancel()

    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert coordinator.status(started["scan_id"])["status"] == "running"

    release.set()
    assert (await coordinator.wait(started["scan_id"]))["status"] == "completed"


@pytest.mark.parametrize(
    ("result", "message"),
    [
        (
            ProbeResult(0, ScanOutcome.RESPONDED, 1, "out of range"),
            "outside requested range",
        ),
        (
            ProbeResult(1, ScanOutcome.RESPONDED, True, "bad latency"),
            "latency_ms",
        ),
        (
            ProbeResult(1, ScanOutcome.IDENTIFIED, 1, "bad identity", identity={"x": 1}),
            "identity",
        ),
    ],
)
async def test_adversarial_provider_emissions_fail_safely(hass, result, message):
    async def run(_request, emit, _cancelled):
        emit(result)

    coordinator = ModbusScanCoordinator(hass, [_FakeProvider(run)])
    started = await coordinator.start(_fake_request(start_id=1, end_id=1))
    done = await coordinator.wait(started["scan_id"])

    assert done["status"] == "failed"
    assert message in done["error"]
    assert done["completed_addresses"] == 1
    json.dumps(coordinator.status(started["scan_id"]))
    json.dumps(coordinator.results(started["scan_id"]))


async def test_duplicate_emission_is_rejected_without_double_counting_address(hass):
    result = ProbeResult(1, ScanOutcome.RESPONDED, 1, "valid")

    async def run(_request, emit, _cancelled):
        emit(result)
        emit(result)

    coordinator = ModbusScanCoordinator(hass, [_FakeProvider(run)])
    started = await coordinator.start(_fake_request(start_id=1, end_id=1))
    done = await coordinator.wait(started["scan_id"])

    assert done["status"] == "failed"
    assert "duplicate" in done["error"].lower()
    assert done["completed_addresses"] == 1
    assert sum(done["outcome_counts"].values()) == 1


async def test_provider_gateway_error_is_not_double_counted(hass):
    async def run(_request, emit, _cancelled):
        emit(ProbeResult(1, ScanOutcome.GATEWAY_ERROR, 1, "disconnected"))
        raise GatewayProviderError("disconnected", address=1)

    coordinator = ModbusScanCoordinator(hass, [_FakeProvider(run)])
    started = await coordinator.start(_fake_request(start_id=1, end_id=1))
    done = await coordinator.wait(started["scan_id"])

    assert done["status"] == "failed"
    assert done["completed_addresses"] == 1
    assert done["outcome_counts"]["gateway_error"] == 1
    assert len(coordinator.results(started["scan_id"])["responders"]) == 0
