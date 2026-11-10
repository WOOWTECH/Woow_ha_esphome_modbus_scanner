// The Bridge Protocol v2 contract (ADR 0005): the fallback limits until a Gateway reports its own.
import contract from "../../custom_components/woow_esphome_modbus_scanner/modbus_scan/bridge_v2/contract.json" with {type: "json"};
const HARD = contract.hard_limits;
const SLAVE_MAX = HARD.slave_max;
export const DOMAIN = "woow_esphome_modbus_scanner";
export const SERVICES = Object.freeze([
  "check_gateway", "get_history",
  "list_gateways", "set_pausable_pollers",
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
  "responded", "modbus_exception", "timeout", "possible_collision", "gateway_error",
]);
// Only Scan history stored by 0.4.x (FC43 device identification) holds these rows.
const HISTORY_ONLY_OUTCOMES = Object.freeze(["identified"]);
/** The counts strip: the spec outcomes, plus a history-only outcome a 0.4.x Scan actually counted. */
export function visibleOutcomes(counts) {
  return [...OUTCOMES, ...HISTORY_ONLY_OUTCOMES.filter((name) => (counts?.[name] || 0) > 0)];
}
export const PROBE_TYPES = Object.freeze(["holding_register", "input_register"]);
export const DEFAULTS = Object.freeze({
  provider: "mock", gateway_id: "mock:rs485-gateway", start_id: 1, end_id: 12,
  address: 1, probe_type: "holding_register", register_address: 0,
  register_count: 1, timeout_ms: 500, retries: 1,
  inter_request_delay_ms: 100, pause_normal_polling: false,
  mock_scenario: "found_default", safety_confirmed: false, large_range_confirmed: false, bridge: "",
  device_profile_id: "generic",
});
/** A Bus name as Gateways report it (the Bridge Protocol v2 identifier charset). */
const BUS_NAME = /^[0-9A-Za-z_-]{1,32}$/;
const PARITIES = ["NONE", "EVEN", "ODD"];
function serialLabel(serial) {
  if (!serial || typeof serial !== "object") return "";
  const {baud_rate: baud, parity, stop_bits: stop} = serial;
  if (!Number.isInteger(baud) || baud < 1 || !PARITIES.includes(parity) || ![1, 2].includes(stop)) return "";
  return ` (${baud} baud, parity ${parity}, ${stop} stop bit${stop === 2 ? "s" : ""})`;
}
/**
 * A result's Bus name with the serial parameters its Gateway reports for it, e.g.
 * "rs485 (9600 baud, parity NONE, 1 stop bit)", from untrusted response data. A Gateway serves
 * one Bus, so the panel offers no Bus choice: HA resolves the Bus of every Scan.
 */
