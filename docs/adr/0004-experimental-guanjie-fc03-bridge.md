# Experimental Guanjie FC03 bridge (historical local 0.3.0.dev1)

> Historical decision record. The current `0.4.0.dev1` deployment adds encrypted
> native API access, firmware health/watchdog, verified recovery and an actual
> physical sidebar. See [current acceptance](../design/hardening-live-acceptance.md)
> and [upgrade/rollback](../design/hardening-upgrade-rollback.md). The plaintext
> installation notes below describe the original prototype, not current devices.

This is a local development change, not an upstream release or generic ESPHome
Modbus support. The upstream sidebar/tutorial remain mock-oriented. Use HA
services for physical bench tests. No hardware acceptance is implied by unit tests.

## Scope and contract

- Explicit host + expected MAC in the singleton config flow. Blank fields retain
  mock-only behavior. The MAC is verified before invoking any ESPHome action.
- ESPHome native API action `modbus_scanner_probe_v1(request_id, slave, reg)` and
  the `Modbus Scanner Result` text sensor are required, with an exact signature.
- Only FC03/count=1, slave 1–32, documented IN-D17 register allowlist and the
  existing fixed 700ms bus timeout are supported. No FC04/FC43/general transport.
- Results include schema v1, random per-attempt request ID, slave/register,
  outcome, latency, and data or exception code. Cached or other-client results
  are never responder evidence. Invalid correlated results fail closed.
- The original ESPHome hub owns CRC/frame parsing. Unparseable frames may end in
  timeout; this bridge cannot diagnose collisions from raw UART bytes. A reply
  does not imply unique device identity.
- Each probe temporarily suspends that node's polling, drains its existing
  transaction, waits 1000ms, performs a single read, waits 1000ms, then restores
  the original RAM transport address and resumes polling. It never changes the
  requested/active address preference, never writes NVS and never issues FC06.
- Normal control/address/WiFi-reset requests are rejected during a probe.
  An already queued control sequence prevents starting a scan probe.
- Polling automatically resumes after a terminal hub callback even if the API
  client disconnects; no remote lease/release message is required. Cancellation
  stops subsequent probes, not a transaction already on the wire. This relies on
  the pinned native hub's terminal callback/700ms timeout, not a second master.
- Long scans can temporarily make normal entity data stale. Polling recovery is
  part of post-scan acceptance, not inferred from returning a probe response.
- The optional HA ESPHome device selector cross-checks the gateway MAC. It does
  not by itself create a transport or supply a read interface.

## Security and installation

The existing all-authenticated-users service policy remains a risk: anyone with
HA access may generate physical bus traffic. Only explicitly enrolled gateways
are available. This prototype preserves the target firmware's existing unencrypted
native API, and is suitable only for a trusted isolated LAN. MAC comparison is
an identity mistake check, not cryptographic authentication. Do not expose port
6053 publicly. Firmware secrets and builds must remain outside the repository.

Pin ESPHome 2026.9.0 as required by the original custom component. Keep a compiled
original-source recovery image and the original OTA credential before flashing.
Recompiling original source is not a bit-for-bit backup of the running flash.
Do not touch the other node or rewrite partitions/bootloader.

## First physical acceptance

```yaml
action: woow_esphome_modbus_scanner.test_address
data:
  provider: esphome
  gateway_id: esphome:aabbccddeeff  # replace with your enrolled gateway
  address: 1
  probe_type: holding_register
  register_address: 25089  # 0x6201
  register_count: 1
  timeout_ms: 700
  retries: 0
  pause_normal_polling: true
```

Retrieve status/results using the returned scan_id. Verify a fresh, correlated
FC03 response and later recovery of normal polling. Then, if appropriate, scan a
small range before considering 1–32. Never present mock outcomes as hardware
results. Provider-only CLI tests do not establish HA service deployment.

## Validation commands

```
python -m unittest discover -s tools -p test_bridge.py -v
g++ -std=c++17 -Wall -Wextra -Werror -fsanitize=undefined \
  firmware/guanjie-scanner/scanner_test.cpp -o /tmp/scanner_test
/tmp/scanner_test
```

The C++ tests cover arbitration state/quiet intervals/timeout/wraparound, not the
actual UART or complete component. A full ESPHome compile and live acceptance
are mandatory before claiming the feature works on hardware.
