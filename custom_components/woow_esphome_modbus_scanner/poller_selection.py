"""Pausable Poller choices per Gateway and Bus, kept in the config entry's options.

The firmware stores nothing: HA keeps the last checklist the user saved for each Bus and
revalidates it whenever it learns the Gateway's current poller table (check or Scan).
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from homeassistant.core import HomeAssistant

from .modbus_scan.models import ONE_BUS_PER_GATEWAY, GatewayInfo, resolve_bus
from .modbus_scan.pollers import choose as choose_pollers
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
        which case the saved checklists are returned as they are. Once known, only Buses the
        Gateway reports keep a checklist; the saved rows of any other Bus count as removed.
        With ``prune`` this also saves the checklists without the removed rows and without
        the Buses the Gateway no longer reports, so each removal is reported once.
        """
        saved = self.saved(gateway_id)
        selection, removed = _reconciled(tables, saved)
        if (
            tables is not None
            and prune
            and (any(removed.values()) or not set(saved) <= set(tables))
        ):
            self.save(gateway_id, {bus: selection[bus] for bus in saved if bus in tables})
        return selection, removed

    def for_gateway(self, gateway: GatewayInfo, *, prune: bool) -> dict[str, Any]:
        """Pausable Poller checklist per Bus of a Scan Lease Gateway, revalidated if known.

        Empty for a Gateway without Scan Lease support: the one place that rule is checked.
        With ``prune`` the saved rows the firmware no longer has are dropped (see ``revalidate``).
        No checklist while the Gateway is refused for reporting several Buses: it has no Bus a
        checklist applies to until a read reports one Bus again (the saved one is kept).
        """
        if not gateway.supports_scan_lease:
            return {}
        if gateway.multiple_buses:
            return {"poller_selection": {}, "removed_pollers": {}}
        selection, removed = self.revalidate(
            gateway.gateway_id, gateway.pausable_poller_tables, prune=prune
        )
        return {"poller_selection": selection, "removed_pollers": removed}

    def save_choice(
        self, gateway: GatewayInfo | None, bus: str | None, indices
    ) -> dict[str, Any]:
        """Save which Pausable Pollers of one Bus a Scan pauses (indices of its table).

        The one place that decides whether a choice can be saved, and for which Bus:

        - once HA knows the Gateway's poller table, for its one Bus, validated against that
          table; ``bus`` may be omitted and, when given, must name that Bus;
        - before that (no check or Scan since HA started), for the one Bus a checklist was
          saved for, validated against that checklist as the panel shows it;
        - never for a Gateway refused for reporting several Buses (ADR 0011).

        Returns the Bus and the Gateway's checklists after. Checklists of Buses the Gateway
        no longer reports are dropped by the same save once its table is known.
        """
        if gateway is None or not gateway.supports_scan_lease:
            raise ValueError(
                "Pausable Poller selection needs an enrolled Gateway with Scan Lease support"
            )
        gateway_id = gateway.gateway_id
        if gateway.multiple_buses:
            raise ValueError(
                f"Gateway {gateway_id} reports more than one Bus, but {ONE_BUS_PER_GATEWAY}"
            )
        tables = gateway.pausable_poller_tables
        saved = self.saved(gateway_id)
        if tables is None:
            # A saved Bus is not a known one: a request naming another is told to check.
            selection = saved if len(saved) == 1 else {}
            target = bus if bus is not None else next(iter(selection), None)
        else:
            selection, _removed = _reconciled(tables, saved)
            target = resolve_bus(gateway_id, gateway.bus, bus)
        if target is None:
            raise ValueError(
                f"The Bus of Gateway {gateway_id} is not known yet; check the Gateway first"
            )
        if target not in selection:
            raise ValueError(
                f"Bus {target} has no known Pausable Poller table; check the Gateway first"
            )
        checklist, unknown = choose_pollers(selection[target], indices)
        if unknown:
            raise ValueError(f"Bus {target} has no Pausable Poller with index {unknown}")
        saved[target] = checklist
        kept = {key: rows for key, rows in saved.items() if key in selection}
        self.save(gateway_id, kept)
        after, removed = _reconciled(tables, kept)
        return {"bus": target, "poller_selection": after, "removed_pollers": removed}


def _reconciled(
    tables: dict[str, list[dict[str, Any]]] | None, saved: Checklists
) -> tuple[Checklists, Checklists]:
    """``saved`` checked against the current ``tables`` (see ``revalidate``), not saved."""
    if tables is None:
        return saved, {}
    selection: Checklists = {}
    removed: Checklists = {}
    for bus in sorted({*tables, *saved}):
        selection[bus], removed[bus] = reconcile(tables.get(bus, ()), saved.get(bus))
    return {bus: rows for bus, rows in selection.items() if bus in tables}, removed
