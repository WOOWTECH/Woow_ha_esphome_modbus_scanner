"""Pausable Poller choices per Gateway and Bus, kept in the config entry's options.

The firmware stores nothing: HA keeps the last checklist the user saved for each Bus and
revalidates it whenever it learns the Gateway's current poller table (check or Scan).
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from homeassistant.core import HomeAssistant

from .modbus_scan.pollers import reconcile

OPTION_KEY = "pausable_poller_selection"

Checklists = dict[str, list[dict[str, Any]]]


def without_gateways(options: dict[str, Any], gateway_ids) -> dict[str, Any]:
    """Entry options with the saved checklists of these (removed) Gateways dropped."""
    selection = {
        gateway_id: checklists
        for gateway_id, checklists in options.get(OPTION_KEY, {}).items()
        if gateway_id not in set(gateway_ids)
    }
    return {**options, OPTION_KEY: selection} if OPTION_KEY in options else dict(options)


class PollerSelectionStore:
    """Read and write saved checklists of the scanner's config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str | None) -> None:
        self._hass = hass
        self._entry_id = entry_id

    def _entry(self):
        if self._entry_id is None:
            return None
        return self._hass.config_entries.async_get_entry(self._entry_id)

    def saved(self, gateway_id: str) -> Checklists:
        """The saved checklist of each Bus of one Gateway (empty when none was saved)."""
        entry = self._entry()
        if entry is None:
            return {}
        return deepcopy(entry.options.get(OPTION_KEY, {}).get(gateway_id, {}))

    def save(self, gateway_id: str, checklists: Checklists) -> None:
        """Replace one Gateway's saved checklists (all of its Buses)."""
        entry = self._entry()
        if entry is None:
            return
        selection = deepcopy(dict(entry.options.get(OPTION_KEY, {})))
        if checklists:
            selection[gateway_id] = deepcopy(checklists)
        else:
            selection.pop(gateway_id, None)
        self._hass.config_entries.async_update_entry(
            entry, options={**entry.options, OPTION_KEY: selection}
        )

    def revalidate(
        self, gateway_id: str, tables: dict[str, list[dict[str, Any]]] | None, *, prune: bool
    ) -> tuple[Checklists, Checklists]:
        """(checklist per Bus, saved rows the firmware no longer has, per Bus).

        ``tables`` is the Gateway's current poller table per Bus, or None while unknown, in
        which case the saved checklists are returned as they are. With ``prune`` this also
        saves the checklists without the removed rows, so each removal is reported once.
        """
        saved = self.saved(gateway_id)
        if tables is None:
            return saved, {}
        selection: Checklists = {}
        removed: Checklists = {}
        for bus in sorted({*tables, *saved}):
            selection[bus], removed[bus] = reconcile(tables.get(bus, ()), saved.get(bus))
        selection = {bus: rows for bus, rows in selection.items() if bus in tables}
        if prune and any(removed.values()):
            self.save(gateway_id, {bus: selection[bus] for bus in saved if bus in tables})
        return selection, removed
