"""Bridge protocol v2 adapter for the vendor-neutral ``modbus_scanner`` ESPHome component."""

from .provider import EndpointResolver, V2Gateway, V2GatewayProvider


def build_provider(gateways, *, endpoint: EndpointResolver | None = None):
    """Create the v2 provider from config-entry gateway dictionaries."""
    return V2GatewayProvider(
        [
            V2Gateway(
                host=g["host"],
                mac=g["mac"],
                name=g.get("name"),
                port=g.get("port", 6053),
                noise_psk=g.get("noise_psk"),
                esphome_entry_id=g.get("esphome_entry_id"),
            )
            for g in gateways
        ],
        endpoint=endpoint,
    )


__all__ = ["V2Gateway", "V2GatewayProvider", "build_provider"]
