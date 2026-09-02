"""Woow ESPHome Modbus Scanner integration lifecycle."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import (
    DATA_COORDINATOR,
    DATA_COORDINATOR_OWNER,
    DATA_LIFECYCLE,
    DATA_STATIC_PATH_REGISTERED,
    DOMAIN,
    PANEL_COMPONENT_NAME,
    PANEL_ICON,
    PANEL_STATIC_URL,
    PANEL_TITLE,
    PANEL_URL_PATH,
    VERSION,
)
from .services import async_register_services, async_unregister_services

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass(slots=True)
class _LifecycleState:
    """Serialize singleton ownership changes for one Home Assistant instance."""

    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    owner_entry_id: str | None = None
    owner_generation: int = 0
    pending_entry_id: str | None = None
    pending_generation: int = 0
    next_generation: int = 0


def _lifecycle(hass: HomeAssistant) -> _LifecycleState:
    domain_data = hass.data.setdefault(DOMAIN, {})
    lifecycle = domain_data.get(DATA_LIFECYCLE)
    if lifecycle is None:
        lifecycle = _LifecycleState()
        domain_data[DATA_LIFECYCLE] = lifecycle
    return lifecycle


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the config-entry-only integration base."""
    return True


async def _async_register_panel(hass: HomeAssistant) -> None:
    """Serve the versioned bundle once and expose its all-user sidebar panel."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if not domain_data.get(DATA_STATIC_PATH_REGISTERED):
        bundle = Path(__file__).parent / "frontend" / PANEL_COMPONENT_NAME
        await hass.http.async_register_static_paths(
            [StaticPathConfig(PANEL_STATIC_URL, str(bundle.with_suffix(".js")), True)]
        )
        domain_data[DATA_STATIC_PATH_REGISTERED] = True
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=PANEL_COMPONENT_NAME,
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        module_url=PANEL_STATIC_URL,
        require_admin=False,
        config={"version": VERSION},
    )


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

        # Publish identity before the first await. An unload dispatched while
        # panel registration is pending can then claim this exact generation
        # instead of incorrectly treating the setup as having no owner.
        lifecycle.next_generation += 1
        generation = lifecycle.next_generation
        lifecycle.pending_entry_id = entry.entry_id
        lifecycle.pending_generation = generation
        try:
            await _async_register_panel(hass)
        except BaseException:
            if (
                lifecycle.pending_entry_id == entry.entry_id
                and lifecycle.pending_generation == generation
            ):
                lifecycle.pending_entry_id = None
                lifecycle.pending_generation = 0
            raise
        lifecycle.pending_entry_id = None
        lifecycle.pending_generation = 0
        lifecycle.owner_entry_id = entry.entry_id
        lifecycle.owner_generation = generation
        async_register_services(hass, entry.entry_id, generation)
        return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload only the generation owned when this unload was dispatched."""
    lifecycle = _lifecycle(hass)
    observed_owner = None
    if lifecycle.owner_entry_id == entry.entry_id:
        observed_owner = (entry.entry_id, lifecycle.owner_generation)
    elif lifecycle.pending_entry_id == entry.entry_id:
        observed_owner = (entry.entry_id, lifecycle.pending_generation)
    async with lifecycle.lock:
        if observed_owner is None or (
            lifecycle.owner_entry_id,
            lifecycle.owner_generation,
        ) != observed_owner:
            # A stale, overlapping, or defensive duplicate unload must not tear
            # down a newer generation or a different owning entry. A pending
            # setup becomes the matching owner before releasing this lock.
            return True

        owner = observed_owner
        domain_data = hass.data[DOMAIN]
        coordinator = (
            domain_data.get(DATA_COORDINATOR)
            if domain_data.get(DATA_COORDINATOR_OWNER) == owner
            else None
        )

        # Stop new calls before awaiting active tasks. Handlers dispatched by
        # this generation also re-check generation ownership.
        async_unregister_services(hass, *owner)
        frontend.async_remove_panel(hass, PANEL_URL_PATH)
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
