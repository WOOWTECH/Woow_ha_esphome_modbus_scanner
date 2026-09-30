"""Synthetic transport evidence only: no TCP or RTU traffic."""

import asyncio
from dataclasses import replace
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aioesphomeapi import (
    TextSensorInfo,
    TextSensorState,
    UserService,
    UserServiceArg,
    UserServiceArgType,
)
import pytest

from custom_components.woow_esphome_modbus_scanner.modbus_scan.esphome_provider import (
    ESPHomeGateway,
    ESPHomeGatewayProvider,
)
from custom_components.woow_esphome_modbus_scanner.modbus_scan.health import HealthSession
from custom_components.woow_esphome_modbus_scanner.modbus_scan.models import ProbeType, ScanRequest
from custom_components.woow_esphome_modbus_scanner.modbus_scan.profile_generated import PROFILE
from custom_components.woow_esphome_modbus_scanner.modbus_scan.provider import GatewayProviderError

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


def snapshot(**changes):
    return {
        "v": 1,
        "hash": PROFILE["profile_hash"],
        "boot": 99,
        "seq": 1,
        "ms": 1000,
        "core": True,
        "busy": False,
        "addr": 1,
        "target": 1,
        "age": 0,
        "fault": False,
        **changes,
    }


class Client:
    def __init__(self):
        self.closed = False
        self.calls = []
        self.snapshots = 0

    async def connect(self, **kwargs):
        self.on_stop = kwargs["on_stop"]

    async def device_info(self):
        return SimpleNamespace(mac_address=GATEWAY.mac)

    async def list_entities_services(self):
        return [
            TextSensorInfo(key=1, name="Modbus Scanner Result"),
            TextSensorInfo(key=2, name="Modbus Scanner Health"),
        ], [
            UserService(
                name="modbus_scanner_probe_v1",
                key=10,
                args=[
                    UserServiceArg("request_id", UserServiceArgType.STRING),
                    UserServiceArg("slave", UserServiceArgType.INT),
                    UserServiceArg("reg", UserServiceArgType.INT),
                ],
            ),
            UserService(
                name="modbus_scanner_status_v1",
                key=11,
                args=[UserServiceArg("request_id", UserServiceArgType.STRING)],
            ),
        ]

    def subscribe_states(self, callback):
        self.callback = callback

    async def execute_service(self, service, data):
        self.calls.append(service.name)
        if service.key == 11:
            self.snapshots += 1
            payload = snapshot(id=data["request_id"], seq=self.snapshots, ms=self.snapshots * 1000)
            self.callback(TextSensorState(key=2, state=json.dumps(payload)))
        else:
            payload = {
                "v": 1,
                "id": data["request_id"],
                "slave": data["slave"],
                "reg": data["reg"],
                "outcome": "responded",
                "latency_ms": 12,
                "value": 1,
            }
            self.callback(TextSensorState(key=1, state=json.dumps(payload)))

    async def disconnect(self):
        self.closed = True


def provider(client, gateway=GATEWAY):
    return ESPHomeGatewayProvider([gateway], client_factory=lambda *args, **kwargs: client)


async def test_api_check_never_probes_bus():
    client = Client()
    health = await provider(client).check_gateway(GATEWAY.gateway_id)
    assert client.calls == ["modbus_scanner_status_v1"]
    assert health["bridge_status"] == "profile_verified"
    assert health["recovery_status"] == "unknown"
    assert client.closed


async def test_recovery_requires_new_normal_snapshot():
    client = Client()
    p = provider(client)
    rows = []
    progress = []
    await p.run_scan(REQUEST, rows.append, lambda: False, progress=progress.append)
    assert rows[0].raw_value == 1 and rows[0].register_address == 0x6201
    assert p.health[GATEWAY.gateway_id]["recovery_status"] == "verified"
    assert client.snapshots >= 3 and client.closed


async def test_recovery_rejects_old_core_observations(monkeypatch):
    session = HealthSession(None, 1, None)
    session.snapshot = AsyncMock(
        side_effect=[
            snapshot(),
            snapshot(seq=2, ms=2000, age=1100),
            snapshot(seq=3, ms=3000, age=10),
        ]
    )
    real_sleep = asyncio.sleep

    async def fast_sleep(_delay):
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)
    result = await session.verify_recovery()
    assert session.snapshot.await_count == 3 and result["seq"] == 3


@pytest.mark.parametrize(
    "change,code", [({"boot": 100}, "DEVICE_RESTARTED"), ({"fault": True}, "FIRMWARE_FAULT")]
)
async def test_recovery_detects_reboot_and_latched_fault(change, code):
    session = HealthSession(None, 1, None)
    session.snapshot = AsyncMock(side_effect=[snapshot(), snapshot(**change)])
    with pytest.raises(GatewayProviderError) as error:
        await session.verify_recovery()
    assert error.value.code == code


async def test_cleanup_cannot_leak_or_replace_primary_failure():
    client = Client()
    client.device_info = AsyncMock(side_effect=RuntimeError("PRIVATE_PRIMARY"))
    client.disconnect = AsyncMock(side_effect=RuntimeError("PRIVATE_CLEANUP"))
    p = provider(client)
    with pytest.raises(GatewayProviderError) as error:
        await p.run_scan(REQUEST, lambda row: None, lambda: False)
    assert "PRIVATE" not in str(error.value)
    assert p.health[GATEWAY.gateway_id]["cleanup_status"] == "failed"
    assert "PRIVATE" not in json.dumps(p.list_gateways()[0].as_dict())


