import {PHYSICAL_PROFILE} from "./profile-generated.js";
export {PHYSICAL_PROFILE} from "./profile-generated.js";
export const DOMAIN = "woow_esphome_modbus_scanner";
export const SERVICES = Object.freeze([
  "check_gateway", "get_history",
  "list_gateways",
  "start_scan",
  "get_scan_status",
  "get_scan_results",
  "cancel_scan",
  "test_address",
  "list_device_profiles", "import_device_profile", "export_device_profile", "delete_device_profile",
]);
export const MOCK_SCENARIOS = Object.freeze([
  "found_default", "all_offline", "partial_timeout", "modbus_exception",
  "possible_collision", "gateway_disconnect",
]);
export const OUTCOMES = Object.freeze([
  "identified", "responded", "modbus_exception", "timeout",
  "possible_collision", "gateway_error",
]);
export const PROBE_TYPES = Object.freeze(["device_identification", "holding_register", "input_register"]);
export const DEFAULTS = Object.freeze({
  provider: "mock", gateway_id: "mock:rs485-gateway", start_id: 1, end_id: 12,
  address: 1, probe_type: "device_identification", register_address: 0,
  register_count: 1, timeout_ms: 500, retries: 1,
  inter_request_delay_ms: 100, pause_normal_polling: false,
  mock_scenario: "found_default", safety_confirmed: false, large_range_confirmed: false, bridge: "",
  device_profile_id: "generic",
});
/** The built-in Generic Device Profile, as list_device_profiles returns it (used until the list loads). */
export const GENERIC_PROFILE = Object.freeze({
  id: "generic", name: "Generic Device Profile", vendor: "Generic", model: "Any Modbus RTU device", version: "1",
  function_codes: [3, 4], allowed_registers: null, defaults: {}, fields: [], builtin: true, deletable: false,
  limits: Object.freeze({slave_min: 1, slave_max: 247, probe_types: ["device_identification", "holding_register", "input_register"],
    register_count_max: 4, allowed_registers: null, timeout_ms_min: 100, timeout_ms_max: 2000}),
});
const PROFILE_ID = /^[a-z0-9][a-z0-9_-]{0,63}$/;
const FUNCTION_CODE_PROBES = Object.freeze({3: "holding_register", 4: "input_register"});
/** Ranges with more IDs than this need a second confirmation (the service requires large_range_confirmed). */
export const LARGE_RANGE_THRESHOLD = 32;
export const INTEGER_BOUNDS = Object.freeze({
  start_id: [1, 247], end_id: [1, 247], address: [1, 247],
  register_address: [0, 65535], register_count: [1, 125],
  timeout_ms: [10, 10000], retries: [0, 5], inter_request_delay_ms: [0, 5000],
});
export const PHYSICAL_REGISTERS = PHYSICAL_PROFILE.allowed_registers;
export const PHYSICAL_DEFAULTS = PHYSICAL_PROFILE.defaults;
const PHYSICAL_GATEWAY = /^esphome:[0-9a-f]{12}$/;
/** Hard limits of bridge v2 Gateways (the contract file's hard_limits; a model test checks them). */
export const V2_LIMITS = Object.freeze({
  slave_min: 1, slave_max: 247, register_count_max: 4, timeout_ms_min: 100, timeout_ms_max: 2000,
  probe_types: Object.freeze(["holding_register", "input_register"]),
});
export const V2_DEFAULTS = Object.freeze({
  probe_type: "holding_register", register_address: 0, register_count: 1, timeout_ms: 1000,
  retries: 0, inter_request_delay_ms: 100, pause_normal_polling: true,
});
export function isBridgeV2(gateway) {
  return gateway?.provider === "esphome" && Array.isArray(gateway.capabilities) && gateway.capabilities.includes("bridge_v2");
}
const isV2Form = (form) => form.provider === "esphome" && form.bridge === "v2";
/** The gateway's bounds intersected with the selected Device Profile's limits. */
export function boundsFor(form, profile = GENERIC_PROFILE) {
  const gateway = gatewayBoundsFor(form);
  const l = profile?.limits;
  if (!l) return gateway;
  const meet = ([low, high], min, max) => [Math.max(low, min), Math.min(high, max)];
  return {...gateway,
    start_id: meet(gateway.start_id, l.slave_min, l.slave_max), end_id: meet(gateway.end_id, l.slave_min, l.slave_max),
    address: meet(gateway.address, l.slave_min, l.slave_max), register_count: meet(gateway.register_count, 1, l.register_count_max),
    timeout_ms: meet(gateway.timeout_ms, l.timeout_ms_min, l.timeout_ms_max)};
}
function gatewayBoundsFor(form) {
  if (isV2Form(form)) {
    const slaves = [V2_LIMITS.slave_min, V2_LIMITS.slave_max];
    return {...INTEGER_BOUNDS, start_id: slaves, end_id: slaves, address: slaves,
      register_count: [1, V2_LIMITS.register_count_max], timeout_ms: [V2_LIMITS.timeout_ms_min, V2_LIMITS.timeout_ms_max]};
  }
  const l = PHYSICAL_PROFILE.limits;
  return form.provider === "esphome" ? {...INTEGER_BOUNDS, start_id:[l.slave_min,l.slave_max], end_id:[l.slave_min,l.slave_max], address:[l.slave_min,l.slave_max], register_count:[l.register_count,l.register_count], timeout_ms:[l.timeout_ms,l.timeout_ms], retries:[0,l.retries_max], inter_request_delay_ms:[0,l.inter_request_delay_max_ms]} : INTEGER_BOUNDS;
}
/** Apply a Device Profile's defaults; values it does not define stay, unless the profile forbids them. */
export function selectDeviceProfile(form, profile) {
  const d = profile?.defaults || {};
  const next = {...form, device_profile_id: profile?.id || "generic", safety_confirmed: false, large_range_confirmed: false};
  const mapping = {slave_start: "start_id", slave_end: "end_id", register: "register_address", count: "register_count",
    timeout_ms: "timeout_ms", inter_request_delay_ms: "inter_request_delay_ms", retries: "retries"};
  for (const [key, target] of Object.entries(mapping)) if (Number.isInteger(d[key])) next[target] = d[key];
  if (FUNCTION_CODE_PROBES[d.function_code]) next.probe_type = FUNCTION_CODE_PROBES[d.function_code];
  const probes = profile?.limits?.probe_types;
  if (Array.isArray(probes) && probes.length && !probes.includes(next.probe_type)) next.probe_type = probes[0];
  const allowed = profile?.allowed_registers;
  if (Array.isArray(allowed) && allowed.length && !allowed.includes(Number(next.register_address))) next.register_address = allowed[0];
  return next;
}
/** "Name version (id)" from a Scan status or result, or null when the Scan predates Device Profiles. */
export function profileLabel(record) {
  const p = record?.device_profile;
  if (!p || typeof p.id !== "string") return null;
  return `${p.name || p.id}${p.version ? ` ${p.version}` : ""} (${p.id})`;
}
export function selectGateway(form, gateway) {
  if (isBridgeV2(gateway)) {
    return {...form, ...V2_DEFAULTS, provider:gateway.provider, gateway_id:gateway.gateway_id, bridge:"v2", safety_confirmed:false};
  }
  const defaults = gateway.provider === "esphome" ? PHYSICAL_DEFAULTS : DEFAULTS;
  return {...form, ...defaults, provider:gateway.provider, gateway_id:gateway.gateway_id, bridge:gateway.provider === "esphome" ? "v1" : "", safety_confirmed:false};
}
/** Raw register evidence in decimal and hex, e.g. "1234 (0x04D2), 65535 (0xFFFF)". */
export function formatRawValues(row) {
  const values = Array.isArray(row?.raw_values) ? row.raw_values : Number.isInteger(row?.raw_value) ? [row.raw_value] : [];
  const shown = values.filter((value) => Number.isInteger(value) && value >= 0 && value <= 65535);
  return shown.length ? shown.map((value) => `${value} (0x${value.toString(16).toUpperCase().padStart(4, "0")})`).join(", ") : null;
}
const LEASE_STATES = ["active", "ended", "unconfirmed"];
const LEASE_END_REASONS = ["released", "idle", "hard_limit", "superseded"];
/**
 * What the panel shows about a Scan's Scan Lease, or null when no lease applies.
 * `stale` names the paused devices whose entity values are frozen while the lease may hold.
 */
