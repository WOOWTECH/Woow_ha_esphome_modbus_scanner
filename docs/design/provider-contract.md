# Gateway provider contract

## Implemented providers (0.5.0.dev1)

- `MockGatewayProvider` (`provider: mock`): two simulated Gateways
  (`mock:rs485-gateway` with one Bus, `mock:multi-bus-gateway` with two) and six
  Mock Scenarios. No network, serial, ESPHome or Modbus I/O.
- The ESPHome provider (`provider: esphome`) routes each enrolled Gateway to its
  adapter: bridge v2 (`modbus_scan/bridge_v2/`, the `modbus_scanner` firmware
  component, contract in `bridge_v2/contract.json`) or legacy bridge v1
  (`modbus_scan/legacy_v1/`, deprecated). Adapters are registered in one place,
  `modbus_scan/adapters.py`.

Each provider reports its limits and defaults as `ProbeLimits` on its
`GatewayInfo`; the coordinator validates every request against those limits
intersected with the selected Device Profile's limits.

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

## Requirements for a physical provider

Written before any physical adapter existed; the bridge v2 adapter meets them,
with polling pause implemented as a Gateway-owned Scan Lease
([ADR 0007](../adr/0007-per-scan-lease-with-gateway-owned-recovery.md)) instead
of an HA-side `finally`. A physical adapter must:

1. Resolve an optional Home Assistant `esphome_device_id` to an explicit
   provider gateway and verify that gateway is currently available.
2. Establish that a supported upstream API exposes the required serial/Modbus
   read transaction. A registry device alone is not a transport API.
3. Use only holding-register (FC03) or input-register (FC04) read probes; FC43/14
   device identification is out of scope for 0.5.0. It must never write a
   register, change a Slave ID, or restart a node.
4. Enforce the coordinator's one-Scan-per-Bus key and avoid hidden parallel
   requests inside the adapter. Scans on different Buses of one Gateway may run
   at once but share the Gateway's single Probe slot.
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

Adding another adapter requires an ADR, integration tests at the service seam,
documentation updates and a version change.
