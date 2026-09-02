"""Singleton config-entry lifecycle and unload-race tests."""

import asyncio

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.woow_esphome_modbus_scanner import (
    async_setup_entry,
    async_unload_entry,
)
from custom_components.woow_esphome_modbus_scanner.const import (
    DATA_COORDINATOR,
    DATA_COORDINATOR_OWNER,
    DATA_LIFECYCLE,
    DATA_SERVICE_OWNER,
    DOMAIN,
    PUBLIC_SERVICES,
)


@pytest.fixture(autouse=True)
def bypass_panel_registration(monkeypatch):
    """Keep lifecycle tests focused on generation/service ownership."""
    async def register_panel(_hass):
        return None

    monkeypatch.setattr(
        "custom_components.woow_esphome_modbus_scanner._async_register_panel",
        register_panel,
    )
    monkeypatch.setattr(
        "custom_components.woow_esphome_modbus_scanner.frontend.async_remove_panel",
        lambda *_args, **_kwargs: None,
    )


def _assert_unloaded(hass, coordinator):
    domain_data = hass.data[DOMAIN]
    assert set(domain_data) == {DATA_LIFECYCLE}
    assert domain_data[DATA_LIFECYCLE].owner_entry_id is None
    assert coordinator._tasks == {}
    assert coordinator._active == {}
    assert all(not hass.services.has_service(DOMAIN, name) for name in PUBLIC_SERVICES)


async def test_setup_registers_only_public_services_and_unload_cleans_tasks(hass):
    entry = MockConfigEntry(domain=DOMAIN, title="Woow ESPHome Modbus Scanner", data={})
    entry.add_to_hass(hass)
    assert await async_setup_entry(hass, entry)

    started = await hass.services.async_call(
        DOMAIN,
        "start_scan",
        {
            "start_id": 1,
            "end_id": 100,
            "inter_request_delay_ms": 100,
            "safety_confirmed": True,
        },
        blocking=True,
        return_response=True,
    )
    coordinator = hass.data[DOMAIN][DATA_COORDINATOR]

    assert await async_unload_entry(hass, entry)
    await hass.async_block_till_done()

    assert coordinator.status(started["scan_id"])["status"] == "cancelled"
    _assert_unloaded(hass, coordinator)


async def test_unload_removes_services_before_coordinator_shutdown(hass, monkeypatch):
    entry = MockConfigEntry(domain=DOMAIN, title="Woow ESPHome Modbus Scanner", data={})
    entry.add_to_hass(hass)
    assert await async_setup_entry(hass, entry)
    coordinator = hass.data[DOMAIN][DATA_COORDINATOR]
    shutdown_entered = asyncio.Event()
    finish_shutdown = asyncio.Event()

    async def interleaved_shutdown(self):
        assert self is coordinator
        shutdown_entered.set()
        await finish_shutdown.wait()

    monkeypatch.setattr(type(coordinator), "async_shutdown", interleaved_shutdown)
    unload = asyncio.create_task(async_unload_entry(hass, entry))
    await shutdown_entered.wait()

    assert not hass.services.has_service(DOMAIN, "start_scan")
    assert hass.data[DOMAIN][DATA_COORDINATOR] is coordinator

    finish_shutdown.set()
    assert await unload
    _assert_unloaded(hass, coordinator)


