# Woow ESPHome Modbus Scanner

A HACS-compatible Home Assistant custom integration for safe, provider-backed,
best-effort Modbus address discovery. Version **0.1.0** is intentionally
hardware-free: it ships only a deterministic `MockGatewayProvider` and never
opens an ESPHome connection or a Modbus transport.

繁體中文：[README_zh-TW.md](README_zh-TW.md)

## Status and safety

This release is useful for automations, service-client development, lifecycle
testing, and evaluating result semantics without hardware. It is **not** a real
bus scanner yet.

Discovery is read-only and best-effort. A timeout does not prove an address is
unused. A response does not prove a Slave ID uniquely identifies one physical
device. Noise and duplicate IDs can look like a possible collision. A future
physical scan may disrupt normal polling even when all probes are read-only.

`start_scan` therefore accepts only the literal JSON/YAML boolean
`safety_confirmed: true`; truthy numbers and strings are rejected. All six
services require an administrator when a Home Assistant user context is
present. Trusted internal calls without a user context remain supported.

## Installation

### HACS custom repository

1. In HACS, add this repository as an **Integration** custom repository.
2. Install **Woow ESPHome Modbus Scanner**.
3. Restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration** and add it once.

### Manual

Copy `custom_components/woow_esphome_modbus_scanner` into your Home Assistant
`custom_components` directory, restart, then add the integration. The config
flow is singleton: a second entry is rejected.

## Public services

The domain is `woow_esphome_modbus_scanner`. The complete and only public
service set is:

- `list_gateways`
- `start_scan`
- `get_scan_status`
- `get_scan_results`
- `cancel_scan`
- `test_address`

Example mock scan:

```yaml
service: woow_esphome_modbus_scanner.start_scan
data:
  provider: mock
  gateway_id: mock:rs485-gateway
  start_id: 1
  end_id: 12
  probe_type: device_identification
  timeout_ms: 500
  retries: 1
  inter_request_delay_ms: 0
  mock_profile: found_default
  safety_confirmed: true
response_variable: started
```

Use the returned `scan_id` with `get_scan_status` and `get_scan_results`.
`test_address` uses the same coordinator but constrains work to one address.
Only one scan may own a provider/gateway pair at a time. Terminal history is
bounded in memory (20 scans by default) and is not persisted across reloads.

The service UI includes an optional `esphome_device_id` device selector filtered
to Home Assistant's ESPHome integration. It is reserved for a future adapter;
0.1.0 accepts it for forward-compatible service forms but mock behavior is
unchanged and no selected device is contacted.

## Deterministic mock profiles

- `found_default`
- `all_offline`
- `partial_timeout`
- `modbus_exception`
- `possible_collision`
- `gateway_disconnect`

Results normalize identity replies, generic replies, protocol exceptions,
timeouts, possible collisions, and gateway failures. Timeout details are counted
but not retained as responder records, keeping result memory bounded by actual
non-timeout outcomes.

## Future ESPHome adapter contract

No ESPHome adapter is included in 0.1.0. A future provider must implement the
`GatewayProvider` protocol documented in
[`docs/design/provider-contract.md`](docs/design/provider-contract.md): advertise
provider-owned gateways synchronously and run one validated request
asynchronously, emitting normalized `ProbeResult` objects incrementally while
honoring cooperative cancellation. It must map the selected Home Assistant
device to an explicit gateway, use only read probes, serialize access per
gateway, restore paused polling in `finally`, and translate transport loss to
`GatewayProviderError`. The coordinator deliberately owns validation, lifecycle,
history, and response shapes; the adapter must not bypass those controls.

An ESPHome device selector is not evidence that Home Assistant or ESPHome expose
the low-level serial transaction API needed for this contract. Feasibility and
an upstream API must be established before a real provider can be claimed.

## Development

The hermetic suite exercises models, mock behavior, coordinator adversarial
boundaries, service schemas/responses/admin gating, singleton config flow, and
unload races. `pytest --collect-only -q` collects exactly **105 tests** for 0.1.0.
Live smoke testing is opt-in and mock-only.

```bash
uv venv --python 3.13.2
uv pip install -r requirements-test.txt
.venv/bin/ruff check .
.venv/bin/pytest --collect-only -q
.venv/bin/pytest --cov=custom_components/woow_esphome_modbus_scanner \
  --cov-report=term-missing --cov-fail-under=90
.venv/bin/python -m compileall -q custom_components tests/live
```

See [`tests/live/README.md`](tests/live/README.md) for the external Home
Assistant mock-service smoke script. No deployment, release, or hardware test is
part of the hermetic commands.

## License

MIT — see [LICENSE](LICENSE).