export function leaseNotice(status) {
  const state = status?.lease_status;
  if (!LEASE_STATES.includes(state)) return null;
  const pollers = Array.isArray(status.paused_pollers) ? status.paused_pollers : [];
  const label = (poller) => {
    const name = typeof poller.name === "string" ? poller.name.slice(0, 64) : `#${Number.isInteger(poller.index) ? poller.index : "?"}`;
    return Number.isInteger(poller.address) && poller.address >= 1 && poller.address <= 247 ? `${name} (${poller.address})` : name;
  };
  return {
    state,
    reason: state === "ended" && LEASE_END_REASONS.includes(status.lease_end_reason) ? status.lease_end_reason : null,
    stale: state === "ended" ? [] : pollers.filter((poller) => poller && typeof poller === "object").map(label),
  };
}
const wholeNumber = (value) => (typeof value === "number" || (typeof value === "string" && /^[+-]?\d+$/.test(value))) && Number.isInteger(Number(value));
/** Estimated range-scan duration: ID count x (timeout + inter-request delay); null for an invalid range. */
export function estimatedDurationMs(form) {
  const fields = [form.start_id, form.end_id, form.timeout_ms, form.inter_request_delay_ms];
  if (!fields.every(wholeNumber) || Number(form.start_id) > Number(form.end_id)) return null;
  return (Number(form.end_id) - Number(form.start_id) + 1) * (Number(form.timeout_ms) + Number(form.inter_request_delay_ms));
}
export function needsLargeRangeConfirmation(form) {
  return wholeNumber(form.start_id) && wholeNumber(form.end_id) && Number(form.end_id) - Number(form.start_id) + 1 > LARGE_RANGE_THRESHOLD;
}
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

