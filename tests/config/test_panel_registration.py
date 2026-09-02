"""Sidebar registration, versioned static serving, and unload tests."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.woow_esphome_modbus_scanner import async_setup_entry, async_unload_entry
from custom_components.woow_esphome_modbus_scanner.const import (
    DOMAIN,
    PANEL_COMPONENT_NAME,
    PANEL_ICON,
    PANEL_STATIC_URL,
    PANEL_TITLE,
    PANEL_URL_PATH,
    VERSION,
)


async def test_registers_all_user_panel_and_versioned_static_bundle(hass, monkeypatch):
    static_register = AsyncMock()
    panel_register = AsyncMock()
    panel_remove = Mock()
    monkeypatch.setattr(
        hass, "http", SimpleNamespace(async_register_static_paths=static_register), raising=False
    )
    monkeypatch.setattr(
        "custom_components.woow_esphome_modbus_scanner.panel_custom.async_register_panel",
        panel_register,
    )
    monkeypatch.setattr(
        "custom_components.woow_esphome_modbus_scanner.frontend.async_remove_panel", panel_remove
    )
    entry = MockConfigEntry(domain=DOMAIN, title=PANEL_TITLE, data={})
    entry.add_to_hass(hass)

    assert await async_setup_entry(hass, entry)
    assert await async_setup_entry(hass, entry)
    static_register.assert_awaited_once()
    static_path = static_register.await_args.args[0][0]
    assert static_path.url_path == PANEL_STATIC_URL
    assert f"/{VERSION}/" in static_path.url_path
    assert static_path.cache_headers is True
    assert Path(static_path.path).name == f"{PANEL_COMPONENT_NAME}.js"
    assert Path(static_path.path).is_file()
    panel_register.assert_awaited_once_with(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=PANEL_COMPONENT_NAME,
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        module_url=PANEL_STATIC_URL,
        require_admin=False,
        config={"version": VERSION},
    )

    assert await async_unload_entry(hass, entry)
    panel_remove.assert_called_once_with(hass, PANEL_URL_PATH)


async def test_unload_dispatched_during_initial_panel_setup_owns_pending_generation(
    hass, monkeypatch
):
    """An interleaved first unload must remove the panel setup it observed."""
    registration_started = asyncio.Event()
    finish_registration = asyncio.Event()

    async def register_panel(*_args, **_kwargs):
        registration_started.set()
        await finish_registration.wait()

    static_register = AsyncMock()
    panel_register = AsyncMock(side_effect=register_panel)
    panel_remove = Mock()
    monkeypatch.setattr(
        hass, "http", SimpleNamespace(async_register_static_paths=static_register), raising=False
    )
    monkeypatch.setattr(
        "custom_components.woow_esphome_modbus_scanner.panel_custom.async_register_panel",
        panel_register,
    )
    monkeypatch.setattr(
        "custom_components.woow_esphome_modbus_scanner.frontend.async_remove_panel",
        panel_remove,
    )
    entry = MockConfigEntry(domain=DOMAIN, title=PANEL_TITLE, data={})
    entry.add_to_hass(hass)

    setup_task = asyncio.create_task(async_setup_entry(hass, entry))
    await registration_started.wait()
    unload_task = asyncio.create_task(async_unload_entry(hass, entry))
    await asyncio.sleep(0)
    finish_registration.set()

    assert await setup_task is True
    assert await unload_task is True
    panel_remove.assert_called_once_with(hass, PANEL_URL_PATH)
    assert not hass.services.has_service(DOMAIN, "start_scan")


async def test_reload_reuses_static_route_but_registers_fresh_panel(hass, monkeypatch):
    static_register = AsyncMock()
    panel_register = AsyncMock()
    panel_remove = Mock()
    monkeypatch.setattr(
        hass, "http", SimpleNamespace(async_register_static_paths=static_register), raising=False
    )
    monkeypatch.setattr(
        "custom_components.woow_esphome_modbus_scanner.panel_custom.async_register_panel",
        panel_register,
    )
    monkeypatch.setattr(
        "custom_components.woow_esphome_modbus_scanner.frontend.async_remove_panel", panel_remove
    )
    entry = MockConfigEntry(domain=DOMAIN, title=PANEL_TITLE, data={})
    entry.add_to_hass(hass)

    assert await async_setup_entry(hass, entry)
    assert await async_unload_entry(hass, entry)
    assert await async_setup_entry(hass, entry)

    static_register.assert_awaited_once()
    assert panel_register.await_count == 2
    assert panel_remove.call_count == 1
    assert await async_unload_entry(hass, entry)
