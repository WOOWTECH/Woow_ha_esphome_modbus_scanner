"""Woow ESPHome Modbus Scanner integration lifecycle."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    DATA_COORDINATOR,
    DATA_COORDINATOR_OWNER,
    DATA_LIFECYCLE,
    DOMAIN,
)
from .services import async_register_services, async_unregister_services


@dataclass(slots=True)
class _LifecycleState:
    """Serialize singleton ownership changes for one Home Assistant instance."""

    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    owner_entry_id: str | None = None
    owner_generation: int = 0
    next_generation: int = 0


def _lifecycle(hass: HomeAssistant) -> _LifecycleState:
    domain_data = hass.data.setdefault(DOMAIN, {})
    lifecycle = domain_data.get(DATA_LIFECYCLE)
    if lifecycle is None:
        lifecycle = _LifecycleState()
        domain_data[DATA_LIFECYCLE] = lifecycle
    return lifecycle


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Accept YAML discovery while remaining config-entry only."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one generation of the singleton scanner config entry."""
    lifecycle = _lifecycle(hass)
    async with lifecycle.lock:
        if lifecycle.owner_entry_id == entry.entry_id:
            return True
        if lifecycle.owner_entry_id is not None:
            # Config flow prevents this normally. Fail closed if storage or a
            # caller nevertheless supplies a second entry.
            return False

        lifecycle.next_generation += 1
        generation = lifecycle.next_generation
        lifecycle.owner_entry_id = entry.entry_id
        lifecycle.owner_generation = generation
        async_register_services(hass, entry.entry_id, generation)
        return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload only the generation owned when this unload was dispatched."""
    lifecycle = _lifecycle(hass)
    observed_owner = (
        (entry.entry_id, lifecycle.owner_generation)
        if lifecycle.owner_entry_id == entry.entry_id
        else None
    )
    async with lifecycle.lock:
        if observed_owner is None or (
            lifecycle.owner_entry_id,
            lifecycle.owner_generation,
        ) != observed_owner:
            # A stale, overlapping, or defensive duplicate unload must not tear
            # down a newer generation or a different owning entry.
            return True

        owner = observed_owner
        domain_data = hass.data[DOMAIN]
        coordinator = (
            domain_data.get(DATA_COORDINATOR)
            if domain_data.get(DATA_COORDINATOR_OWNER) == owner
            else None
        )

        # Stop new calls before awaiting active tasks. Handlers dispatched by
        # this generation also re-check ownership after authorization.
        async_unregister_services(hass, *owner)
        if coordinator is not None:
            await coordinator.async_shutdown()
            if (
                domain_data.get(DATA_COORDINATOR) is coordinator
                and domain_data.get(DATA_COORDINATOR_OWNER) == owner
            ):
                domain_data.pop(DATA_COORDINATOR, None)
                domain_data.pop(DATA_COORDINATOR_OWNER, None)

        if (
            lifecycle.owner_entry_id == entry.entry_id
            and lifecycle.owner_generation == owner[1]
        ):
            lifecycle.owner_entry_id = None
            lifecycle.owner_generation = 0
        return True
