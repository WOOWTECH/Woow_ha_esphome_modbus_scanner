import {LitElement, html, nothing} from "lit";
import {panelStyles} from "./styles.js";
import {stringsFor} from "./i18n.js";
import {
  DEFAULTS, DOMAIN, OUTCOMES, PROFILES, SERVICES, errorMessage, normalizeResponse,
  safePreferences, sanitizePreferences, sanitizeRecent, startPayload, testPayload, validateForm,
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
    _advancedOpen: {state: true},
  };

  constructor() {
    super();
    const saved = sanitizePreferences(this._read(STORAGE_KEY, {}));
    this._form = saved.form;
    this._advancedOpen = saved.advancedOpen;
    this._recent = sanitizeRecent(this._read(RECENT_KEY, []));
    this._gateways = [];
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
  _set(name, value) {
    this._form = {...this._form, [name]: value};
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
      if (this._gateways.length && !this._gateways.some((item) => item.gateway_id === this._form.gateway_id)) {
        this._set("provider", this._gateways[0].provider);
        this._set("gateway_id", this._gateways[0].gateway_id);
      }
      this._message = this._gateways.length ? this._text.gatewayCount(this._gateways.length) : this._text.noGateway;
    });
  }
  async _start(single = false) {
    const t = this._text;
    const errors = validateForm(this._form, single, {integer:t.invalidInteger, order:t.orderError, safety:t.safetyError, gateway:t.gatewayError});
    this._errors = errors;
    if (Object.keys(errors).length) {
      this._message = t.correcting;
      await this.updateComplete;
      const order = ["gateway", "start_id", "end_id", "address", "register_address", "register_count", "timeout_ms", "retries", "inter_request_delay_ms", "safety"];
      this.renderRoot.querySelector(`#${order.find((id) => errors[id === "gateway" ? "gateway_id" : id === "safety" ? "safety_confirmed" : id])}`)?.focus();
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
    const invalid = Boolean(this._errors[name]);
    return html`<div class="field"><label for=${name}>${label}</label><input id=${name} type="number" min=${min} max=${max} .value=${String(this._form[name])} @input=${(event) => this._set(name, event.target.value)} aria-describedby="${name}-help${invalid ? ` ${name}-error` : ""}" aria-invalid=${invalid ? "true" : "false"}><small id="${name}-help">${help}</small>${invalid ? html`<small class="error" id="${name}-error">${this._errors[name]}</small>` : nothing}</div>`;
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
    const selectedProfile = this._form.mock_profile;
    return html`
      <header class="top ${this.narrow ? "narrow" : ""}"><button class="menu secondary" @click=${this._menu} aria-label=${t.menu}><ha-icon icon="mdi:menu"></ha-icon></button><ha-icon icon="mdi:radar"></ha-icon><h1>${t.title}</h1></header>
      <main class="shell">
        <aside class="banner"><div><strong>${t.mock}</strong><p>${t.banner}</p></div><nav aria-label=${t.tutorialLinks}><a href=${TUTORIAL} target="_blank" rel="noopener">${t.tutorial}</a><a href=${DOWNLOAD}>${t.download}</a></nav></aside>
        <div class="grid"><div>
          <section class="card" aria-labelledby="gateway-title"><h2 id="gateway-title">${t.gateway}</h2>
            <div class="fields"><div class="field full"><label for="gateway">${t.availableGateway}</label><select id="gateway" .value=${this._form.gateway_id} @change=${(event) => { const gateway = this._gateways.find((item) => item.gateway_id === event.target.value); this._set("gateway_id", event.target.value); if (gateway) this._set("provider", gateway.provider); }} aria-invalid=${this._errors.gateway_id ? "true" : "false"} aria-describedby="gateway-help${this._errors.gateway_id ? " gateway-error" : ""}">${this._gateways.length ? this._gateways.map((item) => html`<option value=${item.gateway_id}>${item.simulated ? t.simulatedGateway : item.name} — ${item.simulated ? t.simulated : item.provider}</option>`) : html`<option value=${this._form.gateway_id}>${this._form.gateway_id} (${t.notRefreshed})</option>`}</select><small id="gateway-help">${t.gatewayHelp}</small>${this._errors.gateway_id ? html`<small class="error" id="gateway-error">${this._errors.gateway_id}</small>` : nothing}</div>
            <div class="field full future"><label for="future-device">${t.futureDevice}</label><select id="future-device" disabled><option>${t.futureUnavailable}</option></select><small>${t.futureHelp}</small></div></div>
            <div class="actions"><button class="secondary" @click=${this._loadGateways} ?disabled=${Boolean(this._busy)}><ha-icon icon="mdi:refresh"></ha-icon>${t.refreshGateways}</button></div>
          </section>
          <section class="card" aria-labelledby="scan-title"><h2 id="scan-title">${t.scanRange}</h2><div class="fields">
            ${this._field("start_id", t.startId, 1, 247, t.startHelp)}${this._field("end_id", t.endId, 1, 247, t.endHelp)}${this._field("address", t.address, 1, 247, t.addressHelp)}
            <div class="field"><label for="profile">${t.profile}</label><select id="profile" .value=${selectedProfile} @change=${(event) => this._set("mock_profile", event.target.value)} aria-describedby="profile-help">${PROFILES.map((profile) => html`<option value=${profile}>${t.profileNames[profile]}</option>`)}</select><small id="profile-help">${t.profileHelp}</small></div>
          </div><div class="profiles" aria-label=${t.quickProfiles}>${PROFILES.map((profile) => { const selected = selectedProfile === profile; return html`<button class="secondary ${selected ? "selected" : ""}" @click=${() => this._set("mock_profile", profile)} aria-pressed=${selected}><ha-icon icon=${selected ? "mdi:check-circle" : "mdi:circle-outline"}></ha-icon>${t.profileNames[profile]}${selected ? html`<span class="sr-only">${t.selected}</span>` : nothing}</button>`; })}</div>
          <div class="profile-description" role="note"><strong>${t.profileNames[selectedProfile]}</strong><p>${t.profiles[selectedProfile]}</p></div>
          <details ?open=${this._advancedOpen} @toggle=${(event) => { this._advancedOpen = event.target.open; this._persist(); }}><summary>${t.advanced}</summary><div class="fields">
            <div class="field full"><label for="probe">${t.probe}</label><select id="probe" .value=${this._form.probe_type} @change=${(event) => this._set("probe_type", event.target.value)}><option value="device_identification">${t.deviceIdentification}</option><option value="holding_register">${t.holdingRegister}</option><option value="input_register">${t.inputRegister}</option></select><small>${t.probeHelp}</small></div>
            ${this._field("register_address", t.registerAddress, 0, 65535, t.registerAddressHelp)}${this._field("register_count", t.registerCount, 1, 125, t.registerCountHelp)}${this._field("timeout_ms", t.timeout, 10, 10000, t.timeoutHelp)}${this._field("retries", t.retries, 0, 5, t.retriesHelp)}${this._field("inter_request_delay_ms", t.delay, 0, 5000, t.delayHelp)}
            <div class="field check"><label><input type="checkbox" .checked=${this._form.pause_normal_polling} @change=${(event) => this._set("pause_normal_polling", event.target.checked)}>${t.pause}</label><small>${t.pauseHelp}</small></div>
          </div></details>
          <div class="field check"><label><input id="safety" type="checkbox" .checked=${this._form.safety_confirmed} @change=${(event) => this._set("safety_confirmed", event.target.checked)} aria-invalid=${this._errors.safety_confirmed ? "true" : "false"} aria-describedby="safety-help${this._errors.safety_confirmed ? " safety-error" : ""}">${t.safety}</label><small id="safety-help">${t.help.timeout}</small>${this._errors.safety_confirmed ? html`<small class="error" id="safety-error">${this._errors.safety_confirmed}</small>` : nothing}</div>
          <div class="actions"><button @click=${() => this._start(false)} ?disabled=${Boolean(this._busy) || running}><ha-icon icon="mdi:play"></ha-icon>${t.start}</button><button class="secondary" @click=${() => this._start(true)} ?disabled=${Boolean(this._busy) || running}><ha-icon icon="mdi:crosshairs-gps"></ha-icon>${t.test}</button><button class="danger" @click=${this._cancel} ?disabled=${Boolean(this._busy) || !running}><ha-icon icon="mdi:stop"></ha-icon>${t.cancel}</button></div>
          </section>
        </div><div>
          <section class="card" aria-labelledby="status-title"><h2 id="status-title">${t.statusTitle}</h2><div class="notice ${phase === "failed" ? "failure" : ""}" role="status" aria-live="polite">${this._message || (phase === "idle" ? t.ready : `${t.statuses[phase] || phase}…`)}</div>
            <div class="field"><label for="recent">${t.recent}</label><select id="recent" @change=${this._selectRecent}><option value="">${this._chosenId() || t.noRecent}</option>${this._recent.map((id) => html`<option value=${id}>${id}</option>`)}</select><small>${t.storage}</small></div>
            <p><strong>${t.phase}:</strong> ${t.statuses[phase] || phase} ${this._status?.current_address ? html`· ${t.columns.address} ${this._status.current_address}` : nothing}<br><code>${this._chosenId() || t.noScanId}</code></p>
            <div class="progress" role="progressbar" aria-label=${t.progress} aria-valuemin="0" aria-valuemax="100" aria-valuenow=${progress}><span style="width:${Math.min(100, Math.max(0, progress))}%"></span></div><small>${this._status?.completed_addresses || 0} / ${this._status?.total_addresses || 0} ${t.addresses} · ${progress}% · ${this._status?.responder_count || 0} ${t.responders}</small>
            <div class="counts">${OUTCOMES.map((outcome) => html`<div class="count"><strong>${counts[outcome] || 0}</strong>${t.outcomes[outcome]}</div>`)}</div>
            ${this._status?.error ? html`<div class="notice failure"><strong>${t.terminalError}:</strong> ${this._localError(this._status.error)}</div>` : nothing}
            <div class="actions"><button class="secondary" @click=${this._refreshStatus} ?disabled=${Boolean(this._busy)}><ha-icon icon="mdi:refresh"></ha-icon>${t.refreshStatus}</button><button class="secondary" @click=${() => this._loadResults()} ?disabled=${Boolean(this._busy)}><ha-icon icon="mdi:table-refresh"></ha-icon>${t.refreshResults}</button></div>
          </section>
        </div></div>
        <section class="card"><h2>${t.evidence}</h2><p>${t.evidenceHelp}</p><div class="table-wrap" tabindex="0" role="region" aria-label=${t.tableLabel}><table><thead><tr>${this._sortHeader("address", t.columns.address)}${this._sortHeader("outcome", t.columns.outcome)}${this._sortHeader("latency_ms", t.columns.latency_ms)}${this._sortHeader("exception_code", t.columns.exception_code)}${this._sortHeader("vendor", t.columns.vendor)}${this._sortHeader("product", t.columns.product)}${this._sortHeader("detail", t.columns.detail)}</tr></thead><tbody>${this._responders().length ? this._responders().map((row) => html`<tr><td>${row.address}</td><td>${t.outcomes[row.outcome] || row.outcome}</td><td>${row.latency_ms}</td><td>${row.exception_code ?? t.dash}</td><td>${row.identity?.vendor || t.dash}</td><td>${row.identity?.product || t.dash}</td><td>${row.detail ? this._detail(row.detail) : t.dash}</td></tr>`) : html`<tr><td colspan="7">${t.noEvidence}</td></tr>`}</tbody></table></div></section>
        <section class="card tutorial"><h2>${t.interpretation}</h2>${OUTCOMES.map((outcome) => html`<section><h3>${t.outcomes[outcome]}</h3><p>${t.help[outcome]}</p></section>`)}<section><h3>${t.unknownHeading}</h3><p>${t.help.unknown}</p></section><section><h3>${t.networkHeading}</h3><p>${t.help.network}</p></section></section>
      </main>`;
  }
}
if (!customElements.get("woow-esphome-modbus-scanner-panel")) customElements.define("woow-esphome-modbus-scanner-panel", WoowEsphomeModbusScannerPanel);
