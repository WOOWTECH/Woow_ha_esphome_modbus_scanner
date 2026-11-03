# ADR 0008: Scanner service set and persisted Scan history

- Status: accepted; supersedes the service-count clauses of
  [ADR 0002](0002-singleton-service-lifecycle.md) and
  [ADR 0003](0003-all-user-sidebar-and-service-policy.md), and the in-memory
  history consequence of ADR 0002
- Date: 2026-11-03
- Version: 0.5.0.dev1

## Context

ADR 0002 and ADR 0003 were written for the mock-only 0.2.0 release. They say
that setup registers "six services" and that the all-user policy covers
"exactly the six scanner services". ADR 0002 also says that Scan history is
in-memory and disappears on unload. All three statements became false before
0.5.0.dev1: 0.4.0.dev1 added `check_gateway` and `get_history` and stored
history in Home Assistant storage, and 0.5.0.dev1 adds `set_pausable_pollers`
and the four Device Profile services.

## Decision

- The scanner services are the services in `services.yaml`. The
  singleton-lifecycle rules of ADR 0002 and the all-user policy of ADR 0003
  apply to every one of them. These documents do not state a count, so a new
  service does not make them stale.
- All active Home Assistant users and internal automations may call every
  scanner service, including the ones that write state:
  - `set_pausable_pollers` writes the Pausable Poller selection of a Bus into the
    config entry options (ADR 0006).
  - `import_device_profile` and `delete_device_profile` write Device Profiles
    into Home Assistant storage (ADR 0005).
  This is the spec #2 policy ("authorization unchanged: all active
  authenticated HA users"). Enrollment, keys and Gateway hosts stay behind
  Home Assistant's own config-flow permissions.
- Scan history is the 20 most recent finished Scans, kept in Home Assistant
  storage. It survives a reload and a restart. It is not part of the config
  entry.

## Consequences

- A user who changes the saved Pausable Poller selection changes the default
  for the next Scan of every user on that Bus. The selection only has an effect
  inside a Scan Lease, which the Gateway ends after 5 s idle or 10 min (ADR 0007).
- A user can delete an imported Device Profile that another user imported.
  Finished Scan results keep the Device Profile label they were recorded with.
- [Authorization boundary](../design/authorization-boundary.md) names these
  writes as part of the all-user policy.
