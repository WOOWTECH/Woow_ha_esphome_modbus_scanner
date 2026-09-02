"""Static public-repository contract checks."""

import json
from pathlib import Path

import yaml

from custom_components import woow_esphome_modbus_scanner as integration
from custom_components.woow_esphome_modbus_scanner.const import DOMAIN, NAME, VERSION

ROOT = Path(__file__).parents[2]
INTEGRATION = ROOT / "custom_components" / DOMAIN


def test_manifest_identity_and_hacs_layout():
    manifest = json.loads((INTEGRATION / "manifest.json").read_text())
    assert manifest["domain"] == DOMAIN
    assert manifest["name"] == NAME
    assert manifest["version"] == VERSION
    assert manifest["config_flow"] is True
    assert list(manifest)[:2] == ["domain", "name"]
    assert list(manifest)[2:] == sorted(list(manifest)[2:])
    assert callable(integration.CONFIG_SCHEMA)
    hacs = json.loads((ROOT / "hacs.json").read_text())
    assert hacs["name"] == NAME
    assert hacs["content_in_root"] is False


def test_services_yaml_exposes_exact_public_names():
    metadata = yaml.safe_load((INTEGRATION / "services.yaml").read_text())
    assert set(metadata) == {
        "list_gateways",
        "start_scan",
        "get_scan_status",
        "get_scan_results",
        "cancel_scan",
        "test_address",
    }


def _repository_files():
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and ".git" not in path.parts
        and ".venv" not in path.parts
        and ".pytest_cache" not in path.parts
        and "node_modules" not in path.parts
        and "__pycache__" not in path.parts
    ]


def test_repository_contains_no_legacy_coupling():
    forbidden = ("woow_multi" + "_protocol", "kn" + "x", "d" + "mx")
    for path in _repository_files():
        if path.suffix.lower() not in {
            ".py",
            ".json",
            ".yaml",
            ".yml",
            ".md",
            ".toml",
            ".js",
            ".html",
        }:
            continue
        text = path.read_text(errors="ignore").lower()
        assert all(term not in text for term in forbidden), path


def test_repository_contains_standalone_generated_panel_bundle():
    bundle = INTEGRATION / "frontend" / "woow-esphome-modbus-scanner-panel.js"
    source = ROOT / "panel_frontend" / "src" / "woow-esphome-modbus-scanner-panel.js"
    assert source.is_file()
    assert bundle.is_file()
    assert bundle.stat().st_size > 10_000

    manifest = json.loads((INTEGRATION / "manifest.json").read_text())
    assert set(manifest["dependencies"]) == {"frontend", "http", "panel_custom"}
