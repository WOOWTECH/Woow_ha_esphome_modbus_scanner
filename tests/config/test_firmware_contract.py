"""The ESPHome codegen of the modbus_scanner component agrees with the bridge v2 contract.

The C++ core is checked against the contract by firmware/tests; this covers the Python
codegen, which fixes the text sensor names HA looks up.
"""

import contextvars
import copy
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
    core = SimpleNamespace(data={}, config={}, raw_config=None)
    path_context = contextvars.ContextVar("Config path")
    stubs = {
        "esphome": MagicMock(),
        "esphome.config": MagicMock(path_context=path_context),
        "esphome.codegen": MagicMock(),
        "esphome.components": MagicMock(),
        "esphome.components.const": MagicMock(),
        "esphome.config_validation": MagicMock(Invalid=_Invalid),
        "esphome.const": MagicMock(
            CONF_NAME="name", CONF_DISABLED_BY_DEFAULT="disabled_by_default"
        ),
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
    return module, core, path_context


def _validate_entries(codegen, entries):
    """Validate each entry the way ESPHome's MULTI_CONF steps do: path [domain, i], a copy."""
    module, core, path_context = codegen
    core.raw_config = {"modbus_scanner": entries}
    results = []
    for index, entry in enumerate(entries):
        token = path_context.set(["modbus_scanner", index])
        try:
            results.append(module._one_entry_per_node(copy.deepcopy(entry)))
        except _Invalid as err:
            results.append(err)
        finally:
            path_context.reset(token)
    return results


def test_codegen_one_scanner_entry_is_valid(codegen):
    module = codegen[0]
    (first,) = _validate_entries(codegen, [{"modbus_id": "hub_a"}])
    # The only entry carries the Gateway's text sensors under their contract names.
    assert {first[key]["name"] for key in module._GATEWAY_SENSORS} == {
        sensor["name"] for sensor in CONTRACT["text_sensors"].values()
    }
    # No state of its own: validating the same config again gives the same result.
    assert _validate_entries(codegen, [{"modbus_id": "hub_a"}]) == [first]
    assert module.ONE_ENTRY_MESSAGE == ONE_ENTRY_MESSAGE


def test_codegen_disables_only_the_info_sensor_by_default(codegen):
    """HA stores no state for a disabled entity, so a long Info logs no error (issue #25)."""
    module = codegen[0]
    (config,) = _validate_entries(codegen, [{"modbus_id": "hub_a"}])
    assert config[module.CONF_INFO_SENSOR]["disabled_by_default"] is True
    for key in (module.CONF_RESULT_SENSOR, module.CONF_LEASE_SENSOR):
        assert "disabled_by_default" not in config[key]  # ESPHome's own default: enabled


def test_codegen_info_sensor_default_applies_to_a_sensor_written_in_yaml(codegen):
    module = codegen[0]
    entry = {"modbus_id": "hub_a", "info_sensor": {"name": module.INFO_SENSOR_NAME}}
    (config,) = _validate_entries(codegen, [entry])
    assert config[module.CONF_INFO_SENSOR] == {
        "name": module.INFO_SENSOR_NAME,
        "disabled_by_default": True,
    }


def test_codegen_yaml_disabled_by_default_overrides_the_info_default(codegen):
    module = codegen[0]
    entry = {
        "modbus_id": "hub_a",
        "info_sensor": {"name": module.INFO_SENSOR_NAME, "disabled_by_default": False},
    }
    (config,) = _validate_entries(codegen, [entry])
    assert config[module.CONF_INFO_SENSOR]["disabled_by_default"] is False


def test_codegen_refuses_only_the_second_of_two_entries(codegen):
    first, second = _validate_entries(codegen, [{"modbus_id": "hub_a"}, {"modbus_id": "hub_b"}])
    assert isinstance(first, dict)
    assert isinstance(second, _Invalid) and str(second) == ONE_ENTRY_MESSAGE


def test_codegen_refuses_every_entry_after_the_first(codegen):
    """ESPHome stops at the second entry's error; the check itself refuses all later ones."""
    hubs = [{"modbus_id": f"hub_{n}"} for n in range(3)]
    first, *rest = _validate_entries(codegen, hubs)
    assert isinstance(first, dict)
    assert [str(err) for err in rest] == [ONE_ENTRY_MESSAGE] * 2


def test_codegen_refuses_a_copy_of_the_second_entry(codegen):
    """The check must not rely on object identity with CORE.raw_config entries."""
    module, core, path_context = codegen
    hub_a, hub_b = {"modbus_id": "hub_a"}, {"modbus_id": "hub_b"}
    core.raw_config = {"modbus_scanner": [hub_a, hub_b]}
    token = path_context.set(["modbus_scanner", 0])
    try:
        assert isinstance(module._one_entry_per_node(dict(hub_a)), dict)
    finally:
        path_context.reset(token)
    token = path_context.set(["modbus_scanner", 1])
    try:
        with pytest.raises(_Invalid, match=ONE_ENTRY_MESSAGE):
            module._one_entry_per_node(dict(hub_b))
    finally:
        path_context.reset(token)


def test_two_scanner_fixture_declares_two_entries():
    """CI runs `esphome config` on this fixture and expects ONE_ENTRY_MESSAGE."""
    config = yaml.safe_load(TWO_SCANNERS)
    assert [entry["modbus_id"] for entry in config["modbus_scanner"]] == ["hub_a", "hub_b"]
    assert len(config["modbus"]) == len(config["uart"]) == 2
