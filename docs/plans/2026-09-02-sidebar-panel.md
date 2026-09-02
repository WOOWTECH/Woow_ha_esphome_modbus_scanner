# Home Assistant Sidebar Panel Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a public Lit-based Home Assistant sidebar panel that guides every HA user through the six scanner services, provides live progress/results/cancellation, and embeds detailed explanations without weakening mock-only truthfulness.

**Architecture:** The Python integration serves and registers one built `panel_custom` bundle at `/woow-esphome-modbus-scanner`, while continuing to own the six service interfaces and scan coordinator. The Lit panel calls response-capable services through the authenticated `hass` frontend object, validates and persists only non-secret form preferences/recent scan IDs, serially polls one active scan, and renders evidence-oriented results. Version 0.2.0 removes user-admin checks from all six services by explicit product decision and registers the panel with `require_admin: false`.

**Tech Stack:** Home Assistant custom integration (Python 3.13), Lit 3, Rollup, native HA WebSocket/service helpers, HA CSS theme variables, MDI via `ha-icon`, pytest, Node tests, Playwright.

---

### Task 1: Open all six services to every HA user

**Files:**
- Modify: `custom_components/woow_esphome_modbus_scanner/services.py`
- Modify: `tests/services/test_admin_policy.py`
- Modify: `README.md`, `README_zh-TW.md`
- Modify: `docs/design/service-and-safety-model.md`
- Modify: `docs/tutorial/woow-esphome-modbus-scanner-v0.1.0-zh-TW.html`

**Steps:**
1. Write failing public-service tests using a non-admin user context for all six services.
2. Run focused tests to prove RED.
3. Remove the user-admin authorization gate and obsolete imports/calls; retain schemas, lifecycle availability and coordinator checks.
4. Document the permanent all-user policy and its future physical-provider risk.
5. Run focused tests to prove GREEN.

### Task 2: Register a standalone all-user sidebar panel

**Files:**
- Modify: `custom_components/woow_esphome_modbus_scanner/const.py`
- Modify: `custom_components/woow_esphome_modbus_scanner/__init__.py`
- Modify: `custom_components/woow_esphome_modbus_scanner/manifest.json`
- Create: `custom_components/woow_esphome_modbus_scanner/frontend/`
- Create/modify: `tests/config/test_panel_registration.py`, lifecycle/repository contract tests

**Steps:**
1. Write failing tests for static-path registration, panel path/title/icon/component config, `require_admin=False`, idempotent setup and unload removal.
2. Implement versioned static bundle registration and panel removal without disturbing generation-based service ownership.
3. Bump manifest to 0.2.0 and add required frontend/http dependencies.
4. Run config/lifecycle tests.

### Task 3: Build the Lit scan workbench

**Files:**
- Create: `panel_frontend/package.json`, lockfile, Rollup config and deploy script
- Create: `panel_frontend/src/woow-esphome-modbus-scanner-panel.js`
- Create: `panel_frontend/src/styles.js` or equivalent modules
- Generate: `custom_components/woow_esphome_modbus_scanner/frontend/woow-esphome-modbus-scanner-panel.js`

**Panel interface:**
- HA top bar/menu event, title `Modbus Scanner`, icon `mdi:radar`, route `/woow-esphome-modbus-scanner`.
- Persistent mock-only/version banner and tutorial/download links.
- Gateway catalog/refresh.
- Basic and advanced scan fields with defaults/bounds and contextual explanations.
- Start scan, test address, cancel, refresh status/results.
- Non-overlapping 1-second status polling, automatic terminal result load, unload cleanup.
- Progress, six outcome counts, terminal error handling, evidence table with sortable address/outcome/latency/exception/vendor/product/detail.
- Mock profile quick actions and detailed outcome/troubleshooting explanations.
- localStorage only for preferences, disclosure state and recent scan IDs; no credentials/tokens/frames/hosts.
- HA theme variables with WoowTech quiet-surface fallback; light/dark, 320/360, 44px controls, keyboard focus, local overflow.

**Steps:**
1. Add failing source/unit contract tests for payload construction, validation, response normalization, state transitions and no-secret storage.
2. Implement minimal panel and make tests pass.
3. Build/deploy bundle and add drift test ensuring generated bundle matches source build.

### Task 4: Add browser and mocked-service end-to-end tests

**Files:**
- Create: `tests/panel/` test helpers/specs
- Modify: CI workflow and test documentation

**Mock HA contract:**
- `hass.callService(domain, service, data, target, notify, returnResponse)` records calls and returns deterministic gateway/status/results/cancel/test payloads.
- Verify exact six service names and `returnResponse=true`.

**Browser scenarios:**
- Desktop, 360px, 320px; light/dark HA variables; no page overflow.
- Gateway load/refresh.
- Form defaults/validation/help text/advanced disclosure/localStorage restore.
- Start → running polls → completed → results.
- Cancel, test address, busy, failed, unknown ID, connection/service errors.
- Keyboard focus, sortable table, code/help links, menu event and disconnected poll cleanup.

### Task 5: Update comprehensive tutorial and release material

**Files:**
- Modify both READMEs and downloadable HTML tutorial
- Modify design/ADR/testing docs
- Add release notes/changelog if appropriate

**Content changes:**
- v0.2.0 sidebar walkthrough and screenshots/illustrations.
- Explicit all-user permission decision.
- How each UI control maps to service fields.
- Progress/results/cancel/test flows.
- Mock-only/future-provider caveats remain first-class.
- Keep v0.1.0 direct download available; add v0.2.0 tutorial/source links after release.

### Task 6: Verify, review, deploy and release

**Local gates:**
- Ruff, full pytest/coverage, frontend unit/build/drift, compileall, HTML static tests, Playwright desktop/mobile/theme/keyboard.
- Independent spec and visual/accessibility reviews; fix and re-review.
- `git diff --check`, clean worktree, generated bundle committed.

**Live HA deployment:**
1. Confirm current 0.1.0 install and config entry.
2. Back up `/config/custom_components/woow_esphome_modbus_scanner`.
3. Atomically deploy 0.2.0, run `ha core check`, restart.
4. Verify entry loaded, six services, panel registry/path/module, `require_admin=false`, mock scan/test/cancel/result behavior, and logs.
5. Roll back backup and restart on failure.

**Publication:**
- Commit/push branch, CI green, merge to main.
- Tag/release v0.2.0 with tutorial HTML asset and checksums.
- Verify README view/download URLs and GitHub release asset.
