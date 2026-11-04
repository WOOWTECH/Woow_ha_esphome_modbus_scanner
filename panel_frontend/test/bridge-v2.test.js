import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {
  DEFAULTS, GENERIC_PROFILE, INTEGER_BOUNDS, boundsFor, estimatedDurationMs, outlastsScanLease, probedWithoutLease, formatRawValues, leaseNotice, safePreferences, sanitizePreferences,
  reconcileGateway, selectGateway, startPayload, supportedGateway, testPayload, validateForm,
} from "../src/model.js";
import {LEGACY_GATEWAY, V2_GATEWAY} from "./gateways.js";

const contract = JSON.parse(readFileSync(new URL(
  "../../custom_components/woow_esphome_modbus_scanner/modbus_scan/bridge_v2/contract.json", import.meta.url,
), "utf8"));

test("a v2 range scan estimated past the lease hard limit is flagged", () => {
  const form = {...selectGateway(DEFAULTS, V2_GATEWAY), start_id: 1, end_id: 247, timeout_ms: 2000, retries: 2};
  const estimate = estimatedDurationMs(form, V2_GATEWAY);
  assert.ok(estimate > contract.lease.hard_limit_ms);
  assert.equal(outlastsScanLease(estimate, V2_GATEWAY), true);
  assert.equal(outlastsScanLease(contract.lease.hard_limit_ms, V2_GATEWAY), false);
  // Legacy and mock gateways hold no Scan Lease, so there is nothing to outlast.
  assert.equal(outlastsScanLease(estimate, {provider: "mock", gateway_id: "mock:rs485-gateway"}), false);
});

test("the contract caps the inter-request delay of bridge v2 Gateways only", () => {
  const cap = contract.lease.inter_request_delay_max_ms;
  const v2 = selectGateway(DEFAULTS, V2_GATEWAY);
  assert.deepEqual(boundsFor(v2).inter_request_delay_ms, [0, cap]);
  assert.ok(validateForm({...v2, inter_request_delay_ms: cap + 1}, true).inter_request_delay_ms);
  const stored = {form: {provider: "esphome", bridge: "v2", gateway_id: V2_GATEWAY.gateway_id, inter_request_delay_ms: cap + 1}};
  assert.equal(reconcileGateway(sanitizePreferences(stored).form, V2_GATEWAY).inter_request_delay_ms, 100);
  // A Legacy Gateway has no Scan Lease and keeps its frozen 5000 ms.
  const v1 = selectGateway(DEFAULTS, LEGACY_GATEWAY);
  assert.deepEqual(boundsFor(v1).inter_request_delay_ms, [0, 5000]);
  assert.equal(validateForm({...v1, inter_request_delay_ms: cap + 1}, true).inter_request_delay_ms, undefined);
  assert.equal(INTEGER_BOUNDS.inter_request_delay_ms[1], 5000);
});

test("selecting a v2 gateway gives generic FC03 defaults and pauses every Pausable Poller", () => {
  const form = selectGateway({...DEFAULTS, safety_confirmed: true}, V2_GATEWAY);
  assert.equal(form.bridge, "v2");
  assert.equal(form.provider, "esphome");
  assert.equal(form.probe_type, "holding_register");
  assert.equal(form.register_count, 1);
  assert.equal(form.pause_normal_polling, true);
  assert.equal(form.safety_confirmed, false);
  assert.ok(supportedGateway(V2_GATEWAY));
  assert.deepEqual(validateForm({...form, address: 200, register_address: 0x1234}, true), {});
  assert.equal(testPayload({...form, address: 200}).address, 200);
  assert.equal(startPayload({...form, safety_confirmed: true}).pause_normal_polling, true);
});

test("v2 form accepts any register, FC04 and up to four registers, within hard limits", () => {
  const form = selectGateway(DEFAULTS, V2_GATEWAY);
  const ok = {...form, probe_type: "input_register", register_count: 4, timeout_ms: 2000, register_address: 9};
  assert.deepEqual(validateForm(ok, true), {});
  assert.deepEqual(boundsFor(form).register_count, [1, 4]);
  const bad = validateForm({...form, register_count: 5, timeout_ms: 99, probe_type: "device_identification"},
    true, {v2: "v2 limits"});
  assert.deepEqual(Object.keys(bad).sort(), ["probe_type", "register_count", "timeout_ms"]);
});

test("v2 preferences survive a reload and are clamped to the limits the Gateway reports", () => {
  const saved = safePreferences({...selectGateway(DEFAULTS, V2_GATEWAY), register_count: 3, address: 200});
  const restored = {form: reconcileGateway(sanitizePreferences(saved).form, V2_GATEWAY)};
  assert.equal(restored.form.bridge, "v2");
  assert.equal(restored.form.gateway_id, V2_GATEWAY.gateway_id);
  assert.equal(restored.form.register_count, 3);
  assert.equal(restored.form.address, 200);
  const clamped = {form: reconcileGateway(sanitizePreferences({form: {...saved.form, register_count: 50, timeout_ms: 5000,
    pause_normal_polling: false}}).form, V2_GATEWAY)};
  assert.equal(clamped.form.register_count, 1);
  assert.equal(clamped.form.timeout_ms, 1000);
  assert.equal(clamped.form.pause_normal_polling, true);  // which pollers is saved in HA
});

