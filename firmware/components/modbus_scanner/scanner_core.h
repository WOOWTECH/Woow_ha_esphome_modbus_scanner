// Pure firmware core of the vendor-neutral modbus_scanner component (bridge protocol v2).
//
// No ESPHome headers: the hub, the clock and the result sensor are injected, so request
// validation, write refusal, hard limits, single in-flight behaviour and per-probe timeout
// handling are host-testable (firmware/tests). Every constant below mirrors the shared
// contract file custom_components/woow_esphome_modbus_scanner/modbus_scan/bridge_v2/contract.json,
// and the host tests fail if they drift apart.
#pragma once

#include <array>
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>

namespace modbus_scanner_core {

// ---- Contract constants (checked against contract.json by the host tests) ----

inline constexpr int kBridgeVersion = 2;
inline constexpr int kResultSchemaVersion = 1;
inline constexpr int kInfoSchemaVersion = 1;
inline constexpr const char *kProbeAction = "modbus_scanner_v2_probe";
inline constexpr const char *kInfoSensorName = "Modbus Scanner v2 Info";
inline constexpr const char *kResultSensorName = "Modbus Scanner v2 Result";

struct ArgSpec {
  const char *name;
  const char *type;
};
// Order matters: the ESPHome glue registers the action with exactly these argument names.
inline constexpr std::array<ArgSpec, 9> kProbeArgs{{
    {"request_id", "string"},
    {"bus", "string"},
    {"slave", "int"},
    {"function_code", "int"},
    {"register", "int"},
    {"count", "int"},
    {"timeout_ms", "int"},
    {"scan_id", "string"},
    {"pause_pollers", "string"},
}};

struct HardLimits {
  int32_t slave_min, slave_max, register_min, register_max, count_min, count_max, timeout_ms_min, timeout_ms_max;
};
inline constexpr HardLimits kLimits{1, 247, 0, 65535, 1, 4, 100, 2000};
inline constexpr std::array<int32_t, 2> kReadFunctionCodes{3, 4};
inline constexpr std::array<int32_t, 6> kWriteFunctionCodes{5, 6, 15, 16, 22, 23};
inline constexpr size_t kIdMaxLength = 32;

namespace error {
inline constexpr const char *INVALID_REQUEST_ID = "invalid_request_id";
inline constexpr const char *WRITE_FUNCTION_REFUSED = "write_function_refused";
inline constexpr const char *UNKNOWN_BUS = "unknown_bus";
inline constexpr const char *INVALID_SLAVE = "invalid_slave";
inline constexpr const char *UNSUPPORTED_FUNCTION_CODE = "unsupported_function_code";
inline constexpr const char *INVALID_REGISTER = "invalid_register";
inline constexpr const char *INVALID_COUNT = "invalid_count";
inline constexpr const char *INVALID_TIMEOUT = "invalid_timeout";
inline constexpr const char *INVALID_SCAN_ID = "invalid_scan_id";
inline constexpr const char *INVALID_POLLER = "invalid_poller";
inline constexpr const char *BUSY = "busy";
inline constexpr const char *QUEUE_REJECTED = "queue_rejected";
inline constexpr const char *NOT_SENT = "not_sent";
inline constexpr const char *INVALID_RESPONSE = "invalid_response";
}  // namespace error

inline constexpr std::array<const char *, 14> kErrorCodes{
    error::INVALID_REQUEST_ID, error::WRITE_FUNCTION_REFUSED, error::UNKNOWN_BUS,     error::INVALID_SLAVE,
    error::UNSUPPORTED_FUNCTION_CODE, error::INVALID_REGISTER, error::INVALID_COUNT,  error::INVALID_TIMEOUT,
    error::INVALID_SCAN_ID,          error::INVALID_POLLER,   error::BUSY,           error::QUEUE_REJECTED,
    error::NOT_SENT,                 error::INVALID_RESPONSE,
};

// ---- Injected collaborators ----

class Clock {
 public:
  virtual ~Clock() = default;
  virtual uint32_t now_ms() = 0;
};

/// Publishes one compact JSON result on the result text sensor.
class ResultSink {
 public:
  virtual ~ResultSink() = default;
  virtual void publish_result(const std::string &json) = 0;
};

/// One Modbus client hub as seen by one scanner Bus.
class BusPort {
 public:
  virtual ~BusPort() = default;
  /// Queue a request PDU (function code + data, no address/CRC) for `slave`. False means the hub
  /// refused it and no callback will follow; true means exactly one terminal callback follows.
  virtual bool queue_request(uint8_t slave, const uint8_t *pdu, size_t len) = 0;
  /// The hub-wide wait for a reply (ESPHome `modbus: send_wait_time`).
  virtual void set_send_wait_ms(uint16_t ms) = 0;
};

struct ProbeRequest {
  std::string request_id;
  std::string bus;
  int32_t slave{0};
  int32_t function_code{0};
  int32_t reg{0};
  int32_t count{0};
  int32_t timeout_ms{0};
  std::string scan_id;
  std::string pause_pollers;
};

// ---- Helpers ----

inline bool valid_id(const std::string &id) {
  if (id.empty() || id.size() > kIdMaxLength)
    return false;
  for (char c : id) {
    bool ok = (c >= '0' && c <= '9') || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_' || c == '-';
    if (!ok)
      return false;
  }
  return true;
}

inline void append_json_string(std::string &out, const std::string &value) {
  out += '"';
  for (unsigned char c : value) {
    if (c == '"' || c == '\\') {
      out += '\\';
      out += static_cast<char>(c);
    } else if (c < 0x20) {
      char buf[8];
      std::snprintf(buf, sizeof(buf), "\\u%04x", c);
      out += buf;
    } else {
      out += static_cast<char>(c);
    }
  }
  out += '"';
}

template<size_t N> inline bool contains(const std::array<int32_t, N> &values, int32_t value) {
  for (int32_t v : values)
    if (v == value)
      return true;
  return false;
}

/// Parse "" or "0,2,5" against the bus's Pausable Poller table size.
inline bool valid_poller_list(const std::string &list, size_t poller_count) {
  if (list.empty())
    return true;
  size_t i = 0;
  while (i <= list.size()) {
    size_t start = i;
    uint32_t value = 0;
    while (i < list.size() && list[i] >= '0' && list[i] <= '9') {
      value = value * 10 + static_cast<uint32_t>(list[i] - '0');
      if (value > 1000)
        return false;
      i++;
    }
    if (i == start || value >= poller_count)
      return false;
    if (i == list.size())
      return true;
    if (list[i] != ',')
      return false;
    i++;
  }
  return false;
}

// ---- One scanner Bus (one per Modbus hub) ----

class Bus {
 public:
  /// `normal_send_wait_ms` is the hub's YAML send_wait_time, restored after every probe.
  Bus(std::string name, BusPort &port, uint16_t normal_send_wait_ms, size_t poller_count = 0)
      : name_(std::move(name)), port_(port), normal_send_wait_ms_(normal_send_wait_ms), poller_count_(poller_count) {}

