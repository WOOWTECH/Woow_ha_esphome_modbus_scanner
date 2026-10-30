import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {
  DEFAULTS, V2_LIMITS, boundsFor, formatRawValues, safePreferences, sanitizePreferences, selectGateway,
  supportedGateway, testPayload, validateForm,
} from "../src/model.js";

const contract = JSON.parse(readFileSync(new URL(
  "../../custom_components/woow_esphome_modbus_scanner/modbus_scan/bridge_v2/contract.json", import.meta.url,
), "utf8"));
const V2_GATEWAY = {
  provider: "esphome", gateway_id: "esphome:aabbccddee01", name: "ESPHome Modbus DDEE01",
  capabilities: ["bridge_v2", "holding_register", "input_register", "multi_register"], can_operate: true,
};

test("panel v2 limits are the contract's hard limits", () => {
  const hard = contract.hard_limits;
  assert.deepEqual(
    {slave: [V2_LIMITS.slave_min, V2_LIMITS.slave_max], count: V2_LIMITS.register_count_max,
      timeout: [V2_LIMITS.timeout_ms_min, V2_LIMITS.timeout_ms_max]},
    {slave: [hard.slave_min, hard.slave_max], count: hard.count_max,
      timeout: [hard.timeout_ms_min, hard.timeout_ms_max]},
  );
});

test("selecting a v2 gateway gives generic FC03 defaults without pausing", () => {
  const form = selectGateway({...DEFAULTS, safety_confirmed: true}, V2_GATEWAY);
  assert.equal(form.bridge, "v2");
  assert.equal(form.provider, "esphome");
  assert.equal(form.probe_type, "holding_register");
  assert.equal(form.register_count, 1);
  assert.equal(form.pause_normal_polling, false);
  assert.equal(form.safety_confirmed, false);
  assert.ok(supportedGateway(V2_GATEWAY));
  assert.deepEqual(validateForm({...form, address: 200, register_address: 0x1234}, true), {});
  assert.equal(testPayload({...form, address: 200}).address, 200);
});

test("v2 form accepts any register, FC04 and up to four registers, within hard limits", () => {
  const form = selectGateway(DEFAULTS, V2_GATEWAY);
  const ok = {...form, probe_type: "input_register", register_count: 4, timeout_ms: 2000, register_address: 9};
  assert.deepEqual(validateForm(ok, true), {});
  assert.deepEqual(boundsFor(form).register_count, [1, 4]);
  const bad = validateForm({...form, register_count: 5, timeout_ms: 99, probe_type: "device_identification",
    pause_normal_polling: true}, true, {v2: "v2 limits"});
  assert.deepEqual(Object.keys(bad).sort(), ["pause_normal_polling", "probe_type", "register_count", "timeout_ms"]);
});

test("v2 preferences survive a reload and are clamped to v2 limits", () => {
  const saved = safePreferences({...selectGateway(DEFAULTS, V2_GATEWAY), register_count: 3, address: 200});
  const restored = sanitizePreferences(saved);
  assert.equal(restored.form.bridge, "v2");
  assert.equal(restored.form.gateway_id, V2_GATEWAY.gateway_id);
  assert.equal(restored.form.register_count, 3);
  assert.equal(restored.form.address, 200);
  const clamped = sanitizePreferences({form: {...saved.form, register_count: 50, timeout_ms: 5000,
    pause_normal_polling: true}});
  assert.equal(clamped.form.register_count, 1);
  assert.equal(clamped.form.timeout_ms, 1000);
  assert.equal(clamped.form.pause_normal_polling, false);
});

test("raw register values are shown in decimal and hex", () => {
  assert.equal(formatRawValues({raw_values: [1234, 65535]}), "1234 (0x04D2), 65535 (0xFFFF)");
  assert.equal(formatRawValues({raw_value: 7}), "7 (0x0007)");
  assert.equal(formatRawValues({}), null);
});
