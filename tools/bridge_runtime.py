"""Load provider-only code for bench tests without importing Home Assistant.

This does not emulate HA services or count as an HA deployment test.
"""

from importlib import import_module
from pathlib import Path
import sys
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
package = ModuleType("_woow_bridge_bench")
package.__path__ = [str(ROOT / "custom_components/woow_esphome_modbus_scanner/modbus_scan")]
sys.modules.setdefault(package.__name__, package)
bridge = import_module("_woow_bridge_bench.esphome_provider")
models = import_module("_woow_bridge_bench.models")
provider = import_module("_woow_bridge_bench.provider")
ESPHomeGateway = bridge.ESPHomeGateway
ESPHomeGatewayProvider = bridge.ESPHomeGatewayProvider
ProbeType = models.ProbeType
ScanRequest = models.ScanRequest
GatewayProviderError = provider.GatewayProviderError
