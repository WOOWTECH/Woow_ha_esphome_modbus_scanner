# Authorization boundary

## Approved policy

Any active Home Assistant user, and any internal automation, can generate
read-only Modbus traffic on any enrolled Bus, for slave IDs 1–247 within the
selected Device Profile (legacy bridge v1 Gateways: 1–32).

All active Home Assistant users may start, test, cancel and API-check enrolled
physical gateways, including non-administrators. Existing internal automations
without a user context remain permitted. There is no automation opt-in setting.
Unknown or inactive named users are rejected. Mock operations retain their
existing contract. `list_gateways.can_operate` informs the UI; service handlers
are authoritative.

Enrollment and credential administration (the config flow: Gateway hosts, MACs,
keys, adding and removing Gateways) still follows HA's own administrative
permissions. Two kinds of scanner state are part of the all-user policy instead
([ADR 0008](../adr/0008-scanner-service-set-and-persisted-history.md)):

- the Pausable Poller selection of each Bus, which `set_pausable_pollers` saves
  in the config entry options (ADR 0006);
- imported Device Profiles, which `import_device_profile` and
  `delete_device_profile` save in HA storage (ADR 0005).

Neither reaches a key, a host or a register outside the Device Profile and
Gateway limits. Opening scanner operations to users does not expose PSKs, authorize
anonymous network access, or allow arbitrary gateway hosts/registers.

## Native ESPHome boundary

Native ESPHome actions are another supported path, not a scanner-specific
per-user security boundary. HA 2026.7.2 registers/forwards these actions without
the scanner service handler. The `modbus_scanner` firmware enforces the bridge
v2 hard limits (slave 1–247, FC03/FC04 only, count 1–4, timeout 100–2000 ms,
write function codes refused), one probe in flight per Bus and the Gateway-owned
Scan Lease timers regardless of caller (legacy bridge v1 nodes keep their own
frozen limits). API encryption
authenticates clients holding the per-device key, not individual HA users.

We do not claim device-wide per-user authorization or install monkeypatches on
native ESPHome handlers. The previously proposed admin-only/automation-opt-in
policy was explicitly rejected and is not the implemented contract.

## Acceptance evidence

The 0.4.0.dev1 live-hardening report ([history](../history/hardening-live-acceptance.md))
records the deployed versions and tests of that release.
Framework tests exercise active administrator/non-admin, inactive user and
context-free automation cases. A mocked browser is not a real-user login test;
production account/login evidence must be identified separately.
