# Guanjie bridge: initial physical acceptance

Date: 2026-09-30 (UTC+08:00). Local experimental branch `0.3.0.dev1`.
These observations are from actual HA services, not mock-provider outcomes.
Private hosts, MACs, credentials, and per-request identifiers are not published.

## Deployment verified

- Home Assistant 2026.7.2: custom integration installed and config entry `loaded`.
- ESPHome 2026.9.0 / ESP32: original-source recovery image compiled and retained;
  experimental bridge firmware compiled and uploaded successfully via native OTA.
- Application-only OTA: no partition table or bootloader update.
- MAC checked before OTA; device name and network configuration preserved.
- After reboot: 29 entities and `modbus_scanner_probe_v1` advertised (previously
  28 entities and no user services). Normal Modbus polling was Online.

## Actual HA -> ESPHome -> Modbus results

| Test | Observed result |
| --- | --- |
| `test_address`, slave 1, FC03, register `0x6201`, count 1 | Completed, value `0`, CRC-valid response, measured bus latency 40 ms |
| `start_scan`, inclusive range 1–3, same register | Completed all 3 addresses; slave 1 responded with `0` in 39 ms; 2 timeouts; no gateway error |
| `cancel_scan`, range 1–3 | Cancelled after the in-flight read at slave 1; 1/3 addresses completed, no further probes |
| Post-test health observation, 30 seconds | Online, normal target/active address still 1; 53 normal status/temperature updates; no warning/error logs observed |

The returned value is the power-state register, not a command to turn anything
off. Test code never issued FC06, changed a persistent address preference, or
altered the slave's own address. Temporary transport addressing is owned by the
bridge. Read latency above excludes pre/post quiet intervals and API overhead.

Timeouts at 2 and 3 do **not** establish that these addresses are unused. A reply
at 1 does **not** establish unique physical identity. This acceptance does not
cover a full 1–32 scan, arbitrary ESPHome firmware, other baud rates, generic
register reads, collision diagnosis, cryptographic transport security, or HA
sidebar physical-mode UX. Use the documented service payloads for this build.

## Software verification

- 12 standalone provider tests passed against aioesphomeapi 45.3.1 (HA's version),
  including missing firmware, identity mismatch, stale/empty initial state,
  mismatched response, bounded retries, cancellation and connection loss.
- C++ host scanner state-machine tests passed with undefined-behavior sanitizer.
- Original and modified full ESPHome firmware compiled successfully.
- Python lint passed; actual HA runtime imports and service execution passed.
- The full upstream pytest/coverage and browser suites were **not** rerun as part
  of this initial hardware acceptance. This remains an experimental feature branch,
  not a production-ready upstream release.

The compile/test cycle caught and fixed an ESPHome lambda pointer mismatch in
initializing the result sensor. The API handler also ignores the unpublished
initial text sensor state while awaiting a correlated result. Neither was hidden
by substituting cached entity telemetry for a real transaction.