export function normalizeResponse(value) {
  if (value && typeof value === "object" && value.response && typeof value.response === "object") return value.response;
  return value;
}

export function validateForm(form, single = false, text = {}, profile = GENERIC_PROFILE) {
  const errors = {};
  const names = single ? ["address", "register_address", "register_count", "timeout_ms", "retries", "inter_request_delay_ms"] : Object.keys(INTEGER_BOUNDS).filter((name) => name !== "address");
  for (const name of names) {
    const number = Number(form[name]);
    const [minimum, maximum] = boundsFor(form, profile)[name];
    const raw = form[name];
    const integer = typeof raw === "number" || (typeof raw === "string" && /^[+-]?\d+$/.test(raw));
    if (!integer || !Number.isInteger(number) || number < minimum || number > maximum) {
      errors[name] = text.integer ? text.integer(minimum, maximum) : `Enter a whole number from ${minimum} to ${maximum}.`;
    }
  }
  if (isV2Form(form)) {
    const message = text.v2 || "Bridge v2 reads FC03/FC04 only.";
    if (!V2_LIMITS.probe_types.includes(form.probe_type)) errors.probe_type = message;
    if (!errors.register_address && !errors.register_count && Number(form.register_address) + Number(form.register_count) - 1 > 65535) {
      errors.register_count = text.registerBlock || "The register block must end at or before register 65535.";
    }
  } else if (form.provider === "esphome") {
    const message = text.physical || "Physical bridge requires FC03, one allowed register, 700 ms timeout and polling pause.";
    if (form.probe_type !== "holding_register") errors.probe_type = message;
    if (!PHYSICAL_REGISTERS.includes(Number(form.register_address))) errors.register_address = message;
    if (form.pause_normal_polling !== true) errors.pause_normal_polling = message;
  }
  const probes = profile?.limits?.probe_types;
  if (!errors.probe_type && Array.isArray(probes) && !probes.includes(form.probe_type)) {
    errors.probe_type = text.profileProbe || "The selected Device Profile does not allow this probe type.";
  }
  const allowed = profile?.allowed_registers;
  if (!errors.register_address && Array.isArray(allowed) && !allowed.includes(Number(form.register_address))) {
    errors.register_address = text.profileRegister ? text.profileRegister(allowed.join(", ")) : `The selected Device Profile allows registers ${allowed.join(", ")} only.`;
  }
  if (!single && Number(form.start_id) > Number(form.end_id)) errors.end_id = text.order || "End ID must be at least Start ID.";
  if (!single && !errors.start_id && !errors.end_id && needsLargeRangeConfirmation(form) && form.large_range_confirmed !== true) {
    errors.large_range_confirmed = text.largeRange || `Confirm scanning more than ${LARGE_RANGE_THRESHOLD} IDs before starting.`;
  }
  if (!single && form.safety_confirmed !== true) errors.safety_confirmed = text.safety || "Confirm the best-effort scan warning before starting.";
  if (!form.gateway_id) errors.gateway_id = text.gateway || "Select an available gateway.";
  return errors;
}

