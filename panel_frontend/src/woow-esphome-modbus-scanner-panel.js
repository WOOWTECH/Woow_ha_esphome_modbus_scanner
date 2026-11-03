import {LitElement, html, nothing} from "lit";
import {panelStyles} from "./styles.js";
import {stringsFor} from "./i18n.js";
import {
  DEFAULTS, DOMAIN, OUTCOMES, MOCK_SCENARIOS, SERVICES, errorMessage, normalizeResponse,
  safePreferences, sanitizePreferences, sanitizeRecent, startPayload, testPayload, validateForm,
  selectGateway, boundsFor, supportedGateway, serviceYaml, evidenceExport, formatRawValues, formatDecodedValues, hasDecodedValues, leaseNotice,
  estimatedDurationMs, needsLargeRangeConfirmation, outlastsScanLease, probedWithoutLease, GENERIC_PROFILE, selectDeviceProfile, profileLabel,
  isBridgeV2, pollerChecklists, removedPollers, selectionPayload, gatewayBuses, selectBus, reconcileBus, INTEGER_BOUNDS, isLegacyGatewayForm,
} from "./model.js";

const STORAGE_KEY = "woow-esphome-modbus-scanner.preferences.v1";
const RECENT_KEY = "woow-esphome-modbus-scanner.recent.v1";
const TERMINAL = new Set(["completed", "cancelled", "failed"]);
const TUTORIAL = "https://github.com/WOOWTECH/Woow_ha_esphome_modbus_scanner/blob/main/docs/tutorial/woow-esphome-modbus-scanner-v0.2.0-zh-TW.html";
const DOWNLOAD = "https://github.com/WOOWTECH/Woow_ha_esphome_modbus_scanner/releases/download/v0.2.0/woow-esphome-modbus-scanner-v0.2.0-zh-TW.html";

export class WoowEsphomeModbusScannerPanel extends LitElement {
  static styles = panelStyles;
  static properties = {
    hass: {attribute: false}, narrow: {type: Boolean}, panel: {attribute: false},
    _form: {state: true}, _gateways: {state: true}, _status: {state: true},
    _results: {state: true}, _errors: {state: true}, _message: {state: true},
    _busy: {state: true}, _recent: {state: true}, _sort: {state: true},
    _advancedOpen: {state: true}, _yaml: {state: true}, _savedHistory: {state: true},
    _profiles: {state: true},
  };

  constructor() {
    super();
    const saved = sanitizePreferences(this._read(STORAGE_KEY, {}));
    this._form = saved.form;
    this._advancedOpen = saved.advancedOpen;
    this._recent = sanitizeRecent(this._read(RECENT_KEY, []));
    this._gateways = [];
    this._yaml = "";
    this._savedHistory = [];
    this._profiles = [GENERIC_PROFILE];
    this._status = null;
    this._results = null;
    this._errors = {};
    this._message = "";
    this._busy = "";
    this._sort = {key: "address", direction: 1};
    this._timer = undefined;
    this._pollToken = 0;
    this._operationGeneration = 0;
    this._currentScanId = "";
    this._loaded = false;
  }