async def test_overlapping_unload_then_setup_transfers_singleton_ownership(
    hass, monkeypatch
):
    first = MockConfigEntry(domain=DOMAIN, title="First", data={})
    second = MockConfigEntry(domain=DOMAIN, title="Second", data={})
    first.add_to_hass(hass)
    second.add_to_hass(hass)
    assert await async_setup_entry(hass, first)
    first_coordinator = hass.data[DOMAIN][DATA_COORDINATOR]
    shutdown_entered = asyncio.Event()
    finish_shutdown = asyncio.Event()

    async def interleaved_shutdown(self):
        assert self is first_coordinator
        shutdown_entered.set()
        await finish_shutdown.wait()

    monkeypatch.setattr(type(first_coordinator), "async_shutdown", interleaved_shutdown)
    unload = asyncio.create_task(async_unload_entry(hass, first))
    await shutdown_entered.wait()
    setup = asyncio.create_task(async_setup_entry(hass, second))
    await asyncio.sleep(0)

    assert not setup.done()
    assert not hass.services.has_service(DOMAIN, "start_scan")

    finish_shutdown.set()
    assert await unload
    assert await setup

    domain_data = hass.data[DOMAIN]
    second_coordinator = domain_data[DATA_COORDINATOR]
    assert second_coordinator is not first_coordinator
    assert domain_data[DATA_COORDINATOR_OWNER][0] == second.entry_id
    assert domain_data[DATA_SERVICE_OWNER] == domain_data[DATA_COORDINATOR_OWNER]
    assert all(hass.services.has_service(DOMAIN, name) for name in PUBLIC_SERVICES)
    assert first_coordinator._tasks == {}

    # A stale unload for a different entry cannot affect the new generation.
    assert await async_unload_entry(hass, first)
    assert hass.data[DOMAIN][DATA_COORDINATOR] is second_coordinator


async def test_overlapping_duplicate_unload_cannot_remove_new_generation(
    hass, monkeypatch
):
    entry = MockConfigEntry(domain=DOMAIN, title="Woow ESPHome Modbus Scanner", data={})
    entry.add_to_hass(hass)
    assert await async_setup_entry(hass, entry)
    first_coordinator = hass.data[DOMAIN][DATA_COORDINATOR]
    first_owner = hass.data[DOMAIN][DATA_COORDINATOR_OWNER]
    shutdown_entered = asyncio.Event()
    finish_shutdown = asyncio.Event()

    async def interleaved_shutdown(self):
        assert self is first_coordinator
        shutdown_entered.set()
        await finish_shutdown.wait()

    monkeypatch.setattr(type(first_coordinator), "async_shutdown", interleaved_shutdown)
    first_unload = asyncio.create_task(async_unload_entry(hass, entry))
    await shutdown_entered.wait()
    setup_again = asyncio.create_task(async_setup_entry(hass, entry))
    await asyncio.sleep(0)
    duplicate_unload = asyncio.create_task(async_unload_entry(hass, entry))
    await asyncio.sleep(0)

    finish_shutdown.set()
    assert await first_unload
    assert await setup_again
    assert await duplicate_unload

    domain_data = hass.data[DOMAIN]
    assert domain_data[DATA_COORDINATOR] is not first_coordinator
    assert domain_data[DATA_COORDINATOR_OWNER][0] == entry.entry_id
    assert domain_data[DATA_COORDINATOR_OWNER][1] > first_owner[1]
    assert all(hass.services.has_service(DOMAIN, name) for name in PUBLIC_SERVICES)


async def test_duplicate_setup_and_non_owner_unload_leave_owner_unchanged(hass):
    owner = MockConfigEntry(domain=DOMAIN, title="Owner", data={})
    other = MockConfigEntry(domain=DOMAIN, title="Other", data={})
    owner.add_to_hass(hass)
    other.add_to_hass(hass)
    assert await async_setup_entry(hass, owner)
    coordinator = hass.data[DOMAIN][DATA_COORDINATOR]
    generation = hass.data[DOMAIN][DATA_COORDINATOR_OWNER]

    assert await async_setup_entry(hass, owner)
    assert not await async_setup_entry(hass, other)
    assert await async_unload_entry(hass, other)

    assert hass.data[DOMAIN][DATA_COORDINATOR] is coordinator
    assert hass.data[DOMAIN][DATA_COORDINATOR_OWNER] == generation
    assert hass.data[DOMAIN][DATA_SERVICE_OWNER] == generation
    assert all(hass.services.has_service(DOMAIN, name) for name in PUBLIC_SERVICES)
