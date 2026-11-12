"""HA diagnostic downloads contain no addresses, keys, raw frames or user data."""

from __future__ import annotations

from .const import DATA_COORDINATOR, DOMAIN, VERSION


def _info_summary(gateway) -> dict | None:
    """What the Gateway's last accepted Info reported, without Bus or Pausable Poller names.

    The Info entity is disabled by default in HA (issue #25), so this is where people see
    it. None until the provider has read an Info.
    """
    health = gateway.get("health") or {}
    if "bridge_version" not in health:
        return None
    buses = gateway.get("buses") or []
    pollers = health.get("pausable_pollers") or {}
    return {
        "bridge_version": health["bridge_version"],
        "serial": buses[0].get("serial") if len(buses) == 1 else None,
        "pausable_poller_count": sum(len(table) for table in pollers.values()),
    }


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
                "info": _info_summary(gateway),
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
