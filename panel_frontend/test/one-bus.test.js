import test from "node:test";
import assert from "node:assert/strict";
import {DEFAULTS, busLabel, sanitizePreferences, selectGateway, startPayload, testPayload} from "../src/model.js";

// A Gateway serves exactly one Bus (ADR 0011): the panel offers no Bus choice and HA resolves it.
const GATEWAY = {
  provider: "esphome", gateway_id: "esphome:aabbccddee01",
  capabilities: ["bridge_v2", "holding_register", "input_register", "multi_register"],
  supports_bus_selection: true, supports_scan_lease: true,
  buses: [{bus: "line_a", serial: {baud_rate: 19200, parity: "EVEN", stop_bits: 2}}],
};

test("the result source names the Bus with the serial parameters its Gateway reports", () => {
  assert.equal(busLabel(GATEWAY, "line_a"), "line_a (19200 baud, parity EVEN, 2 stop bits)");
  assert.equal(busLabel({...GATEWAY, buses: [{bus: "line_a", serial: {baud_rate: 9600, parity: "NONE", stop_bits: 1}}]}, "line_a"),
    "line_a (9600 baud, parity NONE, 1 stop bit)");
  // Unknown or malformed serial parameters leave just the name.
  assert.equal(busLabel({...GATEWAY, buses: [{bus: "line_a", serial: {baud_rate: "9600"}}]}, "line_a"), "line_a");
  assert.equal(busLabel(undefined, "line_a"), "line_a");
  assert.equal(busLabel(GATEWAY, "bad name"), null);
  assert.equal(busLabel(GATEWAY, undefined), null);
  // A Scan that failed before its provider reported the Bus is recorded with `bus: null`: no Bus is named.
  assert.equal(busLabel(GATEWAY, null), null);
});

test("Scans never name a Bus: HA targets the Gateway's one Bus", () => {
  const form = {...selectGateway({...DEFAULTS}, GATEWAY), safety_confirmed: true};
  assert.equal("bus" in form, false);
  assert.equal("bus" in startPayload(form), false);
  assert.equal("bus" in testPayload(form), false);
  // A Bus stored by an older panel is not restored.
  assert.equal("bus" in sanitizePreferences({bus: "line_b", gateway_id: GATEWAY.gateway_id}), false);
});
