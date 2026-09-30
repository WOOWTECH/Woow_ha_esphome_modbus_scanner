"""Singleton configuration and explicit two-gateway enrollment."""

from __future__ import annotations

import re
from typing import Any

from homeassistant import config_entries
import voluptuous as vol

from .const import DOMAIN, NAME


def gateway_input(user_input):
    """Validate paired, unique identities before changing any live enrollment."""
    gateways = []
    for suffix in ("", "_2"):
        host = user_input.get("host" + suffix, "").strip()
        mac = user_input.get("mac" + suffix, "").strip().upper()
        if bool(host) != bool(mac):
            return None, "gateway_pair_required"
        if host and not re.fullmatch(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}", mac):
            return None, "invalid_mac"
        if host:
            if any(g["mac"] == mac or g["host"] == host for g in gateways):
                return None, "duplicate_gateway"
            gateways.append(
                {"host": host, "mac": mac, "name": "ESPHome Modbus " + mac.replace(":", "")[-6:]}
            )
    return gateways, None


def gateway_schema(gateways=()):
    fields = {}
    for index, suffix in enumerate(("", "_2")):
        gateway = gateways[index] if index < len(gateways) else {}
        for key in ("host", "mac"):
            fields[vol.Optional(key + suffix, default=gateway.get(key, ""))] = str
    return vol.Schema(fields)


class WoowEsphomeModbusScannerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """One integration can own two explicitly selected physical gateways."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")
        errors = {}
        if user_input is not None:
            gateways, error = gateway_input(user_input)
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title=NAME, data={"gateways": gateways} if gateways else {}
                )
        return self.async_show_form(step_id="user", data_schema=gateway_schema(), errors=errors)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        entry = self._get_reconfigure_entry()
        errors = {}
        if user_input is not None:
            gateways, error = gateway_input(user_input)
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={"gateways": gateways}
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=gateway_schema(entry.data.get("gateways", [])),
            errors=errors,
        )
