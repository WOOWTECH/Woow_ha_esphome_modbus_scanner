"""The bridge v2 contract file is the only cross-language protocol source.

HA's v2 adapter, the HA fake Gateway and the host-compiled firmware tests all read the same
``contract.json``; CI runs the firmware tests against that file. The former three-way
profile generator (one Python, one JS and one C++ copy of the vendor profile) is gone.
"""

import json
from pathlib import Path

import yaml

from custom_components.woow_esphome_modbus_scanner.const import (
    PANEL_STATIC_URL,
    VERSION,
)
from custom_components.woow_esphome_modbus_scanner.modbus_scan.bridge_v2 import contract

ROOT = Path(__file__).parents[2]
CONTRACT_PATH = "custom_components/woow_esphome_modbus_scanner/modbus_scan/bridge_v2/contract.json"
WORKFLOW = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
REMOVED = (
    "generate_profiles",
    "profile-generated",
    "profile_generated",
    "profiles/guanjie-v1.json",
)
SKIPPED_DIRS = {".git", ".claude", ".venv", ".pytest_cache", ".ruff_cache", "node_modules", "dist"}
TEXT_SUFFIXES = {".py", ".js", ".mjs", ".json", ".yaml", ".yml", ".md", ".h", ".cpp", ".html"}


class _EsphomeLoader(yaml.SafeLoader):
    """Reads ESPHome YAML, keeping ``!secret`` values as plain strings."""


_EsphomeLoader.add_constructor("!secret", lambda loader, node: loader.construct_scalar(node))


def _run_steps(job):
    return [step["run"] for step in WORKFLOW["jobs"][job]["steps"] if "run" in step]


def test_ha_adapter_reads_the_shared_contract_file():
    assert contract.CONTRACT == json.loads((ROOT / CONTRACT_PATH).read_text(encoding="utf-8"))


def test_ha_fake_gateway_and_firmware_tests_read_the_same_contract_file():
    fake_gateway = (ROOT / "tests/services/test_bridge_v2.py").read_text(encoding="utf-8")
    assert CONTRACT_PATH in fake_gateway
    firmware_test = (ROOT / "firmware/tests/scanner_core_test.cpp").read_text(encoding="utf-8")
    assert CONTRACT_PATH in firmware_test  # its default; CI passes the path explicitly too
    ci_runs = "\n".join(_run_steps("tests"))
    assert f"/tmp/scanner-core {CONTRACT_PATH}" in ci_runs


def test_no_removed_profile_tooling_is_referenced():
    assert not (ROOT / "tools/generate_profiles.py").exists()
    assert not (ROOT / "profiles").exists()
    for path in ROOT.rglob("*"):
        if not path.is_file() or SKIPPED_DIRS & set(path.relative_to(ROOT).parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES or path.name == Path(__file__).name:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert all(term not in text for term in REMOVED), path


def test_integration_panel_and_firmware_share_one_version():
    assert VERSION == "0.5.0.dev1"
    manifest = json.loads(
        (ROOT / "custom_components/woow_esphome_modbus_scanner/manifest.json").read_text()
    )
    assert manifest["version"] == VERSION
    assert f"/frontend/{VERSION}/" in PANEL_STATIC_URL
    package = json.loads((ROOT / "panel_frontend/package.json").read_text())
    assert package["version"] == "0.5.0-dev.1"  # the same version in npm's semver spelling
    example = yaml.load(  # noqa: S506 - a SafeLoader subclass
        (ROOT / "firmware/examples/generic-modbus-scanner.yaml").read_text(encoding="utf-8"),
        Loader=_EsphomeLoader,
    )
    assert example["esphome"]["project"]["version"] == VERSION


def test_generic_device_profile_bounds_are_the_contract_hard_limits():
    """ADR 0005: the Generic Device Profile's bounds are the bridge v2 hard limits, not a copy."""
    from custom_components.woow_esphome_modbus_scanner.modbus_scan.device_profile import (
        GENERIC_DEVICE_PROFILE,
        parse_device_profile,
    )

    hard = contract.CONTRACT["hard_limits"]
    limits = GENERIC_DEVICE_PROFILE.limits.as_dict()
    assert (limits["slave_min"], limits["slave_max"]) == (hard["slave_min"], hard["slave_max"])
    assert limits["register_count_max"] == hard["count_max"]
    assert (limits["timeout_ms_min"], limits["timeout_ms_max"]) == (
        hard["timeout_ms_min"],
        hard["timeout_ms_max"],
    )
    assert list(GENERIC_DEVICE_PROFILE.function_codes) == hard["function_codes"]
    for code in hard["write_function_codes"]:
        document = {
            "schema_version": 1,
            "id": "writer",
            "name": "w",
            "vendor": "v",
            "model": "m",
            "version": "1",
            "function_codes": [code],
        }
        try:
            parse_device_profile(document)
        except ValueError as err:
            assert f"FC{code:02d} is a write function code" in str(err)
        else:
            raise AssertionError(f"FC{code} was accepted")


def test_panel_bridge_v2_defaults_are_the_v2_adapters_defaults():
    """The panel's V2_DEFAULTS mirror what the v2 adapter fills in for omitted fields."""
    import re

    from custom_components.woow_esphome_modbus_scanner.modbus_scan.bridge_v2.provider import (
        LIMITS,
    )

    model = (ROOT / "panel_frontend/src/model.js").read_text(encoding="utf-8")
    literal = re.search(r"export const V2_DEFAULTS = Object\.freeze\(\{(.*?)\}\);", model, re.S)
    body = re.sub(r"(\w+):", r'"\1":', literal.group(1)).strip().rstrip(",")
    panel = json.loads("{" + body + "}")
    assert panel == {key: str(value) if isinstance(value, str) else value
                     for key, value in LIMITS.defaults.items()}


def test_inter_request_delay_cap_leaves_the_lease_idle_time_for_round_trips():
    """The contract states the cap; HA validates against it, below the Gateway's idle limit."""
    from custom_components.woow_esphome_modbus_scanner.modbus_scan.models import (
        MAX_INTER_REQUEST_DELAY_MS,
    )

    lease = contract.CONTRACT["lease"]
    assert lease["inter_request_delay_max_ms"] == MAX_INTER_REQUEST_DELAY_MS == 3000
    assert lease["idle_ms"] - lease["inter_request_delay_max_ms"] >= 2000
