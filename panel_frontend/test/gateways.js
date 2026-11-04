// Gateways as list_gateways reports them (GatewayInfo.as_dict): each one carries the limits and
// defaults its adapter enforces, so the panel keeps no per-bridge copy. Values are the frozen
// bridge v1 profile (ADR 0004) and the bridge v2 contract and adapter defaults (ADR 0005).
export const LEGACY_REGISTERS = [25089, 25090, 25091, 25093, 25094, 24837, 24833, 24834, 24835, 24836, 24838, 24849, 24850];
export const LEGACY_GATEWAY = Object.freeze({
  provider: "esphome", gateway_id: "esphome:aabbccddeeff", name: "Guanjie read-only scanner",
  capabilities: ["holding_register", "single_register", "slave_1_32", "timeout_700ms", "automatic_polling_resume"],
  supports_bus_selection: false, supports_scan_lease: false,
  limits: {
    slave_min: 1, slave_max: 32, probe_types: ["holding_register"], register_count_max: 1,
    allowed_registers: LEGACY_REGISTERS, timeout_ms_min: 700, timeout_ms_max: 700, inter_request_delay_ms_max: 5000,
    pause_normal_polling_required: true, pause_normal_polling_supported: true, attempt_overhead_ms: 2700,
    defaults: {start_id: 1, end_id: 3, address: 1, probe_type: "holding_register", register_address: 25089,
      register_count: 1, timeout_ms: 700, retries: 0, inter_request_delay_ms: 250, pause_normal_polling: true},
  },
});
export const V2_GATEWAY = Object.freeze({
  provider: "esphome", gateway_id: "esphome:aabbccddee01", name: "ESPHome Modbus DDEE01",
  capabilities: ["bridge_v2", "holding_register", "input_register", "multi_register"], can_operate: true,
  supports_bus_selection: true, supports_scan_lease: true,
  limits: {
    slave_min: 1, slave_max: 247, probe_types: ["holding_register", "input_register"], register_count_max: 4,
    allowed_registers: null, timeout_ms_min: 100, timeout_ms_max: 2000, inter_request_delay_ms_max: 3000,
    pause_normal_polling_required: false, pause_normal_polling_supported: true, attempt_overhead_ms: 300,
    defaults: {probe_type: "holding_register", register_address: 0, register_count: 1, timeout_ms: 1000,
      retries: 0, inter_request_delay_ms: 100, pause_normal_polling: true},
  },
});
