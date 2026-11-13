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
The info sensor is disabled by default in Home Assistant (issue #25); the integration reads
it over the ESPHome API either way.

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
    CONF_DISABLED_BY_DEFAULT,
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

DOMAIN = "modbus_scanner"
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


def _entry_index():
    """This entry's position in the ``modbus_scanner:`` list, or None outside a validation run.

    ESPHome validates each MULTI_CONF entry in its own step and sets ``path_context`` to
    ``[DOMAIN, index]`` for it (config.py, SchemaValidationStep). The position comes from
    that path, not from comparing this config with the loaded YAML, so it still holds when
    ESPHome hands the validator a copy of the entry.
    """
    from esphome.config import path_context  # imported late: esphome.config loads components

    path = path_context.get(None)
    if path and isinstance(path[-1], int) and not isinstance(path[-1], bool):
        return path[-1]
    return None


def _one_entry_per_node(config):
    """Refuse every entry after the first and give the first the Gateway's text sensors.

    Checked here, before the schema, because a second entry would otherwise fail first on
    ESPHome's duplicate entity-name check (the sensor names are fixed) and the final
    validation step, which runs only on an error-free config, would never be reached.
    MULTI_CONF stays on for the same reason: without it two entries fail as "expected a
    dictionary". The entry's position comes from ESPHome's validation path, so the check
    keeps no state of its own. Entry 0 passes and every later entry is refused with
    ONE_ENTRY_MESSAGE. ESPHome stops validating at the first error (Config.run_validation_steps),
    so two entries and three or more entries alike give one error, on the second entry; the
    third and later entries are never reached.
    """
    if not isinstance(config, dict):
        return config
    index = _entry_index()
    if index is not None and index > 0:
        raise cv.Invalid(ONE_ENTRY_MESSAGE)
    config = dict(config)
    for key, name in _GATEWAY_SENSORS.items():
        config.setdefault(key, {CONF_NAME: name})
    # The Info grows with every Pausable Poller and soon passes Home Assistant's 255-character
    # state limit. HA stores no state for a disabled entity, while ESPHome still lists and
    # publishes it over the API, where the integration reads it. text_sensor_schema() takes
    # no disabled_by_default argument, so the default is filled in here, before the schema;
    # a value written in YAML wins.
    info = config[CONF_INFO_SENSOR]
    if isinstance(info, dict):
        config[CONF_INFO_SENSOR] = {CONF_DISABLED_BY_DEFAULT: True, **info}
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


def _final_validate(config):
    """Runs once per entry (ESPHome passes each MULTI_CONF entry on its own)."""
    modbus.final_validate_modbus_device(DOMAIN, role="client")(config)
    if "api" not in fv.full_config.get():
        raise cv.Invalid("modbus_scanner requires the native 'api:' component")
    return config


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
