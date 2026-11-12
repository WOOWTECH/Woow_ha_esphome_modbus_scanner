# Woow ESPHome Modbus Scanner

> **0.5.0.dev3 is under development** (on `main`). It is not a release and has
> not been deployed or accepted on hardware yet. 0.5.0.dev1 (#17) introduced the
> vendor-neutral component; 0.5.0.dev3 (#26) settles on one Gateway, one Bus and
> drops the multi-Bus support of 0.5.0.dev2. The last deployed build was
> 0.4.0.dev1; see [History](#history).

Read-only, best-effort discovery of which Modbus RTU slave IDs answer on an
RS-485 Bus reached through an ESPHome node, driven from Home Assistant. The
project has two parts:

- a Home Assistant custom integration (`custom_components/woow_esphome_modbus_scanner`)
  with a sidebar workbench, public services, Device Profiles and a mock provider;
- a vendor-neutral ESPHome external component, `modbus_scanner`
  (`firmware/components/modbus_scanner`), that turns any ESPHome node with a
  Modbus RTU hub into a scanner **Gateway**.

繁體中文：[README_zh-TW.md](README_zh-TW.md) · Terms: [GLOSSARY.md](GLOSSARY.md)

## Tutorial

The Traditional-Chinese HTML tutorial for this version is a single offline file:
**[view the 0.5.0 tutorial source](https://github.com/WOOWTECH/Woow_ha_esphome_modbus_scanner/blob/main/docs/tutorial/woow-esphome-modbus-scanner-v0.5.0-zh-TW.html)** ·
**[raw 0.5.0 HTML](https://raw.githubusercontent.com/WOOWTECH/Woow_ha_esphome_modbus_scanner/main/docs/tutorial/woow-esphome-modbus-scanner-v0.5.0-zh-TW.html)**.
The older mock-only tutorials are listed under [History](#history).

## How it works

- A **Gateway** is an enrolled ESPHome node running `modbus_scanner` on
  exactly one **Bus**: the Modbus RTU line (hub) its one `modbus_scanner` entry
  names, with its serial parameters. One Gateway, one Bus: scan a second RS-485
  line with another node.
- A **Scan** is an ordered series of read-only **Probes** (FC03 holding or FC04
  input registers) over a range of slave IDs on one Bus. A slave ID that
  answers is a **Responder**; that is not proof of exactly one physical device.
- A **Device Profile** in Home Assistant holds the readable registers, defaults
  and limits for one class of field device. The built-in **Generic Device
  Profile** permits any register. Profiles can also name registers so results
  show decoded values beside the raw ones.
- Other components polling the same Bus (for example each `modbus_controller`)
  are **Pausable Pollers**, found when the firmware is compiled. During a Scan
  the Gateway holds the ones you selected paused under a **Scan Lease** and
  resumes them by itself.

Design decisions:
[ADR 0005, vendor-neutral component and Device Profiles](docs/adr/0005-vendor-neutral-scanner-component-and-device-profiles.md),
[ADR 0006, Pausable Poller discovery and selection](docs/adr/0006-codegen-discovery-and-runtime-selection-of-pausable-pollers.md),
[ADR 0007, Scan Lease with Gateway-owned recovery](docs/adr/0007-per-scan-lease-with-gateway-owned-recovery.md),
[ADR 0008, scanner service set and persisted history](docs/adr/0008-scanner-service-set-and-persisted-history.md),
[ADR 0011, one Bus per Gateway](docs/adr/0011-one-bus-per-gateway.md).
Earlier ADRs 0001–0003 cover the provider/coordinator split, the singleton
lifecycle and the all-user sidebar.

## Safety and access

Discovery is read-only and best-effort. A timeout does not prove an address is
unused, and a reply does not prove that one physical device owns that slave ID.
The firmware refuses every write function code (FC05, FC06, FC15, FC16, FC22,
FC23) and enforces its own hard limits: slave 1–247, FC03/FC04, 1–4 registers,
100–2000 ms timeout, one Probe in flight per Gateway.

- `start_scan` requires the literal boolean `safety_confirmed: true`; strings
  and numbers are rejected.
- A Scan of more than 32 slave IDs (a Large Range) also requires
  `large_range_confirmed: true`. The sidebar shows the estimated duration,
  IDs × attempts × (timeout + the Gateway's per-attempt overhead) + delays, the
  same figure as the Scan's `estimated_worst_case_ms`, before asking.
- Pausing pollers makes their Home Assistant entities stale for the duration of
  the Scan. See [Pausable Pollers and the Scan Lease](#pausable-pollers-and-the-scan-lease).

**Access policy:** the sidebar and all services are open to every active HA
user and to internal automations; there is no admin gate. In practice, any
active Home Assistant user can generate read-only Modbus traffic on any
enrolled Bus, for slave IDs 1–247 within the selected Device Profile, and see
the Responder evidence. Inactive or unknown users are refused. Control who has
an HA account. Native ESPHome actions are a separate path that the integration
does not police; API encryption authenticates clients, not HA users. See
[authorization boundary](docs/design/authorization-boundary.md).

## Requirements

- Home Assistant with the ESPHome integration (this integration depends on it).
- **ESPHome 2026.9.0 or newer** for the firmware. Older versions fail
  configuration validation with "requires at least ESPHome version 2026.9.0".
- An ESP32 (or other ESPHome target) with a UART wired to an RS-485
  transceiver, a `modbus:` hub and the native `api:` (encryption recommended).

## 1. Add the scanner to your ESPHome node

Keep your existing `uart`, `modbus` and `modbus_controller` configuration and
add the external component plus one `modbus_scanner` entry naming the hub:

```yaml
esphome:
  name: my-modbus-node
  min_version: 2026.9.0

api:
  encryption:
    key: !secret api_encryption_key

external_components:
  - source:
      type: git
      url: https://github.com/WOOWTECH/Woow_ha_esphome_modbus_scanner
      path: firmware/components
    components: [modbus_scanner]

uart:
  id: rs485_uart
  tx_pin: GPIO17
  rx_pin: GPIO16
  baud_rate: 9600

modbus:
  id: rs485
  uart_id: rs485_uart

modbus_controller:
  - id: meter
    modbus_id: rs485
    address: 1
    update_interval: 10s

modbus_scanner:
  - modbus_id: rs485
```

The component registers the read-only probe and lease-release actions
(`modbus_scanner_v2_probe`, `modbus_scanner_v2_release`) and three diagnostic
text sensors (`Modbus Scanner v2 Info`, `Result`, `Lease`); `api:
custom_services` is not needed and none of these sensors is declared in YAML. Every `PollingComponent` bound to the same hub,
here `meter`, becomes a Pausable Poller automatically; adding one later needs a
recompile. Complete example:
[`firmware/examples/generic-modbus-scanner.yaml`](firmware/examples/generic-modbus-scanner.yaml).

**One Gateway, one Bus:** a node has exactly one `modbus_scanner` entry; a
second one fails to compile with "A node supports only one modbus_scanner; scan
a second RS-485 line with another node". On a node with two RS-485 lines, only
one of them can be scanned. The Bus may be named with `bus:` (1–32 characters
from `0-9 A-Z a-z _ -`; the default is the hub id); it reports its baud rate,
parity and stop bits, which HA shows with every result. HA refuses to enroll or
check a Gateway whose info reports more than one Bus.

The wire protocol (bridge protocol v2) is defined in one machine-readable file,
[`bridge_v2/contract.json`](custom_components/woow_esphome_modbus_scanner/modbus_scan/bridge_v2/contract.json),
read by the HA adapter, the test fake and the firmware host tests.

## 2. Install the integration

**HACS:** add this repository as an **Integration** custom repository, install
**Woow ESPHome Modbus Scanner**, restart Home Assistant.

**Manual:** copy `custom_components/woow_esphome_modbus_scanner` into your HA
`custom_components` directory and restart.

Then go to **Settings → Devices & services → Add integration**. The integration
is a single entry; the set-up menu offers:

- **Add a gateway from an ESPHome device** (recommended): lists nodes already in
  HA's ESPHome integration with a known MAC, reuses their host, port and API key,
  and verifies the MAC and the Bridge Protocol v2 signature over the API without sending
  a Modbus frame. Failures name the cause: scanner component missing, Bridge
  Protocol mismatch, identity mismatch, authentication or connection. Every later
  connection reads the host, port and key from that ESPHome entry again, so a new
  IP address or a rotated key there needs no re-enrolment.
- **Add a gateway manually** (advanced): host, MAC and API key, with the same
  checks. Choose Bridge Protocol v2, or v1 for a Legacy Gateway not yet reflashed.
- **Mock gateway only for now.**

Use **Reconfigure** to add, refresh (picks up a new host or key) or remove
Gateways; there is no limit on their number. **Reauthenticate** verifies one
Gateway at a time. Stored keys are never shown.

## 3. Use the sidebar

Open **Modbus Scanner** (`mdi:radar`, route `/woow-esphome-modbus-scanner`). It
is visible to all HA users. Hard-refresh the browser after an update.

1. Pick a Gateway. Its one Bus is scanned; results name it with its serial
   parameters.
2. Pick a Device Profile. Its defaults fill the form and its limits, intersected
   with the Gateway's, bound every field.
3. Check the Gateway so the Pausable Pollers card lists each poller by name and
   slave address. All are checked by default; the selection is saved for the
   Gateway's Bus.
4. Confirm the best-effort warning (and the Large Range warning above 32 IDs),
   then **Start scan**, or **Test address** for one slave ID.

The panel polls status once per second without overlap, loads results at the
end, shows the Scan Lease state and the paused devices whose values are stale,
and lists Responders with raw values (decimal and hex) and, when the Device
Profile defines fields, decoded values with units. Each result names its
Gateway, Bus and Device Profile.

## Device Profiles

A Device Profile is a JSON document, `schema_version` 1, managed with
`list_device_profiles`, `import_device_profile`, `export_device_profile` and
`delete_device_profile`, or the sidebar's Device Profiles card. Imported
profiles live in HA storage and are included in HA backups. Importing an
existing `id` replaces it. Invalid documents are rejected with one error per
field. The built-in `generic` profile cannot be deleted, and a profile in use by
a running Scan cannot be deleted until it ends; finished results keep the
profile label they were recorded with.

| Key | Required | Meaning |
|---|---|---|
| `schema_version` | yes | `1` |
| `id` | yes | 1–64 of `a-z 0-9 _ -`, starting with a letter or digit; `generic` is reserved |
| `name`, `vendor`, `model` | yes | Non-empty text, at most 64 characters |
| `version` | yes | Non-empty text, at most 32 characters |
| `function_codes` | yes | Non-empty list from `3` (holding) and `4` (input); write codes are refused |
| `defaults` | no | `slave_start` + `slave_end` (together), `function_code`, `register`, `count` (1–4), `timeout_ms` (100–2000), `inter_request_delay_ms`, `retries` |
| `allowed_registers` | no | Up to 1024 register addresses; when present, only these may be read |
| `fields` | no | Up to 256 of `{register, name, unit?, scale?, data_type?}`; `data_type` is `u16` (default) or `s16`, `scale` a finite non-zero number |

A complete example is
[`examples/device_profiles/guanjie-ind17.json`](examples/device_profiles/guanjie-ind17.json),
an allowlisted FC03 register map with named fields. Import it from the sidebar
or with:

```yaml
action: woow_esphome_modbus_scanner.import_device_profile
data:
  profile: >-
    {"schema_version": 1, "id": "my-meter", "name": "My meter", "vendor": "Acme",
     "model": "M1", "version": "1", "function_codes": [4],
     "defaults": {"function_code": 4, "register": 0, "count": 2},
     "fields": [{"register": 0, "name": "Voltage", "unit": "V", "scale": 0.1}]}
```

## Pausable Pollers and the Scan Lease

A Scan pauses the Bus's Pausable Pollers you selected so their traffic does not
interleave with the Probes. Save the selection per Bus with
`set_pausable_pollers` (or the sidebar checklist), or pass `pause_pollers` (a
list of indices from `check_gateway`) for one Scan. An empty list pauses
nothing. Pollers the firmware no longer has are dropped and reported as
`removed_pollers`, never sent.

The pause is a Scan Lease held by the Gateway, not by Home Assistant:

- it starts with the first Probe of the Scan; the selected pollers stop and the
  hub's queued frames for their slave addresses are cleared;
- HA releases it when the Scan completes, is cancelled or fails;
- if HA or the connection disappears, the Gateway ends it by itself after
  **5 s** without a Probe, and in every case after **10 minutes** (later Probes
  of a longer Scan run without pausing). On Bridge Protocol v2 the inter-request delay is
  capped at 3000 ms so a Scan's own gaps never reach the idle time;
- on every ending path the Gateway resumes the pollers.

Two consequences to plan for: clearing a paused poller's queue also drops any
writes it had pending (do not change settings on paused devices during a Scan),
and after the lease ends the first fresh reading from a resumed poller can take
up to one of its `update_interval`s. Scan status reports `lease_status`
(`none`, `active`, `ended`, `unconfirmed`) and `lease_end_reason` (`released`,
`idle`, `hard_limit`, `superseded`).

**One Scan per Gateway:** a Gateway serves one Bus, so it runs one Scan and
has one Probe in flight at a time; a second Scan is refused as busy.

## Public services

Domain `woow_esphome_modbus_scanner`. All services are available to every
active user (physical operations need an active user or an internal automation).

| Service | Purpose |
|---|---|
| `list_gateways` | Gateways with provider, Bus (`buses`, always one entry once checked), limits, health, Pausable Poller checklist and `can_operate` |
| `check_gateway` | Verify one Gateway's MAC and Bridge Protocol signature and read its Bus and pollers, without a Modbus frame; a Gateway reporting more than one Bus is refused |
| `set_pausable_pollers` | Save which Pausable Pollers of the Gateway's Bus a Scan pauses (`gateway_id`, `pause_pollers`, optional `bus`) |
| `start_scan` | Start a range Scan; returns its `scan_id` immediately |
| `test_address` | Scan one slave ID (`address`); range confirmation is implicit |
| `get_scan_status` | Progress, phase, lease state, errors and recovery evidence |
| `get_scan_results` | Responder evidence with raw and decoded values |
| `cancel_scan` | Cooperative cancel; a frame already on the wire finishes first |
| `get_history` | Up to 20 terminal snapshots, kept in HA storage across restarts; interrupted Scans are recorded as failed, never replayed |
| `list_device_profiles` | Generic and imported Device Profiles with their limits |
| `import_device_profile` | Validate and store a Device Profile (`profile`: object or JSON text) |
| `export_device_profile` | Return one profile's importable document (`profile_id`) |
| `delete_device_profile` | Delete an imported profile (`profile_id`) |

Fields of `start_scan` (and `test_address`, which takes `address` instead of the
range and has no confirmations). Omitted fields take the Device Profile's
defaults first, then the Gateway's; the defaults below are a Bridge Protocol v2
Gateway's (the mock Gateways default to `holding_register`, 500 ms, one
retry and no pause):

| Field | Default | Notes |
|---|---|---|
| `provider` | `mock` | `mock` or `esphome` |
| `gateway_id` | `mock:rs485-gateway` | From `list_gateways`, e.g. `esphome:aabbccddeeff` |
| `bus` | — | Optional; when given it must name the Gateway's one Bus |
| `esphome_device_id` | — | Optional extra MAC cross-check against an HA ESPHome device |
| `device_profile_id` | `generic` | Its defaults fill omitted fields; its limits apply with the Gateway's |
| `start_id`, `end_id` | Device Profile default | 1–247; required unless the Device Profile defines a slave range |
| `probe_type` | `holding_register` | `holding_register` (FC03) or `input_register` (FC04) |
| `register_address`, `register_count` | 0, 1 | Count 1–4 on Bridge Protocol v2; the block must end at or before 65535 |
| `timeout_ms` | 1000 | 100–2000 on Bridge Protocol v2, applied per Probe on the Gateway |
| `retries`, `inter_request_delay_ms` | 0, 100 | Retries 0–5 after a timeout; delay 0–3000 ms between addresses on Bridge Protocol v2 (kept below the 5 s lease idle time), 0–5000 ms on a Legacy Gateway |
| `pause_normal_polling` | `true` | `false` scans without pausing anything |
| `pause_pollers` | saved selection | Pausable Poller indices for this Scan only |
| `mock_scenario` | `found_default` | Mock provider only |
| `safety_confirmed` | required | Exactly `true` |
| `large_range_confirmed` | — | Exactly `true` when the range covers more than 32 IDs |

Example, a physical Scan of slave IDs 1–10 on one Bus:

```yaml
action: woow_esphome_modbus_scanner.start_scan
data:
  provider: esphome
  gateway_id: esphome:aabbccddeeff   # from list_gateways
  bus: rs485
  start_id: 1
  end_id: 10
  probe_type: holding_register
  register_address: 0
  register_count: 1
  safety_confirmed: true
response_variable: started
```

Use the returned `scan_id` with `get_scan_status` and `get_scan_results`. Only
one Scan may run per Gateway; a second one is refused as busy.

## Mock provider

`provider: mock` needs no hardware and never opens a connection. It offers
`mock:rs485-gateway` (Bus `rs485`). `mock_scenario` selects one fixed outcome set:
`found_default`, `all_offline`, `partial_timeout`, `modbus_exception`,
`possible_collision`, `gateway_disconnect`. Mock register reads return raw
values for FC03/FC04. The former field name `mock_profile` is still accepted as
a **deprecated** alias; sending both is rejected.

```yaml
action: woow_esphome_modbus_scanner.start_scan
data:
  provider: mock
  gateway_id: mock:rs485-gateway
  start_id: 1
  end_id: 12
  mock_scenario: found_default
  safety_confirmed: true
response_variable: started
```

## Legacy Gateways (Bridge Protocol v1)

Gateways enrolled before 0.5.0 that still run the vendor-specific Bridge Protocol v1
firmware keep working with its frozen limits (slave IDs 1–32, FC03, count 1,
one allowlisted register, 700 ms, polling pause required, no `bus`). Each such
Gateway raises a **Repairs** warning. To migrate: add `modbus_scanner` to the
node's YAML as above and reflash it, open the integration's **Reconfigure**,
choose **Add or refresh a gateway from an ESPHome device** for that node (or the
manual option with Bridge Protocol v2), then import the example Device Profile if you
want the former register map. The Repairs issue disappears once the Gateway is
enrolled with Bridge Protocol v2. Legacy support will be removed in a future release.

## Development

```bash
uv venv --python 3.14
uv pip install -r requirements-test.txt
ruff check .
pytest --cov=custom_components/woow_esphome_modbus_scanner \
  --cov-report=term-missing --cov-fail-under=90
g++ -std=c++20 -Wall -Wextra -Werror firmware/tests/scanner_core_test.cpp -o /tmp/scanner-core
/tmp/scanner-core custom_components/woow_esphome_modbus_scanner/modbus_scan/bridge_v2/contract.json
cd panel_frontend && npm ci --include=dev && npm test && npm run check:drift
npx playwright install chromium && npm run test:browser
cd .. && node tests/tutorial/browser_check.mjs
```

CI (`.github/workflows/ci.yml`) also validates and compiles both firmware
examples with ESPHome 2026.9.0 and checks that ESPHome 2026.8.2 refuses them.
Home Assistant's test harness does not run on Windows; use Linux, WSL or Docker.
[`tests/live/README.md`](tests/live/README.md) describes an opt-in REST smoke
test against a running HA that uses only the mock provider.

## History

The project began as a mock-only teaching release and then gained a physical
bridge built for one vendor's equipment. That history is kept for reference;
it does not describe the current design.

- **0.1.0 / 0.2.0 (mock-only):** provider-backed mock scanning and the sidebar.
  The mock-only tutorials remain available:
  [v0.2.0 source](https://github.com/WOOWTECH/Woow_ha_esphome_modbus_scanner/blob/main/docs/tutorial/woow-esphome-modbus-scanner-v0.2.0-zh-TW.html) ·
  [raw v0.2.0 HTML](https://raw.githubusercontent.com/WOOWTECH/Woow_ha_esphome_modbus_scanner/main/docs/tutorial/woow-esphome-modbus-scanner-v0.2.0-zh-TW.html) ·
  [Source-file view for v0.1.0](https://github.com/WOOWTECH/Woow_ha_esphome_modbus_scanner/blob/main/docs/tutorial/woow-esphome-modbus-scanner-v0.1.0-zh-TW.html) ·
  [v0.1.0 tutorial HTML release asset](https://github.com/WOOWTECH/Woow_ha_esphome_modbus_scanner/releases/download/v0.1.0/woow-esphome-modbus-scanner-v0.1.0-zh-TW.html) ·
  [raw v0.1.0 HTML](https://raw.githubusercontent.com/WOOWTECH/Woow_ha_esphome_modbus_scanner/main/docs/tutorial/woow-esphome-modbus-scanner-v0.1.0-zh-TW.html) ·
  [v0.1.0 source archive](https://github.com/WOOWTECH/Woow_ha_esphome_modbus_scanner/archive/refs/tags/v0.1.0.zip).
  They describe mock-only behaviour, not ESPHome firmware.
- **0.3.0.dev1–0.3.0.dev3:** an experimental FC03 bridge for the Guanjie IN-D17
  (slave IDs 1–32, 13 allowlisted registers, 700 ms), see
  [ADR 0004](docs/adr/0004-experimental-guanjie-fc03-bridge.md) (superseded by
  ADR 0005), the [first physical acceptance](docs/history/guanjie-live-acceptance.md),
  the [dual-node validation](docs/history/dual-node-live-acceptance.md) and the
  [UI reacceptance, 124/124](docs/history/ui-reacceptance.md).
- **0.4.0.dev1 (last deployed build):** encrypted API keys, firmware health and
  watchdog, verified polling recovery, persisted history, diagnostics, Repairs
  and reauth, deployed to two nodes. See the
  [live acceptance](docs/history/hardening-live-acceptance.md),
  [upgrade and rollback](docs/history/hardening-upgrade-rollback.md),
  [software checkpoint](docs/history/hardening-software-checkpoint.md) and
  [implementation phases](docs/history/implementation-phases.md).
  Its firmware, `firmware/guanjie-scanner/`, runs Bridge Protocol v1 and stays
  until those nodes are reflashed.
- Earlier design notes: [0.2.0 service and safety model](docs/history/service-and-safety-model.md),
  [0.2.0 testing strategy](docs/history/testing.md). All of these live in
  `docs/history/`.

## License

MIT — see [LICENSE](LICENSE).
