"""Singleton config flow for Woow ESPHome Modbus Scanner."""

from __future__ import annotations

from typing import Any

from homeassistant import config_entries

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

        if user_input is not None:
            return self.async_create_entry(title=NAME, data={})

        return self.async_show_form(step_id="user", data_schema=None)
