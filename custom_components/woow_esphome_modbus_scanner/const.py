"""Constants for Woow ESPHome Modbus Scanner."""

DOMAIN = "woow_esphome_modbus_scanner"
NAME = "Woow ESPHome Modbus Scanner"
VERSION = "0.1.0"

DATA_COORDINATOR = "coordinator"
DATA_COORDINATOR_OWNER = "coordinator_owner"
DATA_LIFECYCLE = "lifecycle"
DATA_SERVICE_OWNER = "service_owner"
DATA_SERVICES_AVAILABLE = "services_available"

SERVICE_LIST_GATEWAYS = "list_gateways"
SERVICE_START_SCAN = "start_scan"
SERVICE_GET_SCAN_STATUS = "get_scan_status"
SERVICE_GET_SCAN_RESULTS = "get_scan_results"
SERVICE_CANCEL_SCAN = "cancel_scan"
SERVICE_TEST_ADDRESS = "test_address"

PUBLIC_SERVICES = (
    SERVICE_LIST_GATEWAYS,
    SERVICE_START_SCAN,
    SERVICE_GET_SCAN_STATUS,
    SERVICE_GET_SCAN_RESULTS,
    SERVICE_CANCEL_SCAN,
    SERVICE_TEST_ADDRESS,
)
