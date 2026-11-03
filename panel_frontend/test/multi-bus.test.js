import test from "node:test";
import assert from "node:assert/strict";
import {
  DEFAULTS, gatewayBuses, pollerChecklists, reconcileBus, sanitizePreferences, selectBus, selectGateway, startPayload,
  testPayload,
} from "../src/model.js";

const TWO_BUSES = {
  provider: "esphome", gateway_id: "esphome:aabbccddee01",
  capabilities: ["bridge_v2", "holding_register", "input_register", "multi_register"],
  buses: [
    {bus: "line_a", serial: {baud_rate: 9600, parity: "NONE", stop_bits: 1}},
    {bus: "line_b", serial: {baud_rate: 19200, parity: "EVEN", stop_bits: 2}},
  ],
  poller_selection: {
    line_a: [{index: 0, name: "meter", address: 1, paused: true}],
    line_b: [{index: 0, name: "pump", address: 4, paused: false}],
  },
  removed_pollers: {line_a: [], line_b: []},
};
const ONE_BUS = {...TWO_BUSES, buses: [TWO_BUSES.buses[0]], poller_selection: {line_a: TWO_BUSES.poller_selection.line_a}};

test("each Bus is listed with its serial parameters", () => {
  assert.deepEqual(gatewayBuses(TWO_BUSES), [
    {bus: "line_a", label: "line_a (9600 baud, parity NONE, 1 stop bit)"},
    {bus: "line_b", label: "line_b (19200 baud, parity EVEN, 2 stop bits)"},
  ]);
  assert.deepEqual(gatewayBuses({...TWO_BUSES, buses: [{bus: "x"}, {bus: "bad name"}, "x", {bus: "y", serial: {baud_rate: "9600"}}]}),
    [{bus: "x", label: "x"}, {bus: "y", label: "y"}]);
  assert.deepEqual(gatewayBuses({provider: "mock"}), []);
});

test("a multi-Bus gateway starts on its first Bus and every Scan names the Bus", () => {
  const form = selectGateway({...DEFAULTS}, TWO_BUSES);
  assert.equal(form.bus, "line_a");
  const chosen = selectBus(form, TWO_BUSES, "line_b");
  assert.equal(chosen.bus, "line_b");
  assert.equal(chosen.safety_confirmed, false);
  assert.equal(startPayload({...chosen, safety_confirmed: true}).bus, "line_b");
  assert.equal(testPayload(chosen).bus, "line_b");
  assert.equal(selectBus(form, TWO_BUSES, "line_c").bus, "line_a");  // unknown Bus names are ignored
});

test("a single-Bus gateway needs no Bus in the request", () => {
  const form = selectGateway({...DEFAULTS, bus: "line_b"}, ONE_BUS);
  assert.equal(form.bus, "");
  assert.equal("bus" in testPayload(form), false);
  assert.equal("bus" in startPayload({...DEFAULTS}), false);
});

test("a reloaded gateway keeps a still-reported Bus and drops a vanished one", () => {
  const form = {...selectGateway({...DEFAULTS}, TWO_BUSES), bus: "line_b", safety_confirmed: true};
  assert.equal(reconcileBus(form, TWO_BUSES), form);
  const moved = reconcileBus(form, {...TWO_BUSES, buses: [TWO_BUSES.buses[0], {bus: "line_c"}]});
  assert.equal(moved.bus, "line_a");
  assert.equal(moved.safety_confirmed, false);
  assert.equal(reconcileBus(form, ONE_BUS).bus, "");
});

test("the poller checklist follows the selected Bus", () => {
  assert.deepEqual(pollerChecklists(TWO_BUSES, "line_b").map((list) => list.bus), ["line_b"]);
  assert.deepEqual(pollerChecklists(TWO_BUSES).map((list) => list.bus), ["line_a", "line_b"]);
  assert.deepEqual(pollerChecklists(ONE_BUS, "").map((list) => list.bus), ["line_a"]);
});

test("a stored Bus survives a reload only when it is a valid Bus name", () => {
  const stored = (bus) => sanitizePreferences({form: {provider: "esphome", bridge: "v2", gateway_id: "esphome:aabbccddee01", bus}}).form.bus;
  assert.equal(stored("line_b"), "line_b");
  assert.equal(stored("bad name"), "");
  assert.equal(stored(42), "");
});
