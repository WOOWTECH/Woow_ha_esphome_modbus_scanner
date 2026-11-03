# ADR 0005: Vendor-neutral scanner component with HA-side Device Profiles

- Status: accepted; supersedes [ADR 0004](0004-experimental-guanjie-fc03-bridge.md)
- Date: 2026-11-03
- Version: 0.5.0.dev1

## Decision

The firmware side is one standalone ESPHome external component,
`modbus_scanner` (`firmware/components/modbus_scanner/`), that any ESPHome
2026.9.0+ node with a Modbus RTU client hub can add with an
`external_components` entry and one `modbus_scanner:` line per hub. It knows
nothing about field devices: it enforces only the bridge protocol v2 hard
limits (slave 1–247, FC03/FC04, count 1–4, timeout 100–2000 ms, write function
codes refused) defined in the machine-readable contract
`modbus_scan/bridge_v2/contract.json`, which the HA adapter, the HA fake Gateway
and the host-compiled firmware tests all read.

Everything device-specific lives in Home Assistant as **Device Profiles**:
validated JSON documents (`schema_version` 1) with function codes, defaults, an
optional register allowlist and named fields for decoding. They are imported,
exported and deleted through services and the sidebar and stored in HA storage,
so they are part of HA backups. The built-in Generic Device Profile cannot be
deleted. A request is validated against the intersection of the Gateway's
limits and the Device Profile's limits.

## Why

ADR 0004 compiled one vendor's register map, slave range and timing into the
firmware, the HA provider and the panel, kept in sync by a three-way generator.
Supporting a second device class meant a firmware rebuild and a release. Moving
the device knowledge to data in HA lets users add device classes without
reflashing, keeps the firmware small and auditable, and makes the safety limits
a single contract rather than three generated copies.

## Considered options

- **Per-vendor firmware components** (the ADR 0004 shape): rejected; every new
  device class needs C++ changes and a reflash.
- **Device Profiles stored on the Gateway**: rejected; the profile must also
  drive HA-side validation, defaults and decoding, and HA storage is already
  backed up.

## Consequences

- The former vendor register map is just an example profile,
  `examples/device_profiles/guanjie-ind17.json`.
- Gateways still on the legacy bridge v1 keep working with their frozen limits
  through `modbus_scan/legacy_v1/`, and each one raises a Repairs issue asking
  for a reflash with `modbus_scanner`. That code is deleted when the last legacy
  Gateway is gone.
- The contract may only grow additively within bridge v2; removing or changing
  an action argument, field or error code needs bridge version 3.
