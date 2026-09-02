"""Static public-repository contract checks."""

import json
from pathlib import Path

import yaml

from custom_components.woow_esphome_modbus_scanner.const import DOMAIN, NAME, VERSION

ROOT = Path(__file__).parents[2]
INTEGRATION = ROOT / "custom_components" / DOMAIN


def test_manifest_identity_and_hacs_layout():
    manifest = json.loads((INTEGRATION / "manifest.json").read_text())
    assert manifest["domain"] == DOMAIN
    assert manifest["name"] == NAME
    assert manifest["version"] == VERSION
    assert manifest["config_flow"] is True
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
        and "__pycache__" not in path.parts
    ]


def test_repository_contains_no_legacy_coupling():
    forbidden = ("woow_multi" + "_protocol", "kn" + "x", "d" + "mx")
    for path in _repository_files():
        if path.suffix.lower() not in {".py", ".json", ".yaml", ".yml", ".md", ".toml"}:
            continue
        text = path.read_text(errors="ignore").lower()
        assert all(term not in text for term in forbidden), path


def test_repository_has_no_browser_bundle_panel_registration_or_editor_runtime():
    files = _repository_files()
    browser_suffixes = {".css", ".html", ".js", ".jsx", ".map", ".svg", ".ts", ".tsx"}
    permitted_static_files = {
        ROOT / "docs" / "tutorial" / "woow-esphome-modbus-scanner-v0.1.0-zh-TW.html",
        ROOT / "tests" / "tutorial" / "browser_check.mjs",
    }
    browser_directories = {"front" + "end", "www"}
    forbidden_code = (
        "async_register_" + "panel",
        "panel_" + "custom",
        "lovel" + "ace",
        "code" + "mirror",
        "mo" + "naco",
    )

    assert not any(
        path.suffix.lower() in browser_suffixes and path not in permitted_static_files
        for path in files
    )
    assert not any(browser_directories.intersection(path.parts) for path in files)
    for path in files:
        if path.suffix.lower() not in {".py", ".json", ".yaml", ".yml"}:
            continue
        text = path.read_text(errors="ignore").lower()
        assert all(term not in text for term in forbidden_code), path

    manifest = json.loads((INTEGRATION / "manifest.json").read_text())
    platform_dependencies = set(manifest.get("dependencies", ())) | set(
        manifest.get("after_dependencies", ())
    )
    assert not platform_dependencies.intersection(
        {"front" + "end", "http", "panel_" + "custom"}
    )
