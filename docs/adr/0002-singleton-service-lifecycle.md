# ADR-0002: Singleton service lifecycle

- Status: Accepted; service count and in-memory history superseded by [ADR 0008](0008-scanner-service-set-and-persisted-history.md)
- Date: 2026-08-17

> **Superseded in part.** The scanner services are now every service in
> `services.yaml`, not six, and Scan history is kept in Home Assistant storage.
> See ADR 0008. The lifecycle rules below still apply.

## Context

Home Assistant services are domain-global while scan tasks need an explicit
owner. Registering them per arbitrary entry creates ambiguous ownership and
unload races.

## Decision

The config flow permits exactly one entry. Setup creates one coordinator and
registers six services idempotently. A persistent lifecycle object serializes
setup and unload, assigning each owner a generation so stale and duplicate calls
cannot tear down newer state. Unload first marks handlers unavailable and removes
services, then cancels and awaits every active task and removes the retained
coordinator. Only the empty lifecycle tombstone remains to serialize later setup.

A handler dispatched before service removal re-checks availability after its
administrator check. It fails closed rather than recreating a coordinator after
unload. Coordinator shutdown also repairs tasks cancelled before their coroutine
body starts.

## Consequences

There is no shared multi-entry lifecycle. Reload has deterministic task and
service ownership. All scan history is intentionally in-memory and disappears
on unload.