export function busLabel(gateway, bus) {
  if (typeof bus !== "string" || !BUS_NAME.test(bus)) return null;
  const rows = Array.isArray(gateway?.buses) ? gateway.buses : [];
  const row = rows.find((item) => item && typeof item === "object" && item.bus === bus);
  return `${bus}${serialLabel(row?.serial)}`;
}
const FUNCTION_CODE_PROBES = Object.freeze({3: "holding_register", 4: "input_register"});
/** The built-in Generic Device Profile, as list_device_profiles returns it (used until the list loads). */
export const GENERIC_PROFILE = Object.freeze({
  id: "generic", name: "Generic Device Profile", vendor: "Generic", model: "Any Modbus RTU device", version: "1",
  function_codes: [...HARD.function_codes], allowed_registers: null, defaults: {}, fields: [], builtin: true, deletable: false,
  limits: Object.freeze({slave_min: HARD.slave_min, slave_max: HARD.slave_max,
    probe_types: HARD.function_codes.map((code) => FUNCTION_CODE_PROBES[code]),
    register_count_max: HARD.count_max, allowed_registers: null, timeout_ms_min: HARD.timeout_ms_min, timeout_ms_max: HARD.timeout_ms_max}),
});
const PROFILE_ID = /^[a-z0-9][a-z0-9_-]{0,63}$/;
/** Ranges with more IDs than this need a second confirmation (the service requires large_range_confirmed). */
export const LARGE_RANGE_THRESHOLD = 32;
/** Bounds until a Gateway reports its limits; the slave range is the contract's. */
export const INTEGER_BOUNDS = Object.freeze({
  start_id: [HARD.slave_min, SLAVE_MAX], end_id: [HARD.slave_min, SLAVE_MAX], address: [HARD.slave_min, SLAVE_MAX],
  register_address: [0, 65535], register_count: [1, 125],
  timeout_ms: [10, 10000], retries: [0, 5], inter_request_delay_ms: [0, 5000],
});
const PHYSICAL_GATEWAY = /^esphome:[0-9a-f]{12}$/;
/** Whether a Scan estimated at `estimateMs` outlasts the Scan Lease of a Gateway that holds one (the contract's hard limit). */
export function outlastsScanLease(estimateMs, gateway) {
  return supportsScanLease(gateway) && Number.isFinite(estimateMs) && estimateMs > contract.lease.hard_limit_ms;
}
export function isBridgeV2(gateway) {
  return gateway?.provider === "esphome" && Array.isArray(gateway.capabilities) && gateway.capabilities.includes("bridge_v2");
}
/** Whether a Scan of this Gateway may hold its chosen Pausable Pollers paused under a Scan Lease, as HA publishes it. */
export const supportsScanLease = (gateway) => gateway?.supports_scan_lease === true;
/** Whether a form (or stored preferences) targets a Bridge Protocol v2 Gateway. */
export const isBridgeV2Form = (form) => form.provider === "esphome" && form.bridge === "v2";
/** Whether a form targets a Legacy Gateway (Bridge Protocol v1), whose help names that protocol. */
export const isLegacyGatewayForm = (form) => form.provider === "esphome" && !isBridgeV2Form(form);
/** The gateway's bounds intersected with the selected Device Profile's limits. */
export function boundsFor(form, profile = GENERIC_PROFILE) {
  const gateway = gatewayBoundsFor(form);
  const l = profile?.limits || GENERIC_PROFILE.limits;
  return {...gateway,
    start_id: meet(gateway.start_id, l.slave_min, l.slave_max), end_id: meet(gateway.end_id, l.slave_min, l.slave_max),
    address: meet(gateway.address, l.slave_min, l.slave_max), register_count: meet(gateway.register_count, 1, l.register_count_max),
    timeout_ms: meet(gateway.timeout_ms, l.timeout_ms_min, l.timeout_ms_max)};
}
/** A Gateway's reported limits (ProbeLimits.as_dict, as list_gateways gives them), or null when it has reported none. */
export const reportedLimits = (limits) => limits && typeof limits === "object" && !Array.isArray(limits) ? limits : null;
const meet = ([low, high], min, max) => [Math.max(low, Number.isInteger(min) ? min : low), Math.min(high, Number.isInteger(max) ? max : high)];
function gatewayBoundsFor(form) {
  const reported = reportedLimits(form.gateway_limits);
  if (reported) {
    const slaves = meet(INTEGER_BOUNDS.address, reported.slave_min, reported.slave_max);
    return {...INTEGER_BOUNDS, start_id: slaves, end_id: slaves, address: slaves,
      register_count: meet(INTEGER_BOUNDS.register_count, 1, reported.register_count_max),
      timeout_ms: meet(INTEGER_BOUNDS.timeout_ms, reported.timeout_ms_min, reported.timeout_ms_max),
      inter_request_delay_ms: meet(INTEGER_BOUNDS.inter_request_delay_ms, 0, reported.inter_request_delay_ms_max)};
  }
  return INTEGER_BOUNDS;
}
/** The form fields a Gateway's reported defaults may set, checked like stored preferences. */
function reportedDefaults(limits) {
  const source = limits?.defaults && typeof limits.defaults === "object" ? limits.defaults : {};
  const defaults = {};
  for (const [name, [minimum, maximum]] of Object.entries(INTEGER_BOUNDS)) {
    if (Number.isInteger(source[name]) && source[name] >= minimum && source[name] <= maximum) defaults[name] = source[name];
  }
  if (PROBE_TYPES.includes(source.probe_type)) defaults.probe_type = source.probe_type;
  if (typeof source.pause_normal_polling === "boolean") defaults.pause_normal_polling = source.pause_normal_polling;
  return defaults;
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
/** Target a Gateway: the limits it reports bound the form and the defaults it reports fill it. */
export function selectGateway(form, gateway) {
  const limits = reportedLimits(gateway?.limits);
  const bridge = isBridgeV2(gateway) ? "v2" : gateway.provider === "esphome" ? "v1" : "";
  return {...form, ...(gateway.provider === "mock" ? DEFAULTS : {}), ...reportedDefaults(limits), provider:gateway.provider,
    gateway_id:gateway.gateway_id, bridge, gateway_limits:limits, safety_confirmed:false};
}
/**
 * Revalidate a restored or kept form once its gateway is (re)loaded: when the limits the Gateway
 * reports are new to the form, values outside them fall back to its defaults; then the Bus is revalidated.
 */
export function reconcileGateway(form, gateway) {
  if (!gateway) return form;
  const limits = reportedLimits(gateway?.limits);
  const next = {...form, gateway_limits: limits};
  if (limits && JSON.stringify(limits) !== JSON.stringify(form.gateway_limits ?? null)) {
    const defaults = reportedDefaults(limits);
    for (const [name, [minimum, maximum]] of Object.entries(gatewayBoundsFor(next))) {
      const value = Number(next[name]);
      if (wholeNumber(next[name]) && value >= minimum && value <= maximum) continue;
      next[name] = name in defaults ? defaults[name] : Math.min(Math.max(Number.isInteger(value) ? value : minimum, minimum), maximum);
    }
    if (Number(next.start_id) > Number(next.end_id)) {
      next.start_id = defaults.start_id ?? next.start_id;
      next.end_id = defaults.end_id ?? next.start_id;
    }
    const probes = limits.probe_types;
    if (Array.isArray(probes) && probes.length && !probes.includes(next.probe_type)) next.probe_type = defaults.probe_type ?? probes[0];
    const allowed = limits.allowed_registers;
    if (Array.isArray(allowed) && allowed.length && !allowed.includes(Number(next.register_address))) {
      next.register_address = defaults.register_address ?? allowed[0];
    }
    // The panel offers no Normal Polling choice for physical Gateways; their defaults decide it.
    if (next.provider === "esphome" && "pause_normal_polling" in defaults) next.pause_normal_polling = defaults.pause_normal_polling;
    if (limits.pause_normal_polling_required === true) next.pause_normal_polling = true;
    if (Object.keys(DEFAULTS).some((key) => next[key] !== form[key])) Object.assign(next, {safety_confirmed: false, large_range_confirmed: false});
  }
  return next;
}
/** Raw register evidence in decimal and hex, e.g. "1234 (0x04D2), 65535 (0xFFFF)". */
export function formatRawValues(row) {
  const values = Array.isArray(row?.raw_values) ? row.raw_values : Number.isInteger(row?.raw_value) ? [row.raw_value] : [];
  const shown = values.filter((value) => Number.isInteger(value) && value >= 0 && value <= 65535);
  return shown.length ? shown.map((value) => `${value} (0x${value.toString(16).toUpperCase().padStart(4, "0")})`).join(", ") : null;
}
/** Device Profile decoded values, e.g. "Voltage = 230.1 V; Current = -1.36 A", or null. */
export function formatDecodedValues(row) {
  const entries = Array.isArray(row?.decoded) ? row.decoded : [];
  const shown = entries
    .filter((entry) => entry && typeof entry.name === "string" && typeof entry.value === "number" && Number.isFinite(entry.value))
    .map((entry) => {
      const unit = typeof entry.unit === "string" && entry.unit ? ` ${entry.unit.slice(0, 16)}` : "";
      return `${entry.name.slice(0, 64)} = ${entry.value}${unit}`;
    });
  return shown.length ? shown.join("; ") : null;
}
/** Whether any Responder carries decoded values (the Generic Device Profile never does). */
export function hasDecodedValues(results) {
  return Array.isArray(results?.responders) && results.responders.some((row) => formatDecodedValues(row) !== null);
}
/** Lease states the panel shows: the contract's, but "none" (no lease), plus HA's own "unconfirmed" (ADR 0007). */
const LEASE_STATES = [...contract.lease.states.filter((state) => state !== "none"), "unconfirmed"];
const LEASE_END_REASONS = contract.lease.end_reasons;
/** Endings the Gateway decides by itself (all but HA's release), possibly while the Scan still runs. */
const EARLY_END_REASONS = LEASE_END_REASONS.filter((reason) => reason !== "released");
/**
 * What the panel shows about a Scan's Scan Lease, or null when no lease applies.
 * `stale` names the paused Pausable Pollers whose entity values are frozen while the lease may hold.
 */
/** "name (slave address)" of a Pausable Poller from untrusted response data. */
function pollerLabel(poller) {
  const name = typeof poller.name === "string" ? poller.name.slice(0, 64) : `#${Number.isInteger(poller.index) ? poller.index : "?"}`;
  return Number.isInteger(poller.address) && poller.address >= 1 && poller.address <= SLAVE_MAX ? `${name} (${poller.address})` : name;
}
const pollerObjects = (value) => Array.isArray(value) ? value.filter((poller) => poller && typeof poller === "object") : [];
export function leaseNotice(status) {
  const state = status?.lease_status;
  if (!LEASE_STATES.includes(state)) return null;
  const reason = state === "ended" && LEASE_END_REASONS.includes(status.lease_end_reason) ? status.lease_end_reason : null;
  return {
    state,
    reason,
    stale: state === "ended" ? [] : pollerObjects(status.paused_pollers).map(pollerLabel),
    endedAfter: leaseEndedAfter(status, reason),
  };
}
/**
 * The last Slave ID finished under the Scan Lease when the Gateway ended it before the Scan
 * did; later Probes ran with Normal Polling resumed. Null when the lease held to the end.
 */
function leaseEndedAfter(status, reason) {
  const after = status?.lease_ended_after_address;
  return EARLY_END_REASONS.includes(reason) && Number.isInteger(after) && after >= 0 && after <= SLAVE_MAX ? after : null;
}
/** Whether a Responder row was probed after the Scan Lease ended early at `endedAfter` (leaseNotice). */
export function probedWithoutLease(endedAfter, row) {
  return Number.isInteger(endedAfter) && Number.isInteger(row?.address) && row.address > endedAfter;
}
/** Chosen Pausable Pollers a Scan did not pause because the firmware no longer has them. */
export function removedPollers(status) {
  return pollerObjects(status?.removed_pollers).map(pollerLabel);
}
/**
 * The saved checklist key of a Gateway's one Bus (ADR 0011): the Bus it reports, else, before a check
 * reports it, the only saved key. Saved keys of former Buses (a dev2 multi-Bus Gateway) never qualify.
 */
function ownBus(gateway, keys) {
  const buses = Array.isArray(gateway.buses) ? gateway.buses : [];
  if (buses.length) return buses.length === 1 && keys.includes(buses[0]?.bus) ? buses[0].bus : null;
  return keys.length === 1 ? keys[0] : null;
}
/**
 * The Pausable Poller checklist of a Gateway with Scan Lease support, as saved in HA (keyed by its
 * one Bus) and revalidated against the firmware: `removed` names saved pollers the firmware dropped.
 * At most one checklist: the Gateway's one Bus.
 */
export function pollerChecklists(gateway) {
  if (!supportsScanLease(gateway) || !gateway.poller_selection || typeof gateway.poller_selection !== "object") return [];
  const saved = Object.entries(gateway.poller_selection).filter(([, rows]) => Array.isArray(rows));
  const own = ownBus(gateway, saved.map(([bus]) => bus));
  return saved.filter(([bus]) => bus === own).map(([bus, rows]) => ({
    bus,
    pollers: pollerObjects(rows).filter((row) => Number.isInteger(row.index) && row.index >= 0)
      .map((row) => ({index: row.index, label: pollerLabel(row), paused: row.paused === true})),
    removed: pollerObjects(gateway.removed_pollers?.[bus]).map(pollerLabel),
  }));
}
/** set_pausable_pollers data after checking (paused=true) or unchecking one poller, or "all". */
export function selectionPayload(gatewayId, bus, pollers, index, paused) {
  const chosen = pollers.filter((poller) => index === "all" ? paused : poller.index === index ? paused : poller.paused);
  return {gateway_id: gatewayId, bus, pause_pollers: chosen.map((poller) => poller.index)};
}
const wholeNumber = (value) => (typeof value === "number" || (typeof value === "string" && /^[+-]?\d+$/.test(value))) && Number.isInteger(Number(value));
/**
 * Estimated range-scan duration, the service's estimated_worst_case_ms formula: IDs x attempts x
 * (timeout + the gateway's reported per-attempt overhead) + (IDs - 1) x delay; null for an invalid range.
 */
export function estimatedDurationMs(form, gateway = null) {
  const fields = [form.start_id, form.end_id, form.timeout_ms, form.retries, form.inter_request_delay_ms];
  if (!fields.every(wholeNumber) || Number(form.start_id) > Number(form.end_id)) return null;
  const reported = gateway?.limits?.attempt_overhead_ms;
  const overhead = Number.isInteger(reported) && reported >= 0 ? reported : 0;
  const ids = Number(form.end_id) - Number(form.start_id) + 1;
  return ids * (Number(form.retries) + 1) * (Number(form.timeout_ms) + overhead) + (ids - 1) * Number(form.inter_request_delay_ms);
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
  const limits = reportedLimits(form.gateway_limits);
  // The same rule that picks the help: a Legacy Gateway's text names Bridge Protocol v1, any other the v2 limits.
  const gatewayText = (isLegacyGatewayForm(form) ? text.physical : text.v2) || "The selected Gateway does not allow this value.";
  if (Array.isArray(limits?.probe_types) && !limits.probe_types.includes(form.probe_type)) errors.probe_type = gatewayText;
  if (limits?.pause_normal_polling_required === true && form.pause_normal_polling !== true) errors.pause_normal_polling = gatewayText;
  if (limits?.pause_normal_polling_supported === false && form.pause_normal_polling === true) errors.pause_normal_polling = gatewayText;
  if (!errors.register_address && !errors.register_count && Number(form.register_address) + Number(form.register_count) - 1 > 65535) {
    errors.register_count = text.registerBlock || "The register block must end at or before register 65535.";
  }
  const probes = profile?.limits?.probe_types;
  if (!errors.probe_type && Array.isArray(probes) && !probes.includes(form.probe_type)) {
    errors.probe_type = text.profileProbe || "The selected Device Profile does not allow this probe type.";
  }
  const allowed = profile?.allowed_registers;
  // Every register of the block is read, so every one must be allowed.
  const block = Array.from({length: Math.max(1, Number(form.register_count) || 1)}, (_, i) => Number(form.register_address) + i);
  const gatewayAllowed = limits?.allowed_registers;
  if (!errors.register_address && !errors.register_count && Array.isArray(gatewayAllowed) && block.some((reg) => !gatewayAllowed.includes(reg))) {
    errors.register_address = gatewayText;
  }
  if (!errors.register_address && !errors.register_count && Array.isArray(allowed) && block.some((reg) => !allowed.includes(reg))) {
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
    provider: form.provider, gateway_id: form.gateway_id,
    probe_type: form.probe_type,
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
  // A Legacy Gateway is usable once HA reports its limits; the panel keeps no copy of them.
  return gateway?.provider === "mock" || isBridgeV2(gateway) || (gateway?.provider === "esphome" && reportedLimits(gateway?.limits) !== null);
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
    outcome_counts:Object.fromEntries(OUTCOMES.map((name) => [name,integer(results?.outcome_counts?.[name],SLAVE_MAX) ?? 0])),
    responders:(results?.responders || []).slice(0,SLAVE_MAX).map((row) => ({
      address:integer(row.address,SLAVE_MAX), outcome:[...OUTCOMES, ...HISTORY_ONLY_OUTCOMES].includes(row.outcome) ? row.outcome : "unknown",
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
  // Checked against the limits the gateway reports once the gateway list loads (reconcileGateway).
  if (source.provider === "esphome") {
    form.provider = "esphome";
    form.bridge = isBridgeV2Form(source) ? "v2" : "v1";
    form.gateway_id = typeof source.gateway_id === "string" && PHYSICAL_GATEWAY.test(source.gateway_id) ? source.gateway_id : "";
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
