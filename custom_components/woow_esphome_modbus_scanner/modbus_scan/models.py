"""Public data models for best-effort Modbus address scanning."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

MIN_SLAVE_ID = 1
MAX_SLAVE_ID = 247
MAX_REGISTER_ADDRESS = 65535
MAX_REGISTER_COUNT = 125
MIN_TIMEOUT_MS = 10
MAX_TIMEOUT_MS = 10_000
MAX_RETRIES = 5
MAX_INTER_REQUEST_DELAY_MS = 5_000


class ProbeType(StrEnum):
    """Supported read-only discovery probes."""

    DEVICE_IDENTIFICATION = "device_identification"
    HOLDING_REGISTER = "holding_register"
    INPUT_REGISTER = "input_register"


class MockProfile(StrEnum):
    """Deterministic mock bus profiles."""

    FOUND_DEFAULT = "found_default"
    ALL_OFFLINE = "all_offline"
    PARTIAL_TIMEOUT = "partial_timeout"
    MODBUS_EXCEPTION = "modbus_exception"
    POSSIBLE_COLLISION = "possible_collision"
    GATEWAY_DISCONNECT = "gateway_disconnect"


class ScanOutcome(StrEnum):
    """Normalized terminal outcome for one attempted address."""

    IDENTIFIED = "identified"
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


@dataclass(frozen=True, slots=True)
class GatewayInfo:
    """A provider-owned gateway advertised to Home Assistant."""

    provider: str
    gateway_id: str
    name: str
    capabilities: tuple[str, ...]
    mock_profiles: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """Serialize for a Home Assistant service response."""
        return {
            "provider": self.provider,
            "gateway_id": self.gateway_id,
            "name": self.name,
            "capabilities": list(self.capabilities),
            "mock_profiles": list(self.mock_profiles),
            "simulated": self.provider == "mock",
        }


@dataclass(frozen=True, slots=True)
class ScanRequest:
    """Validated, provider-independent request for a bounded address range."""

    provider: str
    gateway_id: str
    start_id: int
    end_id: int
    probe_type: ProbeType = ProbeType.DEVICE_IDENTIFICATION
    register_address: int = 0
    register_count: int = 1
    timeout_ms: int = 500
    retries: int = 1
    inter_request_delay_ms: int = 100
    pause_normal_polling: bool = False
    mock_profile: str = MockProfile.FOUND_DEFAULT
    safety_confirmed: bool = False

    @classmethod
    def mock(
        cls,
        *,
        start_id: int = MIN_SLAVE_ID,
        end_id: int = 12,
        profile: str = MockProfile.FOUND_DEFAULT,
        safety_confirmed: bool = True,
        **overrides: Any,
    ) -> ScanRequest:
        """Build a mock request for tests and local callers."""
        values: dict[str, Any] = {
            "provider": "mock",
            "gateway_id": "mock:rs485-gateway",
            "start_id": start_id,
            "end_id": end_id,
            "mock_profile": profile,
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
    def gateway_key(self) -> tuple[str, str]:
        """Concurrency key used by the coordinator."""
        return self.provider, self.gateway_id

    @property
    def estimated_worst_case_ms(self) -> int:
        """Conservative request duration estimate without pre-enqueuing work."""
        per_address = self.timeout_ms * (self.retries + 1)
        delays = max(0, self.address_count - 1) * self.inter_request_delay_ms
        return self.address_count * per_address + delays

    def validate(self, *, require_safety: bool = True) -> None:
        """Validate all transport-independent safety bounds."""
        if not isinstance(self.provider, str) or not self.provider:
            raise ValueError("provider must be a non-empty string")
        if not isinstance(self.gateway_id, str) or not self.gateway_id:
            raise ValueError("gateway_id must be a non-empty string")
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
            raise ValueError("inter_request_delay_ms must be between 0 and 5000")
        if type(self.pause_normal_polling) is not bool:
            raise ValueError("pause_normal_polling must be a boolean")
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

    @property
    def is_responder(self) -> bool:
        """Whether the result provides evidence of a bus responder."""
        return self.outcome in {
            ScanOutcome.IDENTIFIED,
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
        if self.exception_code is not None:
            result["exception_code"] = self.exception_code
        if self.identity is not None:
            result["identity"] = dict(self.identity)
        return result
