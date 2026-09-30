"""HA diagnostic downloads contain no addresses, keys, raw frames or user data."""

from __future__ import annotations

from .const import DATA_COORDINATOR, DOMAIN, VERSION


async def async_get_config_entry_diagnostics(hass, entry):
    data = hass.data.get(DOMAIN, {})
    coordinator = data.get(DATA_COORDINATOR)
    gateways = coordinator.list_gateways()["gateways"] if coordinator else []
    safe = []
    for index, gateway in enumerate(gateways):
        health = gateway.get("health", {})
        safe.append(
            {
                "reference": f"gateway-{index + 1}",
                "provider": gateway["provider"],
                "encrypted": health.get("encrypted", False),
                "api_status": health.get("api_status", "unchecked"),
                "bridge_status": health.get("bridge_status", "unchecked"),
                "bus_status": health.get("bus_status", "unverified"),
                "recovery_status": health.get("recovery_status", "unknown"),
                "cleanup_status": health.get("cleanup_status", "unknown"),
                "error_code": (health.get("error_info") or {}).get("code"),
                "recovery_error_code": (health.get("recovery_error") or {}).get("code"),
                "profile_hash": (gateway.get("profile") or {}).get("profile_hash"),
            }
        )
    history = data.get("history")
    records = history.summaries() if history else []
    return {
        "integration_version": VERSION,
        "physical_policy": "all_active_ha_users_and_internal_automations",
        "gateways": safe,
        "history_storage_error": bool(history and history.load_error),
        "repairs_update_failed": bool(getattr(coordinator, "_issues_failed", False)),
        "terminal_scans": [
            {
                key: record.get(key)
                for key in (
                    "status",
                    "operation_phase",
                    "elapsed_ms",
                    "completed_addresses",
                    "total_addresses",
                    "outcome_counts",
                    "recovery_status",
                    "cleanup_status",
                )
            }
            for record in records
        ],
        "privacy": (
            "Gateway identities, hosts, credentials, raw responses and exception text omitted."
        ),
    }
