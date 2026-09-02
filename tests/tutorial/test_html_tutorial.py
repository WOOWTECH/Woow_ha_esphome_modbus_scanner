"""Static contract for the downloadable Traditional-Chinese HTML tutorial."""

import html
from html.parser import HTMLParser
from pathlib import Path
import re

PUBLIC_SERVICES = (
    "list_gateways",
    "start_scan",
    "get_scan_status",
    "get_scan_results",
    "cancel_scan",
    "test_address",
)

ROOT = Path(__file__).parents[2]
TUTORIAL_PATH = ROOT / "docs" / "tutorial" / "woow-esphome-modbus-scanner-v0.1.0-zh-TW.html"
TUTORIAL = TUTORIAL_PATH.read_text(encoding="utf-8")
REPOSITORY = "https://github.com/WOOWTECH/Woow_ha_esphome_modbus_scanner"


class TutorialParser(HTMLParser):
    """Collect structural facts without third-party parser dependencies."""

    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.ids: set[str] = set()
        self.hrefs: list[str] = []
        self.h1_count = 0
        self.captions = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        self.tags.append((tag, attributes))
        if element_id := attributes.get("id"):
            self.ids.add(element_id)
        if href := attributes.get("href"):
            self.hrefs.append(href)
        if tag == "h1":
            self.h1_count += 1
        if tag == "caption":
            self.captions += 1


def _parsed() -> TutorialParser:
    parser = TutorialParser()
    parser.feed(TUTORIAL)
    return parser


