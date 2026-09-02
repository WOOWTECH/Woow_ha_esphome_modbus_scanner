import test from "node:test";
import assert from "node:assert/strict";
import {
  DEFAULTS, SERVICES, normalizeResponse, safePreferences, sanitizePreferences,
  sanitizeRecent, startPayload, testPayload, validateForm,
} from "../src/model.js";

test("defines the exact six public services", () => {
  assert.deepEqual(SERVICES, ["list_gateways", "start_scan", "get_scan_status", "get_scan_results", "cancel_scan", "test_address"]);
});

test("normalizes Home Assistant wrapped and direct service responses", () => {
  assert.deepEqual(normalizeResponse({response: {scan_id: "id"}}), {scan_id: "id"});
  assert.deepEqual(normalizeResponse({scan_id: "id"}), {scan_id: "id"});
});

test("constructs typed start and single-address payloads", () => {
  const form = {...DEFAULTS, start_id: "2", end_id: "9", address: "7", safety_confirmed: true};
  const start = startPayload(form);
  assert.equal(start.start_id, 2);
  assert.equal(start.end_id, 9);
  assert.equal(start.safety_confirmed, true);
  assert.equal(typeof start.timeout_ms, "number");
  const single = testPayload(form);
  assert.equal(single.address, 7);
  assert.equal("safety_confirmed" in single, false);
  assert.equal("start_id" in single, false);
});

test("validates all documented bounds, ordering, confirmation, and localized errors", () => {
  assert.deepEqual(validateForm({...DEFAULTS, safety_confirmed: true}), {});
  const errors = validateForm({...DEFAULTS, start_id: 0, end_id: 248, timeout_ms: 9, retries: 6});
  assert.deepEqual(Object.keys(errors).sort(), ["end_id", "retries", "safety_confirmed", "start_id", "timeout_ms"]);
  assert.match(validateForm({...DEFAULTS, start_id: 12, end_id: 2, safety_confirmed: true}).end_id, /at least/);
  assert.equal(validateForm({...DEFAULTS, start_id: 0}, false, {integer:(a,b)=>`${a}到${b}`}).start_id, "1到247");
  assert.deepEqual(validateForm({...DEFAULTS, address: 247}, true), {});
});

test("preferences use an allowlist and never persist secret-shaped extras", () => {
  const saved = safePreferences({...DEFAULTS, token: "secret", host: "private", frame: "raw"}, true);
  assert.equal(saved.advancedOpen, true);
  assert.equal(saved.form.token, undefined);
  assert.equal(saved.form.host, undefined);
  assert.equal(saved.form.frame, undefined);
  assert.deepEqual(Object.keys(saved.form).sort(), Object.keys(DEFAULTS).sort());
});

test("malformed and obsolete preferences are sanitized by exact type, enum, and bounds", () => {
  const malformed = sanitizePreferences({advancedOpen: "true", form: {
    ...DEFAULTS, provider:"evil", gateway_id:"private", start_id:"2", end_id:999,
    address:7, retries:2.5, timeout_ms:10, pause_normal_polling:1,
    safety_confirmed:"true", probe_type:"write_register", mock_profile:"obsolete",
    token:"secret",
  }});
  assert.deepEqual(malformed, {form:{...DEFAULTS, address:7, timeout_ms:10}, advancedOpen:false});
  assert.deepEqual(sanitizePreferences(null), {form:{...DEFAULTS}, advancedOpen:false});
  assert.deepEqual(sanitizePreferences({form:[]}), {form:{...DEFAULTS}, advancedOpen:false});
});

test("recent storage accepts only unique canonical UUIDs", () => {
  const valid = "11111111-1111-4111-8111-111111111111";
  assert.deepEqual(sanitizeRecent([valid, valid, "id", 4, {}, "11111111-1111-0111-8111-111111111111"]), [valid]);
  assert.deepEqual(sanitizeRecent({0:valid}), []);
});
