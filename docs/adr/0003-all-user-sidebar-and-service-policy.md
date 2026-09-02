# ADR 0003: All-user sidebar and scanner services

- Status: accepted
- Date: 2026-09-02
- Version: 0.2.0

## Decision

Register one standalone `panel_custom` page at
`/woow-esphome-modbus-scanner` with `require_admin: false`, and permanently
remove admin/user checks from exactly the six scanner services. Authentication,
service schemas, config-entry ownership, gateway serialization, and scan safety
confirmation remain unchanged. The panel is independent of other protocol
integrations and uses only `hass.callService`.

The versioned static Lit/Rollup bundle is distributed inside the integration.
Only non-secret preferences, disclosure state, and recent scan IDs may be stored
in browser localStorage.

## Consequences and explicit risk

Every authenticated Home Assistant user can list gateways, start, inspect,
cancel, and test scans. This is convenient for the mock-only teaching release,
but a future physical provider could allow any user to generate bus traffic,
disrupt normal polling, and inspect responder evidence. Account access must be
controlled. A physical provider may not be enabled without explicitly
reassessing this accepted policy and documenting mitigations; adding hardware
must never silently imply that the current all-user boundary is harmless.
