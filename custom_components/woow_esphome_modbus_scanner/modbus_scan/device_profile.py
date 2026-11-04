"""Device Profile documents: schema validation, limits and request defaults.

A Device Profile is a JSON document (schema_version 1). Its limits always sit inside the
Generic Device Profile's bounds, and a Scan validates against the selected profile *and*
the Gateway's own limits, so the effective limit is their intersection.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
import json
import math
import re
from typing import Any

from .bridge_v2.contract import HARD_LIMITS
from .limits import ProbeLimits
from .models import MAX_INTER_REQUEST_DELAY_MS, MAX_REGISTER_ADDRESS, MAX_RETRIES, ProbeType

SCHEMA_VERSION = 1
GENERIC_PROFILE_ID = "generic"
MAX_DOCUMENT_BYTES = 64 * 1024
MAX_ALLOWED_REGISTERS = 1024
MAX_FIELDS = 256

# Generic Device Profile bounds, every imported profile must stay inside them: the bridge v2
# contract's hard limits (ADR 0005), read from contract.json rather than copied.
SLAVE_MIN, SLAVE_MAX = HARD_LIMITS["slave_min"], HARD_LIMITS["slave_max"]
COUNT_MIN, COUNT_MAX = HARD_LIMITS["count_min"], HARD_LIMITS["count_max"]
TIMEOUT_MIN, TIMEOUT_MAX = HARD_LIMITS["timeout_ms_min"], HARD_LIMITS["timeout_ms_max"]
READ_FUNCTION_CODES = tuple(HARD_LIMITS["function_codes"])
WRITE_FUNCTION_CODES = tuple(HARD_LIMITS["write_function_codes"])
DATA_TYPES = ("u16", "s16")

_FUNCTION_CODE_PROBES = {3: ProbeType.HOLDING_REGISTER, 4: ProbeType.INPUT_REGISTER}
_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
_TOP_LEVEL = {
    "schema_version",
    "id",
    "name",
    "vendor",
    "model",
    "version",
    "function_codes",
    "defaults",
    "allowed_registers",
    "fields",
}
_DEFAULT_KEYS = {
    "slave_start",
    "slave_end",
    "function_code",
    "register",
    "count",
    "timeout_ms",
    "inter_request_delay_ms",
    "retries",
}
_FIELD_KEYS = {"register", "name", "unit", "scale", "data_type"}


class DeviceProfileError(ValueError):
    """A Device Profile document is invalid; ``errors`` holds (path, message) pairs."""

    def __init__(self, errors: list[tuple[str, str]]) -> None:
        self.errors = errors
        super().__init__(
            "Invalid Device Profile: " + "; ".join(f"{path}: {message}" for path, message in errors)
        )


@dataclass(frozen=True, slots=True)
class DeviceProfile:
    """One validated Device Profile."""

    document: dict[str, Any]
    builtin: bool = False

    @property
    def profile_id(self) -> str:
        return self.document["id"]

    @property
    def name(self) -> str:
        return self.document["name"]

    @property
    def function_codes(self) -> tuple[int, ...]:
        return tuple(self.document["function_codes"])

    @property
    def allowed_registers(self) -> tuple[int, ...] | None:
        registers = self.document.get("allowed_registers")
        return tuple(registers) if registers is not None else None

    @property
    def limits(self) -> ProbeLimits:
        probe_types = tuple(_FUNCTION_CODE_PROBES[code] for code in self.function_codes)
        return ProbeLimits(
            f"Device Profile '{self.name}'",
            slave_min=SLAVE_MIN,
            slave_max=SLAVE_MAX,
            probe_types=probe_types,
            register_count_max=COUNT_MAX,
            allowed_registers=self.allowed_registers,
            timeout_ms_min=TIMEOUT_MIN,
            timeout_ms_max=TIMEOUT_MAX,
            defaults=self.request_defaults,
        )

    @property
    def request_defaults(self) -> dict[str, Any]:
        """Service fields this profile fills in when a caller omits them."""
        source = self.document.get("defaults", {})
        mapping = {
            "slave_start": "start_id",
            "slave_end": "end_id",
            "register": "register_address",
            "count": "register_count",
            "timeout_ms": "timeout_ms",
            "inter_request_delay_ms": "inter_request_delay_ms",
            "retries": "retries",
        }
        defaults = {target: source[key] for key, target in mapping.items() if key in source}
        if self.builtin:
            return defaults
        function_code = source.get("function_code", self.function_codes[0])
        defaults["probe_type"] = _FUNCTION_CODE_PROBES[function_code]
        if "register_address" not in defaults and self.allowed_registers:
            defaults["register_address"] = self.allowed_registers[0]
        return defaults

    def decode(self, register_address: int, values: tuple[int, ...]) -> list[dict[str, Any]]:
        """Decoded values for every register in the block that has a field definition."""
        fields = {field["register"]: field for field in self.document.get("fields", [])}
        decoded = []
        for offset, raw in enumerate(values):
            field = fields.get(register_address + offset)
            if field is None:
                continue
            if field.get("data_type", "u16") == "s16" and raw >= 0x8000:
                raw -= 0x10000
            # Decimal keeps a scale such as 0.1 exact (784 * 0.1 is 78.4, not 78.40000000000001).
            value = Decimal(raw) * Decimal(str(field.get("scale", 1)))
            decoded.append(
                {
                    "register": field["register"],
                    "name": field["name"],
                    "unit": field.get("unit"),
                    "value": int(value) if value == value.to_integral_value() else float(value),
                }
            )
        return decoded

    def summary(self) -> dict[str, Any]:
        """Identity only, for labelling Scan status and results."""
        return {
            "id": self.profile_id,
            "name": self.name,
            "version": self.document["version"],
        }

    def as_dict(self) -> dict[str, Any]:
        """Serialize for list responses (document plus derived limits)."""
        return {
            **deepcopy(self.document),
            "allowed_registers": (
                list(self.allowed_registers) if self.allowed_registers is not None else None
            ),
            "defaults": deepcopy(self.document.get("defaults", {})),
            "fields": deepcopy(self.document.get("fields", [])),
            "builtin": self.builtin,
            "deletable": not self.builtin,
            "limits": self.limits.as_dict(),
        }

    def export(self) -> dict[str, Any]:
        """The importable document itself."""
        return deepcopy(self.document)


GENERIC_DEVICE_PROFILE = DeviceProfile(
    {
        "schema_version": SCHEMA_VERSION,
        "id": GENERIC_PROFILE_ID,
        "name": "Generic Device Profile",
        "vendor": "Generic",
        "model": "Any Modbus RTU device",
        "version": "1",
        "function_codes": list(READ_FUNCTION_CODES),
    },
    builtin=True,
)


def _is_int(value: object) -> bool:
    return type(value) is int


class _Checker:
    def __init__(self) -> None:
        self.errors: list[tuple[str, str]] = []

    def fail(self, path: str, message: str) -> None:
        self.errors.append((path, message))

    def text(self, doc: dict, key: str, max_length: int, *, required: bool = True) -> None:
        if key not in doc:
            if required:
                self.fail(key, "is required")
            return
        value = doc[key]
        if not isinstance(value, str) or not value.strip() or len(value) > max_length:
            self.fail(key, f"must be a non-empty string of at most {max_length} characters")

    def integer(self, doc: dict, key: str, path: str, low: int, high: int) -> bool:
        value = doc[key]
        if not _is_int(value) or not low <= value <= high:
            self.fail(path, f"must be an integer from {low} to {high}")
            return False
        return True

    def unknown(self, doc: dict, allowed: set[str], prefix: str) -> None:
        for key in sorted(set(doc) - allowed, key=str):
            self.fail(f"{prefix}{key}", "is not a Device Profile field")


def parse_device_profile(source: object) -> DeviceProfile:
    """Validate an imported document (object or JSON text) into a DeviceProfile."""
    if isinstance(source, str):
        if len(source.encode()) > MAX_DOCUMENT_BYTES:
            raise DeviceProfileError([("$", f"must be at most {MAX_DOCUMENT_BYTES} bytes")])
        try:
            source = json.loads(source)
        except json.JSONDecodeError as err:
            raise DeviceProfileError(
                [("$", f"is not valid JSON (line {err.lineno}, column {err.colno})")]
            ) from err
    if not isinstance(source, dict):
        raise DeviceProfileError([("$", "must be a JSON object")])
    try:
        size = len(json.dumps(source).encode())
    except (TypeError, ValueError) as err:
        raise DeviceProfileError([("$", "must contain only JSON values")]) from err
    if size > MAX_DOCUMENT_BYTES:
        raise DeviceProfileError([("$", f"must be at most {MAX_DOCUMENT_BYTES} bytes")])

    check = _Checker()
    doc = source
    check.unknown(doc, _TOP_LEVEL, "")
    if doc.get("schema_version") != SCHEMA_VERSION or not _is_int(doc.get("schema_version")):
        check.fail("schema_version", f"must be {SCHEMA_VERSION}")
    profile_id = doc.get("id")
    if not isinstance(profile_id, str) or not _ID.fullmatch(profile_id):
        check.fail(
            "id",
            "must be 1-64 characters of lowercase letters, digits, '-' or '_', "
            "starting with a letter or digit",
        )
    elif profile_id == GENERIC_PROFILE_ID:
        check.fail("id", "'generic' is reserved for the built-in Generic Device Profile")
    check.text(doc, "name", 64)
    check.text(doc, "vendor", 64)
    check.text(doc, "model", 64)
    check.text(doc, "version", 32)

    codes = doc.get("function_codes")
    valid_codes: tuple[int, ...] = ()
    if not isinstance(codes, list) or not codes:
        check.fail("function_codes", "must be a non-empty list such as [3] or [3, 4]")
    else:
        for index, code in enumerate(codes):
            path = f"function_codes[{index}]"
            if _is_int(code) and code in WRITE_FUNCTION_CODES:
                check.fail(path, f"FC{code:02d} is a write function code and is never allowed")
            elif not _is_int(code) or code not in READ_FUNCTION_CODES:
                check.fail(path, "must be 3 (holding registers) or 4 (input registers)")
        if len(set(map(repr, codes))) != len(codes):
            check.fail("function_codes", "must not repeat a function code")
        valid_codes = tuple(code for code in codes if _is_int(code) and code in READ_FUNCTION_CODES)

    allowlist = _allowed_registers(check, doc)
    _defaults(check, doc, valid_codes, allowlist)
    _fields(check, doc, allowlist)

    if check.errors:
        raise DeviceProfileError(check.errors)
    return DeviceProfile(deepcopy(doc))


def _allowed_registers(check: _Checker, doc: dict) -> tuple[int, ...] | None:
    if "allowed_registers" not in doc or doc["allowed_registers"] is None:
        return None
    registers = doc["allowed_registers"]
    if not isinstance(registers, list) or not registers:
        check.fail("allowed_registers", "must be omitted or a non-empty list of registers")
        return None
    if len(registers) > MAX_ALLOWED_REGISTERS:
        check.fail("allowed_registers", f"must list at most {MAX_ALLOWED_REGISTERS} registers")
        return None
    for index in range(len(registers)):
        check.integer(registers, index, f"allowed_registers[{index}]", 0, MAX_REGISTER_ADDRESS)
    if len(set(map(repr, registers))) != len(registers):
        check.fail("allowed_registers", "must not repeat a register")
    return tuple(item for item in registers if _is_int(item))


def _defaults(
    check: _Checker, doc: dict, codes: tuple[int, ...], allowlist: tuple[int, ...] | None
) -> None:
    if "defaults" not in doc:
        return
    defaults = doc["defaults"]
    if not isinstance(defaults, dict):
        check.fail("defaults", "must be an object")
        return
    check.unknown(defaults, _DEFAULT_KEYS, "defaults.")
    bounds = {
        "slave_start": (SLAVE_MIN, SLAVE_MAX),
        "slave_end": (SLAVE_MIN, SLAVE_MAX),
        "register": (0, MAX_REGISTER_ADDRESS),
        "count": (COUNT_MIN, COUNT_MAX),
        "timeout_ms": (TIMEOUT_MIN, TIMEOUT_MAX),
        "inter_request_delay_ms": (0, MAX_INTER_REQUEST_DELAY_MS),
        "retries": (0, MAX_RETRIES),
    }
    ok = {
        key: check.integer(defaults, key, f"defaults.{key}", *limits)
        for key, limits in bounds.items()
        if key in defaults
    }
    if "function_code" in defaults:
        code = defaults["function_code"]
        if not _is_int(code) or code not in codes:
            check.fail("defaults.function_code", "must be one of the profile's function_codes")
    if ("slave_start" in defaults) != ("slave_end" in defaults):
        check.fail("defaults", "slave_start and slave_end must be given together")
    elif ok.get("slave_start") and ok.get("slave_end"):
        if defaults["slave_start"] > defaults["slave_end"]:
            check.fail("defaults.slave_end", "must be at least slave_start")
    if ok.get("register"):
        count = defaults["count"] if ok.get("count") else 1
        if allowlist is not None and defaults["register"] not in allowlist:
            check.fail("defaults.register", "must be one of allowed_registers")
        elif allowlist is not None and any(
            reg not in allowlist
            for reg in range(defaults["register"], defaults["register"] + count)
        ):
            check.fail(
                "defaults.count", "every register of the default block must be in allowed_registers"
            )
        if defaults["register"] + count - 1 > MAX_REGISTER_ADDRESS:
            check.fail("defaults.count", "the register block must end at or before 65535")


def _fields(check: _Checker, doc: dict, allowlist: tuple[int, ...] | None) -> None:
    if "fields" not in doc:
        return
    fields = doc["fields"]
    if not isinstance(fields, list):
        check.fail("fields", "must be a list of field definitions")
        return
    if len(fields) > MAX_FIELDS:
        check.fail("fields", f"must define at most {MAX_FIELDS} fields")
        return
    seen: set[int] = set()
    for index, field in enumerate(fields):
        prefix = f"fields[{index}]"
        if not isinstance(field, dict):
            check.fail(prefix, "must be an object")
            continue
        check.unknown(field, _FIELD_KEYS, f"{prefix}.")
        if "register" not in field:
            check.fail(f"{prefix}.register", "is required")
        elif check.integer(field, "register", f"{prefix}.register", 0, MAX_REGISTER_ADDRESS):
            register = field["register"]
            if register in seen:
                check.fail(f"{prefix}.register", "is already defined by another field")
            seen.add(register)
            if allowlist is not None and register not in allowlist:
                check.fail(f"{prefix}.register", "must be one of allowed_registers")
        for key, max_length, required in (("name", 64, True), ("unit", 16, False)):
            if key not in field:
                if required:
                    check.fail(f"{prefix}.{key}", "is required")
            elif not isinstance(field[key], str) or not field[key].strip() or len(
                field[key]
            ) > max_length:
                check.fail(
                    f"{prefix}.{key}",
                    f"must be a non-empty string of at most {max_length} characters",
                )
        if "scale" in field:
            scale = field["scale"]
            if (
                type(scale) not in (int, float)
                or not math.isfinite(scale)
                or scale == 0
            ):
                check.fail(f"{prefix}.scale", "must be a finite, non-zero number")
        if field.get("data_type", "u16") not in DATA_TYPES:
            check.fail(f"{prefix}.data_type", "must be 'u16' or 's16'")