  const std::string &name() const { return this->name_; }
  size_t poller_count() const { return this->poller_count_; }
  bool busy() const { return this->in_flight_; }

  // Hub callbacks for this Bus's own probe frame. Calls while idle are ignored.
  void on_sent() {
    if (!this->in_flight_ || this->sent_)
      return;
    this->sent_ = true;
    this->sent_at_ = this->clock_->now_ms();
    // Only one frame is in flight per hub, so the per-probe timeout affects only this probe.
    this->port_.set_send_wait_ms(static_cast<uint16_t>(this->request_.timeout_ms));
  }
  void on_response(const uint8_t *pdu, size_t len) {
    if (!this->in_flight_)
      return;
    const size_t count = static_cast<size_t>(this->request_.count);
    if (len != 2 + 2 * count || pdu[0] != static_cast<uint8_t>(this->request_.function_code) || pdu[1] != 2 * count) {
      this->finish_("gateway_error", "\"error\":\"" + std::string(error::INVALID_RESPONSE) + "\"");
      return;
    }
    std::string values = "\"values\":[";
    for (size_t i = 0; i < count; i++) {
      if (i)
        values += ',';
      values += std::to_string((static_cast<uint16_t>(pdu[2 + 2 * i]) << 8) | pdu[3 + 2 * i]);
    }
    values += ']';
    this->finish_("responded", values);
  }
  void on_exception(uint8_t code) {
    if (this->in_flight_)
      this->finish_("modbus_exception", "\"exception\":" + std::to_string(code));
  }
  void on_no_response() {
    if (this->in_flight_)
      this->finish_("timeout", "");
  }
  void on_not_sent() {
    if (this->in_flight_)
      this->finish_("gateway_error", "\"error\":\"" + std::string(error::NOT_SENT) + "\"");
  }

  // Called by the Bridge only, after validation.
  void attach(Clock *clock, ResultSink *sink) {
    this->clock_ = clock;
    this->sink_ = sink;
  }
  /// Returns nullptr when queued, else the rejection error code.
  const char *start(const ProbeRequest &request) {
    if (this->in_flight_)
      return error::BUSY;
    const uint8_t pdu[5] = {
        static_cast<uint8_t>(request.function_code), static_cast<uint8_t>(request.reg >> 8),
        static_cast<uint8_t>(request.reg & 0xFF),    static_cast<uint8_t>(request.count >> 8),
        static_cast<uint8_t>(request.count & 0xFF),
    };
    this->request_ = request;
    this->in_flight_ = true;
    this->sent_ = false;
    if (!this->port_.queue_request(static_cast<uint8_t>(request.slave), pdu, sizeof(pdu))) {
      this->in_flight_ = false;
      return error::QUEUE_REJECTED;
    }
    return nullptr;
  }

