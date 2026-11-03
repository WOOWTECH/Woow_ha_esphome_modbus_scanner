"""Contracts for the vendor-neutral 0.5.0 documentation: READMEs and the current tutorial."""

from html.parser import HTMLParser
from pathlib import Path
import re

import yaml

from custom_components.woow_esphome_modbus_scanner.const import VERSION

ROOT = Path(__file__).parents[2]
SERVICES = set(
    yaml.safe_load(
        (ROOT / "custom_components/woow_esphome_modbus_scanner/services.yaml").read_text(
            encoding="utf-8"
        )
    )
)
TUTORIAL_NAME = "woow-esphome-modbus-scanner-v0.5.0-zh-TW.html"
TUTORIAL = (ROOT / "docs" / "tutorial" / TUTORIAL_NAME).read_text(encoding="utf-8")
REPOSITORY = "https://github.com/WOOWTECH/Woow_ha_esphome_modbus_scanner"
EXAMPLE_PROFILE = "examples/device_profiles/guanjie-ind17.json"
READMES = {
    "README.md": "## History",
    "README_zh-TW.md": "## 歷史",
}
# The documented fields every scan-shaped reader needs; see services.yaml.
SCAN_FIELDS = (
    "bus",
    "device_profile_id",
    "large_range_confirmed",
    "pause_pollers",
    "mock_scenario",
    "mock_profile",
    "safety_confirmed",
)


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.ids: set[str] = set()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        self.tags.append((tag, attributes))
        if element_id := attributes.get("id"):
            self.ids.add(element_id)
        if href := attributes.get("href"):
            self.hrefs.append(href)


def _parsed() -> _Parser:
    parser = _Parser()
    parser.feed(TUTORIAL)
    return parser


def _without_example_path(text: str) -> str:
    return text.replace(EXAMPLE_PROFILE, "").replace("guanjie-ind17.json", "")


def _assert_vendor_neutral(text: str, where: str) -> None:
    lowered = _without_example_path(text).lower()
    for vendor_term in ("guanjie", "冠傑", "貫捷", "in-d17", "dehumidifier", "除濕機"):
        assert vendor_term not in lowered, f"{where} mentions {vendor_term!r}"


# --- READMEs -------------------------------------------------------------------------


def test_readmes_link_the_current_tutorial_and_describe_the_development_version() -> None:
    blob = f"{REPOSITORY}/blob/main/docs/tutorial/{TUTORIAL_NAME}"
    raw = (
        "https://raw.githubusercontent.com/WOOWTECH/Woow_ha_esphome_modbus_scanner/main/"
        f"docs/tutorial/{TUTORIAL_NAME}"
    )
    for name in READMES:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert blob in text and raw in text, name
        assert VERSION in text, name
        assert "0.4.0.dev1: deployed" not in text, name


def test_readmes_main_part_is_vendor_neutral_and_history_is_separate() -> None:
    for name, history_heading in READMES.items():
        text = (ROOT / name).read_text(encoding="utf-8")
        assert history_heading in text, name
        main, history = text.split(history_heading, 1)
        _assert_vendor_neutral(main, name)
        assert "docs/history/" in history, name
        assert "docs/adr/0004-experimental-guanjie-fc03-bridge.md" in history, name


def test_readmes_document_firmware_install_and_minimum_esphome() -> None:
    for name in READMES:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "2026.9.0" in text, name
        assert "external_components:" in text, name
        assert "path: firmware/components" in text, name
        assert "components: [modbus_scanner]" in text, name
        assert "modbus_scanner:\n  - modbus_id:" in text, name
        assert "modbus_controller:" in text, name
        assert "firmware/examples/multi-bus-modbus-scanner.yaml" in text, name


def test_readmes_state_the_access_policy() -> None:
    en = (ROOT / "README.md").read_text(encoding="utf-8")
    assert (
        "any active Home Assistant user can generate read-only Modbus traffic on any "
        "enrolled Bus, for slave IDs 1–247"
    ) in " ".join(en.split())
    zh = (ROOT / "README_zh-TW.md").read_text(encoding="utf-8")
    assert "任何啟用中的 Home Assistant 使用者都能對任一已登錄 Bus 的 1–247 站號產生唯讀流量" in zh


