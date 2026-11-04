"""User-facing English text uses the GLOSSARY.md terms, not their _Avoid_ synonyms."""

import json
from pathlib import Path
import re

import yaml

ROOT = Path(__file__).parents[2]
INTEGRATION = ROOT / "custom_components" / "woow_esphome_modbus_scanner"
PANEL = ROOT / "panel_frontend" / "src"

# "bridge" is only a name for the Bridge Protocol, never for the Gateway.
# Config keys such as `invalid_bridge` or `bridge_info` never match: `_` is a word character.
AVOIDED = {
    "bare bridge": re.compile(r"\bbridge\b(?!\s+protocol)", re.IGNORECASE),
    "ESP": re.compile(r"\bESP\b"),
    "paused devices": re.compile(r"paused devices", re.IGNORECASE),
    "Unchecked devices": re.compile(r"unchecked devices", re.IGNORECASE),
}

# Keys whose text legitimately keeps an avoided word, with the reason.
ALLOWED = {}

JS_ENTRY = re.compile(r'(\w+|"[^"]*")\s*:\s*("(?:[^"\\]|\\.)*"|`[^`]*`)')


def _flatten(value, prefix=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _flatten(item, f"{prefix}{key}.")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _flatten(item, f"{prefix}{index}.")
    elif isinstance(value, str):
        yield prefix.rstrip("."), value


def _js_english(path, start, end):
    """Key/value pairs of the English dict literal between two markers."""
    source = path.read_text(encoding="utf-8")
    block = source.split(start, 1)[1].split(end, 1)[0]
    return [(key.strip('"'), value[1:-1]) for key, value in JS_ENTRY.findall(block)]


def _user_facing_english():
    for name in ("strings.json", "translations/en.json"):
        data = json.loads((INTEGRATION / name).read_text(encoding="utf-8"))
        for key, text in _flatten(data):
            yield f"{name}:{key}", text
    services = yaml.safe_load((INTEGRATION / "services.yaml").read_text(encoding="utf-8"))
    for key, text in _flatten(services):
        yield f"services.yaml:{key}", text
    for key, text in _js_english(PANEL / "i18n.js", "const en = {", "const zh = {"):
        yield f"i18n.js:{key}", text
    for key, text in _js_english(PANEL / "hardening-i18n.js", "en: {", "zh: {"):
        yield f"hardening-i18n.js:{key}", text


def test_english_user_facing_text_avoids_glossary_synonyms():
    offenders = [
        f"{where} [{term}]: {text}"
        for where, text in _user_facing_english()
        for term, pattern in AVOIDED.items()
        if pattern.search(text) and term not in ALLOWED.get(where, ())
    ]
    assert not offenders, "\n".join(offenders)


def test_the_check_reads_every_source():
    sources = {where.split(":", 1)[0] for where, _ in _user_facing_english()}
    assert sources == {
        "strings.json",
        "translations/en.json",
        "services.yaml",
        "i18n.js",
        "hardening-i18n.js",
    }
