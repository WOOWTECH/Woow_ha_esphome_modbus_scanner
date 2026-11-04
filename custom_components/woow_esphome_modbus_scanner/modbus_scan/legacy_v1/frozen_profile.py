"""The register profile of the bridge v1 firmware already running on Legacy Gateways.

A frozen, hand-kept copy: nothing generates it and it must not change until legacy v1 is
removed. The v1 firmware reports ``profile_hash`` in its health snapshot and HA refuses a
Legacy Gateway that reports anything else, so the hash is the deployed firmware's value, not one to
recompute. Bridge v2 Gateways never use it; their protocol lives in ``bridge_v2/contract.json``.
"""

PROFILE = {
    "profile_id": "guanjie-ind17-fc03",
    "profile_version": 1,
    "bridge_version": 1,
    "read_only": True,
    "limits": {
        "slave_min": 1,
        "slave_max": 32,
        "register_count": 1,
        "timeout_ms": 700,
        "retries_max": 5,
        "inter_request_delay_max_ms": 5000,
        "polling_pause_required": True,
    },
    # Normal control telemetry on v1 firmware indexes this order; never reorder it.
    "allowed_registers": [
        0x6201,
        0x6202,
        0x6203,
        0x6205,
        0x6206,
        0x6105,
        0x6101,
        0x6102,
        0x6103,
        0x6104,
        0x6106,
        0x6111,
        0x6112,
    ],
    "defaults": {
        "start_id": 1,
        "end_id": 3,
        "address": 1,
        "probe_type": "holding_register",
        "register_address": 0x6201,
        "register_count": 1,
        "timeout_ms": 700,
        "retries": 0,
        "inter_request_delay_ms": 250,
        "pause_normal_polling": True,
    },
    "profile_hash": "1620942b806d6d958a6989d0c96c1a6a349887014d821c1b4336a95717269b85",
}
