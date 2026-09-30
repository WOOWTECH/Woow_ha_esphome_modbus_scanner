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
export const PHYSICAL_REGISTERS = Object.freeze([0x6201, 0x6202, 0x6203, 0x6205, 0x6206, 0x6105, 0x6101, 0x6102, 0x6103, 0x6104, 0x6106, 0x6111, 0x6112]);
export const PHYSICAL_DEFAULTS = Object.freeze({start_id:1, end_id:3, address:1, probe_type:"holding_register", register_address:0x6201, register_count:1, timeout_ms:700, retries:0, inter_request_delay_ms:250, pause_normal_polling:true});
const PHYSICAL_GATEWAY = /^esphome:[0-9a-f]{12}$/;
export function boundsFor(form) {
  return form.provider === "esphome" ? {...INTEGER_BOUNDS, start_id:[1,32], end_id:[1,32], address:[1,32], register_count:[1,1], timeout_ms:[700,700]} : INTEGER_BOUNDS;
}
export function selectGateway(form, gateway) {
  const defaults = gateway.provider === "esphome" ? PHYSICAL_DEFAULTS : DEFAULTS;
  return {...form, ...defaults, provider:gateway.provider, gateway_id:gateway.gateway_id, safety_confirmed:false};
}
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
    const [minimum, maximum] = boundsFor(form)[name];
    const raw = form[name];
    const integer = typeof raw === "number" || (typeof raw === "string" && /^[+-]?\d+$/.test(raw));
    if (!integer || !Number.isInteger(number) || number < minimum || number > maximum) {
      errors[name] = text.integer ? text.integer(minimum, maximum) : `Enter a whole number from ${minimum} to ${maximum}.`;
    }
  }
  if (form.provider === "esphome") {
    const message = text.physical || "Physical bridge requires FC03, one allowed register, 700 ms timeout and polling pause.";
    if (form.probe_type !== "holding_register") errors.probe_type = message;
    if (!PHYSICAL_REGISTERS.includes(Number(form.register_address))) errors.register_address = message;
    if (form.pause_normal_polling !== true) errors.pause_normal_polling = message;
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
    pause_normal_polling: form.pause_normal_polling === true,
    ...(form.provider === "mock" ? {mock_profile: form.mock_profile} : {}),
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
  // A stored acknowledgement is not consent for a new browser session.
  form.safety_confirmed = false;
  if (source.provider === "esphome") {
    form.provider = "esphome";
    form.gateway_id = typeof source.gateway_id === "string" && PHYSICAL_GATEWAY.test(source.gateway_id) ? source.gateway_id : "";
    // Migrate old incompatible preferences, without silently changing provider.
    for (const key of ["probe_type", "register_count", "timeout_ms", "pause_normal_polling"]) form[key] = PHYSICAL_DEFAULTS[key];
    if (!PHYSICAL_REGISTERS.includes(form.register_address)) form.register_address = PHYSICAL_DEFAULTS.register_address;
    for (const key of ["start_id", "end_id", "address"]) if (form[key] > 32) form[key] = PHYSICAL_DEFAULTS[key];
    if (form.start_id > form.end_id) {form.start_id = 1; form.end_id = 3;}
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
