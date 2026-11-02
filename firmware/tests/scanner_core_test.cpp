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
  void publish_result(const std::string &json) override { results.push_back(json); }
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
    return true;
  }
  void set_send_wait_ms(uint16_t ms) override { send_wait_history.push_back(ms); }
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
  if (failures) {
    std::fprintf(stderr, "%d check(s) failed\n", failures);
    return 1;
  }
  std::printf("PASS scanner_core_test\n");
  return 0;
}
