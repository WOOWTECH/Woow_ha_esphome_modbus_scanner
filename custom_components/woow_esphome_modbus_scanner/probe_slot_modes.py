"""The Probe Slot mode of each Gateway's last info read, kept across restarts (ADR 0010).

New Scans are admitted under this mode. Without it HA would forget the mode on every
restart and admit Scans of a per-Bus Gateway under the shared-slot fallback's limits until
its info was read again.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DATA_PROBE_SLOT_MODES, DOMAIN
from .modbus_scan.models import ProbeSlots

STORAGE_KEY = f"{DOMAIN}.probe_slot_modes"
_SAVE_DELAY_S = 1


class ProbeSlotModes:
    """Last read Probe Slot mode per Gateway id; a Gateway never read has none."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store = Store(hass, 1, STORAGE_KEY)
        self._modes: dict[str, ProbeSlots] = {}

    async def async_load(self) -> None:
        """Load the stored modes; an unreadable entry is dropped, not fatal."""
        data = await self._store.async_load()
        modes = data.get("modes", {}) if isinstance(data, dict) else {}
        for gateway_id, mode in modes.items() if isinstance(modes, dict) else ():
            if isinstance(gateway_id, str) and mode in set(ProbeSlots):
                self._modes[gateway_id] = ProbeSlots(mode)

    def get(self, gateway_id: str) -> ProbeSlots | None:
        return self._modes.get(gateway_id)

    def remember(self, gateway_id: str, mode: ProbeSlots) -> None:
        """Keep the mode an info read gave; saves only when it changed."""
        if self._modes.get(gateway_id) == mode:
            return
        self._modes[gateway_id] = mode
        self._store.async_delay_save(
            lambda: {"modes": {key: str(value) for key, value in self._modes.items()}},
            _SAVE_DELAY_S,
        )


async def async_probe_slot_modes(hass: HomeAssistant) -> ProbeSlotModes:
    """The one loaded instance per HA, shared by setup and the config flow."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if (modes := domain_data.get(DATA_PROBE_SLOT_MODES)) is not None:
        return modes
    modes = ProbeSlotModes(hass)
    await modes.async_load()
    # A concurrent first call may have stored its instance while this one loaded.
    return domain_data.setdefault(DATA_PROBE_SLOT_MODES, modes)
