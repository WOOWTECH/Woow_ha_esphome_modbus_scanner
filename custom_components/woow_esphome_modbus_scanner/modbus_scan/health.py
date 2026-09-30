"""Nonce-correlated firmware health; API snapshots never issue bus transactions."""

from __future__ import annotations

import asyncio
import inspect
import json
from uuid import uuid4

from aioesphomeapi import TextSensorInfo, UserServiceArgType

from .profile_generated import PROFILE
from .provider import GatewayProviderError


class HealthSession:
    def __init__(self, client, sensor, service):
        self.client, self.sensor, self.service = client, sensor, service
        self.pending = None
        self.expected = None

    @classmethod
    def discover(cls, client, entities, services):
        sensors = [
            e
            for e in entities
            if isinstance(e, TextSensorInfo) and e.name == "Modbus Scanner Health"
        ]
        actions = [s for s in services if s.name == "modbus_scanner_status_v1"]
        if not sensors and not actions:
            return None  # Legacy firmware: recovery must remain unknown.
        if (
            len(sensors) != 1
            or len(actions) != 1
            or len(actions[0].args) != 1
            or {a.name: a.type for a in actions[0].args}
            != {"request_id": UserServiceArgType.STRING}
        ):
            raise GatewayProviderError(
                "Invalid health bridge signature", code="BRIDGE_UNSUPPORTED", phase="verify_bridge"
            )
        return cls(client, sensors[0].key, actions[0])

    def disconnected(self):
        if self.pending is not None and not self.pending.done():
            self.pending.set_exception(
                GatewayProviderError(
                    "Health connection lost", code="API_DISCONNECTED", phase="recovery"
                )
            )

    def accept(self, state):
        if (
            self.pending is None
            or self.pending.done()
            or state.key != self.sensor
            or getattr(state, "missing_state", False)
        ):
            return
        if not isinstance(getattr(state, "state", None), str) or len(state.state) > 512:
            return
        try:
            data = json.loads(state.state)
        except (ValueError, TypeError, AttributeError):
            return
        if not isinstance(data, dict) or data.get("id") != self.expected:
            return
        try:
            if type(data.get("v")) is not int or data["v"] != 1:
                raise ValueError
            for key in ("boot", "seq", "ms", "age"):
                if type(data.get(key)) is not int or not 0 <= data[key] <= 0xFFFFFFFF:
                    raise ValueError
            for key in ("core", "busy", "fault"):
                if type(data.get(key)) is not bool:
                    raise ValueError
            for key in ("addr", "target"):
                if type(data.get(key)) is not int or not 1 <= data[key] <= 32:
                    raise ValueError
            if data.get("hash") != PROFILE["profile_hash"]:
                self.pending.set_exception(
                    GatewayProviderError(
                        "Firmware profile does not match the installed integration",
                        code="PROFILE_MISMATCH",
                        phase="verify_bridge",
                    )
                )
                return
            allowed = (
                "v",
                "id",
                "hash",
                "boot",
                "seq",
                "ms",
                "core",
                "busy",
                "addr",
                "target",
                "age",
                "fault",
            )
            self.pending.set_result({key: data[key] for key in allowed})
        except (ValueError, TypeError, KeyError):
            self.pending.set_exception(
                GatewayProviderError(
                    "Invalid firmware health snapshot", code="RESPONSE_INVALID", phase="recovery"
                )
            )

    async def snapshot(self):
        self.expected = uuid4().hex
        self.pending = asyncio.get_running_loop().create_future()
        try:
            async with asyncio.timeout(3):
                result = self.client.execute_service(self.service, {"request_id": self.expected})
                if inspect.isawaitable(result):
                    await result
                return await self.pending
        finally:
            if not self.pending.done():
                self.pending.cancel()

    async def verify_recovery(self):
        """All core observations must postdate this fresh recovery baseline."""
        async with asyncio.timeout(25):
            baseline = await self.snapshot()
            while True:
                await asyncio.sleep(0.5)
                current = await self.snapshot()
                if current["boot"] != baseline["boot"]:
                    raise GatewayProviderError(
                        "ESP restarted while checking recovery",
                        code="DEVICE_RESTARTED",
                        phase="recovery",
                    )
                if current["fault"]:
                    raise GatewayProviderError(
                        "Firmware latched an unsafe transport state",
                        code="FIRMWARE_FAULT",
                        phase="recovery",
                    )
                delta = (current["seq"] - baseline["seq"]) & 0xFFFFFFFF
                elapsed = (current["ms"] - baseline["ms"]) & 0xFFFFFFFF
                if (
                    0 < delta < 0x80000000
                    and elapsed < 30000
                    and current["age"] <= elapsed
                    and current["core"]
                    and not current["busy"]
                    and current["addr"] == current["target"] == baseline["target"]
                ):
                    return current
