# Woow ESPHome Modbus Scanner

Read-only, best-effort discovery of which Modbus RTU slave IDs answer on an RS-485 bus reached through an ESPHome node, driven from Home Assistant.

## Language

**Gateway**:
An enrolled ESPHome node that runs the scanner component on one or more Buses.
_Avoid_: Bridge, node, ESP, device

**Enrollment**:
Registering a Gateway with the integration after its identity and Bridge Protocol have been verified; only enrolled Gateways can be scanned.
_Avoid_: Pairing, adding a device

**Bridge Protocol**:
The versioned contract between the integration and the scanner component on a Gateway; v2 is current and v1 is the deprecated vendor-specific predecessor.
_Avoid_: Firmware API, bridge (as a name for the Gateway)

**Legacy Gateway**:
A Gateway still running Bridge Protocol v1, which keeps its fixed vendor limits until it is reflashed with the scanner component.
_Avoid_: Old gateway, v1 device

**Bus**:
One Modbus RTU line on a Gateway, served by exactly one scanner instance; Scans of one Bus run one at a time.
_Avoid_: Hub, line, channel, port

**Probe**:
One read-only request sent to a single slave ID on a Gateway's bus.
_Avoid_: Ping, poll, read

**Probe Slot**:
The turn a Probe holds while it is in flight. In per-Bus mode every Bus has its own; in the shared-slot fallback (any Bus whose own result and lease sensors HA cannot resolve) the whole Gateway has one, and its Buses take turns for it.
_Avoid_: Lock, channel, bus lock

**Scan**:
An ordered series of Probes over a range of slave IDs on one Bus.
_Avoid_: Sweep, discovery job

**Responder**:
A slave ID that produced a correlated reply to a Probe; it is not proof of exactly one physical device behind that ID.
_Avoid_: Device, slave, found device

**Device Profile**:
The readable registers, defaults and limits for one class of field device; the Generic Device Profile is the only built-in one.
_Avoid_: Profile (unqualified), device map, template

**Profile Field**:
A named register in a Device Profile, with optional unit and scale, used to show a Responder's raw value as a decoded value.
_Avoid_: Mapping, point, tag

**Generic Device Profile**:
The vendor-neutral Device Profile that permits any register with bounded read size and no register allowlist.
_Avoid_: Default profile, universal profile

**Large Range**:
A Scan over more than 32 slave IDs, which needs a second explicit confirmation because of its duration and traffic.
_Avoid_: Full scan, big scan

**Mock Scenario**:
One of the fixed, reproducible outcome sets produced by the mock provider for development and testing.
_Avoid_: Mock profile, simulation profile

**Normal Polling**:
The periodic traffic that other components on the same Gateway send to field devices outside of any Scan.
_Avoid_: Background reads, regular traffic

**Pausable Poller**:
A component polling the same Bus as the scanner that a Scan may hold paused; the user chooses which ones per Bus.
_Avoid_: Pause list entry, controller

**Scan Lease**:
The window during which a Gateway holds the selected Pausable Pollers paused for one Scan, ended by completion, idle expiry, a hard limit, or a probe of another Scan superseding it; the Gateway itself enforces every ending except completion.
_Avoid_: Pause window, lock
