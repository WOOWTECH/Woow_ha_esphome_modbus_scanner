#include "modbus_scanner.h"

#include <array>
#include <utility>

#include "esphome/core/hal.h"
#include "esphome/core/log.h"

namespace esphome::modbus_scanner {

static const char *const TAG = "modbus_scanner";

void ModbusScannerGateway::setup() {
  std::array<std::string, modbus_scanner_core::kProbeArgs.size()> arg_names;
  for (size_t i = 0; i < arg_names.size(); i++)
    arg_names[i] = modbus_scanner_core::kProbeArgs[i].name;
  this->register_service(&ModbusScannerGateway::on_probe, modbus_scanner_core::kProbeAction, arg_names);
  std::array<std::string, modbus_scanner_core::kReleaseArgs.size()> release_names;
  for (size_t i = 0; i < release_names.size(); i++)
    release_names[i] = modbus_scanner_core::kReleaseArgs[i].name;
  this->register_service(&ModbusScannerGateway::on_release, modbus_scanner_core::kReleaseAction, release_names);
  if (this->info_sensor_ != nullptr)
    this->info_sensor_->publish_state(this->core_.info_json());
}

// The Gateway ends a Scan Lease by itself (idle or hard limit) even when HA is gone.
void ModbusScannerGateway::loop() { this->core_.loop(); }

void ModbusScannerGateway::dump_config() {
  ESP_LOGCONFIG(TAG,
                "Modbus scanner (bridge v%d):\n"
                "  Buses: %u",
                modbus_scanner_core::kBridgeVersion, static_cast<unsigned>(this->core_.buses().size()));
  for (auto *bus : this->core_.buses())
    ESP_LOGCONFIG(TAG, "  Bus: %s (%u Pausable Pollers)", bus->name().c_str(),
                  static_cast<unsigned>(bus->poller_count()));
}

uint32_t ModbusScannerGateway::now_ms() { return millis(); }

void ModbusScannerGateway::publish_result(const std::string &json) {
  ESP_LOGD(TAG, "Result: %s", json.c_str());
  if (this->result_sensor_ != nullptr)
    this->result_sensor_->publish_state(json);
}

void ModbusScannerGateway::publish_lease(const std::string &json) {
  ESP_LOGI(TAG, "Scan Lease: %s", json.c_str());
  if (this->lease_sensor_ != nullptr)
    this->lease_sensor_->publish_state(json);
}

void ModbusScannerGateway::on_release(std::string bus, std::string scan_id) { this->core_.release(bus, scan_id); }

void ModbusScannerGateway::on_probe(std::string request_id, std::string bus, int32_t slave, int32_t function_code,
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
