#include "guanjie.h"
#include "esphome/core/log.h"
#include "esphome/core/application.h"
#include "nvs.h"

namespace esphome::guanjie {
static const char *const TAG="guanjie";
void AddressNumber::control(float value) { owner_->request_address(value); }
void FunctionSwitch::write_state(bool value) { owner_->request_function(continuous_,value); }
void ForgetWifiButton::press_action() { owner_->request_wifi_reset(); }
class WifiPreferenceStore {
 public:
  bool flush() {return global_preferences->sync();}
  bool open() {return nvs_open("esphome",NVS_READWRITE,&handle_)==ESP_OK;}
  bool erase_wifi(const char *key) {auto e=nvs_erase_key(handle_,key);return e==ESP_OK || e==ESP_ERR_NVS_NOT_FOUND;}
  bool commit() {return nvs_commit(handle_)==ESP_OK;}
  void close() {nvs_close(handle_);}
 private:
  nvs_handle_t handle_{};
};
void GuanjieClimate::request_wifi_reset() {
  if(scanner_.busy())return;
  if(wifi_reset_requested_)return;
  wifi_reset_requested_=true;protocol_.pause_for_maintenance();
}
void GuanjieClimate::setup() {
  // Dedicated versioned preference key; never restore climate control settings on boot.
  preference_=global_preferences->make_preference<uint8_t>(0x474A0001);
  uint8_t address=1;
  if (!preference_.load(&address) || !valid_address(address)) address=1;
  protocol_.requested=protocol_.active=address;
  this->set_address(address);
  address_number_->publish_state(address);
  current_temperature=NAN;current_humidity=NAN;target_humidity=NAN;target_temperature=NAN;
  publish_();
}
void GuanjieClimate::dump_config() {
  LOG_CLIMATE("", "Guanjie IN-D17", this);
  ESP_LOGCONFIG(TAG,"FC03/FC06 only; dynamic slave 1-32; boot never writes; poll freshness 15s");
}
climate::ClimateTraits GuanjieClimate::traits() {
  climate::ClimateTraits t;
  t.set_supported_modes({climate::CLIMATE_MODE_OFF,climate::CLIMATE_MODE_DRY,climate::CLIMATE_MODE_FAN_ONLY});
  t.set_supported_fan_modes({climate::CLIMATE_FAN_LOW,climate::CLIMATE_FAN_MEDIUM,climate::CLIMATE_FAN_HIGH});
  t.set_feature_flags(climate::CLIMATE_SUPPORTS_CURRENT_TEMPERATURE |
      climate::CLIMATE_SUPPORTS_TARGET_HUMIDITY | climate::CLIMATE_SUPPORTS_ACTION);
  t.set_visual_min_humidity(20);t.set_visual_max_humidity(90);
  return t;
}
void GuanjieClimate::loop() {
  const uint32_t now=millis();
  protocol_.expire(now);
  if(wifi_reset_requested_ && !protocol_.in_flight) {
    WifiPreferenceStore store;
    auto result=forget_wifi_credentials(store);
    wifi_reset_requested_=false;
    if(result==ForgetResult::OK) {
      ESP_LOGI(TAG,"WiFi credentials forgotten; rebooting to provisioning AP; other preferences retained");
      App.safe_reboot();
      return;
    }
    ESP_LOGE(TAG,"WiFi-only reset failed at stage %u; not rebooting",static_cast<unsigned>(result));
    protocol_.resume_after_maintenance_failure();
  }
  if (scanner_.busy()) {
    if (scanner_.should_send(now,protocol_.in_flight)) {
      this->set_address(scanner_.slave);
      if (!this->read_holding_registers(scanner_.reg,1))
        scanner_.finish("gateway_error",now);
    }
    if (scanner_.can_resume(now)) {
      this->set_address(protocol_.active);
      scanner_publish_(scanner_.request_id,scanner_.slave,scanner_.reg,
                       scanner_.outcome,scanner_.latency,scanner_.value,scanner_.exception);
      scanner_.released();
    }
    if (protocol_.dirty) publish_();
    return;
  }
  Transaction tx;
  if (protocol_.next(now,tx)) {
    // Address changes only with no transaction in flight. The native hub snapshots it in its frame.
    this->set_address(tx.slave);
    bool accepted=tx.function==3 ? this->read_holding_registers(tx.reg,1) : this->write_single_register(tx.reg,tx.value);
    if (!accepted) protocol_.failure(now);
  }
  if (protocol_.dirty) publish_();
}
void GuanjieClimate::on_response(std::span<const uint8_t>,std::span<const uint8_t> response) {
  if (scanner_.phase==Scanner::Phase::IN_FLIGHT) {
    if(response.size()==4 && response[0]==3 && response[1]==2)
      scanner_.finish("responded",millis(),static_cast<uint16_t>((response[2]<<8)|response[3]));
    else scanner_.finish("gateway_error",millis());
    return;
  }
  protocol_.response(response.data(),response.size(),millis());
}
void GuanjieClimate::on_error(std::span<const uint8_t>,modbus::ExceptionCode error) {
  if (scanner_.phase==Scanner::Phase::IN_FLIGHT) {
    scanner_.finish("modbus_exception",millis(),0,static_cast<uint8_t>(error));return;
  }
  ESP_LOGW(TAG,"Modbus exception %u",static_cast<unsigned>(error));protocol_.failure(millis());
}
bool GuanjieClimate::on_no_response(std::span<const uint8_t>) {
  if (scanner_.phase==Scanner::Phase::IN_FLIGHT) scanner_.finish("timeout",millis());
  else protocol_.failure(millis());
  return false;
}
void GuanjieClimate::on_not_sent(std::span<const uint8_t>) {
  if (scanner_.phase==Scanner::Phase::IN_FLIGHT) scanner_.finish("gateway_error",millis());
  else protocol_.failure(millis());
}
void GuanjieClimate::scanner_publish_(const std::string &id,int slave,int reg,
    const char *outcome,uint32_t latency,uint16_t value,uint8_t exception) {
  if(!scanner_result_ || !Scanner::valid_id(id)) return;
  // id is exactly 32 lowercase hex characters; no caller-supplied JSON text.
  char buffer[256];
  snprintf(buffer,sizeof(buffer),
    "{\"v\":1,\"id\":\"%s\",\"slave\":%d,\"reg\":%d,\"outcome\":\"%s\",\"latency_ms\":%lu,\"value\":%u,\"exception\":%u}",
    id.c_str(),slave,reg,outcome,static_cast<unsigned long>(latency),value,exception);
  scanner_result_->publish_state(buffer);
}
void GuanjieClimate::scanner_probe(const std::string &id,int slave,int reg) {
  if (!Scanner::valid_id(id)) return;
  if (wifi_reset_requested_ || protocol_.maintenance || protocol_.command_pending() ||
      !scanner_.begin(id,slave,reg)) {
    scanner_publish_(id,slave,reg,"gateway_error",0);
  }
}
void GuanjieClimate::request_address(float value) {
  if(scanner_.busy()) {protocol_.result="Address change rejected during scan";protocol_.dirty=true;return;}
  if(protocol_.maintenance) {protocol_.result="Address change rejected during WiFi reset";protocol_.dirty=true;return;}
  if (!valid_address(value)) {
    protocol_.change_address(value,millis());return;
  }
  if (static_cast<uint8_t>(value)==protocol_.requested) return;
  uint8_t desired=static_cast<uint8_t>(value);
  if (!preference_.save(&desired) || !global_preferences->sync()) {
    // Do not leave a failed requested value pending for a later background preference flush.
    uint8_t previous=protocol_.requested;
    preference_.save(&previous);
    global_preferences->sync();
    protocol_.result="Address not changed: flash save failed";protocol_.dirty=true;return;
  }
  protocol_.change_address(value,millis());address_number_->publish_state(value);
}
void GuanjieClimate::request_function(bool continuous,bool value) {
  if(scanner_.busy()) {protocol_.result="Control rejected during scan";protocol_.dirty=true;return;}
  Write command;
  if (continuous) {
    if (!value && !valid_humidity(protocol_.last_humidity)) {
      protocol_.result="Choose target humidity first; no setpoint known for this slave";protocol_.dirty=true;return;
    }
    command={0x6203,static_cast<uint16_t>(value?0:protocol_.last_humidity)};
  } else command={0x6206,static_cast<uint16_t>(value?1:0)};
  protocol_.submit(&command,1,millis());
}
void GuanjieClimate::control(const climate::ClimateCall &call) {
  if(scanner_.busy()) {protocol_.result="Control rejected during scan";protocol_.dirty=true;return;}
  if(call.get_mode().has_value() && *call.get_mode()==climate::CLIMATE_MODE_OFF) {
    Write off{0x6201,0};protocol_.submit(&off,1,millis());return;
  }
  std::array<Write,4> commands;size_t n=0;
  // ESPHome/HA generic climate UIs may offer temperature: it is never a supported machine command.
  if (call.get_target_temperature().has_value() || call.get_target_temperature_low().has_value() ||
      call.get_target_temperature_high().has_value()) {
    protocol_.result="Rejected: IN-D17 has humidity control, not target temperature";protocol_.dirty=true;return;
  }
  if (call.get_target_humidity().has_value()) {
    float h=*call.get_target_humidity();
    if (!valid_humidity(h)) { protocol_.result="Rejected: humidity must be integer 20-90";protocol_.dirty=true;return; }
    commands[n++]={0x6203,static_cast<uint16_t>(h)};
  }
  if (call.get_fan_mode().has_value()) {
    auto fan=*call.get_fan_mode();uint16_t value;
    if(fan==climate::CLIMATE_FAN_LOW)value=1;
    else if(fan==climate::CLIMATE_FAN_MEDIUM)value=2;
    else if(fan==climate::CLIMATE_FAN_HIGH)value=3;
    else {protocol_.result="Rejected: unsupported fan mode";protocol_.dirty=true;return;}
    commands[n++]={0x6202,value};
  }
  if(call.get_mode().has_value()) {
    auto mode=*call.get_mode();
    if(mode==climate::CLIMATE_MODE_DRY || mode==climate::CLIMATE_MODE_FAN_ONLY) {
      commands[n++]={0x6205,static_cast<uint16_t>(mode==climate::CLIMATE_MODE_DRY)};
      commands[n++]={0x6201,1};
    } else {protocol_.result="Rejected: unsupported HVAC mode";protocol_.dirty=true;return;}
  }
  if(n) protocol_.submit(commands.data(),n,millis());
}
void GuanjieClimate::publish_() {
  protocol_.dirty=false;
  const bool ready=protocol_.ready(millis());
  online_->publish_state(ready);
  active_address_->publish_state(protocol_.active);
  status_->publish_state(protocol_.requested!=protocol_.active ? "Switching" : ready ? "Online" : "Offline / acquiring");
  result_->publish_state(protocol_.result);
  for(size_t i=0;i<sensors_.size();++i) if(sensors_[i]) {
    float v=protocol_.valid[i]?static_cast<float>(protocol_.values[i]):NAN;
    if(i==6 && protocol_.valid[i])v=temperature1(protocol_.values[i]);
    sensors_[i]->publish_state(v);
  }
  for(auto &flag:flags_) {
    if(protocol_.valid[5])flag.sensor->publish_state((protocol_.values[5]&flag.mask)!=0);
    else flag.sensor->invalidate_state();
  }
  current_temperature=protocol_.valid[6]?temperature1(protocol_.values[6]):NAN;
  target_humidity=protocol_.valid[2] && protocol_.values[2]!=0 ? protocol_.values[2] : NAN;
  if(protocol_.valid[4])air_->publish_state(protocol_.values[4]!=0);
  else air_->set_has_state(false); // Switch API has no unknown-state packet: see README.
  if(protocol_.valid[2])continuous_->publish_state(protocol_.values[2]==0);
  else continuous_->set_has_state(false);
  if(ready) {
    mode=protocol_.values[0]==0?climate::CLIMATE_MODE_OFF:
        protocol_.values[3]?climate::CLIMATE_MODE_DRY:climate::CLIMATE_MODE_FAN_ONLY;
    fan_mode=protocol_.values[1]==1?climate::CLIMATE_FAN_LOW:
        protocol_.values[1]==2?climate::CLIMATE_FAN_MEDIUM:climate::CLIMATE_FAN_HIGH;
    // Physical status, not requested mode, controls action. No fabricated compressor state.
    uint16_t status=protocol_.values[5];
    action=(status&0x80)?climate::CLIMATE_ACTION_DRYING:(status&0x40)?climate::CLIMATE_ACTION_FAN:
        protocol_.values[0]?climate::CLIMATE_ACTION_IDLE:climate::CLIMATE_ACTION_OFF;
    published_climate_=true;
  }
  // There is no native "unknown HVAC mode" value. Preserve last read mode and expose online=false.
  if(published_climate_)publish_state();
}
}
