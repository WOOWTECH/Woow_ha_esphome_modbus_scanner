"""Bridge protocol v2 contract, loaded from the shared machine-readable contract file.

``contract.json`` is the single source of truth; the firmware host tests read the same file.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

CONTRACT: dict[str, Any] = json.loads(
    Path(__file__).with_name("contract.json").read_text(encoding="utf-8")
)

BRIDGE_VERSION: int = CONTRACT["bridge_version"]
PROBE_ACTION: str = CONTRACT["actions"]["probe"]["name"]
PROBE_ARGS: dict[str, str] = {
    arg["name"]: arg["type"] for arg in CONTRACT["actions"]["probe"]["args"]
}
INFO_SENSOR: str = CONTRACT["text_sensors"]["info"]["name"]
RESULT_SENSOR: str = CONTRACT["text_sensors"]["result"]["name"]
HARD_LIMITS: dict[str, Any] = CONTRACT["hard_limits"]
OUTCOMES: tuple[str, ...] = tuple(CONTRACT["outcomes"])
ERROR_CODES: tuple[str, ...] = tuple(CONTRACT["error_codes"])
RESULT_SCHEMA_VERSION: int = CONTRACT["result"]["schema_version"]
RESULT_COMMON_FIELDS: tuple[str, ...] = tuple(CONTRACT["result"]["common_fields"])
RESULT_OUTCOME_FIELDS: dict[str, tuple[str, ...]] = {
    outcome: tuple(fields) for outcome, fields in CONTRACT["result"]["outcome_fields"].items()
}
INFO_SCHEMA_VERSION: int = CONTRACT["info"]["schema_version"]
INFO_FIELDS: tuple[str, ...] = tuple(CONTRACT["info"]["fields"])
INFO_BUS_FIELDS: tuple[str, ...] = tuple(CONTRACT["info"]["bus_fields"])
INFO_POLLER_FIELDS: tuple[str, ...] = tuple(CONTRACT["info"]["poller_fields"])
# Optional info fields naming a Bus's own result and lease sensors (bus_text_sensors).
INFO_BUS_RESULT_SENSOR: str = CONTRACT["bus_text_sensors"]["result"]["info_field"]
INFO_BUS_LEASE_SENSOR: str = CONTRACT["bus_text_sensors"]["lease"]["info_field"]
INFO_SERIAL_FIELDS: tuple[str, ...] = tuple(CONTRACT["info"]["serial_fields"])
SERIAL_PARITIES: tuple[str, ...] = tuple(CONTRACT["info"]["serial_parities"])

RELEASE_ACTION: str = CONTRACT["actions"]["release"]["name"]
RELEASE_ARGS: dict[str, str] = {
    arg["name"]: arg["type"] for arg in CONTRACT["actions"]["release"]["args"]
}
LEASE_SENSOR: str = CONTRACT["text_sensors"]["lease"]["name"]
LEASE_SCHEMA_VERSION: int = CONTRACT["lease"]["schema_version"]
LEASE_STATES: tuple[str, ...] = tuple(CONTRACT["lease"]["states"])
LEASE_END_REASONS: tuple[str, ...] = tuple(CONTRACT["lease"]["end_reasons"])
# The longest wait HA keeps between Probes of one Scan, so the Scan never ends its own lease.
LEASE_INTER_REQUEST_DELAY_MAX_MS: int = CONTRACT["lease"]["inter_request_delay_max_ms"]

_ID = CONTRACT["identifiers"]["request_id"]
REQUEST_ID_PATTERN = re.compile(f"[{_ID['charset']}]{{{_ID['min_length']},{_ID['max_length']}}}")
