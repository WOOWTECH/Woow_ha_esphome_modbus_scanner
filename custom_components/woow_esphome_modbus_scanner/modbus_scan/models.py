"""Public data models for best-effort Modbus address scanning."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
import re
from typing import Any

MIN_SLAVE_ID = 1
MAX_SLAVE_ID = 247
MAX_REGISTER_ADDRESS = 65535
MAX_REGISTER_COUNT = 125
MIN_TIMEOUT_MS = 10
MAX_TIMEOUT_MS = 10_000
MAX_RETRIES = 5
# The widest inter-request delay any Gateway accepts. A Gateway may cap it lower through its
# ProbeLimits: a bridge v2 Gateway uses the contract's lease.inter_request_delay_max_ms (3 s, below
# the 5 s Scan Lease idle limit); a Legacy Gateway keeps its frozen 5 s.
MAX_INTER_REQUEST_DELAY_MS = 5_000
# A range Scan over more IDs than this needs large_range_confirmed besides safety_confirmed.
LARGE_RANGE_THRESHOLD = 32
# A Bus name: what a Gateway reports and what a Scan targets (bridge v2 identifier charset).
BUS_NAME_PATTERN = r"[0-9A-Za-z_-]{1,32}"


class ProbeType(StrEnum):
    """Supported read-only discovery probes."""

    HOLDING_REGISTER = "holding_register"
    INPUT_REGISTER = "input_register"


class MockScenario(StrEnum):
    """Deterministic Mock Scenarios (fixed outcome sets of the mock provider)."""

    FOUND_DEFAULT = "found_default"
    ALL_OFFLINE = "all_offline"
    PARTIAL_TIMEOUT = "partial_timeout"
    MODBUS_EXCEPTION = "modbus_exception"
    POSSIBLE_COLLISION = "possible_collision"
    GATEWAY_DISCONNECT = "gateway_disconnect"


class ScanOutcome(StrEnum):
    """Normalized terminal outcome for one attempted address."""

    RESPONDED = "responded"
    MODBUS_EXCEPTION = "modbus_exception"
    TIMEOUT = "timeout"
    POSSIBLE_COLLISION = "possible_collision"
    GATEWAY_ERROR = "gateway_error"


class ScanPhase(StrEnum):
    """Lifecycle phase exposed by status queries."""

    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class LeaseStatus(StrEnum):
    """Scan Lease state in Scan status and results: the contract's states plus HA's own."""

    ACTIVE = "active"
    ENDED = "ended"
    NONE = "none"
    # HA could not confirm the ending (no answer to the release); the Gateway's idle expiry
    # resumes Normal Polling by itself (ADR 0007).
    UNCONFIRMED = "unconfirmed"


class LeaseEndReason(StrEnum):
    """Why a Scan Lease ended: the bridge v2 contract's lease.end_reasons."""

    RELEASED = "released"
    IDLE = "idle"
    HARD_LIMIT = "hard_limit"
    SUPERSEDED = "superseded"


# Endings the Gateway decides by itself, possibly before the Scan finishes.
EARLY_LEASE_END_REASONS = frozenset(
    {LeaseEndReason.IDLE, LeaseEndReason.HARD_LIMIT, LeaseEndReason.SUPERSEDED}
)


@dataclass(frozen=True, slots=True)
class GatewayInfo:
    """A provider-owned gateway advertised to Home Assistant."""

    provider: str
    gateway_id: str
    name: str
    capabilities: tuple[str, ...]
    mock_scenarios: tuple[str, ...] = ()
    profile: dict[str, Any] | None = None
    health: dict[str, Any] | None = None
    limits: Any = None  # ProbeLimits reported by the provider adapter
    # The Gateway's Buses as {"bus", "serial"} rows; empty while the provider does not know.
    buses: tuple[dict[str, Any], ...] = ()
    # A Scan may target one of several Buses, even before the provider knows them.
    supports_bus_selection: bool = False
    # A Scan may hold the Bus's chosen Pausable Pollers paused under a Scan Lease.
    supports_scan_lease: bool = False

    @property
    def pausable_poller_tables(self) -> dict[str, list[dict[str, Any]]] | None:
        """The Gateway's Pausable Poller table per Bus as last read, or None while unknown."""
        tables = (self.health or {}).get("pausable_pollers")
        return tables if self.supports_scan_lease else None

    def as_dict(self) -> dict[str, Any]:
        """Serialize for a Home Assistant service response."""
        return {
            "provider": self.provider,
            "gateway_id": self.gateway_id,
            "name": self.name,
            "capabilities": list(self.capabilities),
            "mock_scenarios": list(self.mock_scenarios),
            "simulated": self.provider == "mock",
            **({"profile": deepcopy(self.profile)} if self.profile is not None else {}),
            **({"health": deepcopy(self.health)} if self.health is not None else {}),
            **({"limits": self.limits.as_dict()} if self.limits is not None else {}),
            "buses": deepcopy(list(self.buses)),
        }


