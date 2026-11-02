#include "modbus_scanner.h"

#include <array>
#include <utility>

#include "esphome/core/hal.h"
#include "esphome/core/log.h"

namespace esphome::modbus_scanner {

static const char *const TAG = "modbus_scanner";

void ModbusScannerBridge::setup() {
  std::array<std::string, modbus_scanner_core::kProbeArgs.size()> arg_names;
  for (size_t i = 0; i < arg_names.size(); i++)
    arg_names[i] = modbus_scanner_core::kProbeArgs[i].name;
  this->register_service(&ModbusScannerBridge::on_probe, modbus_scanner_core::kProbeAction, arg_names);
  if (this->info_sensor_ != nullptr)
    this->info_sensor_->publish_state(this->core_.info_json());
}

void ModbusScannerBridge::dump_config() {
  ESP_LOGCONFIG(TAG,
                "Modbus scanner (bridge v%d):\n"
                "  Buses: %u",
                modbus_scanner_core::kBridgeVersion, static_cast<unsigned>(this->core_.buses().size()));
  for (auto *bus : this->core_.buses())
    ESP_LOGCONFIG(TAG, "  Bus: %s", bus->name().c_str());
}

uint32_t ModbusScannerBridge::now_ms() { return millis(); }

void ModbusScannerBridge::publish_result(const std::string &json) {
  ESP_LOGD(TAG, "Result: %s", json.c_str());
  if (this->result_sensor_ != nullptr)
    this->result_sensor_->publish_state(json);
}

void ModbusScannerBridge::on_probe(std::string request_id, std::string bus, int32_t slave, int32_t function_code,
                                   int32_t reg, int32_t count, int32_t timeout_ms, std::string scan_id,
                                   std::string pause_pollers) {
  modbus_scanner_core::ProbeRequest request;
  request.request_id = std::move(request_id);
  request.bus = std::move(bus);
  request.slave = slave;
  request.function_code = function_code;
  request.reg = reg;
  request.count = count;
  request.timeout_ms = timeout_ms;
  request.scan_id = std::move(scan_id);
  request.pause_pollers = std::move(pause_pollers);
  this->core_.probe(request);
}

}  // namespace esphome::modbus_scanner