def _plain(fragment: str) -> str:
    """Return whitespace-normalized visible text from an HTML fragment."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", fragment)).split())


def _table_rows(caption: str) -> list[tuple[str, ...]]:
    """Return exact body rows for the uniquely captioned tutorial table."""
    match = re.search(
        rf"<table><caption>{re.escape(caption)}</caption>.*?<tbody>(.*?)</tbody></table>",
        TUTORIAL,
        re.DOTALL,
    )
    assert match, f"missing table: {caption}"
    rows = re.findall(r"<tr>(.*?)</tr>", match.group(1), re.DOTALL)
    return [
        tuple(
            _plain(cell)
            for cell in re.findall(r"<(?:th|td)(?: [^>]*)?>(.*?)</(?:th|td)>", row, re.DOTALL)
        )
        for row in rows
    ]


def _relative_luminance(hex_color: str) -> float:
    channels = [int(hex_color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def test_tutorial_version_language_and_mock_only_scope() -> None:
    assert '<html lang="zh-Hant">' in TUTORIAL
    assert "v0.1.0 僅限 MOCK 模擬" in TUTORIAL
    assert "不連線 ESPHome" in TUTORIAL
    assert "不掃描任何實體硬體" in TUTORIAL
    assert "不是韌體" in TUTORIAL
    assert "v0.1.0" in TUTORIAL_PATH.name


def test_semantic_landmarks_one_h1_and_required_sections() -> None:
    parser = _parsed()
    tags = {tag for tag, _attrs in parser.tags}
    assert {"header", "nav", "main", "section", "footer"} <= tags
    assert parser.h1_count == 1
    assert {
        "scope",
        "architecture",
        "modbus",
        "install",
        "services",
        "labs",
        "payloads",
        "profiles",
        "operations",
        "rest",
        "troubleshooting",
        "roadmap",
        "testing",
        "glossary",
        "sources",
    } <= parser.ids


def test_exact_six_public_service_names_are_documented() -> None:
    documented = set(
        re.findall(
            r"woow_esphome_modbus_scanner\.([a-z_]+)",
            TUTORIAL,
        )
    )
    assert documented == set(PUBLIC_SERVICES)
    for service in PUBLIC_SERVICES:
        assert f"<code>{service}</code>" in TUTORIAL


def test_start_scan_field_rows_bind_exact_defaults_ranges_and_behavior() -> None:
    assert _table_rows("start_scan 完整資料欄位、預設值、範圍與行為") == [
        ("provider", "選用；mock", "僅 mock", "選定模擬 provider；未來識別 adapter。"),
        (
            "gateway_id",
            "選用；mock:rs485-gateway",
            "非空字串，但須是 provider 列出者",
            "選唯一 fixture；未來精確選 transport/gateway。",
        ),
        (
            "esphome_device_id",
            "選用；無",
            "字串，UI selector 篩 ESPHome 整合裝置",
            "接受但完全忽略、不接觸裝置；為未來映射保留。",
        ),
        ("start_id", "必要；UI 預填 1", "整數 1–247", "含首位址；必須 ≤ end_id。"),
        ("end_id", "必要；UI 預填 12", "整數 1–247", "含末位址。"),
        (
            "probe_type",
            "選用；device_identification",
            "device_identification、holding_register、input_register",
            "fixture outcome 不隨 probe 改變；未來只允許這三種唯讀探測。",
        ),
        (
            "register_address",
            "選用；0",
            "整數 0–65535",
            "mock 不改結果；未來僅 register probes 使用的 zero-based 位址。",
        ),
        ("register_count", "選用；1", "整數 1–125", "mock 不改結果；未來為讀取數量。"),
        (
            "timeout_ms",
            "選用；500",
            "整數 10–10000 ms",
            "mock outcome/latency 不受此值控制；用於最壞估算，未來控制每次嘗試。",
        ),
        ("retries", "選用；1", "整數 0–5", "mock 不重試；用於最壞估算，未來表示首次後額外嘗試。"),
        (
            "inter_request_delay_ms",
            "選用；100",
            "整數 0–5000 ms",
            "mock 位址間至少 10 ms；未來是交易間最小延遲。",
        ),
        (
            "pause_normal_polling",
            "選用；false",
            "布林",
            "mock 無輪詢、無硬體副作用；未來僅 adapter 明確支援才可暫停並在 finally 恢復。",
        ),
        (
            "mock_profile",
            "選用；found_default",
            "本頁第 8 節六值",
            "選 deterministic fixture；未來實體 provider 不應假裝支援。",
        ),
        (
            "safety_confirmed",
            "必要；無預設",
            "只能是 literal boolean true",
            '掃描範圍確認；字串 "true"、1、浮點均拒絕。',
        ),
    ]


def test_test_address_and_scan_id_rows_bind_exact_contract() -> None:
    shared_fields = (
        "除以下差異外，共用 <code>provider</code>、<code>gateway_id</code>、"
        "<code>esphome_device_id</code>、<code>probe_type</code>、"
        "<code>register_address</code>、<code>register_count</code>、"
        "<code>timeout_ms</code>、<code>retries</code>、"
        "<code>inter_request_delay_ms</code>、<code>pause_normal_polling</code>、"
        "<code>mock_profile</code> 的<strong>相同預設、範圍、mock 效果與未來意圖</strong>。"
    )
    assert shared_fields in TUTORIAL
    assert _table_rows("test_address 特有差異") == [
        (
            "address",
            "必要；UI 預填 1；整數 1–247",
            "start_id 與 end_id 都設成此位址，經相同 coordinator 執行。",
        ),
        (
            "safety_confirmed",
            "不提供",
            "單一位址的範圍確認由動作隱含設為 true；其他安全與管理權限不取消。",
        ),
    ]
    assert _table_rows("scan_id 查詢與取消動作") == [
        (
            "get_scan_status",
            "scan_id 必要，canonical 小寫連字號 UUID",
            "必定回應",
            "進度、時間、counts、錯誤與取消旗標。",
        ),
        (
            "get_scan_results",
            "同上",
            "必定回應",
            "responder 明細、完整 counts 與 best-effort 聲明。",
        ),
        (
            "cancel_scan",
            "同上",
            "呼叫者要求時回應",
            "running 時設旗標；已終止則不改終態，回傳目前 status。",
        ),
    ]


def test_normative_modbus_and_lifecycle_caveats_are_present() -> None:
    required = (
        "位址 0 是 broadcast",
        "通用 discovery",
        "Read Device Identification 是<strong>選用</strong>",
        "重複 ID",
        "timeout",
        "running、completed、cancelled、failed",
        "best_effort: true",
        "uniqueness_guaranteed: false",
        "最近 20 筆",
        "canonical",
    )
    assert all(item in TUTORIAL for item in required)


def test_six_mock_scenario_tables_bind_exact_addresses_codes_and_effects() -> None:
    expected = {
        "情境 1：found_default": [
            ("1", "identified", "vendor WOOWTECH；product WT-RS485-01"),
            ("3", "responded", "一般有效回覆"),
            ("5", "modbus_exception", "code 2"),
            ("12", "identified", "vendor Acme Controls；product ACM-12"),
            ("其他", "timeout", "不保留 responder 明細"),
        ],
        "情境 2：all_offline": [
            (
                "要求範圍全部",
                "timeout",
                "completed 仍可達 100%；responders 空，不表示真實匯流排為空。",
            ),
        ],
        "情境 3：partial_timeout": [
            ("2、11、42", "responded", "一般有效回覆"),
            ("7、21", "identified", "Mock Industries；MI-007 或 MI-021"),
            ("其他", "timeout", "只計數"),
        ],
        "情境 4：modbus_exception": [
            ("4、17", "modbus_exception", "2"),
            ("9", "modbus_exception", "3"),
            ("其他", "timeout", "無"),
        ],
        "情境 5：possible_collision": [
            ("7", "possible_collision", "latency 9；CRC/framing 不一致，重複 ID 或雜訊皆可能。"),
            ("其他", "timeout", "只計數"),
        ],
        "情境 6：gateway_disconnect": [
            ("中斷前的位址 1", "identified", "若範圍含 1：WOOWTECH / WT-RS485-01"),
            ("中斷前的位址 3", "responded", "若範圍含 3。"),
            ("其他中斷前位址", "timeout", "一般 fixture。"),
            (
                "address ≥ max(start_id + 3, 4) 的第一筆",
                "gateway_error",
                "scan 立即 failed；訊息 Simulated gateway disconnected；後續不執行。",
            ),
        ],
    }
    assert all(_table_rows(caption) == rows for caption, rows in expected.items())
    parser = _parsed()
    assert parser.captions == sum(tag == "table" for tag, _attrs in parser.tags)


def test_sources_are_official_and_in_page_links_resolve() -> None:
    parser = _parsed()
    expected = {
        "https://www.home-assistant.io/docs/scripts/perform-actions/",
        "https://developers.home-assistant.io/docs/api/rest/",
        "https://esphome.io/components/modbus_controller/",
        "https://www.modbus.org/file/secure/modbusprotocolspecification.pdf",
        "https://www.modbus.org/file/secure/modbusoverserial.pdf",
    }
    assert expected <= set(parser.hrefs)
    for href in parser.hrefs:
        if href.startswith("#"):
            assert href[1:] in parser.ids


def test_no_external_runtime_assets_or_legacy_coupling() -> None:
    parser = _parsed()
    for tag, attrs in parser.tags:
        if tag in {"script", "img", "iframe"}:
            assert not attrs.get("src")
        if tag == "link":
            assert attrs.get("rel") not in {"stylesheet", "preload", "modulepreload"}
    assert "@import" not in TUTORIAL
    forbidden = ("woow_multi" + "_protocol", "kn" + "x", "d" + "mx")
    assert all(term not in TUTORIAL.lower() for term in forbidden)


def test_brand_contrast_typography_radii_print_and_responsive_hooks() -> None:
    required = (
        "#6183FC",
        "--brand-ink:#2347bd",
        "--r12:12px",
        "--r20:20px",
        "--r28:28px",
        "--pill:999px",
        'font-family:Outfit,"Noto Sans TC"',
        'font-family:Poppins,"Noto Sans TC"',
        "position:sticky",
        "min-height:44px",
        "skip-link",
        ":focus-visible",
        "prefers-reduced-motion:reduce",
        "@media print",
        "@media(max-width:360px)",
        "overflow-x:auto",
        "thead{display:table-header-group}",
        'aria-live="polite"',
        'class="copy"',
        "<svg",
        "存取日期：2026-09-02",
        "系統 sans-serif",
    )
    assert all(item in TUTORIAL for item in required)
    brand_luminance = _relative_luminance("#2347bd")
    muted_luminance = _relative_luminance("#5e6879")
    white_luminance = _relative_luminance("#ffffff")
    assert (white_luminance + 0.05) / (brand_luminance + 0.05) >= 4.5
    assert (white_luminance + 0.05) / (muted_luminance + 0.05) >= 3.0
    assert ".btn,button{min-height:44px" in TUTORIAL
    assert "background:var(--brand-ink);color:#fff" in TUTORIAL
    assert "border:2px solid var(--muted)" in TUTORIAL
    print_surface_reset = (
        ".hero,.section,.card,.danger,.note,.caution,.eyebrow,.chip,"
        "code,kbd,caption,th,td{color:#000!important;background:#fff!important}"
    )
    assert print_surface_reset in TUTORIAL
    assert ".danger,.note,.caution{border-color:#777!important}" in TUTORIAL
    assert ".lede,.search-message,.footer{color:#000!important}" in TUTORIAL
    assert not re.search(r"border-radius:(?:5|8)px", TUTORIAL)
    assert "letter-spacing:-.04em" not in TUTORIAL
    assert "gradient(" not in TUTORIAL.lower()


def test_accessible_toc_regions_headers_and_static_banner() -> None:
    parser = _parsed()
    tables = [attrs for tag, attrs in parser.tags if tag == "table"]
    wraps = [
        attrs for tag, attrs in parser.tags if tag == "div" and attrs.get("class") == "table-wrap"
    ]
    pres = [attrs for tag, attrs in parser.tags if tag == "pre"]
    headers = [attrs for tag, attrs in parser.tags if tag == "th"]
    assert tables and len(wraps) == len(tables)
    assert all(
        attrs.get("role") == "region" and attrs.get("tabindex") == "0" and attrs.get("aria-label")
        for attrs in wraps
    )
    assert pres and all(attrs.get("tabindex") == "0" and attrs.get("aria-label") for attrs in pres)
    assert headers and all(attrs.get("scope") == "col" for attrs in headers)
    assert '<details class="toc" id="toc" open><summary>本頁目錄</summary>' in TUTORIAL
    assert '<a class="btn back" href="#toc" aria-label="回到本頁目錄">回到目錄</a>' in TUTORIAL
    assert '<aside class="mock-banner">' in TUTORIAL
    assert 'class="mock-banner" role="status"' not in TUTORIAL
    assert '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">' in TUTORIAL


def test_all_content_and_only_content_controls_work_progressively() -> None:
    assert ".enhanced .searchable[hidden]" in TUTORIAL
    assert ".search,.copy{display:none}" in TUTORIAL
    assert ".enhanced .search{display:flex}" in TUTORIAL
    assert ".enhanced .copy{display:block}" in TUTORIAL
    assert "document.documentElement.classList.add('enhanced')" in TUTORIAL
    assert "matchMedia('(max-width:850px)').matches" in TUTORIAL
    assert "document.documentElement.classList.add('js')" not in TUTORIAL
    hero_tag = re.search(r"<section class=\"hero[^>]*>", TUTORIAL).group()
    assert " hidden" not in hero_tag
    assert "navigator.clipboard" in TUTORIAL
    assert "aria-live" in TUTORIAL


def test_readmes_offer_source_view_release_asset_raw_archive_and_mock_warning() -> None:
    blob = f"{REPOSITORY}/blob/main/docs/tutorial/woow-esphome-modbus-scanner-v0.1.0-zh-TW.html"
    release_asset = (
        f"{REPOSITORY}/releases/download/v0.1.0/woow-esphome-modbus-scanner-v0.1.0-zh-TW.html"
    )
    raw = (
        "https://raw.githubusercontent.com/WOOWTECH/"
        "Woow_ha_esphome_modbus_scanner/main/docs/tutorial/"
        "woow-esphome-modbus-scanner-v0.1.0-zh-TW.html"
    )
    archive = f"{REPOSITORY}/archive/refs/tags/v0.1.0.zip"
    for readme_name in ("README.md", "README_zh-TW.md"):
        text = (ROOT / readme_name).read_text(encoding="utf-8")
        assert blob in text
        assert release_asset in text
        assert raw in text
        assert archive in text
        assert "Source-file view" in text or "檢視原始檔" in text
        assert "MOCK" in text[:2500]
        assert "not ESPHome\n> firmware" in text or "不是 ESPHome 韌體" in text
