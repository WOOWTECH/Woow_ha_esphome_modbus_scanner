#pragma once
namespace esphome::guanjie {
// ESPHome2026.9.0 AP-only WiFi uses preference type88491487; ESP32 stores decimal keys.
inline constexpr const char *WIFI_PREFERENCE_KEY="88491487";
enum class ForgetResult { OK, FLUSH_FAILED, OPEN_FAILED, ERASE_FAILED, COMMIT_FAILED };
// Narrow backend interface permits host fault injection without touching a real NVS device.
// erase_wifi returns true for a missing key (already forgotten); no namespace erase exists here.
template<class Store> ForgetResult forget_wifi_credentials(Store &store) {
  if(!store.flush())return ForgetResult::FLUSH_FAILED;
  if(!store.open())return ForgetResult::OPEN_FAILED;
  if(!store.erase_wifi(WIFI_PREFERENCE_KEY)) {store.close();return ForgetResult::ERASE_FAILED;}
  if(!store.commit()) {store.close();return ForgetResult::COMMIT_FAILED;}
  store.close();return ForgetResult::OK;
}
}
