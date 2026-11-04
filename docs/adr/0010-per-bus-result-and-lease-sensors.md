# ADR 0010: Per-Bus Result and Lease sensors, so Buses probe independently

- Status: accepted; supersedes the "Scans of different Buses on one Gateway take turns for
  Probes" consequence of [ADR 0007](0007-per-scan-lease-with-gateway-owned-recovery.md)
- Date: 2026-11-04
- Version: 0.5.0.dev1

## Decision

Every Bus on a Gateway gets its own result and lease text sensor:
`Modbus Scanner v2 Result <bus>` and `Modbus Scanner v2 Lease <bus>`, `<bus>` being the
Bus name. The `modbus_scanner` codegen creates them for every entry; users do not declare
them, and existing YAML only needs a reflash. The Bus reports their exact entity names in
its info entry as the optional `result_sensor` and `lease_sensor` fields.

The Gateway's shared Info, Result and Lease sensors stay. Every result and lease message
of a Bus goes to that Bus's own sensor and is mirrored on the shared one, so older HA
versions, which read only the shared sensors and keep one Probe Slot per Gateway, keep
working. A rejection for a Bus the Gateway does not have goes to the shared result sensor
only. This is an additive change within Bridge Protocol v2 (`bus_text_sensors` and
`info.optional_bus_fields` in `contract.json`); `bridge_version` stays 2.

HA has exactly two modes per Gateway, chosen each time it reads info. It never mixes them:

- **Per-Bus mode**: every Bus in info names both sensors, and each name matches exactly
  one text sensor. HA reads only the per-Bus sensors and ignores the shared mirrors. The
  Probe Slot is keyed by (Gateway, Bus), and `concurrent_wait_max_ms` does not apply, so
  each Scan waits only for its own `inter_request_delay_ms`.
- **Shared-slot fallback**: any other case, such as v2 firmware from before this change,
  a missing field or a name that does not resolve. The whole Gateway keeps one Probe Slot,
  reads the shared sensors, and refuses a concurrent Scan whose waits would pass
  `lease.inter_request_delay_max_ms`.

Both modes require the shared sensors. HA takes the names from info and never derives
them from the pattern.

Every Scan reads info itself and takes the Probe Slot that its own info gives. New Scans
are admitted under the mode of the last info read (by `check_gateway` or a Scan), and that
mode stays until the next info read: a Scan that starts or ends does not change it. Until a
Gateway's info has been read once, HA assumes the shared slot. `check_gateway` reports the
mode as `health.probe_slots` (`per_bus` or `shared`), the Gateway's limits report
`probes_take_turns`, and `list_gateways` reports the Buses that run a Scan now as
`running_buses`.

## Why

The ESPHome API batches state per entity and sends only the latest state of each entity in
a batch. With one result sensor per Gateway, two Buses publishing results close together
lose one of them, so HA had to keep one Probe in flight per Gateway. The Buses then took
turns: concurrent Scans each ran about twice as slow, about three Buses at the defaults
were the most that could scan together, a lost result on one Bus held the slot for up to
the timeout plus 5 s, which could push another Bus's Scan Lease past its 5 s idle time,
and two Buses ending their leases in the same `loop()` could lose a lease message. A
sensor per Bus keeps each Bus's messages on its own entity, so a batch can no longer
merge them.

The all-or-nothing rule keeps the model simple. Scans on one Gateway either all take
turns or never do, and one rule decides which.

## Considered options

- **ESPHome action responses** (`supports_response`): rejected; they need ESPHome
  internals that `CustomAPIDevice` does not expose.
- **Sequence numbers on the shared sensor**: rejected; they detect a lost state but
  cannot recover one the batch never sent.
- **Choosing the mode per Bus**: rejected; Buses of one Gateway in different modes would
  still contend on the shared sensors.
- **Removing the shared sensors (Bridge Protocol v3)**: rejected for now; older HA
  versions would stop working with new firmware.

## Consequences

- New firmware publishes every message twice, on the Bus's sensor and the shared one.
- In the shared-slot fallback the duration estimate still leaves out other Scans' Probes.
  When another Bus of the Gateway is scanning, the sidebar says so next to the estimate.
  The sidebar shows an estimate only for a Large Range, so the caveat shows only there.
- A Gateway reflashed to firmware without per-Bus sensors after its last info read can have
  Scans admitted under the per-Bus limits. Each of these Scans still reads info and takes
  the shared slot, so no result is lost; the waits can pass the Scan Lease idle limit, and
  the Gateway then ends the lease and Normal Polling resumes during the Scan. We accept
  this: holding every Scan's mode at the shared slot until its info read would refuse two
  Buses started a moment apart, the main use of this change.
- A user entity that happens to have the same name as a per-Bus sensor makes that name
  match two text sensors, so HA falls back to the shared slot for the whole Gateway.
- Hardware multi-Bus validation needs a reflash and is tracked separately (#16, part B).