@dataclass(frozen=True, slots=True)
class ScanRequest:
    """Validated, provider-independent request for a bounded address range."""

    provider: str
    gateway_id: str
    start_id: int
    end_id: int
    probe_type: ProbeType = ProbeType.HOLDING_REGISTER
    # The Bus a Scan targets; None lets a Gateway with exactly one Bus use that one.
    bus: str | None = None
    register_address: int = 0
    register_count: int = 1
    timeout_ms: int = 500
    retries: int = 1
    inter_request_delay_ms: int = 100
    pause_normal_polling: bool = False
    mock_scenario: str = MockScenario.FOUND_DEFAULT
    safety_confirmed: bool = False
    # Pausable Pollers to pause: explicit indices of the Bus's poller table, else the saved
    # checklist per Bus (see pollers.reconcile), else every poller.
    pause_pollers: tuple[int, ...] | None = None
    pause_checklists: dict[str, list[dict[str, Any]]] | None = None

    @classmethod
    def mock(
        cls,
        *,
        start_id: int = MIN_SLAVE_ID,
        end_id: int = 12,
        scenario: str = MockScenario.FOUND_DEFAULT,
        safety_confirmed: bool = True,
        **overrides: Any,
    ) -> ScanRequest:
        """Build a mock request for tests and local callers."""
        values: dict[str, Any] = {
            "provider": "mock",
            "gateway_id": "mock:rs485-gateway",
            "start_id": start_id,
            "end_id": end_id,
            "mock_scenario": scenario,
            "safety_confirmed": safety_confirmed,
            "inter_request_delay_ms": 0,
        }
        values.update(overrides)
        return cls(**values)

    @property
    def address_count(self) -> int:
        """Number of addresses in the inclusive range."""
        return self.end_id - self.start_id + 1

    @property
    def gateway_key(self) -> tuple[str, str, str | None]:
        """Concurrency key used by the coordinator: one Scan at a time per Bus.

        A None Bus stands for the whole Gateway, so it conflicts with every Bus of it.
        """
        return self.provider, self.gateway_id, self.bus

    def validate(self, *, require_safety: bool = True) -> None:
        """Validate all transport-independent safety bounds."""
        if not isinstance(self.provider, str) or not self.provider:
            raise ValueError("provider must be a non-empty string")
        if not isinstance(self.gateway_id, str) or not self.gateway_id:
            raise ValueError("gateway_id must be a non-empty string")
        if self.bus is not None and (
            not isinstance(self.bus, str) or not re.fullmatch(BUS_NAME_PATTERN, self.bus)
        ):
            raise ValueError("bus must be 1-32 characters from 0-9, A-Z, a-z, '_' and '-'")
        integer_fields = {
            "start_id": self.start_id,
            "end_id": self.end_id,
            "register_address": self.register_address,
            "register_count": self.register_count,
            "timeout_ms": self.timeout_ms,
            "retries": self.retries,
            "inter_request_delay_ms": self.inter_request_delay_ms,
        }
        for field_name, value in integer_fields.items():
            if type(value) is not int:
                raise ValueError(f"{field_name} must be an integer")
        if not MIN_SLAVE_ID <= self.start_id <= MAX_SLAVE_ID:
            raise ValueError("start_id must be between 1 and 247")
        if not MIN_SLAVE_ID <= self.end_id <= MAX_SLAVE_ID:
            raise ValueError("end_id must be between 1 and 247")
        if self.start_id > self.end_id:
            raise ValueError("start_id must not be greater than end_id")
        if not isinstance(self.probe_type, ProbeType):
            raise ValueError(f"Unsupported probe_type: {self.probe_type}")
        if not 0 <= self.register_address <= MAX_REGISTER_ADDRESS:
            raise ValueError("register_address must be between 0 and 65535")
        if not 1 <= self.register_count <= MAX_REGISTER_COUNT:
            raise ValueError("register_count must be between 1 and 125")
        if not MIN_TIMEOUT_MS <= self.timeout_ms <= MAX_TIMEOUT_MS:
            raise ValueError("timeout_ms must be between 10 and 10000")
        if not 0 <= self.retries <= MAX_RETRIES:
            raise ValueError("retries must be between 0 and 5")
        if not 0 <= self.inter_request_delay_ms <= MAX_INTER_REQUEST_DELAY_MS:
            raise ValueError(
                f"inter_request_delay_ms must be between 0 and {MAX_INTER_REQUEST_DELAY_MS}"
            )
        if type(self.pause_normal_polling) is not bool:
            raise ValueError("pause_normal_polling must be a boolean")
        if self.pause_pollers is not None and (
            not isinstance(self.pause_pollers, tuple)
            or any(type(index) is not int or index < 0 for index in self.pause_pollers)
        ):
            raise ValueError("pause_pollers must be Pausable Poller indices")
        if require_safety and self.safety_confirmed is not True:
            raise ValueError("safety_confirmed must be true before starting a scan")


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """Normalized provider outcome for a single address."""

    address: int
    outcome: ScanOutcome
    latency_ms: int
    detail: str
    exception_code: int | None = None
    identity: dict[str, str] | None = None
    register_address: int | None = None
    raw_value: int | None = None
    attempts: int | None = None
    # Every register read by a multi-register Probe; raw_value is the first of them.
    raw_values: tuple[int, ...] | None = None

    @property
    def is_responder(self) -> bool:
        """Whether the result provides evidence of a bus responder."""
        return self.outcome in {
            ScanOutcome.RESPONDED,
            ScanOutcome.MODBUS_EXCEPTION,
            ScanOutcome.POSSIBLE_COLLISION,
        }

    def as_dict(self) -> dict[str, Any]:
        """Serialize without implying that an address maps to a unique device."""
        result: dict[str, Any] = {
            "address": self.address,
            "outcome": self.outcome.value,
            "latency_ms": self.latency_ms,
            "detail": self.detail,
        }
        if self.register_address is not None:
            result.update(
                register_address=self.register_address,
                raw_value=self.raw_value,
                attempts=self.attempts,
            )
        if self.raw_values is not None:
            result["raw_values"] = list(self.raw_values)
        if self.exception_code is not None:
            result["exception_code"] = self.exception_code
        if self.identity is not None:
            result["identity"] = dict(self.identity)
        return result