function sharedPayload(form) {
  return {
    provider: form.provider, gateway_id: form.gateway_id, probe_type: form.probe_type,
    register_address: Number(form.register_address), register_count: Number(form.register_count),
    timeout_ms: Number(form.timeout_ms), retries: Number(form.retries),
    inter_request_delay_ms: Number(form.inter_request_delay_ms),
    pause_normal_polling: form.pause_normal_polling === true,
    ...(form.provider === "mock" ? {mock_scenario: form.mock_scenario} : {}),
    ...(form.device_profile_id && form.device_profile_id !== "generic" ? {device_profile_id: form.device_profile_id} : {}),
  };
}
export function startPayload(form) {
  return {...sharedPayload(form), start_id: Number(form.start_id), end_id: Number(form.end_id), safety_confirmed: true,
    ...(needsLargeRangeConfirmation(form) ? {large_range_confirmed: true} : {})};
}
export function testPayload(form) { return {...sharedPayload(form), address: Number(form.address)}; }
export function supportedGateway(gateway) {
  return gateway?.provider === "mock" || isBridgeV2(gateway) || (gateway?.provider === "esphome" && gateway.profile?.profile_hash === PHYSICAL_PROFILE.profile_hash);
}
export function serviceYaml(form, profile = GENERIC_PROFILE) {
  if (Object.keys(validateForm(form, false, {}, profile)).length) throw new Error("Confirm the warning and correct the scan parameters first.");
  const lines = Object.entries(startPayload(form)).map(([key, value]) => `  ${key}: ${JSON.stringify(value)}`);
  return `action: ${DOMAIN}.start_scan\ndata:\n${lines.join("\n")}\n`;
}

/** Deliberately excludes gateway identity, vendor strings, free text and credentials. */
export function evidenceExport(status, results) {
  const integer = (value, max) => Number.isInteger(value) && value >= 0 && value <= max ? value : null;
  return {
    schema_version:1, source:DOMAIN, best_effort:true, uniqueness_guaranteed:false,
    provider:["mock","esphome"].includes(results?.provider) ? results.provider : "unknown",
    status:["running","completed","cancelled","failed"].includes(results?.status) ? results.status : "unknown",
    recovery_status:["unknown","pending","verified","failed"].includes(status?.recovery_status) ? status.recovery_status : "unknown",
    outcome_counts:Object.fromEntries(OUTCOMES.map((name) => [name,integer(results?.outcome_counts?.[name],247) ?? 0])),
    responders:(results?.responders || []).slice(0,247).map((row) => ({
      address:integer(row.address,247), outcome:OUTCOMES.includes(row.outcome) ? row.outcome : "unknown",
      latency_ms:integer(row.latency_ms,10000), exception_code:integer(row.exception_code,255),
      register_address:integer(row.register_address,65535), raw_value:integer(row.raw_value,65535),
      raw_values:Array.isArray(row.raw_values) ? row.raw_values.slice(0,4).map((value) => integer(value,65535)) : null,
      attempts:integer(row.attempts,6),
    })),
    privacy:"Identities and free-text fields omitted; numeric register evidence retained.",
  };
}

