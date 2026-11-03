import test from "node:test";
import assert from "node:assert/strict";
import {
  DEFAULTS, estimatedDurationMs, needsLargeRangeConfirmation, safePreferences, sanitizePreferences,
  selectGateway, serviceYaml, startPayload, validateForm,
} from "../src/model.js";

const V2_GATEWAY = {
  provider: "esphome", gateway_id: "esphome:aabbccddee01", name: "ESPHome Modbus DDEE01",
  capabilities: ["bridge_v2", "holding_register", "input_register", "multi_register"], can_operate: true,
};
const v2Form = (changes = {}) => ({...selectGateway(DEFAULTS, V2_GATEWAY), safety_confirmed: true, ...changes});

// The Gateway as list_gateways reports it: limits carry the per-attempt overhead of its bridge.
const LISTED_V2 = {...V2_GATEWAY, limits: {attempt_overhead_ms: 300}};

test("estimated duration uses the service's formula, retries and the gateway's overhead", () => {
  // The service's worked example (tests/services/test_bridge_v2.py): 3 IDs x 2 attempts x
  // (200 ms + 300 ms) + 2 gaps x 50 ms = 3.1 s, the Scan's estimated_worst_case_ms.
  const form = v2Form({start_id: 1, end_id: 3, timeout_ms: 200, retries: 1, inter_request_delay_ms: 50});
  assert.equal(estimatedDurationMs(form, LISTED_V2), 3100);
  // 247 IDs x 1 attempt x (1000 ms + 300 ms) + 246 x 100 ms = 345.7 s
  assert.equal(estimatedDurationMs(v2Form({start_id: 1, end_id: 247}), LISTED_V2), 345_700);
  // Without a reported overhead (mock gateway) only timeouts and delays count.
  assert.equal(estimatedDurationMs(v2Form({start_id: "10", end_id: "12", timeout_ms: "200", inter_request_delay_ms: "0"})), 600);
  assert.equal(estimatedDurationMs(v2Form({start_id: 5, end_id: 1}), LISTED_V2), null);
});

test("a range above 32 IDs needs a second confirmation before it can start", () => {
  assert.equal(needsLargeRangeConfirmation(v2Form({start_id: 1, end_id: 32})), false);
  assert.equal(needsLargeRangeConfirmation(v2Form({start_id: 1, end_id: 33})), true);
  assert.deepEqual(validateForm(v2Form({start_id: 1, end_id: 32})), {});
  const errors = validateForm(v2Form({start_id: 1, end_id: 33}), false, {largeRange: "confirm the long scan"});
  assert.deepEqual(errors, {large_range_confirmed: "confirm the long scan"});
  assert.deepEqual(validateForm(v2Form({start_id: 1, end_id: 247, large_range_confirmed: true})), {});
  // A single-address test never needs the range confirmation.
  assert.deepEqual(validateForm(v2Form({start_id: 1, end_id: 247, address: 200}), true), {});
});

test("the start payload carries the large-range confirmation only when it is needed", () => {
  assert.equal("large_range_confirmed" in startPayload(v2Form({start_id: 1, end_id: 32})), false);
  assert.equal(startPayload(v2Form({start_id: 1, end_id: 200, large_range_confirmed: true})).large_range_confirmed, true);
  assert.match(serviceYaml(v2Form({start_id: 1, end_id: 200, large_range_confirmed: true})), /large_range_confirmed: true/);
});

test("the large-range confirmation is never restored from browser storage", () => {
  const saved = safePreferences(v2Form({start_id: 1, end_id: 247, large_range_confirmed: true}));
  assert.equal(sanitizePreferences(saved).form.large_range_confirmed, false);
  assert.equal(sanitizePreferences(saved).form.end_id, 247);
});

test("a v2 register block may not run past register 65535", () => {
  assert.deepEqual(validateForm(v2Form({register_address: 65532, register_count: 4}), true), {});
  const errors = validateForm(v2Form({register_address: 65534, register_count: 3}), true, {registerBlock: "block too long"});
  assert.deepEqual(errors, {register_count: "block too long"});
});