def test_readmes_document_every_service_field_and_concept() -> None:
    for name in READMES:
        text = (ROOT / name).read_text(encoding="utf-8")
        for service in SERVICES:
            assert f"`{service}`" in text, f"{name}: {service}"
        for field in SCAN_FIELDS:
            assert f"`{field}`" in text, f"{name}: {field}"
        for item in (
            "set_pausable_pollers",
            EXAMPLE_PROFILE,
            "schema_version",
            "allowed_registers",
            "Repairs",
            "bridge v1",
            "docs/adr/0005-vendor-neutral-scanner-component-and-device-profiles.md",
            "docs/adr/0006-codegen-discovery-and-runtime-selection-of-pausable-pollers.md",
            "docs/adr/0007-per-scan-lease-with-gateway-owned-recovery.md",
        ):
            assert item in text, f"{name}: {item}"


# --- current tutorial ----------------------------------------------------------------


def test_tutorial_identity_version_and_sections() -> None:
    assert '<html lang="zh-Hant">' in TUTORIAL
    assert VERSION in TUTORIAL
    parser = _parsed()
    assert sum(tag == "h1" for tag, _attrs in parser.tags) == 1
    toc = re.search(r'<nav class="toc-content".*?</nav>', TUTORIAL, re.DOTALL).group()
    anchors = re.findall(r'href="#([a-z-]+)"', toc)
    # tests/tutorial/browser_check.mjs expects exactly 15 TOC entries starting at #scope.
    assert anchors == [
        "scope",
        "architecture",
        "modbus",
        "firmware",
        "install",
        "services",
        "profiles",
        "lease",
        "labs",
        "payloads",
        "mock",
        "rest",
        "troubleshooting",
        "glossary",
        "sources",
    ]
    assert set(anchors) <= parser.ids


def test_tutorial_is_vendor_neutral() -> None:
    _assert_vendor_neutral(TUTORIAL, TUTORIAL_NAME)
    assert EXAMPLE_PROFILE in TUTORIAL


def test_tutorial_documents_every_public_service_and_no_other() -> None:
    documented = set(re.findall(r"woow_esphome_modbus_scanner\.([a-z_]+)", TUTORIAL))
    assert documented <= SERVICES
    for service in SERVICES:
        assert f"<code>{service}</code>" in TUTORIAL, service
    for field in SCAN_FIELDS:
        assert f"<code>{field}</code>" in TUTORIAL, field


def test_tutorial_documents_firmware_install_and_minimum_esphome() -> None:
    for item in (
        "ESPHome 2026.9.0",
        "external_components:",
        "path: firmware/components",
        "components: [modbus_scanner]",
        "modbus_scanner:\n  - modbus_id: rs485",
        "modbus_controller:",
        "bus: line_a",
        "PollingComponent",
    ):
        assert item in TUTORIAL, item


def test_tutorial_states_access_policy_and_safety_facts() -> None:
    for item in (
        "任何啟用中的 Home Assistant 使用者都能對任一已登錄 Bus 的 1–247 站號產生唯讀流量",
        "超過 32 個",
        "5 秒",
        "10 分鐘",
        "待送的寫入",
        "update_interval",
        "一次只有一個 probe",
        "Repairs",
        "bridge v1",
        "schema_version",
        "allowed_registers",
        "Generic Device Profile",
    ):
        assert item in TUTORIAL, item


def test_tutorial_accessibility_and_offline_contract() -> None:
    parser = _parsed()
    tables = [attrs for tag, attrs in parser.tags if tag == "table"]
    wraps = [a for t, a in parser.tags if t == "div" and a.get("class") == "table-wrap"]
    assert tables and len(wraps) == len(tables)
    assert sum(tag == "caption" for tag, _attrs in parser.tags) == len(tables)
    assert all(a.get("role") == "region" and a.get("tabindex") == "0" for a in wraps)
    assert all(a.get("scope") == "col" for t, a in parser.tags if t == "th")
    pres = [attrs for tag, attrs in parser.tags if tag == "pre"]
    assert pres and all(a.get("tabindex") == "0" and a.get("aria-label") for a in pres)
    for tag, attrs in parser.tags:
        if tag in {"script", "img", "iframe"}:
            assert not attrs.get("src")
        if tag == "link":
            assert attrs.get("rel") not in {"stylesheet", "preload", "modulepreload"}
    assert "@import" not in TUTORIAL
    for href in parser.hrefs:
        if href.startswith("#"):
            assert href[1:] in parser.ids, href
    forbidden = ("woow_multi" + "_protocol", "kn" + "x", "d" + "mx")
    assert all(term not in TUTORIAL.lower() for term in forbidden)
