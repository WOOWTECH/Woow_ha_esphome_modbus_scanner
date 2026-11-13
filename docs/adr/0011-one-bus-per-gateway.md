# ADR 0011: One Bus per Gateway

- Status: accepted; supersedes [ADR 0010](0010-per-bus-result-and-lease-sensors.md) and the
  "Scans of different Buses on one Gateway take turns for Probes" consequence of
  [ADR 0007](0007-per-scan-lease-with-gateway-owned-recovery.md)
- Date: 2026-11-09
- Version: 0.5.0.dev3
- Issue: #26

## Decision

A Gateway serves exactly one Bus. A node with two `modbus_scanner:` entries fails to
compile, and HA refuses to enroll or check a Gateway whose info reports more than one Bus.
To scan a second RS-485 line, use a second node.

Bridge Protocol v2 keeps its wire format: the `bus` action argument and the `buses` array in
info stay, and `buses` always has one entry; `bridge_version` stays 2. The per-Bus Result and
Lease sensors of ADR 0010 are removed, together with the two probing modes (`per_bus`,
`shared_slot_fallback`), `probe_slots` and `concurrent_wait_max_ms`. With one Bus, a Gateway
has at most one Probe in flight and at most one Scan, so nothing takes turns. The Bus keeps its
name and serial parameters, which HA shows with every result, and Pausable Poller selections
stay keyed by Bus.

## Why

Several Buses per Gateway (#9, extended by #18) came from generalising the scanner to "any
Modbus hub", not from a product or customer that needed it, and WOOWTECH's Gateways have a
single RS-485 port. It kept costing: the per-Bus probing machinery in firmware, HA and the
panel, about a thousand lines of tests, live acceptance that could not run without two-Bus
hardware (#16), and the Info sensor growing past Home Assistant's 255-character state limit
(#25). No 0.5.x was released, so removing it needs no migration.

## Considered options

- **Bridge Protocol v3 without `bus`**: rejected. Every Gateway would need a reflash and HA
  would have to speak v2 and v3, only for a cleaner wire format.
- **Keep the feature and defer its acceptance**: rejected. The cost stays while the feature
  still has no user.

## Consequences

- A node with two RS-485 lines can be scanned on one of them only.
- The protocol carries a `buses` array that always has one entry. Do not read it as
  multi-Bus support.
- #25 is reduced but not fixed: without the per-Bus sensor names a single-Bus Info is about
  160 characters, but every Pausable Poller adds about 34 characters plus its name.
  *Update (#25):* the Info format stays as is; the Info sensor is instead disabled by default,
  so HA stores no state for it, and diagnostics summarize it.
- A Gateway refused for several Buses offers no Pausable Poller checklist and refuses to save
  one, with the one-Bus message. HA keeps the refusal through later failures of any other
  kind (offline, connect); only a check or Scan whose info reports exactly one Bus lifts it.
  The saved checklist is kept and is offered again after that.
- Before any check or Scan after a restart, HA knows no Bus: a save goes to the single Bus a
  checklist was saved for, and is refused for any other Bus.
- A passing check or Enrollment clears only the MULTIPLE_BUSES Repairs issue. Every other
  Gateway issue is still cleared only by a Scan whose cleanup closed and whose recovery is
  verified.
- The retired Probe Slot mode storage file is removed on a best-effort basis at every setup.
  This is a storage cleanup, not a settings migration, so removing several Buses still needs
  no migration.