  get _text() { return stringsFor(this.hass); }
  get _profile() { return this._profiles.find((item) => item.id === this._form.device_profile_id) || GENERIC_PROFILE; }
  connectedCallback() {
    super.connectedCallback();
    if (this.hass && !this._loaded) this._loadGateways();
  }
  disconnectedCallback() {
    this._operationGeneration += 1;
    this._currentScanId = "";
    this._stopPolling();
    super.disconnectedCallback();
  }
  updated(changed) {
    if (changed.has("hass")) {
      if (!this.hass) {
        this._operationGeneration += 1;
        this._currentScanId = "";
        this._stopPolling();
      } else if (!this._loaded) this._loadGateways();
    }
  }
  _read(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch (_error) { return fallback; }
  }
  _persist() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(safePreferences(this._form, this._advancedOpen))); } catch (_error) { /* optional */ }
  }
  _remember(scanId) {
    this._recent = sanitizeRecent([scanId, ...this._recent]);
    try { localStorage.setItem(RECENT_KEY, JSON.stringify(this._recent)); } catch (_error) { /* optional */ }
  }
  _selectGateway(gatewayId) {
    if (this._busy || this._status?.status === "running") return;
    const gateway = this._gateways.find((item) => item.gateway_id === gatewayId);
    if (!gateway) return;
    this._operationGeneration += 1;
    this._stopPolling();
    this._currentScanId = "";
    this._status = null;
    this._results = null;
    this._message = "";
    this._errors = {};
    this._yaml = "";
    this._form = selectGateway(this._form, gateway);
    if (gateway.provider === "esphome") this._advancedOpen = true;
    this._persist();
  }
  _selectBus(bus) {
    if (this._busy || this._status?.status === "running") return;
    this._yaml = "";
    this._form = selectBus(this._form, this._gateways.find((g) => g.gateway_id === this._form.gateway_id), bus);
    this._persist();
  }
  _reconcileBus() {
    this._form = reconcileBus(this._form, this._gateways.find((g) => g.gateway_id === this._form.gateway_id && g.provider === this._form.provider));
  }
  _set(name, value) {
    this._yaml = "";
    this._form = {...this._form, [name]: value};
    // The large-range confirmation is consent to one estimate; changing it asks again.
    if (["start_id", "end_id", "timeout_ms", "inter_request_delay_ms"].includes(name)) this._form.large_range_confirmed = false;
    this._errors = {...this._errors, [name]: undefined};
    this._persist();
  }
  async _call(service, data = {}) {
    if (!SERVICES.includes(service)) throw new Error(`Unsupported scanner service: ${service}`);
    if (!this.hass?.callService) throw new Error(this._text.serviceUnavailable);
    const response = await this.hass.callService(DOMAIN, service, data, undefined, undefined, true);
    const normalized = normalizeResponse(response);
    if (!normalized || typeof normalized !== "object") throw new Error(this._text.invalidResponse);
    return normalized;
  }
  async _action(name, work) {
    if (this._busy) return;
    this._busy = name;
    this._message = "";
    try { await work(); }
    catch (error) { this._message = this._localError(error); }
    finally { this._busy = ""; }
  }
  _localError(error) {
    const message = errorMessage(error);
    const t = this._text;
    if (/unauthorized|permission denied/i.test(message)) return t.readOnly;
    if (/Bridge v1 supports|ESPHome bridge v1/i.test(message)) return t.physicalHelp;
    if (/connection lost/i.test(message)) return `${t.networkHeading}: ${t.help.network}`;
    if (/unknown scan id/i.test(message)) return t.unknownState;
    if (/simulated gateway disconnected| is busy/i.test(message)) return t.help.gateway_error;
    return message;
  }
  async _loadGateways() {
    return this._action("gateways", async () => {
      const payload = await this._call("list_gateways");
      if (!Array.isArray(payload.gateways)) throw new Error(this._text.noGateway);
      this._gateways = payload.gateways;
      this._loaded = true;
      this._reconcileBus();
      // Never silently replace a saved physical gateway with mock mode.
      const available = this._gateways.some((item) => item.gateway_id === this._form.gateway_id && item.provider === this._form.provider);
      this._message = !available ? this._text.missingGateway : this._text.gatewayCount(this._gateways.length);
      await this._fetchProfiles();
    });
  }
  async _fetchProfiles() {
    const payload = await this._call("list_device_profiles");
    if (!Array.isArray(payload.profiles)) throw new Error(this._text.invalidResponse);
    this._profiles = payload.profiles.filter((item) => item && typeof item.id === "string");
    if (!this._profiles.some((item) => item.id === "generic")) this._profiles = [GENERIC_PROFILE, ...this._profiles];
    if (!this._profiles.some((item) => item.id === this._form.device_profile_id)) {
      this._form = {...this._form, device_profile_id: "generic"};
      this._message = this._text.profileFallback;
      this._persist();
    }
  }
  _selectProfile(profileId) {
    if (this._busy || this._status?.status === "running") return;
    const profile = this._profiles.find((item) => item.id === profileId);
    if (!profile) return;
    this._yaml = "";
    this._errors = {};
    this._form = selectDeviceProfile(this._form, profile);
    this._persist();
  }
  async _uploadProfile(event) {
    const input = event.target;
    const file = input.files?.[0];
    if (!file) return;
    return this._action("profiles", async () => {
      try {
        // The service validates the text itself, so JSON errors come back with line and column.
        const result = await this._call("import_device_profile", {profile: await file.text()});
        await this._fetchProfiles();
        this._selectProfileAfterImport(result.profile?.id);
        this._message = this._text.profileImported(result.profile?.name || result.profile?.id, result.replaced === true);
      } finally { input.value = ""; }
    });
  }
  _selectProfileAfterImport(profileId) {
    const profile = this._profiles.find((item) => item.id === profileId);
    if (profile && this._status?.status !== "running") { this._form = selectDeviceProfile(this._form, profile); this._persist(); }
  }
  async _exportProfile(profileId) {
    return this._action("profiles", async () => {
      const result = await this._call("export_device_profile", {profile_id: profileId});
      const blob = new Blob([JSON.stringify(result.profile, null, 2)], {type: "application/json"});
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url; link.download = `${profileId}.json`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  }
  async _deleteProfile(profile) {
    if (!profile.deletable) return;
    return this._action("profiles", async () => {
      await this._call("delete_device_profile", {profile_id: profile.id});
      await this._fetchProfiles();
      this._message = this._text.profileDeleted(profile.name);
    });
  }
  async _checkGateway() {
    if (this._status?.status === "running") return;
    const gateway = this._gateways.find((g) => g.gateway_id === this._form.gateway_id);
    if (gateway?.provider !== "esphome" || gateway.can_operate !== true) return;
    const generation = this._operationGeneration;
    return this._action("check", async () => {
      const result = await this._call("check_gateway", {gateway_id:gateway.gateway_id});
      if (generation !== this._operationGeneration || !this.isConnected) return;
      // The check learns the Gateway's Buses (with their serial parameters).
      this._gateways = this._gateways.map((g) => g.gateway_id === gateway.gateway_id ? {...g, health:result.health, poller_selection:result.poller_selection, removed_pollers:result.removed_pollers, ...(Array.isArray(result.buses) ? {buses:result.buses} : {})} : g);
      this._reconcileBus();
      this._message = this._text.healthChecked;
    });
  }
  async _savePollers(bus, pollers, index, paused) {
    if (this._status?.status === "running") return;
    const gatewayId = this._form.gateway_id;
    const generation = this._operationGeneration;
    return this._action("pollers", async () => {
      const result = await this._call("set_pausable_pollers", selectionPayload(gatewayId, bus, pollers, index, paused));
      if (generation !== this._operationGeneration || !this.isConnected) return;
      // Keep removals reported by the last check visible; the saved checklist is the answer's.
      this._gateways = this._gateways.map((g) => g.gateway_id === gatewayId ? {...g, poller_selection:result.poller_selection} : g);
      this._message = this._text.pollersSaved;
    });
  }
  _pollersCard(gateway, disabled) {
    const t = this._text;
    const checklists = pollerChecklists(gateway, this._form.bus);
    if (!checklists.length) return html`<p>${t.pollersUnknown}</p>`;
    return checklists.map(({bus, pollers, removed}) => html`<fieldset class="pollers"><legend>${t.pollersBus(bus)}</legend>
      ${pollers.length ? pollers.map((poller) => html`<div class="field check"><label><input type="checkbox" data-poller=${poller.index} .checked=${poller.paused} ?disabled=${disabled} @change=${(event) => this._savePollers(bus, pollers, poller.index, event.target.checked)}>${poller.label}</label></div>`) : html`<p>${t.pollersEmpty}</p>`}
      ${pollers.length ? html`<div class="actions"><button class="secondary" ?disabled=${disabled} @click=${() => this._savePollers(bus, pollers, "all", true)}>${t.pollersAll}</button><button class="secondary" ?disabled=${disabled} @click=${() => this._savePollers(bus, pollers, "all", false)}>${t.pollersClear}</button></div>` : nothing}
      ${pollers.length && !pollers.some((poller) => poller.paused) ? html`<p class="notice" role="status">${t.pollersNone}</p>` : nothing}
      ${removed.length ? html`<p class="notice failure" role="status">${t.pollersRemoved} ${removed.join(", ")}</p>` : nothing}
      <small>${t.pollersHelp}</small></fieldset>`);
  }
  async _loadHistory() {
    const generation = this._operationGeneration;
    return this._action("history", async () => {
      const result = await this._call("get_history");
      if (generation !== this._operationGeneration || !this.isConnected) return;
      if (!Array.isArray(result.scans)) throw new Error(this._text.invalidResponse);
      this._savedHistory = result.scans.slice(0,20);
      for (const status of [...this._savedHistory].reverse()) this._remember(status.scan_id);
      this._message = this._text.historyHelp;
    });
  }
  _downloadEvidence() {
    if (!this._results) return;
    const blob = new Blob([JSON.stringify(evidenceExport(this._status, this._results), null, 2)], {type:"application/json"});
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url; link.download = "modbus-scan-evidence.json";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  _showYaml() {
    try { this._yaml = serviceYaml(this._form, this._profile); }
    catch (_error) { this._message = this._text.correcting + " " + this._text.safetyError; }
  }
  async _start(single = false) {
    if (this._busy || this._status?.status === "running") return;
    const t = this._text;
    const errors = validateForm(this._form, single, {integer:t.invalidInteger, order:t.orderError, safety:t.safetyError, gateway:t.gatewayError, physical:t.physicalHelp, v2:t.v2Help, largeRange:t.largeRangeError, registerBlock:t.registerBlock, profileProbe:t.profileProbe, profileRegister:t.profileRegister}, this._profile);
    if (!this._gateways.some((item) => item.gateway_id === this._form.gateway_id && item.provider === this._form.provider)) errors.gateway_id = t.missingGateway;
    const gateway = this._gateways.find((g) => g.gateway_id === this._form.gateway_id);
    if (gateway && !supportedGateway(gateway)) errors.gateway_id = t.unsupportedProfile;
    if (gateway?.health?.firmware_state?.fault) errors.gateway_id = t.firmwareFault;
    if (gateway?.provider === "esphome" && gateway.can_operate !== true) errors.gateway_id = t.readOnly;
    this._errors = errors;
    if (Object.keys(errors).length) {
      this._message = t.correcting;
      await this.updateComplete;
      const order = ["gateway", "start_id", "end_id", "address", "register_address", "register_count", "timeout_ms", "retries", "inter_request_delay_ms", "safety", "large-range"];
      const errorKey = {gateway:"gateway_id", safety:"safety_confirmed", "large-range":"large_range_confirmed"};
      this.renderRoot.querySelector(`#${order.find((id) => errors[errorKey[id] || id])}`)?.focus();
      return;
    }
    const generation = ++this._operationGeneration;
    this._currentScanId = "";
    this._stopPolling();
    return this._action(single ? "test" : "start", async () => {
      this._results = null;
      const payload = await this._call(single ? "test_address" : "start_scan", single ? testPayload(this._form) : startPayload(this._form));
      if (generation !== this._operationGeneration || !this.isConnected) return;
      if (!payload.scan_id) throw new Error(t.startMissing);
      this._currentScanId = payload.scan_id;
      this._status = payload;
      this._remember(payload.scan_id);
      this._message = single ? t.testStarted : t.started;
      if (TERMINAL.has(payload.status || payload.phase)) await this._loadResults(payload.scan_id, true, generation);
      else this._schedulePoll(payload.scan_id, generation);
    });
  }
  _stopPolling() {
    this._pollToken += 1;
    if (this._timer !== undefined) clearTimeout(this._timer);
    this._timer = undefined;
  }
  _isCurrent(scanId, generation) { return generation === this._operationGeneration && scanId === this._currentScanId && this.isConnected; }
  _schedulePoll(scanId, generation = this._operationGeneration) {
    if (!this._isCurrent(scanId, generation)) return;
    const token = ++this._pollToken;
    this._timer = setTimeout(() => this._poll(scanId, token, generation), 1000);
  }
  _isUnknown(error) { return /unknown(?: or expired)? scan(?: id)?/i.test(errorMessage(error)); }
  _handleUnknown(error, scanId, generation) {
    if (!this._isUnknown(error) || !this._isCurrent(scanId, generation)) return false;
    this._stopPolling();
    this._status = {scan_id: scanId, status: "unknown", phase: "unknown", progress_percent: 0, outcome_counts: {}};
    this._results = null;
    this._message = this._text.unknownState;
    return true;
  }
  async _poll(scanId, token, generation) {
    this._timer = undefined;
    if (token !== this._pollToken || !this._isCurrent(scanId, generation) || !this.hass) return;
    try {
      const status = await this._call("get_scan_status", {scan_id: scanId});
      if (token !== this._pollToken || !this._isCurrent(scanId, generation) || status.scan_id && status.scan_id !== scanId) return;
      this._status = status;
      if (TERMINAL.has(status.status || status.phase)) {
        this._stopPolling();
        await this._loadResults(scanId, true, generation);
      } else this._timer = setTimeout(() => this._poll(scanId, token, generation), 1000);
    } catch (error) {
      if (this._handleUnknown(error, scanId, generation)) return;
      if (token === this._pollToken && this._isCurrent(scanId, generation)) {
        this._stopPolling();
        this._message = this._text.pollingStopped(this._localError(error));
      }
    }
  }
  _chosenId() { return this._currentScanId || this._status?.scan_id || this._recent[0] || ""; }
  async _refreshStatus() {
    const scanId = this._chosenId();
    if (!scanId) { this._message = this._text.noChosen; return; }
    this._stopPolling();
    if (!this._currentScanId) this._currentScanId = scanId;
    const generation = this._operationGeneration;
    return this._action("status", async () => {
      try {
        const payload = await this._call("get_scan_status", {scan_id: scanId});
        if (!this._isCurrent(scanId, generation) || payload.scan_id && payload.scan_id !== scanId) return;
        this._status = payload;
        this._message = this._text.statusRefreshed;
        if (TERMINAL.has(payload.status || payload.phase)) await this._loadResults(scanId, true, generation);
        else this._schedulePoll(scanId, generation);
      } catch (error) {
        if (!this._isCurrent(scanId, generation)) return;
        if (!this._handleUnknown(error, scanId, generation)) throw error;
      }
    });
  }
  async _loadResults(scanId = this._chosenId(), automatic = false, generation = this._operationGeneration) {
    if (!scanId) { this._message = this._text.noResultsId; return; }
    if (!this._currentScanId) this._currentScanId = scanId;
    const load = async () => {
      try {
        const results = await this._call("get_scan_results", {scan_id: scanId});
        if (!this._isCurrent(scanId, generation) || results.scan_id && results.scan_id !== scanId) return;
        this._results = results;
        this._message = automatic ? this._text.finished(results.status || "finished") : this._text.resultsRefreshed;
      } catch (error) {
        if (!this._isCurrent(scanId, generation)) return;
        if (!this._handleUnknown(error, scanId, generation)) throw error;
      }
    };
    if (automatic) return load().catch((error) => { if (this._isCurrent(scanId, generation)) this._message = this._text.terminalLoadFailed(this._localError(error)); });
    return this._action("results", load);
  }
  async _cancel() {
    const scanId = this._chosenId();
    if (!scanId) { this._message = this._text.noCancel; return; }
    this._stopPolling();
    const generation = this._operationGeneration;
    return this._action("cancel", async () => {
      try {
        const status = await this._call("cancel_scan", {scan_id: scanId});
        if (!this._isCurrent(scanId, generation) || status.scan_id && status.scan_id !== scanId) return;
        this._status = status;
        this._message = this._text.cancelRequested;
        if (!TERMINAL.has(status.status || status.phase)) this._schedulePoll(scanId, generation);
        else await this._loadResults(scanId, true, generation);
      } catch (error) {
        if (!this._isCurrent(scanId, generation)) return;
        if (!this._handleUnknown(error, scanId, generation)) throw error;
      }
    });
  }
  _selectRecent(event) {
    const scanId = event.target.value;
    if (!scanId) return;
    this._operationGeneration += 1;
    this._stopPolling();
    this._currentScanId = scanId;
    this._status = {scan_id: scanId, status: "unknown", phase: "unknown"};
    this._results = null;
    this._message = this._text.recentSelected;
  }
  _sortBy(key) { this._sort = this._sort.key === key ? {key, direction: -this._sort.direction} : {key, direction: 1}; }
  _detail(value) { return this._text.details[value] || value; }
  _responders() {
    const rows = [...(this._results?.responders || [])];
    const {key, direction} = this._sort;
    return rows.sort((a, b) => {
      const value = (row) => key === "vendor" || key === "product" ? row.identity?.[key] || "" : row[key] ?? "";
      return String(value(a)).localeCompare(String(value(b)), undefined, {numeric: true}) * direction;
    });
  }
  _field(name, label, min, max, help) {
    [min, max] = boundsFor(this._form, this._profile)[name] || [min, max];
    const fixed = isLegacyGatewayForm(this._form) && (name === "register_count" || name === "timeout_ms");
    const invalid = Boolean(this._errors[name]);
    return html`<div class="field"><label for=${name}>${label}</label><input id=${name} type="number" min=${min} max=${max} ?readonly=${fixed} .value=${String(this._form[name])} @input=${(event) => this._set(name, event.target.value)} aria-describedby="${name}-help${invalid ? ` ${name}-error` : ""}" aria-invalid=${invalid ? "true" : "false"}><small id="${name}-help">${help}</small>${invalid ? html`<small class="error" id="${name}-error">${this._errors[name]}</small>` : nothing}</div>`;
  }
  _largeRangeField() {
    const t = this._text;
    const invalid = Boolean(this._errors.large_range_confirmed);
    const count = Number(this._form.end_id) - Number(this._form.start_id) + 1;
    const gateway = this._gateways.find((g) => g.gateway_id === this._form.gateway_id);
    const estimate = estimatedDurationMs(this._form, gateway);
    const seconds = estimate === null ? "?" : (estimate / 1000).toFixed(1);
    const outlasts = outlastsScanLease(estimate, gateway);
    return html`<div class="field check"><label><input id="large-range" type="checkbox" .checked=${this._form.large_range_confirmed === true} @change=${(event) => this._set("large_range_confirmed", event.target.checked)} aria-invalid=${invalid ? "true" : "false"} aria-describedby=${invalid ? "large-range-error" : nothing}>${t.largeRange(count, seconds)}</label>${outlasts ? html`<small class="notice" id="lease-limit-warning" role="status">${t.leaseLimitWarning}</small>` : nothing}${invalid ? html`<small class="error" id="large-range-error">${this._errors.large_range_confirmed}</small>` : nothing}</div>`;
  }
  _sortHeader(key, label) {
    const active = this._sort.key === key;
    const direction = active ? (this._sort.direction > 0 ? this._text.ascending : this._text.descending) : this._text.unsorted;
    return html`<th scope="col" aria-sort=${active ? (this._sort.direction > 0 ? "ascending" : "descending") : "none"}><button @click=${() => this._sortBy(key)} aria-label=${this._text.sort(label, direction)}>${label}${active ? (this._sort.direction > 0 ? " ↑" : " ↓") : ""}</button></th>`;
  }
  _menu() { this.dispatchEvent(new CustomEvent("hass-toggle-menu", {bubbles: true, composed: true})); }

  render() {
    const t = this._text;
    const phase = this._status?.status || this._status?.phase || "idle";
    const running = phase === "running";
    const counts = this._status?.outcome_counts || this._results?.outcome_counts || {};
    const progress = Number(this._status?.progress_percent || 0);
    const selectedScenario = this._form.mock_scenario;
    const physical = this._form.provider === "esphome";
    // Bridge v2 Gateways take any register, FC03/FC04 and 1–4 registers; only bridge v1 is fixed.
    const v1 = isLegacyGatewayForm(this._form);
    // A Scan Lease is reported only by bridge v2 Gateways; their recovery is Gateway-owned.
    const lease = leaseNotice(this._status);
    const resultsEndedAfter = leaseNotice(this._results)?.endedAfter ?? null;
    const v2Status = Boolean(lease) || (physical && !v1);
    const gatewayAvailable = this._gateways.some((item) => item.gateway_id === this._form.gateway_id && item.provider === this._form.provider);
    const gateway = this._gateways.find((g) => g.gateway_id === this._form.gateway_id);
    const compatible = supportedGateway(gateway);
    const canOperate = !physical || gateway?.can_operate === true;
    const transportFault = Boolean(gateway?.health?.firmware_state?.fault);
    const canCancel = this._status?.provider !== "esphome" || this._gateways.find((g) => g.gateway_id === this._status?.gateway_id)?.can_operate === true;
    const health = gateway?.health || {};
    const historyIds = [...new Set([...this._savedHistory.map((s) => s.scan_id), ...this._recent])];
    return html`
      <header class="top ${this.narrow ? "narrow" : ""}"><button class="menu secondary" @click=${this._menu} aria-label=${t.menu}><ha-icon icon="mdi:menu"></ha-icon></button><ha-icon icon="mdi:radar"></ha-icon><h1>${t.title}</h1></header>
      <main class="shell">
        <aside class="banner"><div><strong>${physical ? t.physicalTitle : t.mock}</strong><p>${physical ? t.physicalBanner : t.banner}</p></div><nav aria-label=${t.tutorialLinks}><a href=${TUTORIAL} target="_blank" rel="noopener">${t.tutorial}</a><a href=${DOWNLOAD}>${t.download}</a></nav></aside>
        <div class="grid"><div>
          <section class="card" aria-labelledby="gateway-title"><h2 id="gateway-title">${t.gateway}</h2>
            <div class="fields"><div class="field full"><label for="gateway">${t.availableGateway}</label><select id="gateway" .value=${this._form.gateway_id} ?disabled=${Boolean(this._busy) || running} @change=${(event) => this._selectGateway(event.target.value)} aria-invalid=${this._errors.gateway_id ? "true" : "false"} aria-describedby="gateway-help${this._errors.gateway_id ? " gateway-error" : ""}">${!gatewayAvailable ? html`<option value=${this._form.gateway_id} .selected=${true}>${this._form.gateway_id || t.gatewayError} (${this._loaded ? t.missingGateway : t.notRefreshed})</option>` : nothing}${this._gateways.map((item) => html`<option value=${item.gateway_id} .selected=${item.gateway_id === this._form.gateway_id}>${item.simulated ? (gatewayBuses(item).length > 1 ? t.simulatedMultiBus : t.simulatedGateway) : item.name} —${item.simulated ? t.simulated : item.provider}</option>`)}</select><small id="gateway-help">${t.gatewayHelp}</small>${this._errors.gateway_id ? html`<small class="error" id="gateway-error">${this._errors.gateway_id}</small>` : nothing}</div>
            ${gatewayAvailable && gatewayBuses(gateway).length > 1 ? html`<div class="field full"><label for="bus">${t.bus}</label><select id="bus" .value=${this._form.bus} ?disabled=${Boolean(this._busy) || running} @change=${(event) => this._selectBus(event.target.value)} aria-describedby="bus-help">${gatewayBuses(gateway).map((row) => html`<option value=${row.bus} .selected=${row.bus === this._form.bus}>${row.label}</option>`)}</select><small id="bus-help">${t.busHelp}</small></div>` : nothing}
            <div class="field full future"><label for="future-device">${t.futureDevice}</label><select id="future-device" disabled><option>${physical ? this._form.gateway_id : t.futureUnavailable}</option></select><small>${t.futureHelp}</small></div></div>
            <div class="actions"><button class="secondary" @click=${this._loadGateways} ?disabled=${Boolean(this._busy)}><ha-icon icon="mdi:refresh"></ha-icon>${t.refreshGateways}</button></div>
          </section>
          ${physical ? html`<section class="card" aria-labelledby="health-title"><h2 id="health-title">${t.healthTitle}</h2><p>${t.apiOnly}</p><dl><dt>${t.apiEvidence}</dt><dd>${health.api_status || t.unchecked} · ${health.checked_at || t.dash}</dd><dt>${t.busEvidence}</dt><dd>${health.last_bus_response_at || t.unchecked}</dd><dt>${t.encryption}</dt><dd>${health.encrypted ? t.yes : t.no}</dd></dl>${transportFault ? html`<p class="notice failure" role="status">${t.firmwareFault}</p>` : nothing}${!compatible ? html`<p class="notice failure">${t.unsupportedProfile}</p>` : nothing}${!canOperate ? html`<p class="notice">${t.readOnly}</p>` : nothing}<button class="secondary" @click=${this._checkGateway} ?disabled=${Boolean(this._busy) || running || !canOperate || !gatewayAvailable}>${t.checkGateway}</button></section>` : nothing}
          ${isBridgeV2(gateway) && gatewayAvailable ? html`<section class="card" aria-labelledby="pollers-title"><h2 id="pollers-title">${t.pollersTitle}</h2>${this._pollersCard(gateway, Boolean(this._busy) || running || !canOperate)}</section>` : nothing}
          <section class="card" aria-labelledby="scan-title"><h2 id="scan-title">${t.scanRange}</h2><div class="fields">
            <div class="field full"><label for="device-profile">${t.deviceProfile}</label><select id="device-profile" ?disabled=${Boolean(this._busy) || running} @change=${(event) => this._selectProfile(event.target.value)} aria-describedby="device-profile-help">${this._profiles.map((item) => html`<option value=${item.id} .selected=${item.id === this._profile.id}>${item.name} ${item.version || ""}${item.builtin ? ` (${t.builtin})` : ""}</option>`)}</select><small id="device-profile-help">${t.deviceProfileHelp}</small></div>
            ${this._field("start_id", t.startId, 1, 247, v1 ? t.physicalRange : t.startHelp)}${this._field("end_id", t.endId, 1, 247, v1 ? t.physicalRange : t.endHelp)}${this._field("address", t.address, 1, 247, v1 ? t.physicalRange : t.addressHelp)}
            <div class="field"><label for="profile">${t.profile}</label><select id="profile" ?disabled=${physical} .value=${selectedScenario} @change=${(event) => this._set("mock_scenario", event.target.value)} aria-describedby="profile-help">${MOCK_SCENARIOS.map((profile) => html`<option value=${profile} .selected=${profile === selectedScenario}>${t.profileNames[profile]}</option>`)}</select><small id="profile-help">${physical ? t.physicalProfiles : t.profileHelp}</small></div>
          </div><div class="profiles" aria-label=${t.quickProfiles}>${MOCK_SCENARIOS.map((profile) => { const selected = selectedScenario === profile; return html`<button class="secondary ${selected ? "selected" : ""}" ?disabled=${physical} @click=${() => this._set("mock_scenario", profile)} aria-pressed=${selected}><ha-icon icon=${selected ? "mdi:check-circle" : "mdi:circle-outline"}></ha-icon>${t.profileNames[profile]}${selected ? html`<span class="sr-only">${t.selected}</span>` : nothing}</button>`; })}</div>
          <div class="profile-description" role="note"><strong>${physical ? t.physicalTitle : t.profileNames[selectedScenario]}</strong><p>${physical ? t.physicalProfiles : t.profiles[selectedScenario]}</p></div>
          <details ?open=${this._advancedOpen} @toggle=${(event) => { this._advancedOpen = event.target.open; this._persist(); }}><summary>${t.advanced}</summary><div class="fields">
            <div class="field full"><label for="probe">${t.probe}</label><select id="probe" .value=${this._form.probe_type} @change=${(event) => this._set("probe_type", event.target.value)}><option value="device_identification" ?disabled=${physical}>${t.deviceIdentification}</option><option value="holding_register">${t.holdingRegister}</option><option value="input_register" ?disabled=${v1}>${t.inputRegister}</option></select><small>${v1 ? t.physicalHelp : physical ? t.v2Help : t.probeHelp}</small></div>
            ${this._field("register_address", t.registerAddress, 0, 65535, v1 ? t.physicalRegisters : t.registerAddressHelp)}${this._field("register_count", t.registerCount, 1, 125, v1 ? t.physicalHelp : physical ? t.v2Help : t.registerCountHelp)}${this._field("timeout_ms", t.timeout, 10, 10000, v1 ? t.physicalHelp : physical ? t.v2Help : t.timeoutHelp)}${this._field("retries", t.retries, 0, 5, t.retriesHelp)}${this._field("inter_request_delay_ms", t.delay, 0, INTEGER_BOUNDS.inter_request_delay_ms[1], t.delayHelp)}
            <div class="field check"><label><input type="checkbox" ?disabled=${physical} .checked=${this._form.pause_normal_polling} @change=${(event) => this._set("pause_normal_polling", event.target.checked)}>${t.pause}</label><small>${v1 ? t.physicalPause : physical ? t.v2Pause : t.pauseHelp}</small></div>
          </div></details>
          <div class="field check"><label><input id="safety" type="checkbox" .checked=${this._form.safety_confirmed} @change=${(event) => this._set("safety_confirmed", event.target.checked)} aria-invalid=${this._errors.safety_confirmed ? "true" : "false"} aria-describedby="safety-help${this._errors.safety_confirmed ? " safety-error" : ""}">${t.safety}</label><small id="safety-help">${t.help.timeout}</small>${this._errors.safety_confirmed ? html`<small class="error" id="safety-error">${this._errors.safety_confirmed}</small>` : nothing}</div>
          ${needsLargeRangeConfirmation(this._form) ? this._largeRangeField() : nothing}
          <div class="actions"><button @click=${() => this._start(false)} ?disabled=${Boolean(this._busy) || running || !gatewayAvailable || !compatible || !canOperate || transportFault}><ha-icon icon="mdi:play"></ha-icon>${t.start}</button><button class="secondary" @click=${() => this._start(true)} ?disabled=${Boolean(this._busy) || running || !gatewayAvailable || !compatible || !canOperate || transportFault}><ha-icon icon="mdi:crosshairs-gps"></ha-icon>${t.test}</button><button class="danger" @click=${this._cancel} ?disabled=${Boolean(this._busy) || !running || !canCancel}><ha-icon icon="mdi:stop"></ha-icon>${t.cancel}</button></div>
          <div class="actions"><button class="secondary" @click=${this._showYaml} ?disabled=${!gatewayAvailable || !compatible || Boolean(this._busy) || running}>${t.yaml}</button></div>
          ${this._yaml ? html`<label for="service-yaml">${t.yamlLabel}</label><textarea id="service-yaml" readonly rows="16" style="width:100%;box-sizing:border-box" .value=${this._yaml}></textarea>` : nothing}
          </section>
          <section class="card" aria-labelledby="profiles-title"><h2 id="profiles-title">${t.deviceProfiles}</h2><p>${t.deviceProfilesHelp}</p>
            <div class="field full"><label for="profile-upload">${t.uploadProfile}</label><input id="profile-upload" type="file" accept="application/json,.json" ?disabled=${Boolean(this._busy)} @change=${this._uploadProfile}></div>
            <ul class="profile-list">${this._profiles.map((item) => html`<li><span><strong>${item.name}</strong> ${item.version || ""} · <code>${item.id}</code>${item.builtin ? ` · ${t.builtin}` : ` · ${item.vendor || ""} ${item.model || ""}`}</span><span class="actions"><button class="secondary" @click=${() => this._exportProfile(item.id)} ?disabled=${Boolean(this._busy)} aria-label="${t.exportProfile} ${item.name}"><ha-icon icon="mdi:download"></ha-icon>${t.exportProfile}</button>${item.deletable ? html`<button class="danger" @click=${() => this._deleteProfile(item)} ?disabled=${Boolean(this._busy)} aria-label="${t.deleteProfile} ${item.name}"><ha-icon icon="mdi:delete"></ha-icon>${t.deleteProfile}</button>` : nothing}</span></li>`)}</ul>
          </section>
        </div><div>
          <section class="card" aria-labelledby="status-title"><h2 id="status-title">${t.statusTitle}</h2><div class="notice ${phase === "failed" ? "failure" : ""}" role="status" aria-live="polite">${this._message || (phase === "idle" ? t.ready : `${t.statuses[phase] || phase}…`)}</div>
            <div class="field"><label for="recent">${t.recent}</label><select id="recent" @change=${this._selectRecent}><option value="">${this._chosenId() || t.noRecent}</option>${historyIds.map((id) => { const saved = this._savedHistory.find((s) => s.scan_id === id); return html`<option value=${id}>${saved ? `${saved.provider} · ${t.statuses[saved.status] || saved.status} · ` : ""}${id}</option>`; })}</select><small>${t.storage}</small></div>
            <div class="actions"><button class="secondary" @click=${this._loadHistory} ?disabled=${Boolean(this._busy) || running}>${t.history}</button></div><small>${t.historyHelp}</small>
            ${this._status ? html`<p>${t.operation}: ${t.operationStates[this._status.operation_phase] || this._status.operation_phase || t.dash} · ${t.attempt}: ${this._status.attempt || 0}<br>${t.elapsed}: ${Math.round((this._status.elapsed_ms || 0)/1000)}s · ${t.budget}: ${Math.ceil((this._status.execution_budget_ms || 0)/1000)}s</p><p>${t.recovery}: ${t.recoveryStates[this._status.recovery_status] || t.recoveryStates.unknown} ${this._status.recovery_error_code || ""}<br>${t.cleanup}: ${this._status.cleanup_status || t.unchecked}</p>${lease ? html`<p>${t.lease}: ${t.leaseStates[lease.state]}${lease.reason ? ` (${t.leaseReasons[lease.reason]})` : ""}</p>${lease.endedAfter !== null ? html`<p class="notice" id="lease-ended-early" role="status">${t.leaseEndedEarly(lease.endedAfter)}</p>` : nothing}${lease.stale.length ? html`<p class="notice" role="status">${t.staleWarning} ${lease.stale.join(", ")}</p>` : nothing}` : nothing}${removedPollers(this._status).length ? html`<p class="notice failure" role="status">${t.scanRemoved} ${removedPollers(this._status).join(", ")}</p>` : nothing}${this._status.error_info ? html`<p>${t.errorCode}: <code>${this._status.error_info.code}</code></p>` : nothing}${this._status.progress_is_checkpoint ? html`<p class="notice failure">${t.checkpoint}</p>` : nothing}${TERMINAL.has(phase) && this._status.provider === "esphome" && !v2Status && this._status.recovery_status !== "verified" ? html`<p class="notice failure" role="status">${t.attention}</p>` : nothing}` : nothing}
            <p><strong>${t.phase}:</strong> ${t.statuses[phase] || phase} ${this._status?.current_address ? html`· ${t.columns.address} ${this._status.current_address}` : nothing}<br><code>${this._chosenId() || t.noScanId}</code></p>
            <div class="progress" role="progressbar" aria-label=${t.progress} aria-valuemin="0" aria-valuemax="100" aria-valuenow=${progress}><span style="width:${Math.min(100, Math.max(0, progress))}%"></span></div><small>${this._status?.completed_addresses || 0} / ${this._status?.total_addresses || 0} ${t.addresses} · ${progress}% · ${this._status?.responder_count || 0} ${t.responders}</small>
            ${this._status?.events?.length ? html`<section aria-label=${t.timeline}><strong>${t.timeline}</strong><ol>${this._status.events.slice(-8).map((event) => html`<li>${Math.round(event.elapsed_ms/1000)}s · ${t.operationStates[event.phase] || t.statuses[event.phase] || t.dash}</li>`)}</ol></section>` : nothing}
            <div class="counts">${OUTCOMES.map((outcome) => html`<div class="count"><strong>${counts[outcome] || 0}</strong>${t.outcomes[outcome]}</div>`)}</div>
            ${this._status?.error ? html`<div class="notice failure"><strong>${t.terminalError}:</strong> ${this._localError(this._status.error)}</div>` : nothing}
            <div class="actions"><button class="secondary" @click=${this._refreshStatus} ?disabled=${Boolean(this._busy)}><ha-icon icon="mdi:refresh"></ha-icon>${t.refreshStatus}</button><button class="secondary" @click=${() => this._loadResults()} ?disabled=${Boolean(this._busy)}><ha-icon icon="mdi:table-refresh"></ha-icon>${t.refreshResults}</button></div>
          </section>
        </div></div>
        <section class="card"><h2>${t.evidence}</h2><p>${t.evidenceHelp} ${t.rawHelp}${hasDecodedValues(this._results) ? ` ${t.decodedHelp}` : ""}</p><button class="secondary" @click=${this._downloadEvidence} ?disabled=${!this._results || Boolean(this._busy)}>${t.exportEvidence}</button>${this._results ? html`<p class="evidence-source"><strong>${t.resultGateway}:</strong> ${this._results.provider || t.simulated} · ${this._results.gateway_id || t.dash}${typeof this._results.bus === "string" ? html` · ${t.bus} <span id="result-bus">${this._results.bus}</span>` : nothing} · ${t.resultScan} <code id="result-scan">${this._results.scan_id || t.dash}</code>${profileLabel(this._results) ? html`<br><strong>${t.resultProfile}:</strong> <span id="result-profile">${profileLabel(this._results)}</span>` : nothing}</p>${resultsEndedAfter !== null ? html`<p class="notice" id="result-lease-ended-early">${t.leaseEndedEarly(resultsEndedAfter)}</p>` : nothing}` : nothing}<div class="table-wrap" tabindex="0" role="region" aria-label=${t.tableLabel}><table><thead><tr>${this._sortHeader("address", t.columns.address)}${this._sortHeader("outcome", t.columns.outcome)}${this._sortHeader("latency_ms", t.columns.latency_ms)}${this._sortHeader("exception_code", t.columns.exception_code)}${this._sortHeader("vendor", t.columns.vendor)}${this._sortHeader("product", t.columns.product)}${this._sortHeader("raw_value", t.rawRegister)}${hasDecodedValues(this._results) ? html`<th scope="col">${t.decodedValue}</th>` : nothing}${this._sortHeader("detail", t.columns.detail)}</tr></thead><tbody>${this._responders().length ? this._responders().map((row) => html`<tr><td>${row.address}${probedWithoutLease(resultsEndedAfter, row) ? html` <small class="without-lease">(${t.withoutLease})</small>` : nothing}</td><td>${t.outcomes[row.outcome] || row.outcome}</td><td>${row.latency_ms}</td><td>${row.exception_code ?? t.dash}</td><td>${row.identity?.vendor || t.dash}</td><td>${row.identity?.product || t.dash}</td><td>${Number.isInteger(row.register_address) ? `0x${row.register_address.toString(16)}` : t.dash} / ${formatRawValues(row) ?? t.dash}</td>${hasDecodedValues(this._results) ? html`<td class="decoded">${formatDecodedValues(row) ?? t.dash}</td>` : nothing}<td>${row.detail ? this._detail(row.detail) : t.dash}</td></tr>`) : html`<tr><td colspan="8">${t.noEvidence}</td></tr>`}</tbody></table></div></section>
        <section class="card tutorial"><h2>${t.interpretation}</h2>${OUTCOMES.map((outcome) => html`<section><h3>${t.outcomes[outcome]}</h3><p>${t.help[outcome]}</p></section>`)}<section><h3>${t.unknownHeading}</h3><p>${t.help.unknown}</p></section><section><h3>${t.networkHeading}</h3><p>${t.help.network}</p></section></section>
      </main>`;
  }
}
if (!customElements.get("woow-esphome-modbus-scanner-panel")) customElements.define("woow-esphome-modbus-scanner-panel", WoowEsphomeModbusScannerPanel);
