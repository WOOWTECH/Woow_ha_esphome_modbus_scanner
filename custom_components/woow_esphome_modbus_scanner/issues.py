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


def report_gateway_issue(hass, gateway_id, code):
    issue_id = "gateway_" + sha256(gateway_id.encode()).hexdigest()[:12]
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