 private:
  void finish_(const char *outcome, const std::string &outcome_fields) {
    uint32_t latency = this->sent_ ? this->clock_->now_ms() - this->sent_at_ : 0;
    if (this->sent_)
      this->port_.set_send_wait_ms(this->normal_send_wait_ms_);
    this->in_flight_ = false;
    this->sent_ = false;
    this->sink_->publish_result(result_json(this->request_, outcome, latency, outcome_fields));
  }

 public:
  static std::string result_json(const ProbeRequest &r, const char *outcome, uint32_t latency_ms,
                                 const std::string &outcome_fields) {
    std::string out = "{\"v\":" + std::to_string(kResultSchemaVersion) + ",\"id\":";
    append_json_string(out, r.request_id);
    out += ",\"bus\":";
    append_json_string(out, r.bus);
    out += ",\"slave\":" + std::to_string(r.slave) + ",\"fc\":" + std::to_string(r.function_code) +
           ",\"reg\":" + std::to_string(r.reg) + ",\"count\":" + std::to_string(r.count) + ",\"outcome\":\"" + outcome +
           "\",\"latency_ms\":" + std::to_string(latency_ms);
    if (!outcome_fields.empty())
      out += "," + outcome_fields;
    out += '}';
    return out;
  }

 private:
  std::string name_;
  BusPort &port_;
  uint16_t normal_send_wait_ms_;
  size_t poller_count_;
  Clock *clock_{nullptr};
  ResultSink *sink_{nullptr};
  ProbeRequest request_;
  bool in_flight_{false};
  bool sent_{false};
  uint32_t sent_at_{0};
};

// ---- Node-wide bridge: the probe action and the info/result sensors, routing by bus ----

class Bridge {
 public:
  Bridge(Clock &clock, ResultSink &sink) : clock_(clock), sink_(sink) {}

  void add_bus(Bus *bus) {
    bus->attach(&this->clock_, &this->sink_);
    this->buses_.push_back(bus);
  }
  const std::vector<Bus *> &buses() const { return this->buses_; }

  /// The `modbus_scanner_v2_probe` action. Publishes exactly one result per correlatable request:
  /// a rejection immediately, otherwise when the hub reports the probe's terminal callback.
  void probe(const ProbeRequest &request) {
    if (!valid_id(request.request_id))
      return;  // Cannot be correlated by HA, so publishing would only add noise.
    Bus *bus = nullptr;
    const char *rejection = this->validate_(request, bus);
    if (rejection == nullptr)
      rejection = bus->start(request);
    if (rejection != nullptr)
      this->sink_.publish_result(
          Bus::result_json(request, "gateway_error", 0, "\"error\":\"" + std::string(rejection) + "\""));
  }

  std::string info_json() const {
    std::string out = "{\"v\":" + std::to_string(kInfoSchemaVersion) +
                      ",\"bridge\":" + std::to_string(kBridgeVersion) + ",\"buses\":[";
    for (size_t i = 0; i < this->buses_.size(); i++) {
      if (i)
        out += ',';
      out += "{\"bus\":";
      append_json_string(out, this->buses_[i]->name());
      out += ",\"pollers\":[]}";
    }
    out += "]}";
    return out;
  }

 private:
  const char *validate_(const ProbeRequest &r, Bus *&bus) {
    // Write function codes are refused before anything else, whatever HA sends.
    if (contains(kWriteFunctionCodes, r.function_code))
      return error::WRITE_FUNCTION_REFUSED;
    for (Bus *candidate : this->buses_)
      if (candidate->name() == r.bus)
        bus = candidate;
    if (bus == nullptr)
      return error::UNKNOWN_BUS;
    if (r.slave < kLimits.slave_min || r.slave > kLimits.slave_max)
      return error::INVALID_SLAVE;
    if (!contains(kReadFunctionCodes, r.function_code))
      return error::UNSUPPORTED_FUNCTION_CODE;
    if (r.reg < kLimits.register_min || r.reg > kLimits.register_max)
      return error::INVALID_REGISTER;
    if (r.count < kLimits.count_min || r.count > kLimits.count_max)
      return error::INVALID_COUNT;
    if (r.reg + r.count - 1 > kLimits.register_max)
      return error::INVALID_REGISTER;
    if (r.timeout_ms < kLimits.timeout_ms_min || r.timeout_ms > kLimits.timeout_ms_max)
      return error::INVALID_TIMEOUT;
    if (!valid_id(r.scan_id))
      return error::INVALID_SCAN_ID;
    if (!valid_poller_list(r.pause_pollers, bus->poller_count()))
      return error::INVALID_POLLER;
    return nullptr;
  }

  Clock &clock_;
  ResultSink &sink_;
  std::vector<Bus *> buses_;
};

}  // namespace modbus_scanner_core
