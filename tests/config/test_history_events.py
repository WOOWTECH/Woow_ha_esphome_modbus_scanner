"""Corrupt persisted event timelines cannot reach the frontend."""

import pytest

from custom_components.woow_esphome_modbus_scanner.history import ScanHistory


@pytest.mark.parametrize(
    "events,valid",
    [
        ([], True),
        ([{"phase": "completed", "elapsed_ms": 123}], True),
        (None, False),
        ("bad", False),
        ([None], False),
        ([{"phase": [], "elapsed_ms": 0}], False),
        ([{"phase": "secret-shaped-unknown", "elapsed_ms": 0}], False),
        ([{"phase": "completed", "elapsed_ms": "1"}], False),
        ([{"phase": "completed", "elapsed_ms": True}], False),
        ([{"phase": "completed", "elapsed_ms": -1}], False),
        ([{"phase": "completed", "elapsed_ms": 0, "extra": "bad"}], False),
        ([{"phase": "probe", "elapsed_ms": 0}] * 33, False),
    ],
)
def test_persisted_events_are_bounded_typed_and_allowlisted(events, valid):
    status = {
        "scan_id": "00000000-0000-4000-8000-000000000001",
        "status": "completed",
        "provider": "mock",
        "gateway_id": "mock-gateway",
        "events": events,
    }
    results = {**status, "responders": []}
    assert ScanHistory._valid({"status": status, "results": results}) is valid