test("raw register values are shown in decimal and hex", () => {
  assert.equal(formatRawValues({raw_values: [1234, 65535]}), "1234 (0x04D2), 65535 (0xFFFF)");
  assert.equal(formatRawValues({raw_value: 7}), "7 (0x0007)");
  assert.equal(formatRawValues({}), null);
});

const PAUSED = [{index: 0, name: "meter", address: 1}, {index: 1, name: "inverter", address: 2}];

test("an active Scan Lease warns that paused devices' entity values are stale", () => {
  const notice = leaseNotice({lease_status: "active", lease_end_reason: null, paused_pollers: PAUSED});
  assert.deepEqual(notice, {state: "active", reason: null, stale: ["meter (1)", "inverter (2)"], endedAfter: null});
});

test("lease endings report their reason and no stale warning", () => {
  for (const reason of contract.lease.end_reasons) {
    const notice = leaseNotice({lease_status: "ended", lease_end_reason: reason, paused_pollers: PAUSED});
    assert.deepEqual(notice, {state: "ended", reason, stale: [], endedAfter: null});
  }
  assert.deepEqual(leaseNotice({lease_status: "unconfirmed", paused_pollers: PAUSED}),
    {state: "unconfirmed", reason: null, stale: ["meter (1)", "inverter (2)"], endedAfter: null});
});

test("a lease the Gateway ended early marks the Responders probed after it", () => {
  const results = {lease_status: "ended", lease_end_reason: "hard_limit", lease_ended_after_address: 120};
  const after = leaseNotice(results).endedAfter;
  assert.equal(after, 120);
  assert.equal(probedWithoutLease(after, {address: 120}), false);
  assert.equal(probedWithoutLease(after, {address: 121}), true);
  // HA's own release never marks rows, and malformed addresses are ignored.
  const released = leaseNotice({...results, lease_end_reason: "released"}).endedAfter;
  assert.equal(released, null);
  assert.equal(probedWithoutLease(released, {address: 200}), false);
  assert.equal(leaseNotice({...results, lease_ended_after_address: "120"}).endedAfter, null);
  assert.equal(probedWithoutLease(leaseNotice({})?.endedAfter, {address: 5}), false);
});

test("no lease, unknown states and hostile poller names render safely", () => {
  assert.equal(leaseNotice({lease_status: "none", paused_pollers: []}), null);
  assert.equal(leaseNotice(undefined), null);
  assert.equal(leaseNotice({lease_status: "bogus"}), null);
  const notice = leaseNotice({lease_status: "ended", lease_end_reason: "<script>", paused_pollers: [
    {index: 0, name: 42, address: 1}, "x", {index: 1, name: "a".repeat(200), address: 999},
  ]});
  assert.equal(notice.reason, null);
  assert.deepEqual(leaseNotice({lease_status: "active", paused_pollers: [{index: 0, name: 42, address: 1}]}).stale,
    ["#0 (1)"]);
});

test("before a Gateway reports limits, the panel's Generic Device Profile and slave range are the contract's", () => {
  const hard = contract.hard_limits;
  const {slave_min, slave_max, register_count_max, timeout_ms_min, timeout_ms_max, probe_types} = GENERIC_PROFILE.limits;
  assert.deepEqual({slave_min, slave_max, register_count_max, timeout_ms_min, timeout_ms_max, function_codes: GENERIC_PROFILE.function_codes},
    {slave_min: hard.slave_min, slave_max: hard.slave_max, register_count_max: hard.count_max,
      timeout_ms_min: hard.timeout_ms_min, timeout_ms_max: hard.timeout_ms_max, function_codes: hard.function_codes});
  assert.deepEqual(probe_types, ["holding_register", "input_register"]);  // FC03, FC04
  assert.deepEqual(INTEGER_BOUNDS.address, [hard.slave_min, hard.slave_max]);
  // Read from the contract file at build time, not copied (ADR 0005).
  const source = readFileSync(new URL("../src/model.js", import.meta.url), "utf8");
  assert.match(source, /import contract from "\.\.\/\.\.\/custom_components\/woow_esphome_modbus_scanner\/modbus_scan\/bridge_v2\/contract\.json" with \{type: "json"\}/);
  for (const file of ["model.js", "woow-esphome-modbus-scanner-panel.js", "i18n.js"]) {
    const text = readFileSync(new URL(`../src/${file}`, import.meta.url), "utf8");
    assert.doesNotMatch(text, /\b(247|2000|600000)\b/, file);
  }
});
