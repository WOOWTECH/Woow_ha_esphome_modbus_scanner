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
}


LEGACY_BRIDGE_PREFIX = "legacy_bridge_"


def _digest(gateway_id: str) -> str:
    return sha256(gateway_id.encode()).hexdigest()[:12]


def sync_legacy_bridge_issues(hass, gateways) -> None:
    """One Repairs issue per enrolled Gateway still on legacy bridge v1.

    Issues of Gateways that are now bridge v2, or no longer enrolled, are removed.
    Delete this function together with ``modbus_scan/legacy_v1/``.
    """
    from .modbus_scan.adapters import BRIDGE_V1, gateway_bridge

    wanted = {}
    for gateway in gateways:
        if gateway_bridge(gateway) != BRIDGE_V1:
            continue
        mac = gateway["mac"].upper()
        gateway_id = "esphome:" + mac.replace(":", "").lower()
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


def report_gateway_issue(hass, gateway_id, code):
    issue_id = "gateway_" + _digest(gateway_id)
    if code is None:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
    elif code in PERSISTENT:
        if code == "API_AUTH_FAILED":
            for entry in hass.config_entries.async_entries(DOMAIN):
                if any(
                    "esphome:" + g["mac"].replace(":", "").lower() == gateway_id
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
