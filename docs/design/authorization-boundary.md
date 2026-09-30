# Authorization boundary

## Approved policy

All active Home Assistant users may start, test, cancel and API-check enrolled
physical gateways, including non-administrators. Existing internal automations
without a user context remain permitted. There is no automation opt-in setting.
Unknown or inactive named users are rejected. Mock operations retain their
existing contract. `list_gateways.can_operate` informs the UI; service handlers
are authoritative.

Config-entry/credential administration still follows HA's own administrative
permissions. Opening scanner operations to users does not expose PSKs, authorize
anonymous network access, or allow arbitrary gateway hosts/registers.

## Native ESPHome boundary

Native ESPHome actions are another supported path, not a scanner-specific
per-user security boundary. HA 2026.7.2 registers/forwards these actions without
the scanner service handler. The firmware enforces its read-only bridge profile,
UART arbitration, cooldown and watchdog regardless of caller. API encryption
authenticates clients holding the per-device key, not individual HA users.

We do not claim device-wide per-user authorization or install monkeypatches on
native ESPHome handlers. The previously proposed admin-only/automation-opt-in
policy was explicitly rejected and is not the implemented contract.

## Acceptance evidence

See the current live-hardening report for deployed versions and actual tests.
Framework tests exercise active administrator/non-admin, inactive user and
context-free automation cases. A mocked browser is not a real-user login test;
production account/login evidence must be identified separately.
