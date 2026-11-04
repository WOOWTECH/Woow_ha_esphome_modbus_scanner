# ADR 0009: FC43/14 device identification removed from 0.5.0

- Status: accepted
- Date: 2026-11-04
- Version: 0.5.0.dev1

## Context

In 0.4.x, `device_identification` (Modbus FC43, MEI type 14) was a Probe type
and the default of the panel and of `start_scan` without a Device Profile. Only
the mock provider implemented it. It returned fixed vendor and product strings
and the outcome `identified`. No physical Gateway sent FC43:

- Bridge Protocol v1 accepts FC03 only (ADR 0004).
- Bridge Protocol v2 allows function codes 3 and 4 only. `contract.json` has a
  case that rejects FC43 with `unsupported_function_code`.

Spec #2 lists "FC01/FC02 and FC43/14 device identification" as out of scope for
this phase. It also lists the 0.5.0 Scan outcomes (Story 52) without
`identified`, and it limits the Generic Device Profile, the firmware and the
mock to FC03/FC04 (Stories 18 and 61). Before this decision, a mock Scan could
report an outcome that a physical Scan can never report.

## Decision

- `device_identification` is not a Probe type in 0.5.0. The service schema
  rejects it.
- `identified` is not a 0.5.0 Scan outcome. No Mock Scenario reports it.
- Scan history written by 0.4.x stays readable. `identified` is accepted as a
  history-only outcome, and the panel still shows its rows, vendor, product and
  count.
- FC43/14 can come back in a later phase as an additive change inside Bridge
  Protocol v2. That needs a firmware parser for identification objects, a new
  Probe type and outcome, and Device Profile support.

## Consequences

- A script or automation that sends `probe_type: device_identification` gets a
  schema error. Remove the field or use `holding_register` / `input_register`.
- A mock Scan without `probe_type` now uses FC03 and reports `responded`
  instead of `identified`. An automation that reads
  `outcome_counts.identified` gets 0.
- Physical Gateways lose nothing, because they never supported FC43.
- The v0.1.0 and v0.2.0 tutorials still show `device_identification`. They
  document those releases and stay unchanged.
