"""Bridge protocol v2 adapter for the vendor-neutral ``modbus_scanner`` ESPHome component."""

from .provider import V2Gateway, V2GatewayProvider


def build_provider(gateways):
    """Create the v2 provider from config-entry gateway dictionaries."""
    return V2GatewayProvider(
        [
            V2Gateway(
                host=g["host"],
                mac=g["mac"],
                name=g.get("name"),
                port=g.get("port", 6053),
                noise_psk=g.get("noise_psk"),
            )
            for g in gateways
        ]
    )


__all__ = ["V2Gateway", "V2GatewayProvider", "build_provider"]
