// Pure firmware core of the vendor-neutral modbus_scanner component (bridge protocol v2).
//
// No ESPHome headers: the hub, the clock, the Pausable Pollers and the sensors are injected, so
// request validation, write refusal, hard limits, single in-flight behaviour, per-probe timeout
// handling and the Scan Lease (pause, renew, idle expiry, hard limit, release, resume) are
// host-testable (firmware/tests). Every constant below mirrors the shared
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
inline constexpr const char *kLeaseSensorName = "Modbus Scanner v2 Lease";
inline constexpr const char *kReleaseAction = "modbus_scanner_v2_release";
inline constexpr int kLeaseSchemaVersion = 1;
inline constexpr uint32_t kLeaseIdleMs = 5000;
inline constexpr uint32_t kLeaseHardLimitMs = 600000;

namespace lease_end {
inline constexpr const char *RELEASED = "released";
inline constexpr const char *IDLE = "idle";
inline constexpr const char *HARD_LIMIT = "hard_limit";
inline constexpr const char *SUPERSEDED = "superseded";
}  // namespace lease_end
inline constexpr std::array<const char *, 4> kLeaseEndReasons{lease_end::RELEASED, lease_end::IDLE,
                                                              lease_end::HARD_LIMIT, lease_end::SUPERSEDED};

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
inline constexpr std::array<ArgSpec, 2> kReleaseArgs{{
    {"bus", "string"},
    {"scan_id", "string"},
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

/// Publishes compact JSON on a pair of result and lease text sensors: the Gateway's shared pair,
/// or one Bus's own pair.
class ResultSink {
 public:
  virtual ~ResultSink() = default;
  virtual void publish_result(const std::string &json) = 0;
  virtual void publish_lease(const std::string &json) = 0;
};

/// One Pausable Poller: a component polling the same hub (ESPHome PollingComponent).
class Poller {
 public:
  virtual ~Poller() = default;
  virtual void pause() = 0;   // stop_poller()
  virtual void resume() = 0;  // start_poller()
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
  /// Drop every unsent frame the hub holds for `address` (ESPHome clear_tx_queue_for_address).
  virtual void clear_queue_for_address(uint8_t address) = 0;
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

/// Indices of a list already accepted by valid_poller_list, in order, without duplicates.
inline std::vector<size_t> parse_poller_list(const std::string &list) {
  std::vector<size_t> out;
  size_t value = 0;
  bool digits = false;
  for (size_t i = 0; i <= list.size(); i++) {
    if (i < list.size() && list[i] != ',') {
      value = value * 10 + static_cast<size_t>(list[i] - '0');
      digits = true;
      continue;
    }
    bool seen = false;
    for (size_t v : out)
      seen = seen || v == value;
    if (digits && !seen)
      out.push_back(value);
    value = 0;
    digits = false;
  }
  return out;
}

inline std::string json_int_array(const std::vector<size_t> &values) {
  std::string out = "[";
  for (size_t i = 0; i < values.size(); i++) {
    if (i)
      out += ',';
    out += std::to_string(values[i]);
  }
  return out + "]";
}

// ---- One scanner Bus (one per Modbus hub) ----

class Bus {
 public:
  /// `normal_send_wait_ms` is the hub's YAML send_wait_time, restored after every probe.
  Bus(std::string name, BusPort &port, uint16_t normal_send_wait_ms)
      : name_(std::move(name)), port_(port), normal_send_wait_ms_(normal_send_wait_ms) {}

  const std::string &name() const { return this->name_; }
  size_t poller_count() const { return this->pollers_.size(); }
  bool busy() const { return this->in_flight_; }
  bool lease_active() const { return this->lease_active_; }

  /// Register the next Pausable Poller; its index is its position in registration order.
  /// `address` is its slave address, or 0 when it has none (its frames are then not cleared).
  void add_poller(std::string name, uint8_t address, Poller *poller) {
    this->pollers_.push_back({std::move(name), address, poller});
  }

  /// The hub UART's serial parameters from YAML, reported in this bus's info entry.
  /// `parity` is one of the contract's serial_parities ("NONE", "EVEN", "ODD").
  void set_serial(uint32_t baud_rate, const char *parity, uint8_t stop_bits) {
    this->serial_ = "{\"baud_rate\":" + std::to_string(baud_rate) + ",\"parity\":";
    append_json_string(this->serial_, parity);
    this->serial_ += ",\"stop_bits\":" + std::to_string(stop_bits) + "}";
  }

  /// This Bus's own Result and Lease text sensors and their exact entity names, reported in its
  /// info entry (ADR 0010). Each result and lease message of the Bus is published there and
  /// mirrored to the Gateway's shared sensors, which older HA versions read.
  void set_own_sensors(ResultSink *sink, std::string result_sensor, std::string lease_sensor) {
    this->own_sink_ = sink;
    this->result_sensor_ = std::move(result_sensor);
    this->lease_sensor_ = std::move(lease_sensor);
  }

  /// This bus's info entry: its name, serial parameters (when known), own sensor names (when it
  /// has them) and Pausable Poller table.
  std::string info_json() const {
    std::string out = "{\"bus\":";
    append_json_string(out, this->name_);
    if (!this->serial_.empty())
      out += ",\"serial\":" + this->serial_;
    if (this->own_sink_ != nullptr) {
      out += ",\"result_sensor\":";
      append_json_string(out, this->result_sensor_);
      out += ",\"lease_sensor\":";
      append_json_string(out, this->lease_sensor_);
    }
    out += ",\"pollers\":[";
    for (size_t i = 0; i < this->pollers_.size(); i++) {
      if (i)
        out += ',';
      out += "{\"index\":" + std::to_string(i) + ",\"name\":";
      append_json_string(out, this->pollers_[i].name);
      out += ",\"address\":" + std::to_string(this->pollers_[i].address) + "}";
    }
    return out + "]}";
  }

  /// Gateway-owned recovery: end the lease on idle expiry or at the hard limit.
  void loop() {
    if (!this->lease_active_)
      return;
    const uint32_t now = this->clock_->now_ms();
    if (now - this->lease_started_ >= kLeaseHardLimitMs)
      this->end_lease_(lease_end::HARD_LIMIT);
    else if (!this->in_flight_ && now - this->lease_touched_ >= kLeaseIdleMs)
      this->end_lease_(lease_end::IDLE);
  }

  /// The release action: end this scan's lease now. Always answers with the scan's lease state.
  void release(const std::string &scan_id) {
    if (this->lease_active_ && scan_id == this->lease_scan_) {
      this->end_lease_(lease_end::RELEASED);
      return;
    }
    if (!this->lease_scan_.empty() && scan_id == this->lease_scan_)
      this->publish_lease_("ended", this->ended_reason_);
    else
      this->publish_lease(lease_json(this->name_, scan_id, "none", {}, nullptr));
  }

  /// Publish a result of this Bus on its own sensor (if any), then on the shared one.
  void publish_result(const std::string &json) {
    if (this->own_sink_ != nullptr)
      this->own_sink_->publish_result(json);
    this->sink_->publish_result(json);
  }
  /// Publish a lease message of this Bus on its own sensor (if any), then on the shared one.
  void publish_lease(const std::string &json) {
    if (this->own_sink_ != nullptr)
      this->own_sink_->publish_lease(json);
    this->sink_->publish_lease(json);
  }

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
      // A CRC-valid frame that does not answer this probe: overlapping replies from a
      // duplicate ID, or a misbehaving slave. It is evidence about this address, not a
      // Gateway fault, so the Scan records it and goes on.
      this->finish_("possible_collision", "");
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

  // Called by the Gateway only, after validation.
  void attach(Clock *clock, ResultSink *sink) {
    this->clock_ = clock;
    this->sink_ = sink;
  }
  /// Returns nullptr when queued, else the rejection error code.
  const char *start(const ProbeRequest &request) {
    if (this->in_flight_)
      return error::BUSY;
    this->lease_for_(request);
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
  struct PollerEntry {
    std::string name;
    uint8_t address;
    Poller *poller;
  };

  /// Begin, renew or supersede the Scan Lease for an accepted probe, before its frame is queued.
  void lease_for_(const ProbeRequest &request) {
    if (this->lease_active_ && request.scan_id != this->lease_scan_)
      this->end_lease_(lease_end::SUPERSEDED);
    if (this->lease_active_) {
      this->lease_touched_ = this->clock_->now_ms();
      return;
    }
    if (request.scan_id == this->lease_scan_)
      return;  // This scan's lease already ended; it never restarts.
    std::vector<size_t> selected = parse_poller_list(request.pause_pollers);
    if (selected.empty())
      return;
    this->lease_scan_ = request.scan_id;
    this->lease_pollers_ = selected;
    this->lease_active_ = true;
    this->lease_started_ = this->lease_touched_ = this->clock_->now_ms();
    for (size_t index : selected)
      this->pollers_[index].poller->pause();
    // Stopping a poller does not drop frames it already queued (including `continuous` ones),
    // so clear them. This runs before the probe is queued: clearing never drops our own probe.
    std::vector<uint8_t> cleared;
    for (size_t index : selected) {
      const uint8_t address = this->pollers_[index].address;
      bool done = address == 0;
      for (uint8_t a : cleared)
        done = done || a == address;
      if (!done) {
        this->port_.clear_queue_for_address(address);
        cleared.push_back(address);
      }
    }
    this->publish_lease_("active", nullptr);
  }

  void end_lease_(const char *reason) {
    this->lease_active_ = false;
    this->ended_reason_ = reason;
    for (size_t index : this->lease_pollers_)
      this->pollers_[index].poller->resume();
    this->publish_lease_("ended", reason);
  }

  void publish_lease_(const char *state, const char *reason) {
    this->publish_lease(lease_json(this->name_, this->lease_scan_, state, this->lease_pollers_, reason));
  }

  void finish_(const char *outcome, const std::string &outcome_fields) {
    uint32_t latency = this->sent_ ? this->clock_->now_ms() - this->sent_at_ : 0;
    if (this->sent_)
      this->port_.set_send_wait_ms(this->normal_send_wait_ms_);
    this->in_flight_ = false;
    this->sent_ = false;
    if (this->lease_active_)
      this->lease_touched_ = this->clock_->now_ms();  // the idle timer starts at the terminal callback
    this->publish_result(result_json(this->request_, outcome, latency, outcome_fields));
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

  static std::string lease_json(const std::string &bus, const std::string &scan_id, const char *state,
                                const std::vector<size_t> &pollers, const char *reason) {
    std::string out = "{\"v\":" + std::to_string(kLeaseSchemaVersion) + ",\"bus\":";
    append_json_string(out, bus);
    out += ",\"scan\":";
    append_json_string(out, scan_id);
    out += ",\"state\":\"" + std::string(state) + "\",\"pollers\":" + json_int_array(pollers);
    if (reason != nullptr)
      out += ",\"reason\":\"" + std::string(reason) + "\"";
    out += '}';
    return out;
  }

 private:
  std::string name_;
  std::string serial_;  // compact JSON object, empty when unknown
  ResultSink *own_sink_{nullptr};  // this Bus's own Result/Lease sensors, or none
  std::string result_sensor_;
  std::string lease_sensor_;
  BusPort &port_;
  uint16_t normal_send_wait_ms_;
  std::vector<PollerEntry> pollers_;
  // The current Scan Lease, or the last one once it ended (lease_active_ false).
  std::string lease_scan_;
  std::vector<size_t> lease_pollers_;
  bool lease_active_{false};
  uint32_t lease_started_{0};
  uint32_t lease_touched_{0};
  const char *ended_reason_{nullptr};
  Clock *clock_{nullptr};
  ResultSink *sink_{nullptr};
  ProbeRequest request_;
  bool in_flight_{false};
  bool sent_{false};
  uint32_t sent_at_{0};
};

// ---- Gateway: the probe/release actions and the shared info/result/lease sensors, routing by bus ----

class Gateway {
 public:
  Gateway(Clock &clock, ResultSink &sink) : clock_(clock), sink_(sink) {}

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
    Bus *bus = this->find_(request.bus);
    const char *rejection = this->validate_(request, bus);
    if (rejection == nullptr)
      rejection = bus->start(request);
    if (rejection == nullptr)
      return;
    const std::string json =
        Bus::result_json(request, "gateway_error", 0, "\"error\":\"" + std::string(rejection) + "\"");
    // A rejection of a known Bus reaches that Bus's own sensor too; an unknown Bus has none.
    if (bus != nullptr)
      bus->publish_result(json);
    else
      this->sink_.publish_result(json);
  }

  /// The `modbus_scanner_v2_release` action: end the scan's lease on that bus now.
  void release(const std::string &bus, const std::string &scan_id) {
    if (!valid_id(scan_id))
      return;
    if (Bus *target = this->find_(bus))
      target->release(scan_id);
  }

  /// Run from the component loop: each Bus recovers Normal Polling by itself.
  void loop() {
    for (Bus *bus : this->buses_)
      bus->loop();
  }

  std::string info_json() const {
    std::string out = "{\"v\":" + std::to_string(kInfoSchemaVersion) +
                      ",\"bridge\":" + std::to_string(kBridgeVersion) + ",\"buses\":[";
    for (size_t i = 0; i < this->buses_.size(); i++) {
      if (i)
        out += ',';
      out += this->buses_[i]->info_json();
    }
    out += "]}";
    return out;
  }

 private:
  Bus *find_(const std::string &name) const {
    for (Bus *candidate : this->buses_)
      if (candidate->name() == name)
        return candidate;
    return nullptr;
  }

  /// `bus` is the request's Bus, or nullptr when the Gateway has no such Bus.
  const char *validate_(const ProbeRequest &r, const Bus *bus) const {
    // Write function codes are refused before anything else, whatever HA sends.
    if (contains(kWriteFunctionCodes, r.function_code))
      return error::WRITE_FUNCTION_REFUSED;
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
