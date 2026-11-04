#pragma once

// ESPHome glue for the vendor-neutral Modbus scanner (bridge protocol v2). All decisions live in
// scanner_core.h; this file only adapts ESPHome's hub, clock, API action and text sensors to it.

#include <memory>
#include <span>
#include <string>
#include <vector>

#include "esphome/components/api/custom_api_device.h"
#include "esphome/components/modbus/modbus.h"
#include "esphome/components/text_sensor/text_sensor.h"
#include "esphome/core/component.h"
#include "scanner_core.h"

namespace esphome::modbus_scanner {

/// A Pausable Poller: any PollingComponent on the same hub, found by codegen.
class PollingComponentPoller : public modbus_scanner_core::Poller {
 public:
  explicit PollingComponentPoller(PollingComponent *component) : component_(component) {}
  void pause() override { this->component_->stop_poller(); }
  void resume() override { this->component_->start_poller(); }

 protected:
  PollingComponent *component_;
};

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
  void clear_queue_for_address(uint8_t address) override { this->parent_->clear_tx_queue_for_address(address); }

  /// Codegen passes the hub UART's YAML serial parameters, reported in the bus's info entry.
  void set_serial(uint32_t baud_rate, const char *parity, uint8_t stop_bits) {
    this->core_.set_serial(baud_rate, parity, stop_bits);
  }

  /// Codegen emits one call per Pausable Poller, in stable table order.
  void add_poller(const char *name, uint8_t address, PollingComponent *component) {
    this->pollers_.push_back(std::make_unique<PollingComponentPoller>(component));
    this->core_.add_poller(name, address, this->pollers_.back().get());
  }

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
  std::vector<std::unique_ptr<PollingComponentPoller>> pollers_;
};

/// The Gateway, one per node: registers the v2 probe and release actions, owns the info/result/lease
/// text sensors and runs each Bus's lease recovery from loop().
class ModbusScannerGateway : public Component,
                             public api::CustomAPIDevice,
                             public modbus_scanner_core::Clock,
                             public modbus_scanner_core::ResultSink {
 public:
  void setup() override;
  void loop() override;
  void dump_config() override;

  void set_info_sensor(text_sensor::TextSensor *sensor) { this->info_sensor_ = sensor; }
  void set_result_sensor(text_sensor::TextSensor *sensor) { this->result_sensor_ = sensor; }
  void set_lease_sensor(text_sensor::TextSensor *sensor) { this->lease_sensor_ = sensor; }
  void add_bus(ModbusScannerBus *bus) { this->core_.add_bus(&bus->core()); }

  uint32_t now_ms() override;
  void publish_result(const std::string &json) override;
  void publish_lease(const std::string &json) override;

  void on_probe(std::string request_id, std::string bus, int32_t slave, int32_t function_code, int32_t reg,
                int32_t count, int32_t timeout_ms, std::string scan_id, std::string pause_pollers);
  void on_release(std::string bus, std::string scan_id);

 protected:
  modbus_scanner_core::Gateway core_{*this, *this};
  text_sensor::TextSensor *info_sensor_{nullptr};
  text_sensor::TextSensor *result_sensor_{nullptr};
  text_sensor::TextSensor *lease_sensor_{nullptr};
};

}  // namespace esphome::modbus_scanner
