#pragma once
#include "protocol.h"
#include "wifi_reset.h"
#include "scanner.h"
#include "esphome/components/button/button.h"
#include "esphome/core/component.h"
#include "esphome/core/preferences.h"
#include "esphome/components/climate/climate.h"
#include "esphome/components/modbus/modbus.h"
#include "esphome/components/number/number.h"
#include "esphome/components/switch/switch.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/components/text_sensor/text_sensor.h"

namespace esphome::guanjie {
class GuanjieClimate;
class AddressNumber : public number::Number {
 public:
  void set_owner(GuanjieClimate *owner) { owner_=owner; }
 protected:
  void control(float value) override;
  GuanjieClimate *owner_{nullptr};
};
class FunctionSwitch : public switch_::Switch {
 public:
  void configure(GuanjieClimate *owner, bool continuous) { owner_=owner; continuous_=continuous; }
 protected:
  void write_state(bool value) override;
  GuanjieClimate *owner_{nullptr};
  bool continuous_{false};
};
class ForgetWifiButton : public button::Button {
 public:
  void set_owner(GuanjieClimate *owner) { owner_=owner; }
 protected:
  void press_action() override;
  GuanjieClimate *owner_{nullptr};
};
class GuanjieClimate : public Component, public climate::Climate, public modbus::ModbusClientDevice {
 public:
  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::DATA; }
  void set_address_number(AddressNumber *p) { address_number_=p;p->set_owner(this); }
  void set_air_switch(FunctionSwitch *p) { air_=p;p->configure(this,false); }
  void set_continuous_switch(FunctionSwitch *p) { continuous_=p;p->configure(this,true); }
  void set_online_sensor(binary_sensor::BinarySensor *p) { online_=p; }
  void set_status_sensor(text_sensor::TextSensor *p) { status_=p; }
  void set_result_sensor(text_sensor::TextSensor *p) { result_=p; }
  void set_active_address_sensor(sensor::Sensor *p) { active_address_=p; }
  void set_value_sensor(uint8_t index, sensor::Sensor *p) { sensors_[index]=p; }
  void set_flag_sensor(uint16_t mask,binary_sensor::BinarySensor *p) { flags_.push_back({mask,p}); }
  void set_forget_wifi_button(ForgetWifiButton *p) {p->set_owner(this);}
  void set_scanner_result(text_sensor::TextSensor *p) { scanner_result_=p; }
  void scanner_probe(const std::string &request_id, int slave, int reg);
  void request_wifi_reset();
  void request_address(float value);
  void request_function(bool continuous,bool value);
  void on_response(std::span<const uint8_t> request, std::span<const uint8_t> response) override;
  void on_error(std::span<const uint8_t> request, modbus::ExceptionCode error) override;
  bool on_no_response(std::span<const uint8_t> request) override;
  void on_not_sent(std::span<const uint8_t> request) override;
 protected:
  climate::ClimateTraits traits() override;
  void control(const climate::ClimateCall &call) override;
  void publish_();
  void scanner_publish_(const std::string &id, int slave, int reg,
                        const char *outcome, uint32_t latency, uint16_t value=0, uint8_t exception=0);
  Scanner scanner_;
  text_sensor::TextSensor *scanner_result_{nullptr};
  Protocol protocol_;
  ESPPreferenceObject preference_;
  AddressNumber *address_number_{nullptr};
  FunctionSwitch *air_{nullptr},*continuous_{nullptr};
  binary_sensor::BinarySensor *online_{nullptr};
  text_sensor::TextSensor *status_{nullptr},*result_{nullptr};
  sensor::Sensor *active_address_{nullptr};
  std::array<sensor::Sensor *,13> sensors_{};
  struct Flag {uint16_t mask;binary_sensor::BinarySensor *sensor;};
  std::vector<Flag> flags_;
  bool published_climate_{false}, wifi_reset_requested_{false};
};
}
