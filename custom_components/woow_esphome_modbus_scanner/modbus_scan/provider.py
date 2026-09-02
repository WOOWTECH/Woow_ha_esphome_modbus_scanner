"""Gateway-provider seam for Modbus scanning."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from .models import GatewayInfo, ProbeResult, ScanRequest

EmitResult = Callable[[ProbeResult], None]
IsCancelled = Callable[[], bool]


class GatewayProviderError(Exception):
    """A gateway transport failed and the current scan cannot continue."""

    def __init__(self, message: str, *, address: int | None = None) -> None:
        super().__init__(message)
        self.address = address


class GatewayProvider(Protocol):
    """Interface implemented by mock now and physical transports later."""

    provider_id: str

    def list_gateways(self) -> Sequence[GatewayInfo]:
        """Return gateways currently available through this provider."""

    async def run_scan(
        self,
        request: ScanRequest,
        emit: EmitResult,
        cancelled: IsCancelled,
    ) -> None:
        """Probe addresses incrementally and emit one normalized result each."""
