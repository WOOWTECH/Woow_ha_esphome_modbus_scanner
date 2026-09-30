"""Singleton config flow for Woow ESPHome Modbus Scanner."""

from __future__ import annotations

import re
from typing import Any

from homeassistant import config_entries
import voluptuous as vol

from .const import DOMAIN, NAME


class WoowEsphomeModbusScannerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create at most one scanner entry."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Create the singleton entry after explicit confirmation."""
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        errors = {}
        if user_input is not None:
            host = user_input.get("host", "").strip()
            mac = user_input.get("mac", "").strip().upper()
            if bool(host) != bool(mac):
                errors["base"] = "gateway_pair_required"
            elif host and not re.fullmatch(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}", mac):
                errors["base"] = "invalid_mac"
            else:
                data = {"gateways": [{"host": host, "mac": mac}]} if host else {}
                return self.async_create_entry(title=NAME, data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional("host"): str,
                    vol.Optional("mac"): str,
                }
            ),
            errors=errors,
        )
