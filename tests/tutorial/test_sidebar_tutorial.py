"""Version 0.2.0 sidebar tutorial contracts."""

from pathlib import Path

ROOT = Path(__file__).parents[2]
TUTORIAL = (
    ROOT / "docs/tutorial/woow-esphome-modbus-scanner-v0.2.0-zh-TW.html"
).read_text(encoding="utf-8")


def test_sidebar_tutorial_keeps_mock_warning_first_class():
    first_content = TUTORIAL.split('<main id="main"', 1)[0]
    assert "v0.2.0 僅限 MOCK 模擬" in first_content
    assert "不連線 ESPHome" in first_content
    assert "不掃描任何實體硬體" in first_content


def test_sidebar_tutorial_documents_route_fields_flows_and_storage():
    required = (
        "/woow-esphome-modbus-scanner",
        "Modbus Scanner",
        "所有 HA 使用者",
        "ESPHome selector",
        "每秒一次且不重疊",
        "Refresh status/results",
        "六種 outcome counts",
        "localStorage",
        "token、host、frame、憑證或回應",
        "unknown",
    )
    assert all(item in TUTORIAL for item in required)


def test_sidebar_tutorial_documents_permanent_permission_risk():
    assert "永久全使用者政策" in TUTORIAL
    assert "不做 admin/user 權限檢查" in TUTORIAL
    assert "任一使用者可能產生匯流排流量" in TUTORIAL
    assert "啟用硬體前" in TUTORIAL
