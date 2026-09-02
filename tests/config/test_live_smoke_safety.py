"""Credential-safety contract for the opt-in live smoke tool."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
from pathlib import Path
import threading

import pytest

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "tests" / "live" / "mock_service_smoke.py"
SPEC = importlib.util.spec_from_file_location("mock_service_smoke", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


@pytest.mark.parametrize(
    ("url", "allow_insecure", "expected"),
    [
        ("https://ha.example/", False, "https://ha.example"),
        ("https://localhost:8123", False, "https://localhost:8123"),
        ("http://localhost:8123/", True, "http://localhost:8123"),
        ("http://127.0.0.1:8123", True, "http://127.0.0.1:8123"),
        ("http://[::1]:8123", True, "http://[::1]:8123"),
    ],
)
def test_live_base_url_accepts_https_or_explicit_loopback_http(
    url, allow_insecure, expected
):
    assert (
        smoke.validate_base_url(url, allow_insecure_loopback=allow_insecure)
        == expected
    )


@pytest.mark.parametrize(
    "url,allow_insecure",
    [
        ("", False),
        ("ha.example", False),
        ("http://ha.example", True),
        ("http://192.168.1.10:8123", True),
        ("http://127.0.0.1:8123", False),
        ("ftp://127.0.0.1", True),
        ("https://user:secret@ha.example", False),
        ("https://ha.example?next=http://evil.example", False),
        ("https://ha.example/#fragment", False),
    ],
)
def test_live_base_url_rejects_unsafe_endpoints(url, allow_insecure):
    with pytest.raises(ValueError, match="HA_URL"):
        smoke.validate_base_url(url, allow_insecure_loopback=allow_insecure)


class _RedirectServerHandler(BaseHTTPRequestHandler):
    source_calls = 0
    target_calls = 0

    def do_POST(self):  # noqa: N802 - stdlib handler API
        if self.path == "/source":
            type(self).source_calls += 1
            self.send_response(302)
            self.send_header("Location", "/target")
            self.end_headers()
            return
        type(self).target_calls += 1
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, _format, *_args):
        pass


def test_live_request_does_not_follow_redirects_or_forward_token(
    monkeypatch, socket_enabled
):
    _RedirectServerHandler.source_calls = 0
    _RedirectServerHandler.target_calls = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RedirectServerHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(smoke, "HA_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setattr(smoke, "HA_TOKEN", "must-not-move")
    monkeypatch.setattr(smoke, "ALLOW_INSECURE_LOOPBACK", True)

    try:
        with pytest.raises(RuntimeError, match="HTTP 302"):
            smoke.request("POST", "/source", {})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert _RedirectServerHandler.source_calls == 1
    assert _RedirectServerHandler.target_calls == 0
