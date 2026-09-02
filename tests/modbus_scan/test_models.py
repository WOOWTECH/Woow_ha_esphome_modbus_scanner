"""Validation tests for provider-neutral Modbus scan models."""

import pytest

from custom_components.woow_esphome_modbus_scanner.modbus_scan.models import (
    ProbeType,
    ScanRequest,
)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("start_id", 1.9),
        ("start_id", True),
        ("end_id", 2.0),
        ("register_address", False),
        ("register_count", 1.5),
        ("timeout_ms", 500.1),
        ("retries", True),
        ("inter_request_delay_ms", 0.1),
    ],
)
def test_direct_request_rejects_non_integer_numeric_fields(field, value):
    request = ScanRequest.mock(**{field: value})

    with pytest.raises(ValueError, match=field):
        request.validate()


def test_request_requires_typed_probe_after_service_normalization():
    request = ScanRequest.mock(probe_type="holding_register")

    with pytest.raises(ValueError, match="probe_type"):
        request.validate()

    ScanRequest.mock(probe_type=ProbeType.HOLDING_REGISTER).validate()


def test_request_validation_is_provider_neutral():
    request = ScanRequest(
        provider="physical",
        gateway_id="serial:/dev/ttyUSB0",
        start_id=1,
        end_id=2,
        mock_profile="provider-owned-value",
        safety_confirmed=True,
    )

    request.validate()
