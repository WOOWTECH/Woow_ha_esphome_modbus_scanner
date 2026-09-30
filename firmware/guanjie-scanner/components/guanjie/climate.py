import esphome.codegen as cg
from esphome.components import (
    binary_sensor,
    button,
    climate,
    modbus,
    number,
    sensor,
    switch,
    text_sensor,
)
import esphome.config_validation as cv
from esphome.const import CONF_ID, ENTITY_CATEGORY_CONFIG, ENTITY_CATEGORY_DIAGNOSTIC, __version__
import esphome.final_validate as fv

DEPENDENCIES = ["modbus"]
AUTO_LOAD = ["number", "switch", "sensor", "binary_sensor", "text_sensor", "button"]
ns = cg.esphome_ns.namespace("guanjie")
GuanjieClimate = ns.class_(
    "GuanjieClimate", climate.Climate, cg.Component, modbus.ModbusClientDevice
)
AddressNumber = ns.class_("AddressNumber", number.Number)
FunctionSwitch = ns.class_("FunctionSwitch", switch.Switch)
ForgetWifiButton = ns.class_("ForgetWifiButton", button.Button)
VALUES = {
    "temperature": 6,
    "humidity1_raw": 7,
    "temperature2_raw": 8,
    "humidity2_raw": 9,
    "pipe_temperature_raw": 10,
    "fan_hours": 11,
    "filter_threshold_hours": 12,
}
FLAGS = {
    "compressor_running": 0x80,
    "fan_running": 0x40,
    "pipe_sensor_fault": 0x10,
    "humidity_sensor_fault": 0x08,
    "room_sensor_fault": 0x04,
    "water_full_fault": 0x02,
    "high_pressure_fault": 0x0800,
    "low_pressure_fault": 0x0400,
}
extra = {
    cv.Required("forget_wifi"): button.button_schema(
        ForgetWifiButton, entity_category=ENTITY_CATEGORY_CONFIG
    ),
    cv.Required("target_address"): number.number_schema(
        AddressNumber, entity_category=ENTITY_CATEGORY_CONFIG
    ),
    cv.Required("air_cleaning"): switch.switch_schema(FunctionSwitch),
    cv.Required("continuous_drying"): switch.switch_schema(FunctionSwitch),
    cv.Required("online"): binary_sensor.binary_sensor_schema(device_class="connectivity"),
    cv.Required("communication_status"): text_sensor.text_sensor_schema(
        entity_category=ENTITY_CATEGORY_DIAGNOSTIC
    ),
    cv.Required("command_result"): text_sensor.text_sensor_schema(
        entity_category=ENTITY_CATEGORY_DIAGNOSTIC
    ),
    cv.Required("active_address"): sensor.sensor_schema(
        accuracy_decimals=0, entity_category=ENTITY_CATEGORY_DIAGNOSTIC
    ),
}
for name in VALUES:
    kw = {"accuracy_decimals": 0}
    if name == "temperature":
        kw.update(unit_of_measurement="°C", device_class="temperature", accuracy_decimals=1)
    elif name.endswith("hours"):
        kw.update(unit_of_measurement="h", entity_category=ENTITY_CATEGORY_DIAGNOSTIC)
    else:
        kw.update(entity_category=ENTITY_CATEGORY_DIAGNOSTIC)
    extra[cv.Optional(name)] = sensor.sensor_schema(**kw)
for name in FLAGS:
    extra[cv.Optional(name)] = binary_sensor.binary_sensor_schema(
        **({"device_class": "problem"} if name.endswith("fault") else {})
    )
CONFIG_SCHEMA = (
    climate.climate_schema(GuanjieClimate)
    .extend(extra)
    .extend(cv.COMPONENT_SCHEMA)
    .extend(modbus.modbus_device_schema(1))
)


def validate_wifi_reset(config):
    if __version__ != "2026.9.0":
        raise cv.Invalid(
            "Guanjie WiFi-only NVS reset must be re-audited before changing ESPHome2026.9.0"
        )
    wifi = fv.full_config.get().get("wifi", {})
    fast_connect = wifi.get("fast_connect", {})
    fast_enabled = (
        fast_connect.get("enabled", False) if isinstance(fast_connect, dict) else bool(fast_connect)
    )
    if wifi.get("ssid") or wifi.get("networks") or fast_enabled:
        raise cv.Invalid(
            "WiFi reset requires AP-only provisioning, no compiled STA networks or fast_connect"
        )
    return config


FINAL_VALIDATE_SCHEMA = validate_wifi_reset


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await climate.register_climate(var, config)
    await modbus.register_modbus_client_device(var, config)
    b = await button.new_button(config["forget_wifi"])
    cg.add(var.set_forget_wifi_button(b))
    n = await number.new_number(config["target_address"], min_value=1, max_value=32, step=1)
    cg.add(var.set_address_number(n))
    for key, method in [
        ("air_cleaning", "set_air_switch"),
        ("continuous_drying", "set_continuous_switch"),
    ]:
        obj = await switch.new_switch(config[key])
        cg.add(getattr(var, method)(obj))
    obj = await binary_sensor.new_binary_sensor(config["online"])
    cg.add(var.set_online_sensor(obj))
    for key, method in [
        ("communication_status", "set_status_sensor"),
        ("command_result", "set_result_sensor"),
    ]:
        obj = await text_sensor.new_text_sensor(config[key])
        cg.add(getattr(var, method)(obj))
    obj = await sensor.new_sensor(config["active_address"])
    cg.add(var.set_active_address_sensor(obj))
    for key, index in VALUES.items():
        if key in config:
            obj = await sensor.new_sensor(config[key])
            cg.add(var.set_value_sensor(index, obj))
    for key, mask in FLAGS.items():
        if key in config:
            obj = await binary_sensor.new_binary_sensor(config[key])
            cg.add(var.set_flag_sensor(mask, obj))
