"""Imported Device Profiles persisted in HA storage (and therefore in HA backups)."""

from __future__ import annotations

import asyncio

from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .modbus_scan.device_profile import (
    GENERIC_DEVICE_PROFILE,
    GENERIC_PROFILE_ID,
    DeviceProfile,
    DeviceProfileError,
    parse_device_profile,
)

STORAGE_KEY = f"{DOMAIN}.device_profiles"
MAX_IMPORTED_PROFILES = 50


class DeviceProfileNotFoundError(LookupError):
    """No Device Profile has the requested id."""


class DeviceProfileStore:
    """The built-in Generic Device Profile plus every imported one."""

    def __init__(self, hass) -> None:
        self._store = Store(hass, 1, STORAGE_KEY)
        self._profiles: dict[str, DeviceProfile] = {}
        self._loaded = False
        self._lock = asyncio.Lock()
        self.skipped_on_load = 0

    async def async_load(self) -> None:
        """Load once; a stored document that no longer validates is skipped, not fatal."""
        async with self._lock:
            if self._loaded:
                return
            data = await self._store.async_load()
            documents = data.get("profiles", []) if isinstance(data, dict) else []
            for document in documents if isinstance(documents, list) else []:
                try:
                    profile = parse_device_profile(document)
                except DeviceProfileError:
                    self.skipped_on_load += 1
                    continue
                self._profiles[profile.profile_id] = profile
            self._loaded = True

    def profiles(self) -> list[DeviceProfile]:
        return [GENERIC_DEVICE_PROFILE, *sorted(self._profiles.values(), key=_sort_key)]

    def get(self, profile_id: str) -> DeviceProfile:
        if profile_id == GENERIC_PROFILE_ID:
            return GENERIC_DEVICE_PROFILE
        try:
            return self._profiles[profile_id]
        except KeyError as err:
            raise DeviceProfileNotFoundError(f"Unknown Device Profile: {profile_id}") from err

    async def async_import(self, source: object) -> tuple[DeviceProfile, bool]:
        """Validate and store a profile; an existing id is replaced. Returns (profile, replaced)."""
        profile = parse_device_profile(source)
        await self.async_load()
        async with self._lock:
            replaced = profile.profile_id in self._profiles
            if not replaced and len(self._profiles) >= MAX_IMPORTED_PROFILES:
                raise ValueError(
                    f"At most {MAX_IMPORTED_PROFILES} Device Profiles can be imported; "
                    "delete one first"
                )
            self._profiles[profile.profile_id] = profile
            await self._save()
        return profile, replaced

    async def async_delete(self, profile_id: str, refuse_if=None) -> None:
        """Delete an imported profile; ``refuse_if(profile_id)`` may raise to veto it."""
        if profile_id == GENERIC_PROFILE_ID:
            raise ValueError("The built-in Generic Device Profile cannot be deleted")
        await self.async_load()
        async with self._lock:
            self.get(profile_id)
            if refuse_if is not None:
                refuse_if(profile_id)  # no await between this check and the removal
            del self._profiles[profile_id]
            await self._save()

    async def _save(self) -> None:
        # Saved immediately (not delayed) so an import survives a restart right after it.
        await self._store.async_save(
            {"profiles": [profile.export() for profile in self._profiles.values()]}
        )


def _sort_key(profile: DeviceProfile) -> tuple[str, str]:
    return profile.name.casefold(), profile.profile_id
