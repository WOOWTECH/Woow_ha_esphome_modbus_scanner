# ADR-0001: Provider-backed, mock-first scanning

- Status: Accepted
- Date: 2026-08-17

## Context

A public scanner needs stable Home Assistant services and strong safety semantics
before a physical transport is available. Tying orchestration directly to one
transport would mix validation, task ownership, and response formatting with
hardware-specific state.

## Decision

Use a provider protocol behind one coordinator. Version 0.1.0 registers only
`MockGatewayProvider`. The coordinator owns strict request and provider-emission
validation, one active scan per provider/gateway key, cooperative cancellation,
unload cancellation, normalized snapshots, and a 20-item terminal history.

Expose only six admin-policy services and one singleton config entry. Include an
optional ESPHome device selector as a clearly non-operational future bridge. Do
not include a panel or other configuration features.

## Consequences

Mock mode is complete without hardware and provides deterministic development
seams. No physical support is implied. A future adapter can be added only by
meeting the provider contract and retaining the coordinator's controls. Results
remain best-effort and never claim address absence or uniqueness.
