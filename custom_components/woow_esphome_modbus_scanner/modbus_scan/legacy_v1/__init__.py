"""Legacy bridge v1 adapter (`modbus_scanner_probe_v1`, IN-D17 firmware).

Every vendor-specific limit of the legacy bridge lives in this package and is
reported to the rest of the integration only through ``ProbeLimits``. Delete
this package and its registration in ``modbus_scan/adapters.py`` once both
Legacy Gateways are reflashed with the vendor-neutral scanner component.
"""

from .provider import ESPHomeGateway, ESPHomeGatewayProvider


def build_provider(gateways):
    """Create the legacy provider from config-entry gateway dictionaries."""
    return ESPHomeGatewayProvider([ESPHomeGateway(**gateway) for gateway in gateways])


__all__ = ["ESPHomeGateway", "ESPHomeGatewayProvider", "build_provider"]
