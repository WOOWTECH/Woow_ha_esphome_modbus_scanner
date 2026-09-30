"""Run: python -m unittest discover -s tools -p test_bridge.py -v.
All provider responses here are FAKE, not hardware acceptance evidence.
"""

import asyncio
from dataclasses import replace
import json
from types import SimpleNamespace
import unittest

from aioesphomeapi import (
    TextSensorInfo,
    TextSensorState,
    UserService,
    UserServiceArg,
    UserServiceArgType,
)
from bridge_runtime import (
    ESPHomeGateway,
    ESPHomeGatewayProvider,
    GatewayProviderError,
    ProbeType,
    ScanRequest,
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
        return [TextSensorInfo(key=1, name="Modbus Scanner Result")], [
            service
        ] if self.services_present else []

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


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def run_provider(self, client, request=REQUEST, cancelled=lambda: False):
        results = []
        provider = ESPHomeGatewayProvider([GATEWAY], client_factory=lambda *a: client)
        await provider.run_scan(request, results.append, cancelled)
        return results

    async def test_correlated_response(self):
        client = FakeClient()
        results = await self.run_provider(client)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].outcome, "responded")
        self.assertIn("0x6201 = 1", results[0].detail)
        self.assertTrue(client.closed)

    async def test_correlated_wrong_register_fails(self):
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
        with self.assertRaises(GatewayProviderError):
            await self.run_provider(client)
        self.assertTrue(client.closed)

    async def test_connection_loss_not_slave_timeout(self):
        class LostClient(FakeClient):
            async def execute_service(self, service, data):
                await self.on_stop(False)

        client = LostClient()
        with self.assertRaisesRegex(GatewayProviderError, "connection lost"):
            await self.run_provider(client)
        self.assertTrue(client.closed)

    async def test_task_cancellation_disconnects(self):
        sent = asyncio.Event()

        class WaitingClient(FakeClient):
            async def execute_service(self, service, data):
                sent.set()

        client = WaitingClient()
        task = asyncio.create_task(self.run_provider(client))
        await asyncio.wait_for(sent.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(client.closed)

    async def test_mac_mismatch_sends_nothing(self):
        client = FakeClient()
        client.mac = "00:00:00:00:00:00"
        with self.assertRaises(GatewayProviderError):
            await self.run_provider(client)
        self.assertFalse(client.calls)
        self.assertTrue(client.closed)

    async def test_missing_firmware_sends_nothing(self):
        client = FakeClient()
        client.services_present = False
        with self.assertRaises(GatewayProviderError):
            await self.run_provider(client)
        self.assertFalse(client.calls)
        self.assertTrue(client.closed)

    async def test_timeout_retries_bounded(self):
        client = FakeClient()
        client.outcome = "timeout"
        results = await self.run_provider(client, replace(REQUEST, retries=2))
        self.assertEqual(len(client.calls), 3)
        self.assertEqual(results[0].outcome, "timeout")
        self.assertEqual(len({x["request_id"] for x in client.calls}), 3)

    async def test_exception_is_evidence(self):
        client = FakeClient()
        client.outcome = "modbus_exception"
        results = await self.run_provider(client)
        self.assertEqual(results[0].exception_code, 2)

    async def test_gateway_error_not_timeout(self):
        client = FakeClient()
        client.outcome = "gateway_error"
        with self.assertRaises(GatewayProviderError):
            await self.run_provider(client)
        self.assertTrue(client.closed)

    async def test_range_exact(self):
        client = FakeClient()
        results = await self.run_provider(
            client, replace(REQUEST, end_id=3, inter_request_delay_ms=0)
        )
        self.assertEqual([r.address for r in results], [1, 2, 3])

    async def test_cancel_before_probe(self):
        client = FakeClient()
        results = await self.run_provider(client, cancelled=lambda: True)
        self.assertEqual(results, [])
        self.assertFalse(client.calls)

    async def test_reject_unsupported_before_connect(self):
        for changes in [
            dict(end_id=33),
            dict(register_address=0),
            dict(timeout_ms=500),
            dict(register_count=2),
            dict(pause_normal_polling=False),
            dict(probe_type=ProbeType.DEVICE_IDENTIFICATION),
        ]:
            client = FakeClient()
            with self.assertRaises(ValueError):
                await self.run_provider(client, replace(REQUEST, **changes))
            self.assertFalse(client.calls)


if __name__ == "__main__":
    unittest.main()
