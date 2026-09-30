"""Singleton configuration and explicit two-gateway enrollment."""

from __future__ import annotations

import asyncio
import base64
import binascii
import re
from typing import Any

from homeassistant import config_entries
from homeassistant.helpers import selector
import voluptuous as vol

from .const import DOMAIN, NAME


def gateway_input(user_input, existing=()):
    """Validate paired, unique identities before changing any live enrollment."""
    gateways = []
    for suffix in ("", "_2"):
        host = user_input.get("host" + suffix, "").strip()
        mac = user_input.get("mac" + suffix, "").strip().upper()
        if bool(host) != bool(mac):
            return None, "gateway_pair_required"
        if host and not re.fullmatch(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}", mac):
            return None, "invalid_mac"
        key = user_input.get("noise_psk" + suffix, "").strip()
        if key and user_input.get("clear_psk" + suffix, False):
            return None, "conflicting_psk"
        if key:
            try:
                if len(base64.b64decode(key, validate=True)) != 32:
                    return None, "invalid_psk"
            except (ValueError, binascii.Error):
                return None, "invalid_psk"
        if key and not host:
            return None, "gateway_pair_required"
        if host:
            if any(g["mac"] == mac or g["host"] == host for g in gateways):
                return None, "duplicate_gateway"
            gateway = {
                "host": host,
                "mac": mac,
                "name": "ESPHome Modbus " + mac.replace(":", "")[-6:],
            }
            # A blank secret means retain, never render the stored key in the form.
            previous = next((g for g in existing if g["mac"].upper() == mac), {})
            if not user_input.get("clear_psk" + suffix, False):
                key = key or previous.get("noise_psk")
            if key and not user_input.get("clear_psk" + suffix, False):
                gateway["noise_psk"] = key
            gateways.append(gateway)
    return gateways, None


def gateway_schema(gateways=()):
    fields = {}
    for index, suffix in enumerate(("", "_2")):
        gateway = gateways[index] if index < len(gateways) else {}
        for key in ("host", "mac"):
            fields[vol.Optional(key + suffix, default=gateway.get(key, ""))] = str
        fields[vol.Optional("noise_psk" + suffix)] = selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        )
        fields[vol.Optional("clear_psk" + suffix, default=False)] = bool
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
                    title=NAME,
                    data={"gateways": gateways},
                )
        return self.async_show_form(step_id="user", data_schema=gateway_schema(), errors=errors)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        from .modbus_scan.esphome_provider import ESPHomeGateway, ESPHomeGatewayProvider
        from .modbus_scan.provider import GatewayProviderError

        entry = self._get_reauth_entry()
        existing = entry.data.get("gateways", [])
        if not existing:
            return self.async_abort(reason="no_physical_gateways")
        errors = {}
        if user_input is not None:
            merged = {}
            for index, gateway in enumerate(existing):
                suffix = "" if index == 0 else "_2"
                merged.update(
                    {
                        "host" + suffix: gateway["host"],
                        "mac" + suffix: gateway["mac"],
                        "noise_psk" + suffix: user_input.get("noise_psk" + suffix, ""),
                        "clear_psk" + suffix: user_input.get("clear_psk" + suffix, False),
                    }
                )
            gateways, error = gateway_input(merged, existing)
            if error:
                errors["base"] = error
            else:
                provider = ESPHomeGatewayProvider([ESPHomeGateway(**g) for g in gateways])
                try:
                    async with asyncio.timeout(20):
                        for gateway in provider.gateways:
                            await provider.check_gateway(gateway)  # API only; never probes RTU.
                except GatewayProviderError as exc:
                    errors["base"] = (
                        "invalid_auth" if exc.code == "API_AUTH_FAILED" else "cannot_connect"
                    )
                except Exception:  # noqa: BLE001 - keys/library messages never reach the form
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_update_reload_and_abort(
                        entry, data_updates={"gateways": gateways}
                    )
        fields = {}
        for index, _gateway in enumerate(existing):
            suffix = "" if index == 0 else "_2"
            fields[vol.Optional("noise_psk" + suffix)] = selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            )
            fields[vol.Optional("clear_psk" + suffix, default=False)] = bool
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=vol.Schema(fields), errors=errors
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        entry = self._get_reconfigure_entry()
        errors = {}
        if user_input is not None:
            gateways, error = gateway_input(user_input, entry.data.get("gateways", []))
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={"gateways": gateways},
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=gateway_schema(entry.data.get("gateways", [])),
            errors=errors,
        )
