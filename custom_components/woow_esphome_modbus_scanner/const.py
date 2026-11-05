"""Constants for Woow ESPHome Modbus Scanner."""

DOMAIN = "woow_esphome_modbus_scanner"
NAME = "Woow ESPHome Modbus Scanner"
VERSION = "0.5.0.dev2"

PANEL_COMPONENT_NAME = "woow-esphome-modbus-scanner-panel"
PANEL_URL_PATH = "woow-esphome-modbus-scanner"
PANEL_TITLE = "Modbus Scanner"
PANEL_ICON = "mdi:radar"
PANEL_STATIC_URL = (
    f"/woow_esphome_modbus_scanner/frontend/{VERSION}/woow-esphome-modbus-scanner-panel.js"
)

DATA_COORDINATOR = "coordinator"
DATA_COORDINATOR_OWNER = "coordinator_owner"
DATA_LIFECYCLE = "lifecycle"
DATA_STATIC_PATH_REGISTERED = "static_path_registered"
DATA_SERVICE_OWNER = "service_owner"
DATA_SERVICES_AVAILABLE = "services_available"
DATA_DEVICE_PROFILES = "device_profiles"
DATA_PROBE_SLOT_MODES = "probe_slot_modes"

SERVICE_LIST_GATEWAYS = "list_gateways"
SERVICE_START_SCAN = "start_scan"
SERVICE_GET_SCAN_STATUS = "get_scan_status"
SERVICE_GET_SCAN_RESULTS = "get_scan_results"
SERVICE_CANCEL_SCAN = "cancel_scan"
SERVICE_TEST_ADDRESS = "test_address"
SERVICE_SET_PAUSABLE_POLLERS = "set_pausable_pollers"
SERVICE_LIST_DEVICE_PROFILES = "list_device_profiles"
SERVICE_IMPORT_DEVICE_PROFILE = "import_device_profile"
SERVICE_EXPORT_DEVICE_PROFILE = "export_device_profile"
SERVICE_DELETE_DEVICE_PROFILE = "delete_device_profile"

PUBLIC_SERVICES = (
    "check_gateway",
    "get_history",
    SERVICE_LIST_GATEWAYS,
    SERVICE_SET_PAUSABLE_POLLERS,
    SERVICE_START_SCAN,
    SERVICE_GET_SCAN_STATUS,
    SERVICE_GET_SCAN_RESULTS,
    SERVICE_CANCEL_SCAN,
    SERVICE_TEST_ADDRESS,
    SERVICE_LIST_DEVICE_PROFILES,
    SERVICE_IMPORT_DEVICE_PROFILE,
    SERVICE_EXPORT_DEVICE_PROFILE,
    SERVICE_DELETE_DEVICE_PROFILE,
)
