# Gateway provider contract

## 0.1.0 implementation

Only `MockGatewayProvider` exists. It advertises one simulated gateway and six
deterministic profiles. It performs no network, serial, ESPHome, or Modbus I/O.

## Interface

A provider supplies a unique `provider_id` and:

```python
def list_gateways() -> Sequence[GatewayInfo]: ...

async def run_scan(
    request: ScanRequest,
    emit: Callable[[ProbeResult], None],
    cancelled: Callable[[], bool],
) -> None: ...
```

`list_gateways` returns stable, provider-owned IDs and honest capabilities.
`run_scan` receives an already validated, bounded request whose `probe_type` is
a `ProbeType`, and emits results incrementally. A successful, non-cancelled run
must emit exactly one result for every address in the inclusive range; empty,
partial, duplicate, or out-of-range output fails the scan. It checks cancellation
between transactions and returns normally when cancellation is observed. A
transport failure that prevents continuation raises `GatewayProviderError`,
including the failing address when known.

The coordinator validates every emission again. Addresses must be exact integers
within the request, appear at most once, and carry a `ScanOutcome`, non-negative
integer latency, string detail, an optional byte-sized exception code, and an
optional string-to-string identity mapping. Invalid adapters fail the scan
without corrupting counts.

## Requirements for a future ESPHome provider

A future adapter must:

1. Resolve an optional Home Assistant `esphome_device_id` to an explicit
   provider gateway and verify that gateway is currently available.
2. Establish that a supported upstream API exposes the required serial/Modbus
   read transaction. A registry device alone is not a transport API.
3. Use only device-identification, holding-register read, or input-register read
   probes. It must never write a register, change a Slave ID, or restart a node.
4. Enforce the coordinator's one-scan-per-gateway key and avoid hidden parallel
   requests inside the adapter.
5. Apply timeout, retry, and inter-request delay bounds without extending work
   beyond the requested inclusive address range.
6. If `pause_normal_polling` is supported, pause only the selected gateway and
   restore polling in `finally` on completion, failure, cancellation, or unload.
   If unsupported, reject the request clearly rather than pretending it worked.
7. Check `cancelled()` between transactions and allow task cancellation to
   propagate after transport cleanup.
8. Normalize CRC-valid protocol exceptions as responder evidence, distinguish
   timeouts from gateway loss, and report ambiguous framing as a possible
   collision rather than a unique discovery.
9. Avoid credentials, host details, raw frames, or private registry data in
   public service responses and logs.

Adding the adapter will require a new ADR, integration tests against the selected
upstream API, documentation updates, and an explicit version change. The
reserved selector in 0.1.0 is forward-compatible UI metadata, not a claim that
these requirements are already feasible.
