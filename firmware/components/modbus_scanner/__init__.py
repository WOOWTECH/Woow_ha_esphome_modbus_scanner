"""Vendor-neutral Modbus RTU scanner (bridge protocol v2) for ESPHome 2026.9+.

Minimal YAML (one entry, naming the Modbus client hub of the node's one Bus)::

    external_components:
      - source: github://WOOWTECH/Woow_ha_esphome_modbus_scanner/firmware/components
        components: [modbus_scanner]
    modbus_scanner:
      - modbus_id: modbus_bus

A Gateway serves exactly one Bus (ADR 0011): a second ``modbus_scanner`` entry fails
validation, so a second RS-485 line is scanned with another node. The Bus may be named with
``bus:``; its info entry reports the hub UART's baud rate, parity and stop bits. The entry
creates the Gateway's probe/release actions and the info/result/lease text sensors, whose
names are fixed by the bridge v2 contract file
(custom_components/woow_esphome_modbus_scanner/modbus_scan/bridge_v2/contract.json).

Pausable Pollers are found here, at code generation: every component in the validated config
that is bound to the same hub (``modbus_id``) and whose generated class inherits
``PollingComponent`` (for example each ``modbus_controller``) gets a stable index in YAML
order. Nothing is listed by hand; adding a poller needs a recompile to appear.
"""

import re

import esphome.codegen as cg
from esphome.components import modbus, text_sensor
from esphome.components.const import CONF_PARITY, CONF_STOP_BITS
import esphome.config_validation as cv
from esphome.const import (
    CONF_ADDRESS,
    CONF_BAUD_RATE,
    CONF_ID,
    CONF_NAME,
    CONF_UART_ID,
    ENTITY_CATEGORY_DIAGNOSTIC,
)
from esphome.core import CORE, ID
import esphome.final_validate as fv

CODEOWNERS = ["@WOOWTECH"]
DEPENDENCIES = ["api", "modbus"]
AUTO_LOAD = ["text_sensor"]
MULTI_CONF = True

# Fixed by the bridge v2 contract; tests/config/test_firmware_contract.py checks they match.
INFO_SENSOR_NAME = "Modbus Scanner v2 Info"
RESULT_SENSOR_NAME = "Modbus Scanner v2 Result"
LEASE_SENSOR_NAME = "Modbus Scanner v2 Lease"
MIN_ESPHOME_VERSION = (2026, 9, 0)

CONF_BUS = "bus"
CONF_GATEWAY_ID = "gateway_id"
CONF_INFO_SENSOR = "info_sensor"
CONF_RESULT_SENSOR = "result_sensor"
CONF_LEASE_SENSOR = "lease_sensor"
ONE_ENTRY_MESSAGE = (
    "A node supports only one modbus_scanner; scan a second RS-485 line with another node"
)

modbus_scanner_ns = cg.esphome_ns.namespace("modbus_scanner")
ModbusScannerGateway = modbus_scanner_ns.class_("ModbusScannerGateway", cg.Component)
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


_GATEWAY_SENSORS = {
    CONF_INFO_SENSOR: INFO_SENSOR_NAME,
    CONF_RESULT_SENSOR: RESULT_SENSOR_NAME,
    CONF_LEASE_SENSOR: LEASE_SENSOR_NAME,
}
_ENTRY_SEEN_KEY = "modbus_scanner_entry_seen"


def _one_entry_per_node(config):
    """Refuse a second entry and give the only one the Gateway's text sensors.

    MULTI_CONF stays on so that a second entry reaches this message rather than ESPHome's
    generic one. Runs before the schema, once per entry, in YAML order; CORE.data is reset
    with every validation.
    """
    if not isinstance(config, dict):
        return config
    if CORE.data.get(_ENTRY_SEEN_KEY):
        raise cv.Invalid(ONE_ENTRY_MESSAGE)
    CORE.data[_ENTRY_SEEN_KEY] = True
    config = dict(config)
    for key, name in _GATEWAY_SENSORS.items():
        config.setdefault(key, {CONF_NAME: name})
    return config


