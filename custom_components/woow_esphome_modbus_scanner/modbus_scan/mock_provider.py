"""Deterministic, asynchronous Modbus scan provider used without hardware."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import replace

from .limits import ProbeLimits
from .models import (
    GatewayInfo,
    MockScenario,
    ProbeResult,
    ProbeType,
    ScanOutcome,
    ScanRequest,
    check_bus,
)
from .provider import EmitResult, GatewayProviderError, IsCancelled

MOCK_GATEWAY_ID = "mock:rs485-gateway"
MOCK_LIMITS = ProbeLimits("A mock Gateway")
MOCK_GATEWAY_NAME = "Simulated RS-485 Gateway"
# The simulated Gateway's one Bus (ADR 0011); it answers with the requested Mock Scenario.
MOCK_BUS = {"bus": "rs485", "serial": {"baud_rate": 9600, "parity": "NONE", "stop_bits": 1}}


class MockGatewayProvider:
    """A deterministic adapter that exercises the real provider seam."""

    provider_id = "mock"

    def __init__(self, *, step_delay_ms: int = 10) -> None:
        self._step_delay_ms = step_delay_ms

    def list_gateways(self) -> tuple[GatewayInfo, ...]:
        """Expose the simulated RS-485 Gateway and all supported capabilities."""
        return (
            GatewayInfo(
                provider=self.provider_id,
                gateway_id=MOCK_GATEWAY_ID,
                name=MOCK_GATEWAY_NAME,
                capabilities=(
                    "holding_register",
                    "input_register",
                    "cancellation",
                ),
                mock_scenarios=tuple(scenario.value for scenario in MockScenario),
                limits=MOCK_LIMITS,
                buses=(deepcopy(MOCK_BUS),),
                supports_bus_selection=True,
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
        check_bus(request.gateway_id, MOCK_BUS["bus"], request.bus)
        if request.mock_scenario not in {item.value for item in MockScenario}:
            raise ValueError(f"Unsupported mock_scenario: {request.mock_scenario}")
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
                request.mock_scenario == MockScenario.GATEWAY_DISCONNECT
                and address >= max(request.start_id + 3, 4)
            ):
                raise GatewayProviderError(
                    "Simulated gateway disconnected", address=address
                )
            result = self._result_for(request.mock_scenario, address)
            if request.probe_type in _REGISTER_PROBES:
                result = _register_read(request, result)
            emit(result)

    @staticmethod
    def _result_for(scenario: str, address: int) -> ProbeResult:
        """Return the stable outcome table for one mock address."""
        if scenario == MockScenario.ALL_OFFLINE:
            return _timeout(address)

        if scenario == MockScenario.FOUND_DEFAULT:
            if address in {1, 3, 12}:
                return _responded(address)
            if address == 5:
                return _exception(address, code=2)
            return _timeout(address)

        if scenario == MockScenario.PARTIAL_TIMEOUT:
            if address in {2, 7, 11, 21, 42}:
                return _responded(address)
            return _timeout(address)

        if scenario == MockScenario.MODBUS_EXCEPTION:
            if address in {4, 9, 17}:
                return _exception(address, code=2 if address != 9 else 3)
            return _timeout(address)

        if scenario == MockScenario.POSSIBLE_COLLISION:
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
        if address in {1, 3}:
            return _responded(address)
        return _timeout(address)


_REGISTER_PROBES = {ProbeType.HOLDING_REGISTER: 3, ProbeType.INPUT_REGISTER: 4}


def _register_read(request: ScanRequest, result: ProbeResult) -> ProbeResult:
    """A register read returns raw register evidence and never a device identity."""
    evidence = {
        "register_address": request.register_address,
        "attempts": 1,
        "identity": None,
    }
    if result.outcome != ScanOutcome.RESPONDED:
        return replace(result, **evidence)
    # Deterministic values: high byte = slave ID, low byte = register offset.
    values = tuple(
        (result.address << 8 | (request.register_address + offset) & 0xFF) & 0xFFFF
        for offset in range(request.register_count)
    )
    label = (
        f"FC{_REGISTER_PROBES[request.probe_type]:02d} register "
        f"0x{request.register_address:04X} x{request.register_count}"
    )
    return replace(
        result,
        **evidence,
        outcome=ScanOutcome.RESPONDED,
        detail=f"{label} = {list(values)}",
        raw_value=values[0],
        raw_values=values,
    )


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


def _exception(address: int, *, code: int) -> ProbeResult:
    return ProbeResult(
        address=address,
        outcome=ScanOutcome.MODBUS_EXCEPTION,
        latency_ms=6 + address % 3,
        exception_code=code,
        detail="CRC-valid Modbus exception; a responder exists but rejected the probe",
    )
