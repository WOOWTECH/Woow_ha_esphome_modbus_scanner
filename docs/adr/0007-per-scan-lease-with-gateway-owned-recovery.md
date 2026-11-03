# ADR 0007: A Scan Lease per Scan, ended and recovered by the Gateway

- Status: accepted
- Date: 2026-11-03
- Version: 0.5.0.dev1

## Decision

Pausing Normal Polling is a **Scan Lease** held by the Gateway for one Scan
(`scan_id`) on one Bus, not a pause/resume pair driven by Home Assistant. The
first accepted probe of a `scan_id` with a non-empty `pause_pollers` begins the
lease: the selected Pausable Pollers are stopped and the hub's queued frames for
their slave addresses are cleared before the probe's own frame is queued. Every
probe of the same `scan_id` renews it. The lease ends on an explicit
`modbus_scanner_v2_release` from HA (sent on completion, cancellation and
errors), after **5 s idle** (no probe in flight, timed from the last probe's
terminal callback), at a **10 min hard limit** from its start, or when a probe
with a different `scan_id` supersedes it. On every ending path the Gateway
resumes the paused pollers itself. A lease that has ended never restarts for
that `scan_id`.

HA reports the lease in Scan status and results as `lease_status`
(`none`, `active`, `ended`, `unconfirmed`), `lease_end_reason` (`released`,
`idle`, `hard_limit`, `superseded`) and the paused pollers. If the connection is
lost or a release is not answered, HA reports `unconfirmed` and relies on the
Gateway's idle expiry.

## Why

HA, the network and the API connection can all disappear mid-Scan. If recovery
depended on HA sending "resume", a restart or Wi-Fi drop could leave field
devices unpolled indefinitely. Making the Gateway own both timers bounds the
worst case without any message from HA, while the per-Scan identity lets HA end
the lease promptly in the normal case and keeps two Scans from sharing one
pause.

## Considered options

- **HA-driven pause/resume actions**: rejected; no recovery when HA or the link
  fails between the two calls.
- **A per-probe pause** (the ADR 0004 bridge): rejected; it re-pauses and
  resumes polling around every probe, adding quiet periods to each probe and
  churning the controllers throughout a long Scan.

## Consequences

- Clearing a paused poller's queued frames also drops any writes that component
  had pending, for example a setpoint change from an HA entity issued just
  before the Scan. Users should not change settings on paused devices during a
  Scan.
- After the lease ends the first fresh reading from a resumed poller may take up
  to one of its `update_interval`s; until then its HA entities show stale values.
  The sidebar names the paused devices while a lease may hold.
- A Scan longer than 10 minutes continues after the hard limit, but its later
  probes run without pausing.
