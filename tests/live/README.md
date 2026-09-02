# Opt-in live mock service smoke

`mock_service_smoke.py` calls a running Home Assistant through its REST service
API. It uses only the deterministic mock provider: no hardware, configuration
write, node restart, or deployment occurs.

Prerequisites: install and configure the integration, then provide an
administrator token explicitly.

```bash
HA_URL=https://homeassistant.example \
HA_TOKEN='administrator-long-lived-token' \
python tests/live/mock_service_smoke.py
```

HTTPS is required by default. For a local endpoint only, opt in explicitly with
`HA_ALLOW_INSECURE_LOOPBACK=1` and use literal loopback, for example
`HA_URL=http://127.0.0.1:8123`. Private-LAN HTTP names and addresses are refused,
and redirects are never followed so the bearer token cannot move to another
endpoint.

The script is excluded from hermetic pytest collection, but its URL and redirect
safety helpers are regression-tested and the script is linted and compiled in CI.
