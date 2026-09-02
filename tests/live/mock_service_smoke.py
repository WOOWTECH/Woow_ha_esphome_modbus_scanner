#!/usr/bin/env python3
"""Explicit, mock-only smoke test for the six services on a live HA instance."""

from __future__ import annotations

import ipaddress
import json
import os
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

DOMAIN = "woow_esphome_modbus_scanner"
EXPECTED = {
    "list_gateways",
    "start_scan",
    "get_scan_status",
    "get_scan_results",
    "cancel_scan",
    "test_address",
}
HA_URL = os.environ.get("HA_URL", "").rstrip("/")
HA_TOKEN = os.environ.get("HA_TOKEN", "")
ALLOW_INSECURE_LOOPBACK = os.environ.get("HA_ALLOW_INSECURE_LOOPBACK") == "1"


class _RejectRedirects(HTTPRedirectHandler):
    """Turn every redirect into an HTTPError before credentials can move."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: PLR0913
        return None


_OPENER = build_opener(_RejectRedirects)


def validate_base_url(url: str, *, allow_insecure_loopback: bool = False) -> str:
    """Require a credential-safe HTTPS endpoint or explicit loopback HTTP."""
    parsed = urlsplit(url)
    if (
        not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("HA_URL must be an absolute endpoint without credentials/query")
    if parsed.scheme == "https":
        return url.rstrip("/")
    is_loopback = parsed.hostname == "localhost"
    if not is_loopback:
        try:
            is_loopback = ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            is_loopback = False
    if parsed.scheme == "http" and allow_insecure_loopback and is_loopback:
        return url.rstrip("/")
    raise ValueError(
        "HA_URL must use HTTPS; HTTP requires HA_ALLOW_INSECURE_LOOPBACK=1 "
        "and a literal loopback endpoint"
    )


def request(method: str, path: str, data: dict | None = None):
    """Call one validated endpoint without following credential-bearing redirects."""
    base_url = validate_base_url(
        HA_URL, allow_insecure_loopback=ALLOW_INSECURE_LOOPBACK
    )
    body = None if data is None else json.dumps(data).encode()
    req = Request(
        f"{base_url}{path}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {HA_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    try:
        with _OPENER.open(req, timeout=15) as response:
            payload = response.read().decode()
    except HTTPError as err:
        detail = err.read().decode()
        raise RuntimeError(f"{method} {path}: HTTP {err.code}: {detail}") from err
    parsed = json.loads(payload) if payload else {}
    if isinstance(parsed, dict):
        return parsed.get("service_response", parsed)
    return parsed


def call(service: str, data: dict | None = None):
    """Call one scanner service and request its response."""
    return request("POST", f"/api/services/{DOMAIN}/{service}?return_response", data or {})


def wait(scan_id: str, *, deadline_seconds: float = 15) -> dict:
    """Poll one mock scan to its terminal state."""
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        status = call("get_scan_status", {"scan_id": scan_id})
        if status["status"] != "running":
            return status
        time.sleep(0.1)
    raise AssertionError(f"scan {scan_id} missed the {deadline_seconds}s deadline")


def main() -> None:
    """Exercise listing, scanning, results, single test, and cancellation."""
    if not HA_URL or not HA_TOKEN:
        raise SystemExit("Set HA_URL and an administrator HA_TOKEN to opt in")
    try:
        validate_base_url(HA_URL, allow_insecure_loopback=ALLOW_INSECURE_LOOPBACK)
    except ValueError as err:
        raise SystemExit(str(err)) from err

    registry = request("GET", "/api/services")
    domain = next((item for item in registry if item.get("domain") == DOMAIN), None)
    found = set(domain.get("services", {})) if domain else set()
    assert found == EXPECTED, f"unexpected services: {sorted(found ^ EXPECTED)}"

    gateways = call("list_gateways")
    assert gateways["gateways"][0]["gateway_id"] == "mock:rs485-gateway"
    assert gateways["gateways"][0]["simulated"] is True

    started = call(
        "start_scan",
        {
            "start_id": 1,
            "end_id": 5,
            "inter_request_delay_ms": 0,
            "mock_profile": "found_default",
            "safety_confirmed": True,
        },
    )
    assert wait(started["scan_id"])["status"] == "completed"
    results = call("get_scan_results", {"scan_id": started["scan_id"]})
    assert [item["address"] for item in results["responders"]] == [1, 3, 5]

    tested = call(
        "test_address",
        {"address": 12, "inter_request_delay_ms": 0, "mock_profile": "found_default"},
    )
    assert wait(tested["scan_id"])["status"] == "completed"

    slow = call(
        "start_scan",
        {
            "start_id": 1,
            "end_id": 100,
            "inter_request_delay_ms": 250,
            "safety_confirmed": True,
        },
    )
    call("cancel_scan", {"scan_id": slow["scan_id"]})
    assert wait(slow["scan_id"])["status"] == "cancelled"
    print("PASS: exact services, listing, scan/results, one-address test, and cancel")


if __name__ == "__main__":
    main()
