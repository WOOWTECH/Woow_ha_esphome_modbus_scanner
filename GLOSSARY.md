# Woow ESPHome Modbus Scanner

Read-only, best-effort discovery of which Modbus RTU slave IDs answer on an RS-485 bus reached through an ESPHome node, driven from Home Assistant.

## Language

**Gateway**:
An enrolled ESPHome node that runs the scanner component on one or more Buses.
_Avoid_: Bridge, node, ESP, device

**Bus**:
One Modbus RTU line on a Gateway, served by exactly one scanner instance; the unit that Scans are serialized on.
_Avoid_: Hub, line, channel, port

**Probe**:
One read-only request sent to a single slave ID on a Gateway's bus.
_Avoid_: Ping, poll, read

**Scan**:
An ordered series of Probes over a range of slave IDs on one Bus.
_Avoid_: Sweep, discovery job

**Responder**:
A slave ID that produced a correlated reply to a Probe; it is not proof of exactly one physical device behind that ID.
_Avoid_: Device, slave, found device

**Device Profile**:
The readable registers, defaults and limits for one class of field device; the Generic Device Profile is the only built-in one.
_Avoid_: Profile (unqualified), device map, template

**Generic Device Profile**:
The vendor-neutral Device Profile that permits any register with bounded read size and no register allowlist.
_Avoid_: Default profile, universal profile

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
The window during which a Gateway holds the selected Pausable Pollers paused for one Scan, ended by completion, idle expiry or a hard limit enforced on the Gateway itself.
_Avoid_: Pause window, lock
