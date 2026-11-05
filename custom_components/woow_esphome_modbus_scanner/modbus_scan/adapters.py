"""Registration point for physical gateway provider adapters.

Every enrolled Gateway names its bridge protocol (``bridge`` key; absent means legacy
``v1``). Each bridge has its own adapter; ``PhysicalGatewayRouter`` presents them to the
coordinator as the single public ``esphome`` provider and routes by gateway id.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

BRIDGE_V1 = "v1"
BRIDGE_V2 = "v2"
BRIDGES = (BRIDGE_V2, BRIDGE_V1)


def physical_gateway_id(mac: str) -> str:
    """The gateway id both bridge adapters give an enrolled MAC, e.g. ``esphome:aabbccddeeff``."""
    return "esphome:" + mac.replace(":", "").lower()


def gateway_bridge(gateway: dict[str, Any]) -> str:
    """Bridge protocol of one enrolled Gateway; entries from before v2 are legacy v1."""
    return gateway.get("bridge", BRIDGE_V1)


class PhysicalGatewayRouter:
    """The ``esphome`` provider: forwards each call to the adapter owning the Gateway."""

    provider_id = "esphome"
    supports_progress = True

    def __init__(self, adapters: Sequence[Any]) -> None:
        self.adapters = tuple(adapters)

    def _adapter(self, gateway_id: str):
        for adapter in self.adapters:
            if gateway_id in adapter.gateways:
                return adapter
        raise ValueError("Unknown physical gateway")

    def list_gateways(self):
        return [gateway for adapter in self.adapters for gateway in adapter.list_gateways()]

    async def run_scan(self, request, emit, cancelled, *, progress=None):
        adapter = self._adapter(request.gateway_id)
        await adapter.run_scan(request, emit, cancelled, progress=progress)

    async def check_gateway(self, gateway_id):
        return await self._adapter(gateway_id).check_gateway(gateway_id)


def build_physical_provider(
    gateways: Sequence[dict[str, Any]],
    *,
    esphome_endpoint: Callable[[str], dict[str, Any] | None] | None = None,
    probe_slot_memory=None,
):
    """Return the provider serving the enrolled physical gateways, if any.

    ``esphome_endpoint`` resolves a linked HA ESPHome entry to its current host, port and
    key at connect time; without it each Gateway uses its stored copy. ``probe_slot_memory``
    keeps each v2 Gateway's last read Probe Slot mode across restarts (ADR 0010).
    """
    if not gateways:
        return None
    adapters = []
    v2 = [g for g in gateways if gateway_bridge(g) == BRIDGE_V2]
    if v2:
        from .bridge_v2 import build_provider as build_v2_provider

        adapters.append(
            build_v2_provider(
                v2, endpoint=esphome_endpoint, probe_slot_memory=probe_slot_memory
            )
        )
    # Legacy bridge v1 registration: delete this block with ``legacy_v1/``.
    v1 = [
        {k: v for k, v in g.items() if k != "bridge"}
        for g in gateways
        if gateway_bridge(g) == BRIDGE_V1
    ]
    if v1:
        from .legacy_v1 import build_provider as build_legacy_v1_provider

        adapters.append(build_legacy_v1_provider(v1))
    return PhysicalGatewayRouter(adapters)
