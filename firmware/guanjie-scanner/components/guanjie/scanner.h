#pragma once
#include <cstdint>
#include <string>
#include "protocol.h"

namespace esphome::guanjie {
// One bounded, read-only transaction. No persistent address changes and no
// lease requiring the network client to remain alive. Quiet intervals drain
// late frames before changing the ModbusClientDevice's temporary address.
class Scanner {
 public:
  enum class Phase { IDLE, DRAIN, QUIET, IN_FLIGHT, COOLDOWN };
  Phase phase{Phase::IDLE};
  std::string request_id;
  uint8_t slave{0};
  uint16_t reg{0}, value{0};
  uint8_t exception{0};
  uint32_t started{0}, deadline{0}, latency{0};
  const char *outcome{"gateway_error"};

  static bool valid_id(const std::string &id) {
    if (id.size()!=32) return false;
    for(char c:id) if (!((c>='0' && c<='9') || (c>='a' && c<='f'))) return false;
    return true;
  }
  bool busy() const { return phase!=Phase::IDLE; }
  bool begin(const std::string &id, int address, int address_reg) {
    if (busy() || !valid_id(id) || address<1 || address>32 ||
        address_reg<0 || address_reg>65535 || register_index(address_reg)<0) return false;
    request_id=id;slave=address;reg=address_reg;value=0;exception=0;latency=0;
    outcome="gateway_error";phase=Phase::DRAIN;return true;
  }
  bool should_send(uint32_t now, bool normal_in_flight) {
    if (phase==Phase::DRAIN && !normal_in_flight) {
      phase=Phase::QUIET;deadline=now+1000;
    }
    if (phase==Phase::QUIET && static_cast<int32_t>(now-deadline)>=0) {
      phase=Phase::IN_FLIGHT;started=now;return true;
    }
    return false;
  }
  void finish(const char *status, uint32_t now, uint16_t data=0, uint8_t error=0) {
    if (phase!=Phase::IN_FLIGHT) return;
    outcome=status;value=data;exception=error;latency=now-started;
    phase=Phase::COOLDOWN;deadline=now+1000;
  }
  bool can_resume(uint32_t now) const {
    return phase==Phase::COOLDOWN && static_cast<int32_t>(now-deadline)>=0;
  }
  void released() { phase=Phase::IDLE; }
};
}