CONFIG_SCHEMA = cv.All(
    _one_entry_per_node,
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(ModbusScannerBus),
            cv.GenerateID(CONF_GATEWAY_ID): cv.declare_id(ModbusScannerGateway),
            cv.GenerateID(modbus.CONF_MODBUS_ID): cv.use_id(modbus.ModbusClient),
            cv.Optional(CONF_BUS): _bus_name,
            **{cv.Optional(key): _sensor(name) for key, name in _GATEWAY_SENSORS.items()},
        }
    ),
    cv.require_esphome_version(*MIN_ESPHOME_VERSION),
)


def _default_bus_name(config):
    raw = str(config[modbus.CONF_MODBUS_ID])
    return re.sub(r"[^0-9A-Za-z_-]", "_", raw)[:32]


def _final_validate(configs):
    full = fv.full_config.get()
    configs = configs if isinstance(configs, list) else [configs]
    if len(configs) > 1:
        raise cv.Invalid(ONE_ENTRY_MESSAGE)
    for config in configs:
        modbus.final_validate_modbus_device("modbus_scanner", role="client")(config)
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


def _hub_serial(hub_id):
    """(baud_rate, parity, stop_bits) of the UART behind the hub, or None if not found."""
    for hub in CORE.config.get("modbus", []):
        if hub[CONF_ID] != hub_id or CONF_UART_ID not in hub:
            continue
        for uart in CORE.config.get("uart", []):
            if uart[CONF_ID] == hub[CONF_UART_ID]:
                return (
                    int(uart[CONF_BAUD_RATE]),
                    str(uart.get(CONF_PARITY, "NONE")),
                    int(uart.get(CONF_STOP_BITS, 1)),
                )
    return None


def _pausable_pollers(hub_id) -> list[dict]:
    """Every declared PollingComponent bound to ``hub_id``, in YAML order (stable indices)."""
    found: list[dict] = []
    seen: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            declared = node.get(CONF_ID)
            if (
                isinstance(declared, ID)
                and declared.is_declaration
                and declared.type is not None
                and declared.type.inherits_from(cg.PollingComponent)
                and isinstance(node.get(modbus.CONF_MODBUS_ID), ID)
                and str(node[modbus.CONF_MODBUS_ID]) == str(hub_id)
                and str(declared) not in seen
            ):
                seen.add(str(declared))
                found.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(CORE.config)
    return found


def _poller_address(config) -> int:
    """The poller's slave address, or 0 when it has none (its frames are then not cleared)."""
    address = config.get(CONF_ADDRESS)
    return address if isinstance(address, int) and 1 <= address <= 247 else 0


async def to_code(config):
    gateway = cg.new_Pvariable(config[CONF_GATEWAY_ID])
    await cg.register_component(gateway, {})
    info = await text_sensor.new_text_sensor(config[CONF_INFO_SENSOR])
    cg.add(gateway.set_info_sensor(info))
    result = await text_sensor.new_text_sensor(config[CONF_RESULT_SENSOR])
    cg.add(gateway.set_result_sensor(result))
    lease = await text_sensor.new_text_sensor(config[CONF_LEASE_SENSOR])
    cg.add(gateway.set_lease_sensor(lease))
    # The component registers its own API action, so the user does not need
    # `api: custom_services: true` in YAML.
    cg.add_define("USE_API_USER_DEFINED_ACTIONS")
    cg.add_define("USE_API_CUSTOM_SERVICES")

    name = config.get(CONF_BUS) or _default_bus_name(config)
    hub = await cg.get_variable(config[modbus.CONF_MODBUS_ID])
    var = cg.new_Pvariable(
        config[CONF_ID], name, _hub_send_wait_ms(config[modbus.CONF_MODBUS_ID])
    )
    cg.add(var.set_parent(hub))
    if serial := _hub_serial(config[modbus.CONF_MODBUS_ID]):
        cg.add(var.set_serial(*serial))
    for poller in _pausable_pollers(config[modbus.CONF_MODBUS_ID]):
        component = await cg.get_variable(poller[CONF_ID])
        name = str(poller.get(CONF_NAME) or poller[CONF_ID])
        cg.add(var.add_poller(name, _poller_address(poller), component))
    cg.add(gateway.set_bus(var))
