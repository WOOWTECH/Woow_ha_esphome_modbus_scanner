#pragma once
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>

namespace esphome::guanjie {
// The PDF uses actual hexadecimal wire addresses, not 40001-style offsets.
inline constexpr std::array<uint16_t, 13> REGISTERS = {
    0x6201, 0x6202, 0x6203, 0x6205, 0x6206, 0x6105,
    0x6101, 0x6102, 0x6103, 0x6104, 0x6106, 0x6111, 0x6112};
struct Write { uint16_t reg; uint16_t value; };
struct Transaction { uint8_t slave; uint8_t function; uint16_t reg; uint16_t value; uint32_t epoch; };
inline bool valid_address(float x) { return std::isfinite(x) && x >= 1 && x <= 32 && std::floor(x) == x; }
inline bool valid_humidity(float x) { return std::isfinite(x) && x >= 20 && x <= 90 && std::floor(x) == x; }
inline int register_index(uint16_t r) {
  for (size_t i=0; i<REGISTERS.size(); ++i) if (REGISTERS[i]==r) return i;
  return -1;
}
inline bool valid_register(uint16_t reg, uint16_t v) {
  if (reg==0x6201 || reg==0x6205 || reg==0x6206) return v<=1;
  if (reg==0x6202) return v>=1 && v<=3;
  if (reg==0x6203) return v==0 || valid_humidity(v);
  return true;
}
inline float temperature1(uint16_t v) {
  // No negative-temperature encoding was specified. Do not invent one.
  return (v>>8)<=9 && (v&255)<=100 ? (v&255)+(v>>8)/10.0f : NAN;
}

// Transport-independent, single-flight state machine. The native Modbus hub owns CRC and timing.
class Protocol {
 public:
  uint8_t requested{1}, active{1};
  uint32_t epoch{0};
  std::array<uint16_t,13> values{};
  std::array<bool,13> valid{};
  std::array<uint32_t,13> observed{};
  bool dirty{true}, in_flight{false}, verifying{false}, maintenance{false};
  uint16_t last_humidity{0};
  const char *result{"Awaiting first read"};
  Transaction transaction{};

  bool ready(uint32_t now) const {
    if (maintenance || requested!=active) return false;
    for (size_t i=0;i<6;++i) if (!valid[i] || now-observed[i]>15000) return false;
    return true;
  }
  bool change_address(float x, uint32_t now) {
    if (!valid_address(x)) { result="Rejected: address must be integer 1-32"; dirty=true; return false; }
    if (requested==static_cast<uint8_t>(x)) return true;
    requested=static_cast<uint8_t>(x); ++epoch;
    invalidate(); last_humidity=0; count_=0; pos_=0; verifying=false;
    not_before_=now+1000; result="Switching address; writes blocked"; dirty=true;
    return true;
  }
  void invalidate() { valid.fill(false); dirty=true; }
  void pause_for_maintenance() {
    maintenance=true; ++epoch; count_=0; verifying=false; invalidate();
    result="WiFi reset pending; draining transaction";
  }
  void resume_after_maintenance_failure() {
    maintenance=false;poll_=0;invalidate();result="WiFi reset failed; credentials may need checking";
  }
  bool submit(const Write *items, size_t count, uint32_t now) {
    if (!ready(now) || count_!=0 || count==0 || count>writes_.size()) {
      result="Rejected: offline, stale state or command busy"; dirty=true; return false;
    }
    for (size_t i=0;i<count;++i) {
      if (items[i].reg<0x6201 || items[i].reg>0x6206 || items[i].reg==0x6204 ||
          !valid_register(items[i].reg,items[i].value)) {
        result="Rejected: unsupported register/value"; dirty=true; return false;
      }
    }
    for (size_t i=0;i<count;++i) writes_[i]=items[i];
    count_=count; pos_=0; result="Command pending readback"; dirty=true; return true;
  }
  bool next(uint32_t now, Transaction &out) {
    if (maintenance || in_flight || static_cast<int32_t>(now-not_before_)<0) return false;
    if (active!=requested) { active=requested; poll_=0; dirty=true; }
    if (count_ && !ready(now)) {
      count_=0; verifying=false; invalidate(); result="Aborted: state became stale";
    }
    if (count_) {
      const auto &w=writes_[pos_];
      transaction={active,static_cast<uint8_t>(verifying?3:6),w.reg,w.value,epoch};
    } else {
      transaction={active,3,REGISTERS[poll_],1,epoch};
    }
    in_flight=true; out=transaction; return true;
  }
  // Called exactly once by the transport for each terminal outcome. No write retries.
  void response(const uint8_t *pdu, size_t n, uint32_t now) {
    if (!in_flight) return;
    if (transaction.epoch!=epoch) { finish_stale(now); return; }
    if (transaction.function==6) {
      if (n!=5 || pdu[0]!=6 || word(pdu+1)!=transaction.reg || word(pdu+3)!=transaction.value) {
        failure(now); return;
      }
      in_flight=false; verifying=true; not_before_=now+150; return;
    }
    if (n!=4 || pdu[0]!=3 || pdu[1]!=2 || !valid_register(transaction.reg,word(pdu+2))) {
      failure(now); return;
    }
    const bool was_ready=ready(now);
    const uint16_t value=word(pdu+2);
    int idx=register_index(transaction.reg);
    if (idx>=0) { values[idx]=value; valid[idx]=true; observed[idx]=now; }
    if (transaction.reg==0x6203 && valid_humidity(value)) last_humidity=value;
    in_flight=false; dirty=true;
    if (!was_ready && ready(now) && !verifying) result="Read polling established";
    if (verifying) {
      if (value!=transaction.value) {
        count_=0; verifying=false; invalidate(); poll_=0;
        result="Write readback mismatch; sequence aborted"; not_before_=now+1000; return;
      }
      verifying=false;
      if (++pos_==count_) { count_=0; pos_=0; result="Write confirmed by readback"; }
      not_before_=now+150;
    } else {
      advance_poll(now);
    }
  }
  void failure(uint32_t now) {
    if (!in_flight) return;
    if (transaction.epoch!=epoch) { finish_stale(now); return; }
    in_flight=false;
    int idx=register_index(transaction.reg);
    if (count_ || idx<6) {
      count_=0; verifying=false; invalidate(); poll_=0;
      result="No valid response; writes blocked"; not_before_=now+1000;
    } else {
      // An undocumented/absent optional sensor must not starve core control polling.
      valid[idx]=false; dirty=true; advance_poll(now);
      not_before_=now+1000; // Drain delayed replies before issuing a different single-register read.
    }
  }
  void expire(uint32_t now) {
    bool stale=false;
    for(size_t i=0;i<valid.size();++i) if(valid[i] && now-observed[i]>15000) {valid[i]=false;stale=true;}
    if(stale) {dirty=true; result="Stale data; awaiting poll";}
  }
  bool command_pending() const { return count_!=0; }
 private:
  static uint16_t word(const uint8_t *p) { return static_cast<uint16_t>((p[0]<<8)|p[1]); }
  void finish_stale(uint32_t now) { in_flight=false; not_before_=now+1000; poll_=0; dirty=true; }
  void advance_poll(uint32_t now) { if (++poll_==REGISTERS.size()) {poll_=0;not_before_=now+5000;} else not_before_=now+150; }
  std::array<Write,4> writes_{};
  size_t count_{0},pos_{0},poll_{0};
  uint32_t not_before_{1000};
};
}  // namespace esphome::guanjie
