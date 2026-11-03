// Host-compiled tests for the modbus_scanner firmware core (no ESPHome headers).
//
// Every protocol expectation is read from the shared bridge contract file, the same file the
// Home Assistant fake gateway uses, so protocol drift fails on both sides.
//
//   g++ -std=c++20 -Wall -Wextra -Werror firmware/tests/scanner_core_test.cpp -o scanner_core_test
//   ./scanner_core_test custom_components/woow_esphome_modbus_scanner/modbus_scan/bridge_v2/contract.json

#include <cstdio>
#include <fstream>
#include <set>
#include <sstream>
#include <string>
#include <vector>

#include "../components/modbus_scanner/scanner_core.h"
#include "mini_json.h"

using mini_json::Value;
namespace core = modbus_scanner_core;

static int failures = 0;
static std::string current_test;

#define CHECK(cond)                                                                       \
  do {                                                                                    \
    if (!(cond)) {                                                                        \
      failures++;                                                                         \
      std::fprintf(stderr, "FAIL [%s] %s:%d: %s\n", current_test.c_str(), __FILE__, __LINE__, #cond); \
    }                                                                                     \
  } while (0)

struct FakeClock : core::Clock {
  uint32_t now{1000};
  uint32_t now_ms() override { return now; }
};

struct FakeSink : core::ResultSink {
  std::vector<std::string> results;
  std::vector<std::string> leases;
  void publish_result(const std::string &json) override { results.push_back(json); }
  void publish_lease(const std::string &json) override { leases.push_back(json); }
};

// Bus-side happenings in order: "pause:<name>", "resume:<name>", "clear:<addr>", "queue:<slave>".
static std::vector<std::string> *event_log = nullptr;
static void log_event(const std::string &event) {
  if (event_log)
    event_log->push_back(event);
}

struct FakePoller : core::Poller {
  std::string name;
  bool paused{false};
  explicit FakePoller(std::string n) : name(std::move(n)) {}
  void pause() override {
    paused = true;
    log_event("pause:" + name);
  }
  void resume() override {
    paused = false;
    log_event("resume:" + name);
  }
};

struct FakePort : core::BusPort {
  struct Frame {
    uint8_t slave;
    std::vector<uint8_t> pdu;
  };
  std::vector<Frame> queued;
  std::vector<uint16_t> send_wait_history;
  bool accept{true};
  bool queue_request(uint8_t slave, const uint8_t *pdu, size_t len) override {
    if (!accept)
      return false;
    queued.push_back({slave, std::vector<uint8_t>(pdu, pdu + len)});
    log_event("queue:" + std::to_string(slave));
    return true;
  }
  void set_send_wait_ms(uint16_t ms) override { send_wait_history.push_back(ms); }
  void clear_queue_for_address(uint8_t address) override { log_event("clear:" + std::to_string(address)); }
};

static constexpr uint16_t kYamlSendWait = 700;

struct Rig {
  FakeClock clock;
  FakeSink sink;
  FakePort port;
  core::Bus bus{"bus0", port, kYamlSendWait};
  core::Bridge bridge{clock, sink};
  Rig() { bridge.add_bus(&bus); }
  Value last() const { return mini_json::parse(sink.results.back()); }
};

static Value load_contract(const char *path) {
  std::ifstream file(path, std::ios::binary);
  if (!file) {
    std::fprintf(stderr, "cannot open contract file %s\n", path);
    std::exit(2);
  }
  std::stringstream buffer;
  buffer << file.rdbuf();
  return mini_json::parse(buffer.str());
}

static core::ProbeRequest request_from(const Value &base, const Value &overrides) {
  auto pick = [&](const char *key) -> const Value & { return overrides.has(key) ? overrides[key] : base[key]; };
  core::ProbeRequest r;
  r.request_id = pick("request_id").str();
  r.bus = pick("bus").str();
  r.slave = static_cast<int32_t>(pick("slave").integer());
  r.function_code = static_cast<int32_t>(pick("function_code").integer());
  r.reg = static_cast<int32_t>(pick("register").integer());
  r.count = static_cast<int32_t>(pick("count").integer());
  r.timeout_ms = static_cast<int32_t>(pick("timeout_ms").integer());
  r.scan_id = pick("scan_id").str();
  r.pause_pollers = pick("pause_pollers").str();
  return r;
}

static core::ProbeRequest base_request(const Value &contract) {
  return request_from(contract["base_request"], Value{});
}

static std::set<std::string> keys_of(const Value &object) {
  std::set<std::string> keys;
  for (const auto &item : object.object)
    keys.insert(item.first);
  return keys;
}

/// A Bus with three Pausable Pollers: meter @1, inverter @2 and a second view of meter @1.
struct LeaseRig : Rig {
  std::vector<std::string> events;
  FakePoller meter{"meter"}, inverter{"inverter"}, meter_b{"meter_b"};
  LeaseRig() {
    event_log = &events;
    bus.add_poller("meter", 1, &meter);
    bus.add_poller("inverter", 2, &inverter);
    bus.add_poller("meter_b", 1, &meter_b);
  }
  ~LeaseRig() { event_log = nullptr; }
  Value last_lease() const { return mini_json::parse(sink.leases.back()); }
  void probe(const Value &contract, const char *request_id, const char *scan_id, const char *pollers,
             int32_t slave = 7) {
    core::ProbeRequest r = base_request(contract);
    r.request_id = request_id;
    r.scan_id = scan_id;
    r.pause_pollers = pollers;
    r.slave = slave;
    bridge.probe(r);
  }
  /// Complete the in-flight probe as a timeout after `elapsed_ms` on the wire.
  void time_out(uint32_t elapsed_ms) {
    bus.on_sent();
    clock.now += elapsed_ms;
    bus.on_no_response();
  }
  void advance(uint32_t ms) {
    clock.now += ms;
    bridge.loop();
  }
};

static uint32_t kIdleMs(const Value &contract) {
  return static_cast<uint32_t>(contract["lease"]["idle_ms"].integer());
}

static std::vector<int64_t> ints(const Value &array) {
  std::vector<int64_t> out;
  for (const auto &item : array.array)
    out.push_back(item.integer());
  return out;
}

// A lease message carries exactly the contract's fields plus the fields of its state.
static void check_lease_shape(const Value &contract, const Value &lease) {
  std::set<std::string> expected = keys_of(contract["lease"]["fields"]);
  for (const auto &key : keys_of(contract["lease"]["state_fields"][lease["state"].str()]))
    expected.insert(key);
  CHECK(keys_of(lease) == expected);
  CHECK(lease["v"].integer() == contract["lease"]["schema_version"].integer());
}

// The result carries exactly the contract's common fields plus the fields of its outcome.
static void check_result_shape(const Value &contract, const Value &result) {
  std::set<std::string> expected = keys_of(contract["result"]["common_fields"]);
  for (const auto &key : keys_of(contract["result"]["outcome_fields"][result["outcome"].str()]))
    expected.insert(key);
  CHECK(keys_of(result) == expected);
  CHECK(result["v"].integer() == contract["result"]["schema_version"].integer());
}

static void test_core_constants_match_contract(const Value &contract) {
  current_test = "constants match contract";
  const Value &action = contract["actions"]["probe"];
  CHECK(action["name"].str() == core::kProbeAction);
  CHECK(action["args"].array.size() == core::kProbeArgs.size());
  for (size_t i = 0; i < core::kProbeArgs.size() && i < action["args"].array.size(); i++) {
    CHECK(action["args"][i]["name"].str() == core::kProbeArgs[i].name);
    CHECK(action["args"][i]["type"].str() == core::kProbeArgs[i].type);
  }
  CHECK(contract["text_sensors"]["info"]["name"].str() == core::kInfoSensorName);
  CHECK(contract["text_sensors"]["result"]["name"].str() == core::kResultSensorName);
  CHECK(contract["text_sensors"]["lease"]["name"].str() == core::kLeaseSensorName);
  const Value &release = contract["actions"]["release"];
  CHECK(release["name"].str() == core::kReleaseAction);
  CHECK(release["args"].array.size() == core::kReleaseArgs.size());
  for (size_t i = 0; i < core::kReleaseArgs.size() && i < release["args"].array.size(); i++) {
    CHECK(release["args"][i]["name"].str() == core::kReleaseArgs[i].name);
    CHECK(release["args"][i]["type"].str() == core::kReleaseArgs[i].type);
  }
  const Value &lease = contract["lease"];
  CHECK(lease["schema_version"].integer() == core::kLeaseSchemaVersion);
  CHECK(lease["idle_ms"].integer() == core::kLeaseIdleMs);
  CHECK(lease["hard_limit_ms"].integer() == core::kLeaseHardLimitMs);
  std::set<std::string> reasons, core_reasons(core::kLeaseEndReasons.begin(), core::kLeaseEndReasons.end());
  for (const auto &reason : lease["end_reasons"].array)
    reasons.insert(reason.str());
  CHECK(reasons == core_reasons);
  CHECK(contract["bridge_version"].integer() == core::kBridgeVersion);
  CHECK(contract["result"]["schema_version"].integer() == core::kResultSchemaVersion);
  CHECK(contract["info"]["schema_version"].integer() == core::kInfoSchemaVersion);

  const Value &limits = contract["hard_limits"];
  CHECK(limits["slave_min"].integer() == core::kLimits.slave_min);
  CHECK(limits["slave_max"].integer() == core::kLimits.slave_max);
  CHECK(limits["register_min"].integer() == core::kLimits.register_min);
  CHECK(limits["register_max"].integer() == core::kLimits.register_max);
  CHECK(limits["count_min"].integer() == core::kLimits.count_min);
  CHECK(limits["count_max"].integer() == core::kLimits.count_max);
  CHECK(limits["timeout_ms_min"].integer() == core::kLimits.timeout_ms_min);
  CHECK(limits["timeout_ms_max"].integer() == core::kLimits.timeout_ms_max);
  std::set<int64_t> read_codes, write_codes;
  for (const auto &code : limits["function_codes"].array)
    read_codes.insert(code.integer());
  for (const auto &code : limits["write_function_codes"].array)
    write_codes.insert(code.integer());
  CHECK(read_codes == std::set<int64_t>(core::kReadFunctionCodes.begin(), core::kReadFunctionCodes.end()));
  CHECK(write_codes == std::set<int64_t>(core::kWriteFunctionCodes.begin(), core::kWriteFunctionCodes.end()));

  std::set<std::string> contract_errors, core_errors(core::kErrorCodes.begin(), core::kErrorCodes.end());
  for (const auto &code : contract["error_codes"].array)
    contract_errors.insert(code.str());
  CHECK(contract_errors == core_errors);
}

static void test_request_cases_from_contract(const Value &contract) {
  for (const auto &item : contract["request_cases"].array) {
    current_test = "request case: " + item["name"].str();
    Rig rig;
    rig.bridge.probe(request_from(contract["base_request"], item["request"]));
    const std::string &expect = item["expect"].str();
    if (expect == "accepted") {
      CHECK(rig.port.queued.size() == 1);
      CHECK(rig.sink.results.empty());
      continue;
    }
    CHECK(rig.port.queued.empty());
    if (expect == "invalid_request_id") {
      // Uncorrelatable, so nothing is published.
      CHECK(rig.sink.results.empty());
      continue;
    }
    CHECK(rig.sink.results.size() == 1);
    if (rig.sink.results.size() != 1)
      continue;
    Value result = rig.last();
    CHECK(result["outcome"].str() == "gateway_error");
    CHECK(result["error"].str() == expect);
    check_result_shape(contract, result);
  }
}

static void test_accepted_probe_reads_registers_with_its_own_timeout(const Value &contract) {
  current_test = "responded probe";
  Rig rig;
  core::ProbeRequest r = base_request(contract);
  r.slave = 17;
  r.function_code = 4;
  r.reg = 0x1234;
  r.count = 2;
  r.timeout_ms = 300;
  rig.bridge.probe(r);
  CHECK(rig.port.queued.size() == 1);
  CHECK(rig.port.queued[0].slave == 17);
  CHECK((rig.port.queued[0].pdu == std::vector<uint8_t>{0x04, 0x12, 0x34, 0x00, 0x02}));
  CHECK(rig.port.send_wait_history.empty());  // hub-wide wait untouched until our frame is on the wire

  rig.bus.on_sent();
  CHECK((rig.port.send_wait_history == std::vector<uint16_t>{300}));
  rig.clock.now += 42;
  const uint8_t reply[] = {0x04, 0x04, 0x04, 0xD2, 0xFF, 0xFF};
  rig.bus.on_response(reply, sizeof(reply));
  CHECK((rig.port.send_wait_history == std::vector<uint16_t>{300, kYamlSendWait}));  // restored
  CHECK(rig.sink.results.size() == 1);
  Value result = rig.last();
  check_result_shape(contract, result);
  CHECK(result["id"].str() == r.request_id);
  CHECK(result["bus"].str() == "bus0");
  CHECK(result["slave"].integer() == 17);
  CHECK(result["fc"].integer() == 4);
  CHECK(result["reg"].integer() == 0x1234);
  CHECK(result["count"].integer() == 2);
  CHECK(result["outcome"].str() == "responded");
  CHECK(result["latency_ms"].integer() == 42);
  CHECK(result["values"].array.size() == 2);
  CHECK(result["values"][0].integer() == 1234);
  CHECK(result["values"][1].integer() == 65535);
  CHECK(!rig.bus.busy());
}

static void test_terminal_outcomes(const Value &contract) {
  struct Case {
    const char *name;
    void (*deliver)(core::Bus &);
    bool sent;
    const char *outcome;
    const char *error;
  };
  const Case cases[] = {
      {"modbus exception", [](core::Bus &b) { b.on_exception(2); }, true, "modbus_exception", nullptr},
      {"no response", [](core::Bus &b) { b.on_no_response(); }, true, "timeout", nullptr},
      {"dropped before transmission", [](core::Bus &b) { b.on_not_sent(); }, false, "gateway_error", "not_sent"},
      {"reply with wrong byte count",
       [](core::Bus &b) {
         const uint8_t reply[] = {0x03, 0x04, 0x00, 0x01};
         b.on_response(reply, sizeof(reply));
       },
       true, "gateway_error", "invalid_response"},
  };
  for (const Case &c : cases) {
    current_test = std::string("terminal: ") + c.name;
    Rig rig;
    rig.bridge.probe(base_request(contract));
    if (c.sent)
      rig.bus.on_sent();
    rig.clock.now += 1000;
    c.deliver(rig.bus);
    CHECK(rig.sink.results.size() == 1);
    Value result = rig.last();
    check_result_shape(contract, result);
    CHECK(result["outcome"].str() == c.outcome);
    if (c.error)
      CHECK(result["error"].str() == c.error);
    if (std::string(c.outcome) == "modbus_exception")
      CHECK(result["exception"].integer() == 2);
    CHECK(result["latency_ms"].integer() == (c.sent ? 1000 : 0));
    // The YAML send_wait_time is back in force whenever the probe frame was transmitted.
    CHECK(rig.port.send_wait_history.empty() == !c.sent);
    if (c.sent)
      CHECK(rig.port.send_wait_history.back() == kYamlSendWait);
    CHECK(!rig.bus.busy());
  }
}

static void test_one_probe_in_flight_per_bus(const Value &contract) {
  current_test = "single in-flight";
  Rig rig;
  rig.bridge.probe(base_request(contract));
  core::ProbeRequest second = base_request(contract);
  second.request_id = "r2";
  rig.bridge.probe(second);
  CHECK(rig.port.queued.size() == 1);
  CHECK(rig.sink.results.size() == 1);
  CHECK(rig.last()["id"].str() == "r2");
  CHECK(rig.last()["error"].str() == "busy");

  rig.bus.on_sent();
  rig.bus.on_no_response();
  second.request_id = "r3";
  rig.bridge.probe(second);
  CHECK(rig.port.queued.size() == 2);
}

static void test_hub_refusal_is_reported_and_frees_the_bus(const Value &contract) {
  current_test = "queue rejected";
  Rig rig;
  rig.port.accept = false;
  rig.bridge.probe(base_request(contract));
  CHECK(rig.sink.results.size() == 1);
  CHECK(rig.last()["error"].str() == "queue_rejected");
  CHECK(!rig.bus.busy());
}

static void test_stray_callbacks_are_ignored(const Value &contract) {
  current_test = "stray callbacks";
  Rig rig;
  rig.bus.on_sent();
  rig.bus.on_no_response();
  const uint8_t reply[] = {0x03, 0x02, 0x00, 0x01};
  rig.bus.on_response(reply, sizeof(reply));
  CHECK(rig.sink.results.empty());
  CHECK(rig.port.send_wait_history.empty());
  (void) contract;
}

static void test_unknown_bus_name_is_echoed_safely(const Value &contract) {
  current_test = "json escaping";
  Rig rig;
  core::ProbeRequest r = base_request(contract);
  r.bus = "x\"},{\"outcome\":\"responded\n";
  rig.bridge.probe(r);
  Value result = rig.last();
  CHECK(result["bus"].str() == r.bus);
  CHECK(result["error"].str() == "unknown_bus");
}

static void test_info_lists_buses_per_contract(const Value &contract) {
  current_test = "info";
  FakeClock clock;
  FakeSink sink;
  FakePort port_a, port_b;
  core::Bus a{"rs485_a", port_a, 2000}, b{"rs485_b", port_b, 2000};
  core::Bridge bridge{clock, sink};
  bridge.add_bus(&a);
  bridge.add_bus(&b);
  Value info = mini_json::parse(bridge.info_json());
  CHECK(keys_of(info) == keys_of(contract["info"]["fields"]));
  CHECK(info["v"].integer() == contract["info"]["schema_version"].integer());
  CHECK(info["bridge"].integer() == contract["bridge_version"].integer());
  CHECK(info["buses"].array.size() == 2);
  for (const auto &bus : info["buses"].array)
    CHECK(keys_of(bus) == keys_of(contract["info"]["bus_fields"]));
  CHECK(info["buses"][1]["bus"].str() == "rs485_b");

  // Each bus routes its own probes.
  core::ProbeRequest r = base_request(contract);
  r.bus = "rs485_b";
  bridge.probe(r);
  CHECK(port_a.queued.empty());
  CHECK(port_b.queued.size() == 1);
}

static void test_info_reports_each_bus_serial_parameters(const Value &contract) {
  current_test = "info serial";
  FakeClock clock;
  FakeSink sink;
  FakePort port_a, port_b;
  core::Bus a{"rs485_a", port_a, 2000}, b{"rs485_b", port_b, 2000};
  b.set_serial(19200, "EVEN", 2);
  core::Bridge bridge{clock, sink};
  bridge.add_bus(&a);
  bridge.add_bus(&b);
  Value info = mini_json::parse(bridge.info_json());
  // A bus whose UART is unknown has no serial object; the field is optional.
  CHECK(!info["buses"][0].has("serial"));
  const Value &serial = info["buses"][1]["serial"];
  CHECK(keys_of(serial) == keys_of(contract["info"]["serial_fields"]));
  CHECK(serial["baud_rate"].integer() == 19200);
  CHECK(serial["parity"].str() == "EVEN");
  CHECK(serial["stop_bits"].integer() == 2);
  bool parity_known = false;
  for (const auto &parity : contract["info"]["serial_parities"].array)
    parity_known = parity_known || parity.str() == serial["parity"].str();
  CHECK(parity_known);
  std::set<std::string> bus_keys = keys_of(contract["info"]["bus_fields"]);
  for (const auto &key : keys_of(contract["info"]["optional_bus_fields"]))
    bus_keys.insert(key);
  CHECK(keys_of(info["buses"][1]) == bus_keys);
}

static void test_two_buses_have_a_probe_in_flight_at_the_same_time(const Value &contract) {
  current_test = "buses in parallel";
  FakeClock clock;
  FakeSink sink;
  FakePort port_a, port_b;
  core::Bus a{"rs485_a", port_a, 2000}, b{"rs485_b", port_b, 2000};
  core::Bridge bridge{clock, sink};
  bridge.add_bus(&a);
  bridge.add_bus(&b);
  core::ProbeRequest ra = base_request(contract), rb = base_request(contract);
  ra.bus = "rs485_a";
  rb.bus = "rs485_b";
  rb.request_id = "rb1";
  bridge.probe(ra);
  bridge.probe(rb);
  CHECK(a.busy() && b.busy());
  CHECK(port_a.queued.size() == 1 && port_b.queued.size() == 1);
  CHECK(sink.results.empty());
  // A second probe on a busy Bus is refused; the other Bus is unaffected.
  ra.request_id = "ra2";
  bridge.probe(ra);
  CHECK(mini_json::parse(sink.results.back())["error"].str() == "busy");
  CHECK(mini_json::parse(sink.results.back())["bus"].str() == "rs485_a");
  CHECK(b.busy());
  b.on_sent();
  b.on_no_response();
  CHECK(mini_json::parse(sink.results.back())["id"].str() == "rb1");
  CHECK(a.busy() && !b.busy());
}

static void test_first_probe_of_a_scan_pauses_selected_pollers_before_queueing(const Value &contract) {
  current_test = "lease begins";
  LeaseRig rig;
  rig.probe(contract, "r1", "scanA", "0,1");
  CHECK(rig.meter.paused);
  CHECK(rig.inverter.paused);
  CHECK(!rig.meter_b.paused);
  // Stopped, and their queued frames dropped, before the probe frame enters the hub queue, so
  // clearing can never drop the scanner's own probe.
  CHECK((rig.events == std::vector<std::string>{"pause:meter", "pause:inverter", "clear:1", "clear:2", "queue:7"}));
  CHECK(rig.sink.leases.size() == 1);
  Value lease = rig.last_lease();
  check_lease_shape(contract, lease);
  CHECK(lease["bus"].str() == "bus0");
  CHECK(lease["scan"].str() == "scanA");
  CHECK(lease["state"].str() == "active");
  CHECK((ints(lease["pollers"]) == std::vector<int64_t>{0, 1}));
}

static void test_each_probe_renews_the_lease_and_in_flight_probes_never_expire_it(const Value &contract) {
  current_test = "lease renews";
  LeaseRig rig;
  rig.probe(contract, "r1", "scanA", "0,1,2", 1);
  rig.time_out(2000);
  rig.advance(4000);
  rig.probe(contract, "r2", "scanA", "0,1,2", 2);
  // A later probe of the same scan neither pauses again, clears again nor republishes.
  CHECK((rig.events == std::vector<std::string>{"pause:meter", "pause:inverter", "pause:meter_b", "clear:1",
                                                "clear:2", "queue:1", "queue:2"}));
  CHECK(rig.sink.leases.size() == 1);
  // A probe on the wire holds the lease however long the hub waits for it.
  rig.bus.on_sent();
  rig.advance(9000);
  CHECK(rig.bus.lease_active());
  rig.bus.on_no_response();
  rig.advance(kIdleMs(contract) - 1);
  CHECK(rig.bus.lease_active());
  CHECK(rig.meter.paused && rig.inverter.paused && rig.meter_b.paused);
}

static void test_client_gone_mid_scan_gateway_resumes_polling_after_idle(const Value &contract) {
  current_test = "lease idle expiry (HA disconnected)";
  LeaseRig rig;
  rig.probe(contract, "r1", "scanA", "1,2");
  rig.time_out(300);
  // HA disconnects here: no more probes and no release ever arrive.
  rig.advance(kIdleMs(contract) - 1);
  CHECK(rig.inverter.paused && rig.meter_b.paused);
  CHECK(rig.sink.leases.size() == 1);
  rig.advance(1);
  CHECK(!rig.inverter.paused && !rig.meter_b.paused);
  CHECK(!rig.bus.lease_active());
  CHECK(rig.sink.leases.size() == 2);
  Value lease = rig.last_lease();
  check_lease_shape(contract, lease);
  CHECK(lease["state"].str() == "ended");
  CHECK(lease["reason"].str() == "idle");
  CHECK((ints(lease["pollers"]) == std::vector<int64_t>{1, 2}));
  rig.advance(60000);
  CHECK(rig.sink.leases.size() == 2);  // ends exactly once
}

static void test_hard_limit_ends_a_lease_that_keeps_being_renewed(const Value &contract) {
  current_test = "lease hard limit";
  LeaseRig rig;
  const uint32_t hard = static_cast<uint32_t>(contract["lease"]["hard_limit_ms"].integer());
  rig.probe(contract, "r0", "scanA", "0");
  rig.time_out(500);
  uint32_t elapsed = 500;
  for (int i = 1; elapsed + 1000 < hard; i++) {
    rig.advance(500);
    std::string id = "r" + std::to_string(i);
    rig.probe(contract, id.c_str(), "scanA", "0");
    rig.time_out(500);
    elapsed += 1000;
  }
  CHECK(rig.meter.paused);
  rig.advance(hard - elapsed);
  CHECK(!rig.meter.paused);
  CHECK(rig.last_lease()["reason"].str() == "hard_limit");
  // The same scan never pauses again, but its probes still run.
  const size_t queued = rig.port.queued.size();
  rig.probe(contract, "late", "scanA", "0");
  CHECK(rig.port.queued.size() == queued + 1);
  CHECK(!rig.meter.paused);
  CHECK(rig.sink.leases.size() == 2);
}

static void test_release_resumes_at_once_and_always_answers(const Value &contract) {
  current_test = "lease release";
  LeaseRig rig;
  rig.probe(contract, "r1", "scanA", "0,2");
  rig.time_out(100);
  rig.events.clear();
  rig.bridge.release("bus0", "scanA");
  CHECK((rig.events == std::vector<std::string>{"resume:meter", "resume:meter_b"}));
  Value lease = rig.last_lease();
  check_lease_shape(contract, lease);
  CHECK(lease["state"].str() == "ended");
  CHECK(lease["reason"].str() == "released");

  // Releasing again (for example after a lost answer) repeats the ending, without resuming twice.
  rig.events.clear();
  rig.bridge.release("bus0", "scanA");
  CHECK(rig.events.empty());
  CHECK(rig.sink.leases.size() == 3);
  CHECK(rig.last_lease()["reason"].str() == "released");

  // A scan that never paused anything is answered with state none.
  rig.bridge.release("bus0", "scanB");
  lease = rig.last_lease();
  check_lease_shape(contract, lease);
  CHECK(lease["scan"].str() == "scanB");
  CHECK(lease["state"].str() == "none");
  CHECK(lease["pollers"].array.empty());

  // Unknown bus or uncorrelatable scan id: nothing to answer.
  rig.bridge.release("bus9", "scanA");
  rig.bridge.release("bus0", "bad id");
  CHECK(rig.sink.leases.size() == 4);
}

static void test_release_while_the_last_probe_is_in_flight(const Value &contract) {
  current_test = "lease release in flight";
  LeaseRig rig;
  rig.probe(contract, "r1", "scanA", "0");
  rig.bus.on_sent();
  rig.bridge.release("bus0", "scanA");
  CHECK(!rig.meter.paused);
  rig.bus.on_no_response();  // the probe still ends normally
  CHECK(rig.sink.results.size() == 1);
  rig.advance(kIdleMs(contract) * 2);
  CHECK(rig.sink.leases.size() == 2);
}

static void test_a_new_scan_supersedes_an_active_lease(const Value &contract) {
  current_test = "lease superseded";
  LeaseRig rig;
  rig.probe(contract, "r1", "scanA", "0");
  rig.time_out(100);
  rig.events.clear();
  rig.probe(contract, "r2", "scanB", "1");
  CHECK((rig.events == std::vector<std::string>{"resume:meter", "pause:inverter", "clear:2", "queue:7"}));
  CHECK(rig.sink.leases.size() == 3);
  Value ended = mini_json::parse(rig.sink.leases[1]);
  CHECK(ended["scan"].str() == "scanA");
  CHECK(ended["reason"].str() == "superseded");
  CHECK(rig.last_lease()["scan"].str() == "scanB");
  CHECK(rig.last_lease()["state"].str() == "active");
}

static void test_no_selection_and_rejected_probes_never_pause(const Value &contract) {
  current_test = "lease not started";
  LeaseRig rig;
  rig.probe(contract, "r1", "scanA", "");
  CHECK(rig.port.queued.size() == 1);
  CHECK(!rig.meter.paused && !rig.inverter.paused);
  CHECK(rig.sink.leases.empty());
  // Busy (one probe in flight) and invalid requests are refused before any pausing.
  rig.probe(contract, "r2", "scanB", "0");
  CHECK(rig.last()["error"].str() == "busy");
  rig.time_out(100);
  rig.probe(contract, "r3", "scanB", "0,3");
  CHECK(rig.last()["error"].str() == "invalid_poller");
  rig.probe(contract, "r4", "scanB", "0", 0);
  CHECK(rig.last()["error"].str() == "invalid_slave");
  CHECK(!rig.meter.paused);
  CHECK(rig.sink.leases.empty());
}

static void test_info_lists_the_pausable_poller_table(const Value &contract) {
  current_test = "info poller table";
  LeaseRig rig;
  Value info = mini_json::parse(rig.bridge.info_json());
  const Value &pollers = info["buses"][0]["pollers"];
  CHECK(pollers.array.size() == 3);
  for (const auto &poller : pollers.array)
    CHECK(keys_of(poller) == keys_of(contract["info"]["poller_fields"]));
  CHECK(pollers[1]["index"].integer() == 1);
  CHECK(pollers[1]["name"].str() == "inverter");
  CHECK(pollers[1]["address"].integer() == 2);
  CHECK(pollers[2]["name"].str() == "meter_b");
  CHECK(pollers[2]["address"].integer() == 1);
  // Indices from the table are exactly what the probe accepts.
  rig.probe(contract, "r1", "scanA", "0,1,2");
  CHECK(rig.sink.results.empty());
}

int main(int argc, char **argv) {
  const char *path =
      argc > 1 ? argv[1] : "custom_components/woow_esphome_modbus_scanner/modbus_scan/bridge_v2/contract.json";
  Value contract = load_contract(path);
  test_core_constants_match_contract(contract);
  test_request_cases_from_contract(contract);
  test_accepted_probe_reads_registers_with_its_own_timeout(contract);
  test_terminal_outcomes(contract);
  test_one_probe_in_flight_per_bus(contract);
  test_hub_refusal_is_reported_and_frees_the_bus(contract);
  test_stray_callbacks_are_ignored(contract);
  test_unknown_bus_name_is_echoed_safely(contract);
  test_info_lists_buses_per_contract(contract);
  test_info_reports_each_bus_serial_parameters(contract);
  test_two_buses_have_a_probe_in_flight_at_the_same_time(contract);
  test_first_probe_of_a_scan_pauses_selected_pollers_before_queueing(contract);
  test_each_probe_renews_the_lease_and_in_flight_probes_never_expire_it(contract);
  test_client_gone_mid_scan_gateway_resumes_polling_after_idle(contract);
  test_hard_limit_ends_a_lease_that_keeps_being_renewed(contract);
  test_release_resumes_at_once_and_always_answers(contract);
  test_release_while_the_last_probe_is_in_flight(contract);
  test_a_new_scan_supersedes_an_active_lease(contract);
  test_no_selection_and_rejected_probes_never_pause(contract);
  test_info_lists_the_pausable_poller_table(contract);
  if (failures) {
    std::fprintf(stderr, "%d check(s) failed\n", failures);
    return 1;
  }
  std::printf("PASS scanner_core_test\n");
  return 0;
}
