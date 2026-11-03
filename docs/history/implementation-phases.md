# Hardening implementation tracker

Baseline: `0.3.0.dev3` / `62eabb3`. Current experimental deployment: `0.4.0.dev1`.
Node 2 was the canary; node 1 followed only after its acceptance. See
[live acceptance and evidence boundaries](hardening-live-acceptance.md),
[authorization](authorization-boundary.md), and
[upgrade/rollback](hardening-upgrade-rollback.md).

The checked items mean implementation and the targeted acceptance described in
the report are complete. They do not imply every destructive fault, every board,
or long-term endurance has been tested. The earlier offline-only checkpoint is
retained as historical evidence, not current deployment status.

## A — Trustworthy state and consistent rules
- [x] Current freshness separated from historical command outcome; stale optional-data regression.
- [x] Canonical versioned profile generates Python, JavaScript and firmware constants.
- [x] Profile-aware omitted defaults; explicit unsupported parameters rejected.
- [x] Structured translated errors and typed register results.
- [x] Capability-driven UI, valid non-executing YAML generation, unknown-profile blocking.
- [x] Boot-relative control-result timestamp, UTC job timestamps and bounded phase timeline.

## B — Recovery and diagnostics
- [x] Bounded cleanup, interruptible waits and operation budgets; cooperative stop/reload recovery.
- [x] Firmware telemetry and host verification of fresh normal polling, not merely bus release.
- [x] API-only health distinct from fresh bus evidence.
- [x] Redacted diagnostics, 32-event ring, actionable Repairs and real reauth acceptance.
- [x] Twenty persisted terminal snapshots; interruption checkpoints never replayed.
- [x] Actual history/export UI, elapsed phases and explicit recovery/cleanup status.

## C — Deployment hardening
- [x] Masked PSKs, retention by MAC, explicit clearing, reauth and secret redaction.
- [x] All active HA users and existing internal automations permitted as requested.
- [x] Real ordinary/read-only-group/admin logins and a real context-free automation.
- [x] Upgrade/rollback documentation, private recovery artifacts and version checks.
- [x] HA-framework, frontend, portable firmware and privacy gates.
- [x] Both device-specific native builds; UART repair and original controls preserved.
- [x] Canary application OTA and encryption; both HA credential consumers updated.
- [x] Second-device migration, real HA UI, concurrent scans, client loss and HA restart tests.

## Explicit limits
- No FC06/FC16 scanner operation, appliance activation, persistent slave-address
  change, automatic reboot/replay, factory reset or Wi-Fi reset.
- Watchdog wedging, malformed-frame injection, sudden power loss, failed OTA/
  rollback drills and multi-day endurance were **not** induced on live hardware.
  Corresponding model/fake-transport tests are labeled as such.
- A bounded live observation is not a multi-day endurance certification, and test
  coverage is not Home Assistant quality-scale certification.
