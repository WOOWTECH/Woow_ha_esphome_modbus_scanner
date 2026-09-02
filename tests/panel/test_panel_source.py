"""Static contracts for the source panel and generated distribution."""

from pathlib import Path
import re

ROOT = Path(__file__).parents[2]
SOURCE = (ROOT / "panel_frontend/src/woow-esphome-modbus-scanner-panel.js").read_text()
MODEL = (ROOT / "panel_frontend/src/model.js").read_text()
STYLES = (ROOT / "panel_frontend/src/styles.js").read_text()
I18N = (ROOT / "panel_frontend/src/i18n.js").read_text()


def test_panel_calls_exact_six_services_and_requests_responses():
    services = set(
        re.findall(
            r'"(list_gateways|start_scan|get_scan_status|get_scan_results|cancel_scan|test_address)"',
            MODEL.split("export const SERVICES", 1)[1].split("]", 1)[0],
        )
    )
    assert services == {
        "list_gateways",
        "start_scan",
        "get_scan_status",
        "get_scan_results",
        "cancel_scan",
        "test_address",
    }
    assert "this.hass.callService(DOMAIN, service, data, undefined, undefined, true)" in SOURCE
    assert "normalizeResponse(response)" in SOURCE


def test_panel_has_serial_polling_cleanup_storage_and_accessibility_contracts():
    required = (
        "setTimeout(() => this._poll(scanId, token, generation), 1000)",
        "disconnectedCallback()",
        "this._stopPolling()",
        "localStorage",
        "safePreferences",
        'new CustomEvent("hass-toggle-menu"',
        'role="progressbar"',
        'aria-live="polite"',
        "focus-visible",
        "@media(max-width:360px)",
        "overflow:auto",
        "min-height:44px",
    )
    combined = SOURCE + STYLES + I18N
    assert all(item in combined for item in required)
    assert "sessionStorage" not in combined
    assert "mdi:" in SOURCE
    assert "<svg" not in SOURCE


def test_panel_documents_mock_scope_future_selector_and_risks():
    required = (
        "MOCK ONLY",
        "never contacts ESPHome",
        "intentionally disabled",
        "best-effort",
        "possible_collision",
        "Unknown scan ID",
        "Network/service errors",
        "Tokens, hosts, frames, replies, and credentials are never stored",
        "僅限模擬",
        "預期終止狀態",
    )
    assert all(item in SOURCE + I18N for item in required)


def test_panel_has_race_storage_sort_and_contrast_hardening():
    combined = SOURCE + MODEL + STYLES
    required = (
        "sanitizePreferences",
        "sanitizeRecent",
        "_operationGeneration",
        "_handleUnknown",
        "aria-sort",
        "mdi:check-circle",
        "border:2px solid var(--control-line)",
        "currentColor",
    )
    assert all(item in combined for item in required)
