import test from "node:test";
import assert from "node:assert/strict";
import {
  DEFAULTS, GENERIC_PROFILE, SERVICES, boundsFor, profileLabel, safePreferences, sanitizePreferences,
  selectDeviceProfile, selectGateway, startPayload, testPayload, validateForm,
} from "../src/model.js";

const V2_GATEWAY = {
  provider: "esphome", gateway_id: "esphome:aabbccddee01", name: "ESPHome Modbus DDEE01",
  capabilities: ["bridge_v2", "holding_register", "input_register", "multi_register"], can_operate: true,
};
// The shape list_device_profiles returns for an imported profile.
const METER = {
  id: "acme-meter", name: "Acme Meter", vendor: "Acme", model: "M-100", version: "1.2.0",
  function_codes: [4], allowed_registers: [16, 17, 18, 19, 32], builtin: false, deletable: true,
  defaults: {slave_start: 2, slave_end: 5, register: 16, count: 2, timeout_ms: 300, inter_request_delay_ms: 0, retries: 0},
  fields: [],
  limits: {slave_min: 1, slave_max: 247, probe_types: ["input_register"], register_count_max: 4,
    allowed_registers: [16, 17, 18, 19, 32], timeout_ms_min: 100, timeout_ms_max: 2000},
};

test("the panel may call the Device Profile services", () => {
  for (const name of ["list_device_profiles", "import_device_profile", "export_device_profile", "delete_device_profile"]) {
    assert.ok(SERVICES.includes(name), name);
  }
});

test("the Generic Device Profile bounds apply to the mock gateway", () => {
  const bounds = boundsFor({...DEFAULTS});
  assert.deepEqual(bounds.register_count, [1, 4]);
  assert.deepEqual(bounds.timeout_ms, [100, 2000]);
  const errors = validateForm({...DEFAULTS, safety_confirmed: true, register_count: 5, timeout_ms: 50});
  assert.deepEqual(Object.keys(errors).sort(), ["register_count", "timeout_ms"]);
});

test("selecting a Device Profile applies its defaults and asks for consent again", () => {
  const form = selectDeviceProfile({...DEFAULTS, safety_confirmed: true, large_range_confirmed: true}, METER);
  assert.equal(form.device_profile_id, "acme-meter");
  assert.deepEqual(
    [form.start_id, form.end_id, form.probe_type, form.register_address, form.register_count, form.timeout_ms, form.inter_request_delay_ms, form.retries],
    [2, 5, "input_register", 16, 2, 300, 0, 0],
  );
  assert.equal(form.safety_confirmed, false);
  assert.equal(form.large_range_confirmed, false);
});

test("a profile without defaults keeps the form values but snaps to its first allowed register", () => {
  const bare = {...METER, defaults: {}, function_codes: [3, 4], limits: {...METER.limits, probe_types: ["holding_register", "input_register"]}};
  const form = selectDeviceProfile({...DEFAULTS, probe_type: "input_register", start_id: 9, end_id: 12, register_address: 7}, bare);
  assert.deepEqual([form.start_id, form.end_id, form.probe_type, form.register_address], [9, 12, "input_register", 16]);
  const holding = selectDeviceProfile({...DEFAULTS}, bare);
  assert.equal(holding.probe_type, "holding_register");
});

test("returning to the Generic Device Profile keeps the current values", () => {
  const meter = selectDeviceProfile({...DEFAULTS}, METER);
  const generic = selectDeviceProfile(meter, GENERIC_PROFILE);
  assert.equal(generic.device_profile_id, "generic");
  assert.equal(generic.register_address, 16);
});

test("the form enforces the selected profile's function codes and register allowlist", () => {
  const form = {...selectDeviceProfile({...DEFAULTS}, METER), safety_confirmed: true};
  assert.deepEqual(validateForm(form, false, {}, METER), {});
  const errors = validateForm({...form, probe_type: "holding_register", register_address: 20}, false,
    {profileProbe: "probe not allowed", profileRegister: (list) => `use ${list}`}, METER);
  assert.equal(errors.probe_type, "probe not allowed");
  assert.equal(errors.register_address, "use 16, 17, 18, 19, 32");
  // Every register of the block is read: 32 is allowed, 33 is not.
  const block = validateForm({...form, register_address: 32, register_count: 2}, false, {profileRegister: (list) => `use ${list}`}, METER);
  assert.equal(block.register_address, "use 16, 17, 18, 19, 32");
  assert.deepEqual(validateForm({...form, register_address: 16, register_count: 4}, false, {}, METER), {});
});

test("profile limits intersect with the gateway's limits", () => {
  const tight = {...METER, limits: {...METER.limits, register_count_max: 2, timeout_ms_min: 200, timeout_ms_max: 900}};
  const v2 = {...selectGateway(DEFAULTS, V2_GATEWAY), safety_confirmed: true};
  const bounds = boundsFor(v2, tight);
  assert.deepEqual(bounds.register_count, [1, 2]);
  assert.deepEqual(bounds.timeout_ms, [200, 900]);
  // Generic allows the mock identification probe, but Bridge v2 still refuses it.
  assert.ok(validateForm({...v2, probe_type: "device_identification"}, false, {}, GENERIC_PROFILE).probe_type);
});

test("payloads name the selected Device Profile and omit it for Generic", () => {
  const generic = {...DEFAULTS, safety_confirmed: true};
  assert.equal("device_profile_id" in startPayload(generic), false);
  const meter = {...selectDeviceProfile(generic, METER), safety_confirmed: true};
  assert.equal(startPayload(meter).device_profile_id, "acme-meter");
  assert.equal(testPayload(meter).device_profile_id, "acme-meter");
});

test("the selected Device Profile id is remembered, but only a well-formed one", () => {
  const saved = safePreferences({...DEFAULTS, device_profile_id: "acme-meter"});
  assert.equal(saved.form.device_profile_id, "acme-meter");
  for (const bad of ["../etc", "Acme Meter", 7, "", "x".repeat(65)]) {
    assert.equal(sanitizePreferences({form: {device_profile_id: bad}}).form.device_profile_id, "generic");
  }
});

test("results are labelled with the Device Profile they ran with", () => {
  assert.equal(profileLabel({device_profile: {id: "acme-meter", name: "Acme Meter", version: "1.2.0"}}), "Acme Meter 1.2.0 (acme-meter)");
  assert.equal(profileLabel({}), null);
});
