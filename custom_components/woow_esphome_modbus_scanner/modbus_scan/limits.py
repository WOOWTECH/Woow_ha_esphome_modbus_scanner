"""Provider-reported probe limits; the service layer validates requests against them."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import (
    MAX_REGISTER_COUNT,
    MAX_SLAVE_ID,
    MAX_TIMEOUT_MS,
    MIN_SLAVE_ID,
    MIN_TIMEOUT_MS,
    ProbeType,
    ScanRequest,
)


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
    pause_normal_polling_required: bool = False
    # Values the service layer fills in for omitted probe fields.
    defaults: dict[str, Any] = field(default_factory=dict, compare=False)

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
        if (
            self.allowed_registers is not None
            and request.register_address not in self.allowed_registers
        ):
            raise ValueError(
                f"Register is not in the {self.label} read allowlist; "
                f"example: {self.allowed_registers[0]} (0x{self.allowed_registers[0]:04X})"
            )
        if not self.timeout_ms_min <= request.timeout_ms <= self.timeout_ms_max:
            if self.timeout_ms_min == self.timeout_ms_max:
                raise ValueError(f"{self.label} requires timeout_ms={self.timeout_ms_min}")
            raise ValueError(
                f"{self.label} requires timeout_ms {self.timeout_ms_min}–{self.timeout_ms_max}"
            )
        if self.pause_normal_polling_required and not request.pause_normal_polling:
            raise ValueError(f"{self.label} requires pause_normal_polling=true")

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
            "timeout_ms_min": self.timeout_ms_min,
            "timeout_ms_max": self.timeout_ms_max,
            "pause_normal_polling_required": self.pause_normal_polling_required,
        }
