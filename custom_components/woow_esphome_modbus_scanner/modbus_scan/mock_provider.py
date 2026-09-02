"""Deterministic, asynchronous Modbus scan provider used without hardware."""

from __future__ import annotations

import asyncio

from .models import (
    GatewayInfo,
    MockProfile,
    ProbeResult,
    ScanOutcome,
    ScanRequest,
)
from .provider import EmitResult, GatewayProviderError, IsCancelled

MOCK_GATEWAY_ID = "mock:rs485-gateway"


class MockGatewayProvider:
    """A deterministic adapter that exercises the real provider seam."""

    provider_id = "mock"

    def __init__(self, *, step_delay_ms: int = 10) -> None:
        self._step_delay_ms = step_delay_ms

    def list_gateways(self) -> tuple[GatewayInfo, ...]:
        """Expose one simulated RS-485 gateway and all supported capabilities."""
        return (
            GatewayInfo(
                provider=self.provider_id,
                gateway_id=MOCK_GATEWAY_ID,
                name="Simulated RS-485 Gateway",
                capabilities=(
                    "device_identification",
                    "holding_register",
                    "input_register",
                    "cancellation",
                ),
                mock_profiles=tuple(profile.value for profile in MockProfile),
            ),
        )

    async def run_scan(
        self,
        request: ScanRequest,
        emit: EmitResult,
        cancelled: IsCancelled,
    ) -> None:
        """Emit deterministic outcomes, delaying only between addresses."""
        request.validate()
        if request.provider != self.provider_id:
            raise ValueError(f"Unsupported mock provider: {request.provider}")
        if request.gateway_id != MOCK_GATEWAY_ID:
            raise ValueError(f"Unknown mock gateway: {request.gateway_id}")
        if request.mock_profile not in {item.value for item in MockProfile}:
            raise ValueError(f"Unsupported mock_profile: {request.mock_profile}")
        delay_ms = max(self._step_delay_ms, request.inter_request_delay_ms)
        for address in range(request.start_id, request.end_id + 1):
            if cancelled():
                return
            if address != request.start_id:
                if delay_ms:
                    await asyncio.sleep(delay_ms / 1000)
                else:
                    await asyncio.sleep(0)
                if cancelled():
                    return
            if (
                request.mock_profile == MockProfile.GATEWAY_DISCONNECT
                and address >= max(request.start_id + 3, 4)
            ):
                raise GatewayProviderError(
                    "Simulated gateway disconnected", address=address
                )
            emit(self._result_for(request.mock_profile, address))

    @staticmethod
    def _result_for(profile: str, address: int) -> ProbeResult:
        """Return the stable outcome table for one mock address."""
        if profile == MockProfile.ALL_OFFLINE:
            return _timeout(address)

        if profile == MockProfile.FOUND_DEFAULT:
            if address == 1:
                return _identified(address, "WOOWTECH", "WT-RS485-01")
            if address == 3:
                return _responded(address)
            if address == 5:
                return _exception(address, code=2)
            if address == 12:
                return _identified(address, "Acme Controls", "ACM-12")
            return _timeout(address)

        if profile == MockProfile.PARTIAL_TIMEOUT:
            if address in {2, 11, 42}:
                return _responded(address)
            if address in {7, 21}:
                return _identified(address, "Mock Industries", f"MI-{address:03d}")
            return _timeout(address)

        if profile == MockProfile.MODBUS_EXCEPTION:
            if address in {4, 9, 17}:
                return _exception(address, code=2 if address != 9 else 3)
            return _timeout(address)

        if profile == MockProfile.POSSIBLE_COLLISION:
            if address == 7:
                return ProbeResult(
                    address=address,
                    outcome=ScanOutcome.POSSIBLE_COLLISION,
                    latency_ms=9,
                    detail=(
                        "Inconsistent CRC/framing; duplicate IDs or bus noise are possible"
                    ),
                )
            return _timeout(address)

        # gateway_disconnect behaves normally until run_scan raises.
        if address == 1:
            return _identified(address, "WOOWTECH", "WT-RS485-01")
        if address == 3:
            return _responded(address)
        return _timeout(address)


def _timeout(address: int) -> ProbeResult:
    return ProbeResult(
        address=address,
        outcome=ScanOutcome.TIMEOUT,
        latency_ms=500 + address % 7,
        detail="No valid reply; this does not prove that the address is unused",
    )


def _responded(address: int) -> ProbeResult:
    return ProbeResult(
        address=address,
        outcome=ScanOutcome.RESPONDED,
        latency_ms=5 + address % 4,
        detail="Valid Modbus response without identity details",
    )


def _identified(address: int, vendor: str, product: str) -> ProbeResult:
    return ProbeResult(
        address=address,
        outcome=ScanOutcome.IDENTIFIED,
        latency_ms=4 + address % 5,
        detail="Valid device-identification response",
        identity={"vendor": vendor, "product": product},
    )


def _exception(address: int, *, code: int) -> ProbeResult:
    return ProbeResult(
        address=address,
        outcome=ScanOutcome.MODBUS_EXCEPTION,
        latency_ms=6 + address % 3,
        exception_code=code,
        detail="CRC-valid Modbus exception; a responder exists but rejected the probe",
    )
