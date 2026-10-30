"""Vendor-neutral Modbus RTU scanner (bridge protocol v2) for ESPHome 2026.9+.

Minimal YAML (one entry per Modbus client hub, i.e. per Bus)::

    external_components:
      - source: github://WOOWTECH/Woow_ha_esphome_modbus_scanner/firmware/components
        components: [modbus_scanner]
    modbus_scanner:
      - modbus_id: modbus_bus

The node-wide probe action and the info/result text sensors are created once, by the first
entry. Their names are fixed by the bridge v2 contract file
(custom_components/woow_esphome_modbus_scanner/modbus_scan/bridge_v2/contract.json).
"""

import re

import esphome.codegen as cg
from esphome.components import modbus, text_sensor
import esphome.config_validation as cv
from esphome.const import CONF_ID, CONF_NAME, ENTITY_CATEGORY_DIAGNOSTIC
from esphome.core import CORE, ID
import esphome.final_validate as fv

CODEOWNERS = ["@WOOWTECH"]
DEPENDENCIES = ["api", "modbus"]
AUTO_LOAD = ["text_sensor"]
MULTI_CONF = True

# Fixed by the bridge v2 contract; tests/config/test_firmware_contract.py checks they match.
INFO_SENSOR_NAME = "Modbus Scanner v2 Info"
RESULT_SENSOR_NAME = "Modbus Scanner v2 Result"
MIN_ESPHOME_VERSION = (2026, 9, 0)

CONF_BUS = "bus"
CONF_INFO_SENSOR = "info_sensor"
CONF_RESULT_SENSOR = "result_sensor"
_BRIDGE_KEY = "modbus_scanner_bridge"

modbus_scanner_ns = cg.esphome_ns.namespace("modbus_scanner")
ModbusScannerBridge = modbus_scanner_ns.class_("ModbusScannerBridge", cg.Component)
ModbusScannerBus = modbus_scanner_ns.class_("ModbusScannerBus", modbus.ModbusClientDevice)


def _bus_name(value):
    value = cv.string_strict(value)
    if not re.fullmatch(r"[0-9A-Za-z_-]{1,32}", value):
        raise cv.Invalid("bus must be 1-32 characters from 0-9, A-Z, a-z, '_' and '-'")
    return value


def _fixed_name(name):
    def validator(config):
        if config.get(CONF_NAME) != name:
            raise cv.Invalid(f"The scanner sensor name is fixed by bridge protocol v2: {name!r}")
        return config

    return validator


def _sensor(name):
    return cv.All(
        text_sensor.text_sensor_schema(
            entity_category=ENTITY_CATEGORY_DIAGNOSTIC, icon="mdi:lan-connect"
        ),
        _fixed_name(name),
    )


CONFIG_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(ModbusScannerBus),
            cv.GenerateID(modbus.CONF_MODBUS_ID): cv.use_id(modbus.ModbusClient),
            cv.Optional(CONF_BUS): _bus_name,
            cv.Optional(CONF_INFO_SENSOR, default={CONF_NAME: INFO_SENSOR_NAME}): _sensor(
                INFO_SENSOR_NAME
            ),
            cv.Optional(CONF_RESULT_SENSOR, default={CONF_NAME: RESULT_SENSOR_NAME}): _sensor(
                RESULT_SENSOR_NAME
            ),
        }
    ),
    cv.require_esphome_version(*MIN_ESPHOME_VERSION),
)


def _default_bus_name(config):
    raw = str(config[modbus.CONF_MODBUS_ID])
    return re.sub(r"[^0-9A-Za-z_-]", "_", raw)[:32]


def _final_validate(configs):
    full = fv.full_config.get()
    for config in configs if isinstance(configs, list) else [configs]:
        modbus.final_validate_modbus_device("modbus_scanner", role="client")(config)
    hubs, names = set(), set()
    for config in full.get("modbus_scanner", []):
        hub = str(config[modbus.CONF_MODBUS_ID])
        if hub in hubs:
            raise cv.Invalid(f"Only one modbus_scanner is allowed per Modbus hub ({hub})")
        hubs.add(hub)
        name = config.get(CONF_BUS) or _default_bus_name(config)
        if name in names:
            raise cv.Invalid(f"Duplicate modbus_scanner bus name {name!r}")
        names.add(name)
    if "api" not in full:
        raise cv.Invalid("modbus_scanner requires the native 'api:' component")
    return configs


FINAL_VALIDATE_SCHEMA = _final_validate


def _hub_send_wait_ms(hub_id) -> int:
    """The hub's YAML send_wait_time, restored after every probe's own timeout."""
    for hub in CORE.config.get("modbus", []):
        if hub[CONF_ID] == hub_id and modbus.CONF_SEND_WAIT_TIME in hub:
            return int(hub[modbus.CONF_SEND_WAIT_TIME].total_milliseconds)
    return 2000


async def _bridge(config):
    if _BRIDGE_KEY in CORE.data:
        return CORE.data[_BRIDGE_KEY]
    bridge = cg.new_Pvariable(
        ID("modbus_scanner_bridge", is_declaration=True, type=ModbusScannerBridge)
    )
    await cg.register_component(bridge, {})
    info = await text_sensor.new_text_sensor(config[CONF_INFO_SENSOR])
    cg.add(bridge.set_info_sensor(info))
    result = await text_sensor.new_text_sensor(config[CONF_RESULT_SENSOR])
    cg.add(bridge.set_result_sensor(result))
    # The component registers its own API action, so the user does not need
    # `api: custom_services: true` in YAML.
    cg.add_define("USE_API_USER_DEFINED_ACTIONS")
    cg.add_define("USE_API_CUSTOM_SERVICES")
    CORE.data[_BRIDGE_KEY] = bridge
    return bridge


async def to_code(config):
    bridge = await _bridge(config)
    name = config.get(CONF_BUS) or _default_bus_name(config)
    hub = await cg.get_variable(config[modbus.CONF_MODBUS_ID])
    var = cg.new_Pvariable(
        config[CONF_ID], name, _hub_send_wait_ms(config[modbus.CONF_MODBUS_ID])
    )
    cg.add(var.set_parent(hub))
    cg.add(bridge.add_bus(var))