/** Return only validated, non-secret preferences from untrusted browser storage. */
export function sanitizePreferences(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {form: {...DEFAULTS}, advancedOpen: false};
  const source = value.form;
  if (!source || typeof source !== "object" || Array.isArray(source) || Object.getPrototypeOf(source) !== Object.prototype) {
    return {form: {...DEFAULTS}, advancedOpen: value.advancedOpen === true};
  }
  const form = {...DEFAULTS};
  for (const [name, [minimum, maximum]] of Object.entries(INTEGER_BOUNDS)) {
    if (typeof source[name] === "number" && Number.isInteger(source[name]) && source[name] >= minimum && source[name] <= maximum) form[name] = source[name];
  }
  if (PROBE_TYPES.includes(source.probe_type)) form.probe_type = source.probe_type;
  // mock_profile is the deprecated pre-0.5 key for the same Mock Scenario.
  const mockScenario = source.mock_scenario ?? source.mock_profile;
  if (MOCK_SCENARIOS.includes(mockScenario)) form.mock_scenario = mockScenario;
  if (source.pause_normal_polling === true || source.pause_normal_polling === false) form.pause_normal_polling = source.pause_normal_polling;
  // Checked against the loaded profile list later; an unknown id falls back to Generic there.
  if (typeof source.device_profile_id === "string" && PROFILE_ID.test(source.device_profile_id)) form.device_profile_id = source.device_profile_id;
  // A stored acknowledgement is not consent for a new browser session.
  form.safety_confirmed = false;
  form.large_range_confirmed = false;
  if (source.provider === "esphome" && source.bridge === "v2") {
    form.provider = "esphome";
    form.bridge = "v2";
    form.gateway_id = typeof source.gateway_id === "string" && PHYSICAL_GATEWAY.test(source.gateway_id) ? source.gateway_id : "";
    const [countMin, countMax] = [1, V2_LIMITS.register_count_max];
    if (form.register_count < countMin || form.register_count > countMax) form.register_count = V2_DEFAULTS.register_count;
    if (form.timeout_ms < V2_LIMITS.timeout_ms_min || form.timeout_ms > V2_LIMITS.timeout_ms_max) form.timeout_ms = V2_DEFAULTS.timeout_ms;
    if (!V2_LIMITS.probe_types.includes(form.probe_type)) form.probe_type = V2_DEFAULTS.probe_type;
    // A v2 Scan pauses every Pausable Poller on its Bus; per-poller choice is a later release.
    form.pause_normal_polling = true;
  } else if (source.provider === "esphome") {
    form.provider = "esphome";
    form.bridge = "v1";
    form.gateway_id = typeof source.gateway_id === "string" && PHYSICAL_GATEWAY.test(source.gateway_id) ? source.gateway_id : "";
    // Migrate old incompatible preferences, without silently changing provider.
    for (const key of ["probe_type", "register_count", "timeout_ms", "pause_normal_polling"]) form[key] = PHYSICAL_DEFAULTS[key];
    if (!PHYSICAL_REGISTERS.includes(form.register_address)) form.register_address = PHYSICAL_DEFAULTS.register_address;
    for (const key of ["start_id", "end_id", "address"]) if (form[key] > PHYSICAL_PROFILE.limits.slave_max) form[key] = PHYSICAL_DEFAULTS[key];
    if (form.start_id > form.end_id) {form.start_id = PHYSICAL_DEFAULTS.start_id; form.end_id = PHYSICAL_DEFAULTS.end_id;}
  }
  return {form, advancedOpen: value.advancedOpen === true};
}

export function sanitizeRecent(value) {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.filter((item) => typeof item === "string" && UUID.test(item)))].slice(0, 10);
}

export function safePreferences(form, advancedOpen = false) {
  const values = Object.fromEntries(Object.keys(DEFAULTS).map((key) => {
    const value = form[key];
    return [key, key in INTEGER_BOUNDS && typeof value === "string" && /^[+-]?\d+$/.test(value) ? Number(value) : value];
  }));
  return sanitizePreferences({form: values, advancedOpen});
}

export function errorMessage(error) {
  if (!error) return "Unknown error.";
  if (typeof error === "string") return error;
  return error.message || error.body?.message || error.error?.message || "Home Assistant did not return a usable response.";
}
