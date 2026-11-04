"""Provider-reported probe limits; the service layer validates requests against them."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from .models import (
    MAX_INTER_REQUEST_DELAY_MS,
    MAX_REGISTER_ADDRESS,
    MAX_REGISTER_COUNT,
    MAX_SLAVE_ID,
    MAX_TIMEOUT_MS,
    MIN_SLAVE_ID,
    MIN_TIMEOUT_MS,
    ProbeType,
    ScanRequest,
)


@dataclass(frozen=True, slots=True)
class ScanTiming:
    """How long one Gateway's Scans take: the worst-case estimate and the operation budget.

    Estimate: every attempt costs ``timeout_ms`` plus ``attempt_overhead_ms`` (what the
    transport adds per attempt), plus the inter-request delay between addresses. Budget (the
    deadline the coordinator enforces): ``setup_ms`` for connect and discovery, then per
    attempt ``attempt_budget_ms`` (plus ``timeout_ms`` unless it already covers it), the
    delays, and ``cleanup_ms``.
    """

    attempt_overhead_ms: int = 0
    setup_ms: int = 0
    attempt_budget_ms: int = 0
    # Whether attempt_budget_ms already covers the attempt's timeout (Bridge Protocol v1,
    # whose timeout is fixed).
    attempt_budget_includes_timeout: bool = False
    cleanup_ms: int = 10_000

    def attempt_ms(self, request: ScanRequest) -> int:
        """Worst-case cost of one attempt: its timeout plus what the transport adds."""
        return request.timeout_ms + self.attempt_overhead_ms

    def estimated_worst_case_ms(self, request: ScanRequest) -> int:
        """Conservative request duration estimate without pre-enqueuing work."""
        return request.attempt_count * self.attempt_ms(request) + request.total_delay_ms

    def execution_budget_ms(self, request: ScanRequest) -> int:
        """Operation ceiling: connect/discovery, every attempt's waits, delays and cleanup."""
        attempts = request.attempt_count
        per_attempt = self.attempt_budget_ms
        if not self.attempt_budget_includes_timeout:
            per_attempt += request.timeout_ms
        return self.setup_ms + attempts * per_attempt + request.total_delay_ms + self.cleanup_ms