async def test_cancel_during_recovery_always_disconnects():
    client = Client()
    p = provider(client)
    started = asyncio.Event()
    original = client.execute_service

    async def execute(service, data):
        if service.key == 11 and client.snapshots >= 2:
            started.set()
            await asyncio.Future()
        await original(service, data)

    client.execute_service = execute
    task = asyncio.create_task(p.run_scan(REQUEST, lambda row: None, lambda: False))
    await asyncio.wait_for(started.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client.closed
    assert p.health[GATEWAY.gateway_id]["recovery_status"] == "unknown"


async def test_constructor_error_is_sanitized():
    def fail(*args, **kwargs):
        raise ValueError("PRIVATE_PSK")

    p = ESPHomeGatewayProvider([GATEWAY], client_factory=fail)
    with pytest.raises(GatewayProviderError) as error:
        await p.run_scan(REQUEST, lambda row: None, lambda: False)
    assert "PRIVATE" not in str(error.value)


async def test_psk_forwarded_but_not_exposed():
    gateway = replace(GATEWAY, noise_psk="A" * 43 + "=")
    captured = {}
    client = Client()

    def factory(*args, **kwargs):
        captured.update(kwargs)
        return client

    p = ESPHomeGatewayProvider([gateway], client_factory=factory)
    await p.check_gateway(gateway.gateway_id)
    assert captured["noise_psk"] == gateway.noise_psk
    assert gateway.noise_psk not in repr(gateway)
    assert gateway.noise_psk not in json.dumps(p.list_gateways()[0].as_dict())


@pytest.mark.parametrize(
    "change",
    [{"v": True}, {"seq": True}, {"core": 1}, {"addr": 33}, {"age": -1}, {"hash": "wrong"}],
)
async def test_correlated_invalid_health_fails_closed(change):
    session = HealthSession(None, 2, None)
    session.expected = "a" * 32
    session.pending = asyncio.get_running_loop().create_future()
    session.accept(
        TextSensorState(key=2, state=json.dumps(snapshot(id=session.expected, **change)))
    )
    with pytest.raises(GatewayProviderError):
        await session.pending


@pytest.mark.parametrize(
    "changes",
    [
        {"probe_type": ProbeType.INPUT_REGISTER},
        {"register_count": 2},
        {"timeout_ms": 701},
        {"pause_normal_polling": False},
        {"start_id": 33, "end_id": 33},
        {"register_address": 0},
    ],
)
def test_physical_profile_rejects_explicit_unsupported_values(changes):
    with pytest.raises(ValueError):
        provider(Client()).validate_request(replace(REQUEST, **changes))


async def test_identity_mismatch_never_executes_any_action():
    client = Client()
    client.device_info = AsyncMock(return_value=SimpleNamespace(mac_address="00:00:00:00:00:00"))
    with pytest.raises(GatewayProviderError) as error:
        await provider(client).check_gateway(GATEWAY.gateway_id)
    assert error.value.code == "IDENTITY_MISMATCH"
    assert not client.calls and client.closed


async def test_missing_bridge_never_executes_action():
    client = Client()
    client.list_entities_services = AsyncMock(return_value=([], []))
    with pytest.raises(GatewayProviderError) as error:
        await provider(client).check_gateway(GATEWAY.gateway_id)
    assert error.value.code == "BRIDGE_UNSUPPORTED"
    assert not client.calls and client.closed


async def test_force_close_after_graceful_cleanup_failure():
    client = Client()

    async def close(force=False):
        if not force:
            raise RuntimeError("PRIVATE")
        client.closed = True

    client.disconnect = close
    p = provider(client)
    await p.check_gateway(GATEWAY.gateway_id)
    assert client.closed and p.health[GATEWAY.gateway_id]["cleanup_status"] == "forced"


async def test_health_fault_prevents_probe():
    client = Client()

    async def execute(service, data):
        assert service.key == 11
        client.callback(
            TextSensorState(key=2, state=json.dumps(snapshot(id=data["request_id"], fault=True)))
        )

    client.execute_service = execute
    with pytest.raises(GatewayProviderError) as error:
        await provider(client).run_scan(REQUEST, lambda row: None, lambda: False)
    assert error.value.code == "FIRMWARE_FAULT" and client.closed


async def test_cancel_before_connect_sends_no_actions():
    client = Client()
    await provider(client).run_scan(REQUEST, lambda row: None, lambda: True)
    assert not client.calls and not hasattr(client, "on_stop")


async def test_busy_and_unknown_api_checks_fail_closed():
    p = provider(Client())
    with pytest.raises(ValueError):
        await p.check_gateway("unknown")
    async with p._locks[GATEWAY.gateway_id]:
        with pytest.raises(GatewayProviderError) as error:
            await p.check_gateway(GATEWAY.gateway_id)
        assert error.value.code == "GATEWAY_BUSY"


async def test_encryption_error_subclass_is_auth_failure():
    from aioesphomeapi.core import EncryptionErrorAPIError

    error = ESPHomeGatewayProvider._transport_error(EncryptionErrorAPIError("PRIVATE"), "connect")
    assert error.code == "API_AUTH_FAILED" and "PRIVATE" not in str(error)


@pytest.mark.parametrize(
    "error,expected",
    [
        (RuntimeError("PRIVATE"), "unknown"),
        (GatewayProviderError("Firmware fault", code="FIRMWARE_FAULT"), "failed"),
    ],
)
async def test_recovery_error_does_not_erase_read_evidence(monkeypatch, error, expected):
    monkeypatch.setattr(HealthSession, "verify_recovery", AsyncMock(side_effect=error))
    client = Client()
    p = provider(client)
    rows = []
    await p.run_scan(REQUEST, rows.append, lambda: False)
    assert len(rows) == 1 and rows[0].raw_value == 1
    assert p.health[GATEWAY.gateway_id]["recovery_status"] == expected
    assert "PRIVATE" not in json.dumps(p.health)
    assert client.closed
