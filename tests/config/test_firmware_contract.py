"""The ESPHome codegen of the modbus_scanner component agrees with the bridge v2 contract.

The C++ core is checked against the contract by firmware/tests; this covers the Python
codegen, which fixes the text sensor names HA looks up.
"""

import json
from pathlib import Path

ROOT = Path(__file__).parents[2]
CONTRACT = json.loads(
    (
        ROOT / "custom_components/woow_esphome_modbus_scanner/modbus_scan/bridge_v2/contract.json"
    ).read_text(encoding="utf-8")
)
CODEGEN = (ROOT / "firmware/components/modbus_scanner/__init__.py").read_text(encoding="utf-8")
EXAMPLE = (ROOT / "firmware/examples/generic-modbus-scanner.yaml").read_text(encoding="utf-8")


def test_codegen_uses_contract_sensor_names():
    for sensor in CONTRACT["text_sensors"].values():
        assert f'"{sensor["name"]}"' in CODEGEN


def test_codegen_requires_esphome_2026_9():
    assert "MIN_ESPHOME_VERSION = (2026, 9, 0)" in CODEGEN
    assert "cv.require_esphome_version(*MIN_ESPHOME_VERSION)" in CODEGEN


def test_example_is_a_plain_modbus_controller_node():
    assert "modbus_controller:" in EXAMPLE
    assert "modbus_scanner:" in EXAMPLE
    assert "api:\n" in EXAMPLE
    assert "actions:" not in EXAMPLE  # the component registers its own probe action
