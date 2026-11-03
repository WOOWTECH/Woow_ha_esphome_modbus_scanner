# Testing strategy

Tests are hermetic and vertical at public seams:

- direct model tests cover strict values and provider-neutral requests;
- mock-provider tests cover every behavior family, cancellation, and delay;
- coordinator tests cover concurrency, normalized output, provider completeness,
  scheduling rollback, bounded history, shutdown, and waiter cancellation;
- Home Assistant service tests cover exact registration, schemas, fixed selectors,
  canonical UUIDs, ASCII integers, typed probes, safety, and the permanent
  non-admin/all-user policy across exactly six services;
- config tests cover singleton flow plus serialized generation ownership,
  overlapping setup/unload, duplicate calls, and dispatched-call races;
- config/static tests cover repository identity, HACS shape, service names,
  standalone panel/static registration, versioning, unload/reload behavior,
  generated bundle presence, and absence of unrelated coupling;
- Node tests cover response normalization, typed payload construction, every
  form bound, and the localStorage allowlist; bundle drift rebuilds and compares
  the committed integration asset byte-for-byte;
- mocked-HA Playwright checks cover desktop/360/320, light/dark variables,
  start-poll-results, cancel, test-address, busy/failure/unknown/network errors,
  sorting, keyboard/menu behavior, and disconnect polling cleanup;
- live-tool safety tests cover HTTPS, explicit loopback HTTP, and redirect refusal.

`pytest --collect-only -q` is the source of truth and collects exactly **129
Python tests** in 0.2.0. The Node runner contains **5 unit tests**; the mocked-HA
and tutorial Playwright scripts report their scenario checks separately in CI. The live smoke script itself is excluded by
`pytest.ini`; it requires explicit environment variables and calls only the mock
provider through a running Home Assistant instance. Its safety helpers remain
covered by the hermetic suite, and CI lints and compiles the script.
