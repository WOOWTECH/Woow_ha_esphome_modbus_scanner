# Hardened bridge deployment and rollback

This remains an experimental `0.4.0.dev1` branch, not an upstream release or a
universal ESPHome/Modbus implementation. Tested stack: HA 2026.7.2,
aioesphomeapi 45.3.1, ESPHome 2026.9.0; independent bench clients also used 46.3.0.

## Configuration and safety

- All active HA users and internal automations may operate enrolled scanners.
  HA still restricts credential/configuration administration to administrators.
- Generate a separate random 32-byte, base64-encoded native API key per device.
  Store it as `scanner_api_key` in private ESPHome secrets. The example YAML
  requires that secret. Do not commit secrets, private configurations or binaries.
- Update **both** the native HA ESPHome entry and the scanner entry for each key.
  A blank scanner key retains the stored key for the same MAC; explicit clearing
  is required for a deliberate return to unencrypted firmware. No automatic
  plaintext fallback exists.
- Compile each device's own project. Do not copy the generic example over an
  installed device: node 1 requires UART-level `flow_control_pin: GPIO33`, not
  the generic example's Modbus-level direction control. Preserve its existing
  `diagnostic_read_only: false` and all original controls/settings. Node 2 keeps
  its own validated configuration. Both use application-only OTA.
- Scanner operations remain FC03/count 1, slave 1–32, the reviewed 13-register
  allowlist and 700 ms timeout. Existing appliance controls are not scanner
  operations and were not exercised during this read-only acceptance.

## Upgrade order

1. Save private device-specific source, secrets, current application binaries and
   the relevant HA entries. Keep an integration backup and verify checksums.
2. Deploy compatible HA code first. Verify a legacy unencrypted bridge still
   reads correctly; recovery for legacy firmware must remain **unknown**.
3. Build both variants with the pinned ESPHome version. OTA only the canary.
4. Verify encrypted identity and update both HA credential consumers through
   supported config/reauth flows. Do not edit live HA storage files.
5. Verify all allowed registers, full range, cancellation, fresh normal-poll
   recovery, address restoration and unchanged appliance state before the second device.
   In this rollout node 2 was the canary; node 1 followed.
6. Repeat checks for the second device, actual HA UI/users, lifecycle and history.
   Hard-refresh the browser after frontend deployment.

## Recovery/rollback

- An unverified recovery is not proof of an offline gateway. Check API health,
  normal-poll freshness and fault state separately. Empty slave timeouts are
  expected, not persistent Repairs.
- A firmware watchdog fault deliberately requires manual maintenance. Do not
  automate reboot, replay, factory reset, Wi-Fi clearing or address writes.
- If rollback is necessary, stop scanner jobs and use the matching **device's**
  saved application-only OTA image and unchanged private OTA credentials. Never
  upload a factory image through this procedure or swap node binaries.
- Rolling back to the previous plaintext API firmware also requires explicitly
  clearing the key in both native ESPHome and scanner configuration. Keep HA
  support installed while making these coordinated changes. Confirm identity,
  normal polling, active/requested address 1 and original appliance settings.
- Restore the integration backup only after firmware/credentials are compatible.
  History is evidence, never a work queue; interrupted jobs must not be replayed.

The canonical HA-side source projects were promoted to the exact compiled
private sources: `/config/esphome/guanjie-device1-readonly` and
`/config/esphome/guanjie-device2-scanner`. The old node-1 source is privately
archived; staging/build caches and matching rollback images are retained.
Use the pinned 2026.9.0 compiler, not an older ESPHome add-on by accident.

Private artifacts are retained outside the repository. Only image checksums and
sanitized acceptance evidence may be published. Rollback images were retained;
a destructive rollback/reflash drill was not part of the acceptance.

## Time and history semantics

`Last Control Result Uptime` is boot-relative seconds from the firmware's 32-bit
millisecond clock (wraps after approximately 49.7 days), not a UTC timestamp.
It is unknown until a control result is recorded after boot. Background polling
and scanner operations do not overwrite historical control outcomes.

HA records UTC job start/end times and at most 32 monotonic elapsed-time phase
events; the panel displays the latest eight. At most 20 terminal snapshots are
persisted. An interrupted start checkpoint becomes `INTERRUPTED`, with later
progress explicitly unknown; the one-second delayed save is not a guarantee
against sudden power loss. Graceful unload/stop allows 35 seconds for cooperative
recovery before force-cancelling; the provider bounds dedicated-socket cleanup.
