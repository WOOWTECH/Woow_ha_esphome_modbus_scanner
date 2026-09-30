# Dual-node physical and frontend validation (2026-09-30)

**Outcome: both enrolled ESPHome nodes work with the physical provider, but the
frontend is NOT fully accepted. Six confirmed UI defects remain.** This is an
experimental feature branch, not a production release.

## What was actually deployed and tested

- HA 2026.7.2; ESPHome 2026.9.0 on both nodes.
- Both nodes advertise `modbus_scanner_probe_v1` and its result text sensor.
- Node A received the bridge without replacing its previous UART-managed RS485
  half-duplex repair. Node B retained its previously deployed bridge firmware.
- The singleton integration now offers a reconfigure flow with two host/MAC
  pairs. Duplicate hosts/MACs and incomplete or malformed pairs are rejected.
- Two independent gateways were exercised through the real HA services. MACs
  were checked before uploading. No FC06, persistent address change, compressor
  command, Wi-Fi clearing, partition-table rewrite or bootloader update was used.
- Recovery images and credentials are private and are not in this repository.

## Physical results

| Check | Node A | Node B |
| --- | --- | --- |
| All 13 allowlisted registers at slave 1 | 13/13 responded | 13/13 responded |
| Observed bus-response latency for those reads | 40–41 ms | 38–39 ms |
| Inclusive scan 1–32 | completed 32/32 | completed 32/32 |
| Full-range outcome | slave 1 responded, 31 timeouts | slave 1 responded, 31 timeouts |
| Concurrent independent gateways | passed | passed |
| Duplicate scan on the same gateway | rejected busy | rejected busy |
| Cancel and later fresh read | passed | passed |
| Reload integration during scans, then read again | passed | passed |
| Correct/wrong HA device identity selection | accepted/rejected | accepted/rejected |
| 5000ms inter-address delay in a two-address scan | exercised | exercised |
| Post-test normal polling, 60 seconds | Online, no warnings | Online, no warnings |

Normal requested/active addresses remained 1; both machines remained OFF and
retained their original setpoints. Reported bus latency excludes draining, quiet
intervals, API latency and the test harness. Timeouts do not prove vacant addresses,
and responses do not prove unique physical identity.

## Test matrix and evidence interpretation

The private detailed report contains **226 logical checks: 220 passed and 6 UI
checks failed**:

- enrollment/reconfigure: 9/9;
- field/API validation: 65/65;
- physical operations: 45/45;
- lifecycle, device mapping and history: 12/12;
- supplemental guards and external tutorial links: 9/9;
- frontend controls: 80/86 after an explicitly documented harness correction.

An additional four recent-history checks, twelve provider unit tests, seven
frontend model tests, the C++ scanner state-machine tests, and bundle drift/lint
checks passed. These are not added to the 226-case count.

The installed frontend bundle was retrieved from HA and exercised with a real
Chromium browser. Its calls were forwarded to actual HA services: both nodes were
read and scanned through the rendered controls. The outer browser context was a
minimal HA shell with REST forwarding, **not an acceptance test of HA login,
native WebSocket error rendering, non-admin accounts, icons supplied by HA, or
the complete HA navigation shell**. The menu test confirms event dispatch only.

Six mock profiles exercised outcome/count/evidence presentation in the actual
HA mock provider. They are not physical collision, exception or disconnect tests.
The future device selector remains disabled; API device-ID mapping was separately
verified. Physical support remains FC03/count=1, allowlisted registers, IDs 1–32
and fixed 700ms timeout, not every option advertised by the upstream mock panel.

## Confirmed UI defects (not fixed by this validation)

1. **High:** physical selection still displays `v0.2.0 — MOCK ONLY` and says the
   panel never contacts hardware. Actual physical calls contradict that notice.
2. Mock-profile selector and quick buttons remain active for physical gateways,
   although they do not affect physical probes.
3. Generic UI bounds still show 247 addresses/count 125 instead of the physical
   limits; backend validation safely rejects unsupported requests.
4. Selecting a physical gateway does not supply compatible defaults. The user
   must manually choose FC03, a supported register, count 1, 700ms, pause=true.
5. **High:** page reload resets the physical gateway selection to mock. This can
   cause users to mistake later simulated evidence for physical results.
6. Edited numeric preferences are lost on reload: DOM input values are strings,
   while preference sanitization retains only numbers.

Until corrected, prefer the explicitly documented HA service payloads and always
check `provider: esphome` and the gateway identity. Do not claim complete UI or
production acceptance.

## Harness incidents and remaining limits

One SSH polling connection failed during the dual full-range scans. The scans
continued in HA; querying their original IDs later confirmed both completed
32/32. The test helper's repeated unauthenticated preliminary SSH handshake was
removed. No responder results were synthesized to fill this gap.

The initial browser helper tried to click a menu that is intentionally hidden
outside narrow shell mode. Another helper used `selectOption(string)`, which
matched a recent-ID placeholder label instead of the option's value. Explicit
narrow context and `selectOption({value: id})` corrected these harness assumptions;
four history checks then passed. Original attempts were retained in private
artifacts; neither incident is counted as a product defect.

No deliberate wiring fault, real duplicate-ID collision, CRC corruption, power
loss or 24/72-hour endurance test was performed. Firmware callbacks and mock
scenarios do not substitute for those physical tests. The native API remains
unencrypted as originally configured; this was not a security certification.
The full upstream HA pytest/coverage suite was not rerun in this environment.
