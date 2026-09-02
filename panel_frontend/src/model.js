export const DOMAIN = "woow_esphome_modbus_scanner";
export const SERVICES = Object.freeze([
  "list_gateways",
  "start_scan",
  "get_scan_status",
  "get_scan_results",
  "cancel_scan",
  "test_address",
]);
export const PROFILES = Object.freeze([
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
  mock_profile: "found_default", safety_confirmed: false,
});
export const INTEGER_BOUNDS = Object.freeze({
  start_id: [1, 247], end_id: [1, 247], address: [1, 247],
  register_address: [0, 65535], register_count: [1, 125],
  timeout_ms: [10, 10000], retries: [0, 5], inter_request_delay_ms: [0, 5000],
});
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

export function normalizeResponse(value) {
  if (value && typeof value === "object" && value.response && typeof value.response === "object") return value.response;
  return value;
}

export function validateForm(form, single = false, text = {}) {
  const errors = {};
  const names = single ? ["address", "register_address", "register_count", "timeout_ms", "retries", "inter_request_delay_ms"] : Object.keys(INTEGER_BOUNDS).filter((name) => name !== "address");
  for (const name of names) {
    const number = Number(form[name]);
    const [minimum, maximum] = INTEGER_BOUNDS[name];
    if (!Number.isInteger(number) || number < minimum || number > maximum) {
      errors[name] = text.integer ? text.integer(minimum, maximum) : `Enter a whole number from ${minimum} to ${maximum}.`;
    }
  }
  if (!single && Number(form.start_id) > Number(form.end_id)) errors.end_id = text.order || "End ID must be at least Start ID.";
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
    pause_normal_polling: form.pause_normal_polling === true, mock_profile: form.mock_profile,
  };
}
export function startPayload(form) {
  return {...sharedPayload(form), start_id: Number(form.start_id), end_id: Number(form.end_id), safety_confirmed: true};
}
export function testPayload(form) { return {...sharedPayload(form), address: Number(form.address)}; }

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
  if (PROFILES.includes(source.mock_profile)) form.mock_profile = source.mock_profile;
  if (source.pause_normal_polling === true || source.pause_normal_polling === false) form.pause_normal_polling = source.pause_normal_polling;
  if (source.safety_confirmed === true || source.safety_confirmed === false) form.safety_confirmed = source.safety_confirmed;
  // v0.2.0 is deliberately fixed to the one mock provider and gateway.
  form.provider = DEFAULTS.provider;
  form.gateway_id = DEFAULTS.gateway_id;
  return {form, advancedOpen: value.advancedOpen === true};
}

export function sanitizeRecent(value) {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.filter((item) => typeof item === "string" && UUID.test(item)))].slice(0, 10);
}

export function safePreferences(form, advancedOpen = false) {
  return sanitizePreferences({form: Object.fromEntries(Object.keys(DEFAULTS).map((key) => [key, form[key]])), advancedOpen});
}

export function errorMessage(error) {
  if (!error) return "Unknown error.";
  if (typeof error === "string") return error;
  return error.message || error.body?.message || error.error?.message || "Home Assistant did not return a usable response.";
}
