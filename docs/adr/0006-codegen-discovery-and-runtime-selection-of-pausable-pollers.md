# ADR 0006: Pausable Pollers are discovered at codegen and selected at runtime

- Status: accepted
- Date: 2026-11-03
- Version: 0.5.0.dev1

## Decision

The `modbus_scanner` component finds a Bus's **Pausable Pollers** during
ESPHome code generation: every declared component in the validated config that
is bound to the same Modbus hub (`modbus_id`) and whose generated class inherits
`PollingComponent` (for example each `modbus_controller`) is added to that
Bus's table, with a stable index in YAML order, its YAML name (else its id) and
its slave address. Nobody lists pollers by hand. The Gateway publishes the
table in its bridge v2 info entry.

Which of them a Scan pauses is chosen at runtime in Home Assistant, per Bus:
the sidebar checklist (`set_pausable_pollers`) saves the selection in the config
entry's options, and `start_scan` / `test_address` may override it for one Scan
with `pause_pollers`. All pollers are paused by default, including pollers new
to the firmware. The selection is revalidated against the table the Gateway
reports on every check and at Scan start; rows that no longer match (index,
name and address) are dropped and reported as `removed_pollers`, never sent. An
empty selection runs the Scan without a Scan Lease.

## Why

A hand-maintained pause list in YAML drifts from the real config and is easy to
forget, and a missed poller silently interleaves its traffic with the Scan.
Codegen sees the full validated config, so the table is complete by
construction. Whether to pause a given device, however, depends on the site
(a meter whose readings may go stale for a while versus a controller that must
keep running), so that choice belongs to the user and must not need a reflash.

## Consequences

- Adding or removing a poller only appears after a recompile and reflash; HA
  then reconciles the saved selection.
- Indices are positional. Reordering pollers in YAML changes indices, and the
  name/address match is what keeps a stale saved row from pausing the wrong
  component.
