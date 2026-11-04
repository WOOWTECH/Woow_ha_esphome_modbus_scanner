import test from "node:test";
import assert from "node:assert/strict";
import {
  DEFAULTS, SERVICES, normalizeResponse, safePreferences, sanitizePreferences,
  sanitizeRecent, startPayload, testPayload, validateForm, selectGateway, boundsFor, reconcileGateway,
} from "../src/model.js";
import {LEGACY_GATEWAY, LEGACY_REGISTERS} from "./gateways.js";

test("defines the exact public services", () => {
  assert.deepEqual(SERVICES, ["check_gateway", "get_history", "list_gateways", "set_pausable_pollers", "start_scan", "get_scan_status", "get_scan_results", "cancel_scan", "test_address",
    "list_device_profiles", "import_device_profile", "export_device_profile", "delete_device_profile"]);
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

test("physical gateway selection supplies a valid FC03 profile and resets consent", () => {
  const form = selectGateway({...DEFAULTS, safety_confirmed:true}, LEGACY_GATEWAY);
  assert.deepEqual(validateForm(form, true), {});
  assert.equal(form.probe_type, "holding_register");
  assert.equal(form.register_address, 25089);
  assert.equal(form.register_count, 1);
  assert.equal(form.timeout_ms, 700);
  assert.equal(form.pause_normal_polling, true);
  assert.equal(form.safety_confirmed, false);
  assert.equal("mock_profile" in testPayload(form), false);
  assert.equal(selectGateway(form, {provider:"mock", gateway_id:"mock:rs485-gateway"}).timeout_ms, 500);
});

test("physical limits, probe, whitelist and polling are validated before a call", () => {
  const form = selectGateway(DEFAULTS, LEGACY_GATEWAY);
  assert.deepEqual(boundsFor(form).end_id, [1,32]);
  assert.deepEqual(boundsFor(form).register_count, [1,1]);
  assert.deepEqual(boundsFor(form).timeout_ms, [700,700]);
  for (const register_address of LEGACY_REGISTERS) assert.deepEqual(validateForm({...form,register_address},true), {});
  for (const [key, value] of Object.entries({address:33, register_count:2, timeout_ms:500, register_address:0, probe_type:"input_register", pause_normal_polling:false})) {
    assert.ok(validateForm({...form,[key]:value},true)[key], key);
  }
});

test("persisted physical selection and edited DOM numbers round-trip", () => {
  const form = {...selectGateway(DEFAULTS, LEGACY_GATEWAY), end_id:"8", register_address:"24833", retries:"2", inter_request_delay_ms:"750", safety_confirmed:true, host:"private", token:"secret"};
  const restored = sanitizePreferences(JSON.parse(JSON.stringify(safePreferences(form,true))));
  assert.equal(restored.form.gateway_id, form.gateway_id);
  assert.equal(restored.form.provider, "esphome");
  assert.equal(restored.form.end_id, 8);
  assert.equal(restored.form.register_address, 24833);
  assert.equal(restored.form.retries, 2);
  assert.equal(restored.form.inter_request_delay_ms, 750);
  assert.equal(restored.form.safety_confirmed, false);
  assert.equal(restored.form.host, undefined);
  assert.equal(restored.form.token, undefined);
});

test("old incompatible physical preferences migrate to the Gateway's limits without selecting mock", () => {
  const stored = sanitizePreferences({form:{...DEFAULTS,provider:"esphome",gateway_id:"esphome:aabbccddeeff",end_id:247}}).form;
  assert.equal(stored.provider,"esphome");
  const form = reconcileGateway(stored, LEGACY_GATEWAY);
  assert.equal(form.provider,"esphome");
  assert.deepEqual(validateForm(form,true),{});
  assert.equal(form.end_id,3);
  const invalid = sanitizePreferences({form:{...form,gateway_id:"https://private/token"}}).form;
  assert.equal(invalid.provider,"esphome");
  assert.equal(invalid.gateway_id,"");
  assert.ok(validateForm(invalid,true).gateway_id);
});

test("empty, boolean and scientific-notation numeric inputs are not silently coerced", () => {
  for (const value of ["", " ", true, null, "1e2"]) assert.ok(validateForm({...DEFAULTS,retries:value},true).retries);
  assert.equal(validateForm({...DEFAULTS,retries:"2"},true).retries,undefined);
});

test("recent storage accepts only unique canonical UUIDs", () => {
  const valid = "11111111-1111-4111-8111-111111111111";
  assert.deepEqual(sanitizeRecent([valid, valid, "id", 4, {}, "11111111-1111-0111-8111-111111111111"]), [valid]);
  assert.deepEqual(sanitizeRecent({0:valid}), []);
});

test("mock payloads name the Mock Scenario with mock_scenario, never the deprecated alias", () => {
  const form = {...DEFAULTS, mock_scenario: "all_offline", safety_confirmed: true};
  for (const payload of [startPayload(form), testPayload(form)]) {
    assert.equal(payload.mock_scenario, "all_offline");
    assert.equal("mock_profile" in payload, false);
  }
});

test("a Mock Scenario saved under the deprecated preference key is kept", () => {
  assert.equal(sanitizePreferences({form: {mock_profile: "partial_timeout"}}).form.mock_scenario, "partial_timeout");
  assert.equal(sanitizePreferences({form: {mock_scenario: "all_offline"}}).form.mock_scenario, "all_offline");
  assert.equal("mock_profile" in sanitizePreferences({form: {mock_profile: "all_offline"}}).form, false);
});

test("the selected Gateway's reported limits bound the form", () => {
  // The shape ProbeLimits.as_dict gives in list_gateways, narrowed below the contract's hard limits.
  const gateway = {provider: "esphome", gateway_id: "esphome:aabbccddee02", capabilities: ["bridge_v2"], limits: {
    slave_min: 1, slave_max: 10, probe_types: ["holding_register", "input_register"], register_count_max: 2,
    allowed_registers: null, timeout_ms_min: 100, timeout_ms_max: 2000, inter_request_delay_ms_max: 3000,
    pause_normal_polling_required: false, pause_normal_polling_supported: true, attempt_overhead_ms: 300, defaults: {}}};
  const form = {...selectGateway(DEFAULTS, gateway), safety_confirmed: true};
  assert.deepEqual(boundsFor(form).address, [1, 10]);
  assert.deepEqual(boundsFor(form).end_id, [1, 10]);
  assert.deepEqual(boundsFor(form).register_count, [1, 2]);
  assert.ok(validateForm({...form, address: 11}, true).address);
  assert.ok(validateForm({...form, register_count: 3}, true).register_count);
});

test("selecting a Gateway fills the form from the defaults it reports", () => {
  const gateway = {provider: "esphome", gateway_id: "esphome:aabbccddee03", capabilities: [], limits: {
    ...LEGACY_GATEWAY.limits, allowed_registers: [7, 8], defaults: {...LEGACY_GATEWAY.limits.defaults, register_address: 7, end_id: 5}}};
  const form = selectGateway({...DEFAULTS, safety_confirmed: true}, gateway);
  assert.equal(form.register_address, 7);
  assert.equal(form.end_id, 5);
  assert.deepEqual(validateForm(form, true), {});
  // Only the Gateway's allowlist, probe types and polling requirement apply.
  for (const [key, value] of Object.entries({register_address: 9, probe_type: "input_register", pause_normal_polling: false})) {
    assert.ok(validateForm({...form, [key]: value}, true)[key], key);
  }
});

test("refreshing the gateway list keeps what the user typed once the Gateway's limits are known", () => {
  const form = {...reconcileGateway(sanitizePreferences({form: {provider: "esphome", gateway_id: LEGACY_GATEWAY.gateway_id}}).form, LEGACY_GATEWAY), end_id: "40"};
  assert.equal(reconcileGateway(form, {...LEGACY_GATEWAY}).end_id, "40");
  assert.ok(validateForm(form, false).end_id);
});
