"""Legacy Gateway provider (Bridge Protocol v1) against a fake aioesphomeapi client.

Folded in from the former ``tools/test_bridge.py`` bench tests. Every provider response here
is FAKE, not hardware acceptance evidence; the HA service seam is covered by
``tests/services/test_legacy_v1_adapter.py``.
"""

import asyncio
from dataclasses import replace
import json
from types import SimpleNamespace

from aioesphomeapi import (
    TextSensorInfo,
    TextSensorState,
    UserService,
    UserServiceArg,
    UserServiceArgType,
)
import pytest

from custom_components.woow_esphome_modbus_scanner.modbus_scan.legacy_v1.provider import (
    ESPHomeGateway,
    ESPHomeGatewayProvider,
)
from custom_components.woow_esphome_modbus_scanner.modbus_scan.models import (
    ProbeType,
    ScanRequest,
)
from custom_components.woow_esphome_modbus_scanner.modbus_scan.provider import (
    GatewayProviderError,
)

GATEWAY = ESPHomeGateway("192.0.2.1", "AA:BB:CC:DD:EE:FF")
REQUEST = ScanRequest(
    "esphome",
    GATEWAY.gateway_id,
    1,
    1,
    probe_type=ProbeType.HOLDING_REGISTER,
    register_address=0x6201,
    timeout_ms=700,
    retries=0,
    pause_normal_polling=True,
    safety_confirmed=True,
)


class FakeClient:
    """aioesphomeapi client boundary of a Legacy Gateway running bridge v1 firmware."""

    mac = GATEWAY.mac
    outcome = "responded"
    services_present = True

    def __init__(self, *args):
        self.calls = []
        self.closed = False

    async def connect(self, **kwargs):
        self.on_stop = kwargs["on_stop"]

    async def device_info(self):
        return SimpleNamespace(mac_address=self.mac)

    async def list_entities_services(self):
        service = UserService(
            name="modbus_scanner_probe_v1",
            key=10,
            args=[
                UserServiceArg("request_id", UserServiceArgType.STRING),
                UserServiceArg("slave", UserServiceArgType.INT),
                UserServiceArg("reg", UserServiceArgType.INT),
            ],
        )
        services = [service] if self.services_present else []
        return [TextSensorInfo(key=1, name="Modbus Scanner Result")], services

    def subscribe_states(self, callback):
        self.callback = callback

    async def execute_service(self, service, data):
        self.calls.append(data)
        # The initial state subscription may arrive after the probe was sent.
        self.callback(TextSensorState(key=1, state="", missing_state=True))
        self.callback(TextSensorState(key=1, state=""))
        payload = dict(
            v=1,
            id="0" * 32,
            slave=data["slave"],
            reg=data["reg"],
            latency_ms=12,
            value=1,
            exception=2,
            outcome=self.outcome,
        )
        self.callback(TextSensorState(key=1, state=json.dumps(payload)))  # Stale: ignore.
        payload["id"] = data["request_id"]
        self.callback(TextSensorState(key=1, state=json.dumps(payload)))

    async def disconnect(self):
        self.closed = True


async def _run(client, request=REQUEST, cancelled=lambda: False):
    results = []
    provider = ESPHomeGatewayProvider([GATEWAY], client_factory=lambda *a: client)
    await provider.run_scan(request, results.append, cancelled)
    return results


async def test_correlated_response_is_the_result():
    client = FakeClient()
    results = await _run(client)
    assert len(results) == 1
    assert results[0].outcome == "responded"
    assert "0x6201 = 1" in results[0].detail
    assert client.closed


async def test_correlated_reply_for_another_register_fails():
    class WrongRegister(FakeClient):
        async def execute_service(self, service, data):
            payload = dict(
                v=1,
                id=data["request_id"],
                slave=data["slave"],
                reg=0x6202,
                latency_ms=1,
                value=1,
                outcome="responded",
            )
            self.callback(TextSensorState(key=1, state=json.dumps(payload)))

    client = WrongRegister()
    with pytest.raises(GatewayProviderError):
        await _run(client)
    assert client.closed


async def test_connection_loss_is_not_a_slave_timeout():
    class LostClient(FakeClient):
        async def execute_service(self, service, data):
            await self.on_stop(False)

    client = LostClient()
    with pytest.raises(GatewayProviderError, match="connection lost"):
        await _run(client)
    assert client.closed


async def test_task_cancellation_disconnects():
    sent = asyncio.Event()

    class WaitingClient(FakeClient):
        async def execute_service(self, service, data):
            sent.set()

    client = WaitingClient()
    task = asyncio.create_task(_run(client))
    await asyncio.wait_for(sent.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client.closed


async def test_mac_mismatch_sends_no_probe():
    client = FakeClient()
    client.mac = "00:00:00:00:00:00"
    with pytest.raises(GatewayProviderError):
        await _run(client)
    assert not client.calls
    assert client.closed


async def test_missing_probe_service_sends_no_probe():
    client = FakeClient()
    client.services_present = False
    with pytest.raises(GatewayProviderError):
        await _run(client)
    assert not client.calls
    assert client.closed


async def test_timeout_retries_are_bounded_with_fresh_request_ids():
    client = FakeClient()
    client.outcome = "timeout"
    results = await _run(client, replace(REQUEST, retries=2))
    assert len(client.calls) == 3
    assert results[0].outcome == "timeout"
    assert len({call["request_id"] for call in client.calls}) == 3


async def test_modbus_exception_is_evidence():
    client = FakeClient()
    client.outcome = "modbus_exception"
    results = await _run(client)
    assert results[0].exception_code == 2


async def test_gateway_error_is_not_a_timeout():
    client = FakeClient()
    client.outcome = "gateway_error"
    with pytest.raises(GatewayProviderError):
        await _run(client)
    assert client.closed


async def test_range_probes_exactly_the_requested_ids():
    client = FakeClient()
    results = await _run(client, replace(REQUEST, end_id=3, inter_request_delay_ms=0))
    assert [result.address for result in results] == [1, 2, 3]


async def test_cancel_before_the_first_probe_sends_nothing():
    client = FakeClient()
    results = await _run(client, cancelled=lambda: True)
    assert results == []
    assert not client.calls


@pytest.mark.parametrize(
    "changes",
    [
        dict(end_id=33),
        dict(register_address=0),
        dict(timeout_ms=500),
        dict(register_count=2),
        dict(pause_normal_polling=False),
        dict(probe_type=ProbeType.DEVICE_IDENTIFICATION),
    ],
)
async def test_unsupported_request_is_rejected_before_any_probe(changes):
    client = FakeClient()
    with pytest.raises(ValueError):
        await _run(client, replace(REQUEST, **changes))
    assert not client.calls
