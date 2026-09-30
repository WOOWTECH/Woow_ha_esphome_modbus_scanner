"""Graceful shutdown must not skip a provider's normal-poll recovery."""

import asyncio

from custom_components.woow_esphome_modbus_scanner.modbus_scan.coordinator import (
    ModbusScanCoordinator,
)
from custom_components.woow_esphome_modbus_scanner.modbus_scan.mock_provider import (
    MockGatewayProvider,
)
from custom_components.woow_esphome_modbus_scanner.modbus_scan.models import ScanRequest


async def test_shutdown_preserves_cooperative_recovery(hass):
    class Recovering(MockGatewayProvider):
        supports_progress = True

        async def run_scan(self, request, emit, cancelled, *, progress):
            while not cancelled():
                await asyncio.sleep(0)
            assert not asyncio.current_task().cancelling()
            await asyncio.sleep(0.01)
            progress({"recovery_status": "verified", "cleanup_status": "closed"})

    coordinator = ModbusScanCoordinator(hass, [Recovering()])
    started = await coordinator.start(ScanRequest.mock(end_id=3))
    await coordinator.async_shutdown()
    status = coordinator.status(started["scan_id"])
    assert status["status"] == "cancelled"
    assert status["recovery_status"] == "verified"
    assert status["cleanup_status"] == "closed"


async def test_shutdown_forces_noncooperative_work_after_grace(hass, monkeypatch):
    monkeypatch.setattr(
        "custom_components.woow_esphome_modbus_scanner.modbus_scan.coordinator.SHUTDOWN_GRACE_SECONDS",
        0.01,
    )

    class Stalled(MockGatewayProvider):
        async def run_scan(self, request, emit, cancelled):
            await asyncio.Event().wait()

    coordinator = ModbusScanCoordinator(hass, [Stalled()])
    started = await coordinator.start(ScanRequest.mock(end_id=3))
    await asyncio.wait_for(coordinator.async_shutdown(), 1)
    assert coordinator.status(started["scan_id"])["status"] == "cancelled"
    assert not coordinator._tasks
