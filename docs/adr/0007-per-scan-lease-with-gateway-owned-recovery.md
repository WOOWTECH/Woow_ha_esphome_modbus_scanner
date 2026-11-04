# ADR 0007: A Scan Lease per Scan, ended and recovered by the Gateway

- Status: accepted; the Buses' turn-taking for Probes superseded by [ADR 0010](0010-per-bus-result-and-lease-sensors.md)
- Date: 2026-11-03
- Version: 0.5.0.dev1

> **Superseded in part.** On firmware with per-Bus Result and Lease sensors each
> Bus of a Gateway probes on its own; the last consequence below (Buses take
> turns for Probes) now applies only to the shared-slot fallback for older v2
> firmware. See ADR 0010. The Scan Lease rules still apply.

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
that `scan_id`. So that a Scan's own gaps never reach the idle time, HA caps
the inter-request delay of a bridge v2 Scan at 3000 ms (the contract's
`lease.inter_request_delay_max_ms`, applied through the bridge v2 probe limits;
Legacy Gateways have no lease and keep their frozen 5000 ms), leaving the rest of the 5 s for API round
trips.

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
  probes run without pausing. When the Gateway ends the lease early (`idle`,
  `hard_limit` or `superseded`) while the Scan runs, HA reports the last Slave ID
  finished under the lease as `lease_ended_after_address`. The sidebar explains
  the early end and marks the Responders probed after it. Before a Large Range
  Scan on a bridge v2 Gateway, the sidebar warns when the estimate is longer than
  the hard limit.
- `superseded` happens only when a probe with another `scan_id` reaches a Bus
  whose lease is still active: for example after an HA restart during a Scan, a
  second HA instance, or a native ESPHome action call. HA itself runs one Scan
  per Bus, so a normal Scan never supersedes another.
- Scans of different Buses on one Gateway take turns for Probes, so a Scan also
  waits one Probe of every other running Scan between its own Probes. HA refuses
  a new Scan when that wait plus the inter-request delay would pass
  `lease.inter_request_delay_max_ms` for any Scan that pauses Normal Polling.
