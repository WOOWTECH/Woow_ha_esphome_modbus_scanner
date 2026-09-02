# Testing strategy

Tests are hermetic and vertical at public seams:

- direct model tests cover strict values and provider-neutral requests;
- mock-provider tests cover every behavior family, cancellation, and delay;
- coordinator tests cover concurrency, normalized output, provider completeness,
  scheduling rollback, bounded history, shutdown, and waiter cancellation;
- Home Assistant service tests cover exact registration, schemas, fixed selectors,
  canonical UUIDs, ASCII integers, typed probes, safety, and admin policy;
- config tests cover singleton flow plus serialized generation ownership,
  overlapping setup/unload, duplicate calls, and dispatched-call races;
- static contract tests cover repository identity, HACS shape, service names,
  absence of unrelated coupling, and absence of browser, panel, or editor code;
- live-tool safety tests cover HTTPS, explicit loopback HTTP, and redirect refusal.

`pytest --collect-only -q` is the source of truth for test counts and collects
exactly 105 tests in 0.1.0. The live smoke script itself is excluded by
`pytest.ini`; it requires explicit environment variables and calls only the mock
provider through a running Home Assistant instance. Its safety helpers remain
covered by the hermetic suite, and CI lints and compiles the script.
