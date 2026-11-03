"""Singleton configuration and Gateway enrollment (any number of Gateways).

Gateways are picked from the nodes already in HA's ESPHome integration, reusing their
host and API key, and verified (MAC and bridge v2 signature) before they are stored.
Manual host/MAC/key entry stays available as an advanced path. Every Gateway lives in
``entry.data["gateways"]`` as ``{host, mac, name, bridge, noise_psk?, port?, ...}``; the
format is unchanged from the two-slot form, so older entries keep working.
"""

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
from .modbus_scan.adapters import BRIDGE_V2, BRIDGES, build_physical_provider, gateway_bridge

ESPHOME_DOMAIN = "esphome"
_MAC = re.compile(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}")


def _password():
    return selector.TextSelector(
        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
    )


def _select(options, *, multiple=False):
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[selector.SelectOptionDict(value=v, label=label) for v, label in options],
            multiple=multiple,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _label(gateway) -> str:
    return f"{gateway.get('name') or gateway['mac']} ({gateway['host']}, {gateway['mac']})"


def _apply_key(gateway, previous, key, clear) -> str | None:
    """Set the gateway key: a blank key retains the stored one; it is never rendered."""
    if key and clear:
        return "conflicting_psk"
    if key:
        try:
            if len(base64.b64decode(key, validate=True)) != 32:
                return "invalid_psk"
        except (ValueError, binascii.Error):
            return "invalid_psk"
    gateway.pop("noise_psk", None)
    if not clear and (key := key or previous.get("noise_psk")):
        gateway["noise_psk"] = key
    return None


def manual_gateway(user_input, existing=()):
    """Validate one manually entered Gateway; a known MAC keeps its key and metadata."""
    host = user_input.get("host", "").strip()
    mac = user_input.get("mac", "").strip().upper()
    if not host or not mac:
        return None, "gateway_pair_required"
    if not _MAC.fullmatch(mac):
        return None, "invalid_mac"
    previous = next((g for g in existing if g["mac"].upper() == mac), {})
    # The bridge selector only offers BRIDGES.
    bridge = user_input.get("bridge") or (gateway_bridge(previous) if previous else BRIDGE_V2)
    gateway = {k: v for k, v in previous.items() if k in ("port", "name")}
    gateway.update(host=host, mac=mac, bridge=bridge)
    gateway.setdefault("name", "ESPHome Modbus " + mac.replace(":", "")[-6:])
    error = _apply_key(
        gateway,
        previous,
        user_input.get("noise_psk", "").strip(),
        user_input.get("clear_psk", False),
    )
    return (None, error) if error else (gateway, None)


def upsert_gateway(existing, gateway):
    """Replace the Gateway with the same MAC, or append; hosts must stay distinct."""
    others = [g for g in existing if g["mac"].upper() != gateway["mac"]]
    if any(g["host"] == gateway["host"] for g in others):
        return None, "duplicate_gateway"
    replaced = [gateway if g["mac"].upper() == gateway["mac"] else g for g in existing]
    return (replaced if len(others) < len(existing) else [*existing, gateway]), None


def esphome_devices(hass) -> dict[str, tuple[config_entries.ConfigEntry, str]]:
    """Nodes in HA's ESPHome integration with a known host and MAC, by entry id."""
    devices = {}
    for entry in hass.config_entries.async_entries(
        ESPHOME_DOMAIN, include_ignore=False, include_disabled=False
    ):
        mac = (entry.unique_id or "").upper()
        if entry.data.get("host") and _MAC.fullmatch(mac):
            devices[entry.entry_id] = (entry, mac)
    return devices


def _verification_error(exc) -> str:
    from .modbus_scan.provider import GatewayProviderError

    if not isinstance(exc, GatewayProviderError):
        return "cannot_connect"
    if exc.code == "API_AUTH_FAILED":
        return "invalid_auth"
    if exc.code == "IDENTITY_MISMATCH":
        return "identity_mismatch"
    if exc.code == "BRIDGE_UNSUPPORTED":
        return "scanner_missing" if exc.reason == "scanner_missing" else "bridge_mismatch"
    return "cannot_connect"


async def verify_gateway(gateway) -> str | None:
    """API-only MAC and bridge check; never sends a Modbus frame. Returns a form error."""
    provider = build_physical_provider([gateway])
    try:
        async with asyncio.timeout(20):
            for info in provider.list_gateways():
                await provider.check_gateway(info.gateway_id)
    except Exception as exc:  # noqa: BLE001 - keys/library messages never reach the form
        return _verification_error(exc)
    return None


class WoowEsphomeModbusScannerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """One integration entry; any number of enrolled physical Gateways."""

    VERSION = 1

    def _existing(self) -> list[dict[str, Any]]:
        if self.source == config_entries.SOURCE_RECONFIGURE:
            return list(self._get_reconfigure_entry().data.get("gateways", []))
        return []

    def _save(self, gateways):
        if self.source == config_entries.SOURCE_RECONFIGURE:
            return self.async_update_reload_and_abort(
                self._get_reconfigure_entry(), data_updates={"gateways": gateways}
            )
        return self.async_create_entry(title=NAME, data={"gateways": gateways})

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")
        return self.async_show_menu(
            step_id="user", menu_options=["esphome_device", "manual", "mock_only"]
        )

    async def async_step_mock_only(self, user_input=None):
        return self._save([])

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        options = ["esphome_device", "manual"]
        if self._existing():
            options.append("remove_gateway")
        return self.async_show_menu(step_id="reconfigure", menu_options=options)

    async def async_step_esphome_device(self, user_input=None):
        devices = esphome_devices(self.hass)
        if not devices:
            return self.async_abort(reason="no_esphome_devices")
        errors = {}
        if user_input is not None:
            entry, mac = devices[user_input["device"]]
            gateway = {
                "host": entry.data["host"],
                "port": entry.data.get("port", 6053),
                "mac": mac,
                "name": entry.title,
                "bridge": BRIDGE_V2,
            }
            if entry.data.get("noise_psk"):
                gateway["noise_psk"] = entry.data["noise_psk"]
            gateway["esphome_entry_id"] = entry.entry_id
            gateways, error = upsert_gateway(self._existing(), gateway)
            error = error or await verify_gateway(gateway)
            if error is None:
                return self._save(gateways)
            errors["base"] = error
        schema = vol.Schema(
            {
                vol.Required("device"): _select(
                    [
                        (entry_id, f"{entry.title} ({entry.data['host']}, {mac})")
                        for entry_id, (entry, mac) in devices.items()
                    ]
                )
            }
        )
        return self.async_show_form(step_id="esphome_device", data_schema=schema, errors=errors)

    async def async_step_manual(self, user_input=None):
        errors = {}
        if user_input is not None:
            existing = self._existing()
            gateway, error = manual_gateway(user_input, existing)
            gateways = None
            if gateway is not None:
                gateways, error = upsert_gateway(existing, gateway)
            if error is None:
                return self._save(gateways)
            errors["base"] = error
        schema = vol.Schema(
            {
                vol.Required("host"): str,
                vol.Required("mac"): str,
                # Blank keeps a known MAC's bridge; a new Gateway defaults to v2.
                vol.Optional("bridge"): _select(
                    [(bridge, bridge) for bridge in BRIDGES]
                ),
                vol.Optional("noise_psk"): _password(),
                vol.Optional("clear_psk", default=False): bool,
            }
        )
        return self.async_show_form(step_id="manual", data_schema=schema, errors=errors)

    async def async_step_remove_gateway(self, user_input=None):
        existing = self._existing()
        if user_input is not None:
            remove = set(user_input.get("gateways", []))
            return self._save([g for g in existing if g["mac"] not in remove])
        options = [(g["mac"], _label(g)) for g in existing]
        schema = vol.Schema({vol.Required("gateways"): _select(options, multiple=True)})
        return self.async_show_form(step_id="remove_gateway", data_schema=schema)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        entry = self._get_reauth_entry()
        existing = entry.data.get("gateways", [])
        if not existing:
            return self.async_abort(reason="no_physical_gateways")
        errors = {}
        if user_input is not None:
            # The selector only offers enrolled MACs.
            mac = user_input.get("gateway", existing[0]["mac"])
            previous = next(g for g in existing if g["mac"] == mac)
            gateway = dict(previous)
            error = _apply_key(
                gateway,
                previous,
                user_input.get("noise_psk", "").strip(),
                user_input.get("clear_psk", False),
            )
            error = error or await verify_gateway(gateway)
            if error is None:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={"gateways": [gateway if g is previous else g for g in existing]},
                )
            errors["base"] = error
        schema = vol.Schema(
            {
                vol.Required("gateway", default=existing[0]["mac"]): _select(
                    [(g["mac"], _label(g)) for g in existing]
                ),
                vol.Optional("noise_psk"): _password(),
                vol.Optional("clear_psk", default=False): bool,
            }
        )
        return self.async_show_form(step_id="reauth_confirm", data_schema=schema, errors=errors)