@dataclass(frozen=True, slots=True)
class ProbeLimits:
    """What one gateway can safely probe, as reported by its provider adapter."""

    label: str
    slave_min: int = MIN_SLAVE_ID
    slave_max: int = MAX_SLAVE_ID
    probe_types: tuple[ProbeType, ...] = tuple(ProbeType)
    register_count_max: int = MAX_REGISTER_COUNT
    allowed_registers: tuple[int, ...] | None = None
    timeout_ms_min: int = MIN_TIMEOUT_MS
    timeout_ms_max: int = MAX_TIMEOUT_MS
    inter_request_delay_ms_max: int = MAX_INTER_REQUEST_DELAY_MS
    pause_normal_polling_required: bool = False
    pause_normal_polling_supported: bool = True
    # Set when Scans of a Gateway's Buses take turns for one Probe slot: the longest a Scan
    # that may hold a Scan Lease can wait between a Probe's result and its next Probe.
    concurrent_wait_max_ms: int | None = None
    # Values the service layer fills in for omitted probe fields.
    defaults: dict[str, Any] = field(default_factory=dict, compare=False)
    timing: ScanTiming = field(default_factory=ScanTiming, compare=False)

    @property
    def example_register(self) -> int | None:
        """The register a request reads by default, so allowlist errors and hints name it.

        The default register if it is allowed, else the first allowed one in the order given
        (what a Device Profile without a default register reads). The panel's register hint
        reads it from ``as_dict``.
        """
        if not self.allowed_registers:
            return None
        preferred = self.defaults.get("register_address")
        return preferred if preferred in self.allowed_registers else self.allowed_registers[0]

    def validate(self, request: ScanRequest) -> None:
        """Reject any request outside these limits with an actionable message."""
        if not self.slave_min <= request.start_id <= request.end_id <= self.slave_max:
            raise ValueError(
                f"{self.label} supports slave IDs {self.slave_min}–{self.slave_max} only"
            )
        if request.probe_type not in self.probe_types:
            allowed = ", ".join(str(item) for item in self.probe_types)
            raise ValueError(f"{self.label} requires probe_type in: {allowed}")
        if request.register_count > self.register_count_max:
            raise ValueError(f"{self.label} requires register_count<={self.register_count_max}")
        if request.register_address + request.register_count - 1 > MAX_REGISTER_ADDRESS:
            raise ValueError(
                f"The register block must end at or before register {MAX_REGISTER_ADDRESS}"
            )
        if self.allowed_registers is not None:
            # Every register of the block is read, so every one must be allowed.
            first = request.register_address
            block = range(first, first + request.register_count)
            outside = next((reg for reg in block if reg not in self.allowed_registers), None)
            if outside is not None:
                raise ValueError(
                    f"{self.label} cannot read register {outside} (0x{outside:04X}): it is "
                    f"not in the read allowlist; every register of the block must be "
                    f"allowed; example: {self.example_register} (0x{self.example_register:04X})"
                )
        if not self.timeout_ms_min <= request.timeout_ms <= self.timeout_ms_max:
            if self.timeout_ms_min == self.timeout_ms_max:
                raise ValueError(f"{self.label} requires timeout_ms={self.timeout_ms_min}")
            raise ValueError(
                f"{self.label} requires timeout_ms {self.timeout_ms_min}–{self.timeout_ms_max}"
            )
        if request.inter_request_delay_ms > self.inter_request_delay_ms_max:
            raise ValueError(
                f"{self.label} requires inter_request_delay_ms<={self.inter_request_delay_ms_max}"
            )
        if self.pause_normal_polling_required and not request.pause_normal_polling:
            raise ValueError(f"{self.label} requires pause_normal_polling=true")
        if not self.pause_normal_polling_supported and request.pause_normal_polling:
            raise ValueError(
                f"{self.label} cannot pause Normal Polling yet; set pause_normal_polling=false"
            )

    def validate_alongside(self, request: ScanRequest, running: Sequence[ScanRequest]) -> None:
        """Refuse a Scan whose Probe turns would make a pausing Scan wait past the limit.

        Between two Probes a Scan waits its inter-request delay plus one Probe (timeout and
        attempt overhead) of every other running Scan of the Gateway.
        """
        if self.concurrent_wait_max_ms is None or not running:
            return
        scans = [*running, request]
        turn = [self.timing.attempt_ms(scan) for scan in scans]
        for index, scan in enumerate(scans):
            if not scan.pause_normal_polling or scan.attempt_count == 1:
                continue  # no Scan Lease to keep, or no next Probe to wait for
            delay = scan.inter_request_delay_ms if scan.address_count > 1 else 0
            wait = delay + sum(turn) - turn[index]
            if wait > self.concurrent_wait_max_ms:
                waiting = "this Scan" if scan is request else f"the Scan on Bus {scan.bus}"
                raise ValueError(
                    f"{self.label} cannot start this Scan on Bus {request.bus} now: the "
                    f"Buses of a Gateway take turns for Probes, so {waiting} would wait up "
                    f"to {wait} ms between Probes, more than the "
                    f"{self.concurrent_wait_max_ms} ms that stays within the Scan Lease idle "
                    f"limit; lower timeout_ms or inter_request_delay_ms, or wait for the "
                    f"other Scan to finish"
                )

    def as_dict(self) -> dict[str, Any]:
        """Serialize for a Home Assistant service response."""
        return {
            "slave_min": self.slave_min,
            "slave_max": self.slave_max,
            "probe_types": [str(item) for item in self.probe_types],
            "register_count_max": self.register_count_max,
            "allowed_registers": (
                list(self.allowed_registers) if self.allowed_registers is not None else None
            ),
            "example_register": self.example_register,
            "timeout_ms_min": self.timeout_ms_min,
            "timeout_ms_max": self.timeout_ms_max,
            "inter_request_delay_ms_max": self.inter_request_delay_ms_max,
            "pause_normal_polling_required": self.pause_normal_polling_required,
            "pause_normal_polling_supported": self.pause_normal_polling_supported,
            # The panel's duration estimate uses the same formula as the service's.
            "attempt_overhead_ms": self.timing.attempt_overhead_ms,
            # The panel fills its form from these, so it keeps no per-Gateway copy.
            "defaults": {
                key: str(value) if isinstance(value, ProbeType) else value
                for key, value in self.defaults.items()
            },
        }
