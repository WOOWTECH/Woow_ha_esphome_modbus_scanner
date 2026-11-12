"""Persistent actionable faults only; an empty slave address is not a Repair."""

from hashlib import sha256

from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN
from .modbus_scan.models import FaultCode

PERSISTENT = {
    FaultCode.API_AUTH_FAILED,
    FaultCode.IDENTITY_MISMATCH,
    FaultCode.BRIDGE_UNSUPPORTED,
    FaultCode.PROFILE_MISMATCH,
    FaultCode.FIRMWARE_FAULT,
    FaultCode.MULTIPLE_BUSES,
}

# The one fault a passing Gateway check or Enrollment clears: it read the Gateway's info and
# found exactly one Bus. Every other issue is cleared only by a Scan whose cleanup closed and
# whose recovery is verified, as before one Bus per Gateway (ADR 0011).
CLEARED_BY_CHECK = FaultCode.MULTIPLE_BUSES

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


def _issue_code(hass, issue_id: str) -> str | None:
    issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
    return None if issue is None else (issue.translation_placeholders or {}).get("code")


def report_gateway_issue(hass, gateway_id, code, *, check=False) -> None:
    """Raise the Gateway's Repairs issue for a persistent fault ``code``; None: it is fixed.

    A None from a Scan (cleanup closed, recovery verified) clears any issue. With ``check``
    the outcome is a Gateway check's or Enrollment's, and a None clears only
    ``CLEARED_BY_CHECK``.
    """
    issue_id = _gateway_issue_id(gateway_id)
    if code is None:
        if not check or _issue_code(hass, issue_id) == CLEARED_BY_CHECK:
            ir.async_delete_issue(hass, DOMAIN, issue_id)
    elif code in PERSISTENT:
        if code == FaultCode.API_AUTH_FAILED:
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
