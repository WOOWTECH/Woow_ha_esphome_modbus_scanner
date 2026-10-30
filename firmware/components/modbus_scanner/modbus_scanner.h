#pragma once

// ESPHome glue for the vendor-neutral Modbus scanner (bridge protocol v2). All decisions live in
// scanner_core.h; this file only adapts ESPHome's hub, clock, API action and text sensors to it.

#include <span>
#include <string>

#include "esphome/components/api/custom_api_device.h"
#include "esphome/components/modbus/modbus.h"
#include "esphome/components/text_sensor/text_sensor.h"
#include "esphome/core/component.h"
#include "scanner_core.h"

namespace esphome::modbus_scanner {

/// One scanner per Modbus client hub (a Bus). Probes are queued to arbitrary slaves through the
/// hub's public queue; the hub keeps one frame in flight and correlates the reply to it.
class ModbusScannerBus : public modbus::ModbusClientDevice, public modbus_scanner_core::BusPort {
 public:
  ModbusScannerBus(const char *name, uint16_t yaml_send_wait_ms) : core_(name, *this, yaml_send_wait_ms) {}

  modbus_scanner_core::Bus &core() { return this->core_; }

  bool queue_request(uint8_t slave, const uint8_t *pdu, size_t len) override {
    return this->parent_->queue_pdu(slave, std::span<const uint8_t>(pdu, len), this);
  }
  void set_send_wait_ms(uint16_t ms) override { this->parent_->set_send_wait_time(ms); }

  void on_sent(std::span<const uint8_t> /*request_pdu*/) override { this->core_.on_sent(); }
  void on_response(std::span<const uint8_t> /*request_pdu*/, std::span<const uint8_t> response_pdu) override {
    this->core_.on_response(response_pdu.data(), response_pdu.size());
  }
  void on_error(std::span<const uint8_t> /*request_pdu*/, modbus::ExceptionCode code) override {
    this->core_.on_exception(static_cast<uint8_t>(code));
  }
  bool on_no_response(std::span<const uint8_t> /*request_pdu*/) override {
    this->core_.on_no_response();
    return false;  // A probe is never retried by the hub; HA decides about retries.
  }
  void on_not_sent(std::span<const uint8_t> /*request_pdu*/) override { this->core_.on_not_sent(); }

 protected:
  modbus_scanner_core::Bus core_;
};

/// Node-wide singleton: registers the v2 probe action and owns the info/result text sensors.
class ModbusScannerBridge : public Component,
                            public api::CustomAPIDevice,
                            public modbus_scanner_core::Clock,
                            public modbus_scanner_core::ResultSink {
 public:
  void setup() override;
  void dump_config() override;

  void set_info_sensor(text_sensor::TextSensor *sensor) { this->info_sensor_ = sensor; }
  void set_result_sensor(text_sensor::TextSensor *sensor) { this->result_sensor_ = sensor; }
  void add_bus(ModbusScannerBus *bus) { this->core_.add_bus(&bus->core()); }

  uint32_t now_ms() override;
  void publish_result(const std::string &json) override;

  void on_probe(std::string request_id, std::string bus, int32_t slave, int32_t function_code, int32_t reg,
                int32_t count, int32_t timeout_ms, std::string scan_id, std::string pause_pollers);

 protected:
  modbus_scanner_core::Bridge core_{*this, *this};
  text_sensor::TextSensor *info_sensor_{nullptr};
  text_sensor::TextSensor *result_sensor_{nullptr};
};

}  // namespace esphome::modbus_scanner
