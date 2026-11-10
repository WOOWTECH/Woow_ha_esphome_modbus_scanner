"""Persistent actionable faults only; an empty slave address is not a Repair."""

from hashlib import sha256

from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

PERSISTENT = {
    "API_AUTH_FAILED",
    "IDENTITY_MISMATCH",
    "BRIDGE_UNSUPPORTED",
    "PROFILE_MISMATCH",
    "FIRMWARE_FAULT",
    "MULTIPLE_BUSES",
}


# Faults a passing Gateway check (API connection, MAC, Bridge Protocol signature and, on
# bridge v2, exactly one Bus) proves fixed. The others (PROFILE_MISMATCH, FIRMWARE_FAULT) are
# about transport state after a Probe: only a Scan whose recovery is verified clears them.
CLEARED_BY_CHECK = {"API_AUTH_FAILED", "IDENTITY_MISMATCH", "BRIDGE_UNSUPPORTED", "MULTIPLE_BUSES"}

LEGACY_BRIDGE_PREFIX = "legacy_bridge_"


def _digest(gateway_id: str) -> str:
    return sha256(gateway_id.encode()).hexdigest()[:12]


def sync_legacy_bridge_issues(hass, gateways) -> None:
    """One Repairs issue per enrolled Gateway still on legacy bridge v1.

    Issues of Gateways that are now bridge v2, or no longer enrolled, are removed.
    Delete this function together with ``modbus_scan/legacy_v1/``.
    """
    from .modbus_scan.adapters import BRIDGE_V1, gateway_bridge, physical_gateway_id

    wanted = {}
    for gateway in gateways:
        if gateway_bridge(gateway) != BRIDGE_V1:
            continue
        mac = gateway["mac"].upper()
        gateway_id = physical_gateway_id(mac)
        wanted[LEGACY_BRIDGE_PREFIX + _digest(gateway_id)] = {
            "name": gateway.get("name") or mac,
            "host": gateway["host"],
            "mac": mac,
        }
    registry = ir.async_get(hass)
    for domain, issue_id in list(registry.issues):
        if domain == DOMAIN and issue_id.startswith(LEGACY_BRIDGE_PREFIX):
            if issue_id not in wanted:
                ir.async_delete_issue(hass, DOMAIN, issue_id)
    for issue_id, placeholders in wanted.items():
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="legacy_bridge",
            translation_placeholders=placeholders,
        )


def _gateway_issue_id(gateway_id: str) -> str:
    return "gateway_" + _digest(gateway_id)


def clear_gateway_issue_after_check(hass, gateway_id) -> None:
    """A check of this Gateway passed: drop its Repairs issue if the check proves it fixed."""
    issue_id = _gateway_issue_id(gateway_id)
    issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
    if issue is not None and (issue.translation_placeholders or {}).get("code") in CLEARED_BY_CHECK:
        ir.async_delete_issue(hass, DOMAIN, issue_id)


def report_gateway_issue(hass, gateway_id, code):
    issue_id = _gateway_issue_id(gateway_id)
    if code is None:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
    elif code in PERSISTENT:
        if code == "API_AUTH_FAILED":
            from .modbus_scan.adapters import physical_gateway_id

            for entry in hass.config_entries.async_entries(DOMAIN):
                if any(
                    physical_gateway_id(g["mac"]) == gateway_id
                    for g in entry.data.get("gateways", [])
                ):
                    entry.async_start_reauth(hass)
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key="gateway_action_required",
            translation_placeholders={"code": code},
        )
