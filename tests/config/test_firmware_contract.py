"""The ESPHome codegen of the modbus_scanner component agrees with the bridge v2 contract.

The C++ core is checked against the contract by firmware/tests; this covers the Python
codegen, which fixes the text sensor names HA looks up.
"""

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import yaml

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


TWO_SCANNERS = (ROOT / "firmware/tests/two-modbus-scanners.yaml").read_text(encoding="utf-8")
ONE_ENTRY_MESSAGE = (
    "A node supports only one modbus_scanner; scan a second RS-485 line with another node"
)


def test_example_is_a_plain_modbus_controller_node():
    example = EXAMPLE
    assert "modbus_controller:" in example
    assert "modbus_scanner:" in example
    assert "api:\n" in example
    assert "actions:" not in example  # the component registers its own probe action


def test_example_has_one_scanner():
    config = yaml.safe_load(EXAMPLE.replace("!secret", ""))
    assert config["modbus_scanner"] == [{"modbus_id": "rs485"}]


class _Invalid(Exception):
    """Stands in for esphome.config_validation.Invalid."""


@pytest.fixture
def codegen(monkeypatch):
    """The codegen module, imported against stub esphome modules (ESPHome is not installed)."""
    core = SimpleNamespace(data={}, config={})
    stubs = {
        "esphome": MagicMock(),
        "esphome.codegen": MagicMock(),
        "esphome.components": MagicMock(),
        "esphome.components.const": MagicMock(),
        "esphome.config_validation": MagicMock(Invalid=_Invalid),
        "esphome.const": MagicMock(CONF_NAME="name"),
        "esphome.core": MagicMock(CORE=core),
        "esphome.final_validate": MagicMock(),
    }
    for name, module in stubs.items():
        monkeypatch.setitem(sys.modules, name, module)
        # `import esphome.config_validation as cv` reads the attribute of the parent package.
        parent, _, child = name.rpartition(".")
        if parent:
            setattr(stubs[parent], child, module)
    spec = importlib.util.spec_from_file_location(
        "modbus_scanner_codegen", ROOT / "firmware/components/modbus_scanner/__init__.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, core


def test_codegen_refuses_a_second_modbus_scanner_entry(codegen):
    module, core = codegen
    first = module._one_entry_per_node({"modbus_id": "hub_a"})
    # The only entry carries the Gateway's text sensors under their contract names.
    assert {first[key]["name"] for key in module._GATEWAY_SENSORS} == {
        sensor["name"] for sensor in CONTRACT["text_sensors"].values()
    }
    with pytest.raises(_Invalid, match=ONE_ENTRY_MESSAGE):
        module._one_entry_per_node({"modbus_id": "hub_b"})
    assert module.ONE_ENTRY_MESSAGE == ONE_ENTRY_MESSAGE
    assert core.data


def test_final_validation_refuses_two_entries(codegen):
    module, _core = codegen
    with pytest.raises(_Invalid, match=ONE_ENTRY_MESSAGE):
        module._final_validate([{"modbus_id": "hub_a"}, {"modbus_id": "hub_b"}])


def test_two_scanner_fixture_declares_two_entries():
    """CI runs `esphome config` on this fixture and expects ONE_ENTRY_MESSAGE."""
    config = yaml.safe_load(TWO_SCANNERS)
    assert [entry["modbus_id"] for entry in config["modbus_scanner"]] == ["hub_a", "hub_b"]
    assert len(config["modbus"]) == len(config["uart"]) == 2
