#!/usr/bin/env node
/** Mocked-Home-Assistant browser, race, visual, storage, and accessibility checks. */
import {createReadStream} from "node:fs";
import {mkdir} from "node:fs/promises";
import {createServer} from "node:http";
import {resolve, sep} from "node:path";
import {chromium} from "../../panel_frontend/node_modules/playwright/index.mjs";

const root = resolve(process.cwd(), "..");
const screenshots = resolve(root, "docs/screenshots");
const bundleUrl = "/custom_components/woow_esphome_modbus_scanner/frontend/woow-esphome-modbus-scanner-panel.js";
const shell = `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><style>html,body{margin:0}ha-icon{display:inline-flex;width:24px;height:24px;align-items:center;justify-content:center;font:700 18px/1 sans-serif}</style><script>customElements.define('ha-icon',class extends HTMLElement{static get observedAttributes(){return ['icon']}connectedCallback(){this.setAttribute('aria-hidden','true');this.draw()}attributeChangedCallback(){this.draw()}draw(){const glyphs={'mdi:menu':'☰','mdi:radar':'◉','mdi:refresh':'↻','mdi:play':'▶','mdi:crosshairs-gps':'⌖','mdi:stop':'■','mdi:table-refresh':'▦','mdi:check-circle':'●','mdi:circle-outline':'○'};this.textContent=glyphs[this.getAttribute('icon')]||'◆'}});</script></head><body><woow-esphome-modbus-scanner-panel></woow-esphome-modbus-scanner-panel><script type="module">import '${bundleUrl}';
window.calls=[]; window.menuEvents=0; window.mode='normal'; window.polls=0; window.statusDeferred=[]; window.resultsDeferred=[]; window.cancelDeferred=[]; document.body.addEventListener('hass-toggle-menu',()=>window.menuEvents++);
const uuid='11111111-1111-4111-8111-111111111111'; const uuid2='22222222-2222-4222-8222-222222222222';
const responders=[{address:3,outcome:'responded',latency_ms:8,detail:'Generic valid response'},{address:1,outcome:'identified',latency_ms:5,identity:{vendor:'WOOWTECH',product:'WT-RS485-01'},detail:'Identity'}];
const result={scan_id:uuid,status:'completed',phase:'completed',responders,outcome_counts:{identified:1,responded:1,modbus_exception:0,timeout:0,possible_collision:0,gateway_error:0},completed_addresses:2,total_addresses:2,best_effort:true,uniqueness_guaranteed:false};
const hass={locale:{language:new URL(location.href).searchParams.get('lang')||'en'},callService:async(domain,service,data,target,notify,returnResponse)=>{window.calls.push({domain,service,data,target,notify,returnResponse}); if(window.mode==='network') throw new Error('Connection lost'); if(window.mode==='busy'&&service==='start_scan') throw new Error('Gateway mock/mock:rs485-gateway is busy'); if(window.mode==='unknown'&&['get_scan_status','get_scan_results','cancel_scan'].includes(service)) throw new Error('Unknown scan ID'); if(service==='list_gateways') return {response:{gateways:[{provider:'mock',gateway_id:'mock:rs485-gateway',name:'Simulated RS-485 Gateway',simulated:true}]}}; if(service==='start_scan'||service==='test_address') return {scan_id:uuid,status:'running',phase:'running',progress_percent:0,outcome_counts:{}}; if(service==='cancel_scan'){if(window.mode==='deferredCancel') return new Promise((resolve,reject)=>window.cancelDeferred.push({resolve,reject})); return {response:{scan_id:uuid,status:'cancelled',phase:'cancelled',progress_percent:50,outcome_counts:{timeout:1}}};} if(service==='get_scan_status'){window.polls++; if(window.mode==='deferredStatus') return new Promise((resolve,reject)=>window.statusDeferred.push({resolve,reject})); if(window.mode==='failure') return {...result,status:'failed',phase:'failed',error:'Simulated gateway disconnected'}; if(window.mode==='hold') return {scan_id:uuid,status:'running',phase:'running',progress_percent:25,completed_addresses:1,total_addresses:4,outcome_counts:{timeout:1}}; return window.polls<2?{scan_id:uuid,status:'running',phase:'running',progress_percent:50,completed_addresses:1,total_addresses:2,outcome_counts:{timeout:1}}:result;} if(service==='get_scan_results'){if(window.mode==='deferredResults') return new Promise((resolve,reject)=>window.resultsDeferred.push({resolve,reject})); return {response:result};} throw new Error('unexpected service');}};
const panel=document.querySelector('woow-esphome-modbus-scanner-panel'); panel.hass=hass; panel.narrow=true; window.panel=panel; window.fixture={uuid,uuid2,result};</script></body></html>`;
const server = createServer((request, response) => {
  const pathName = new URL(request.url, "http://127.0.0.1").pathname;
  if (pathName === "/") { response.setHeader("Content-Type", "text/html"); response.end(shell); return; }
  const path = resolve(root, `.${pathName}`);
  if (!path.startsWith(`${root}${sep}`)) { response.writeHead(403).end(); return; }
  response.setHeader("Content-Type", "text/javascript");
  const stream = createReadStream(path); stream.on("error", () => response.writeHead(404).end()); stream.pipe(response);
});
const check = (condition, message) => { if (!condition) throw new Error(message); };
const luminance = (rgb) => {
  const values = rgb.match(/[\d.]+/g).slice(0,3).map((value)=>{const n=Number(value)/255; return n<=.04045?n/12.92:((n+.055)/1.055)**2.4;});
  return .2126*values[0]+.7152*values[1]+.0722*values[2];
};
const contrast = (a,b) => {const x=luminance(a),y=luminance(b); return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);};
const capturePanel = async (page, filename) => {
  const originalPosition = await page.evaluate(() => {
    const top = document.querySelector("woow-esphome-modbus-scanner-panel")?.shadowRoot?.querySelector(".top");
    if (!top) throw new Error("panel top bar missing for screenshot");
    const position = top.style.position;
    top.style.position = "static";
    window.scrollTo(0, 0);
    return position;
  });
  try { await page.screenshot({path:resolve(screenshots,filename),fullPage:true}); }
  finally {
    await page.evaluate((position) => {
      const top = document.querySelector("woow-esphome-modbus-scanner-panel")?.shadowRoot?.querySelector(".top");
      if (top) top.style.position = position;
      window.scrollTo(0, 0);
    }, originalPosition);
  }
};
await mkdir(screenshots, {recursive:true});
await new Promise((ready) => server.listen(0, "127.0.0.1", ready));
let browser;
try {
  browser = await chromium.launch({headless: true});
  const base = `http://127.0.0.1:${server.address().port}/`;
  const page = await browser.newPage({viewport: {width: 1280, height: 1000}});
  const errors=[]; page.on("pageerror", (error)=>errors.push(error.message));
  await page.goto(base);
  const panel = page.locator("woow-esphome-modbus-scanner-panel");
  await panel.getByText("1 gateway available.").waitFor();
  check(await page.evaluate(() => calls[0].service === "list_gateways" && calls[0].returnResponse === true), "gateway call contract failed");

  // Defaults, disclosure help, complete profile help, invalid focus and associations.
  check(await panel.locator("#start_id").inputValue()==="1" && await panel.locator("#end_id").inputValue()==="12", "numeric defaults missing");
  check(await panel.locator("#profile").inputValue()==="found_default", "mock profile default missing or invalid");
  check(!(await panel.locator("details").getAttribute("open")), "advanced disclosure default should be closed");
  await panel.locator("summary").click();
  await panel.getByText(/Per attempt; mock uses it only/).waitFor();
  check(await panel.locator(".profile-description").textContent().then((v)=>v.includes("address 1")&&v.includes("completed")), "profile fixture/terminal help incomplete");
  for (const name of ["Found default","All offline","Partial timeout","Modbus exception","Possible collision","Gateway disconnect"]) {
    await panel.locator(".profiles").getByRole("button",{name:new RegExp(name)}).click();
    check(/Expected terminal state: (completed|failed)/.test(await panel.locator(".profile-description").textContent()), `${name} terminal/fixture help missing`);
  }
  check(await panel.locator(".profiles button[aria-pressed=true] ha-icon").getAttribute("icon")==="mdi:check-circle", "selected profile check cue missing");
  await panel.locator(".profiles").getByRole("button", {name:/Found default/}).click();
  check(await panel.locator("#profile").inputValue()==="found_default", "default profile was not restored before baseline screenshots");
  await page.evaluate(() => panel._form={...panel._form,gateway_id:""});
  await panel.getByRole("button", {name:"Start scan"}).click();
  check(await panel.locator("#gateway").evaluate((e)=>e===e.getRootNode().activeElement), "gateway error not focused");
  check(await panel.locator("#gateway").getAttribute("aria-invalid")==="true" && (await panel.locator("#gateway").getAttribute("aria-describedby")).includes("gateway-error"), "gateway error association missing");
  await page.evaluate(() => panel._set("gateway_id","mock:rs485-gateway"));
  await panel.locator("#start_id").fill("0");
  await panel.getByRole("button", {name:"Start scan"}).click();
  check(await panel.locator("#start_id").evaluate((e)=>e===e.getRootNode().activeElement), "first invalid control not focused");
  check(await panel.locator("#start_id").getAttribute("aria-invalid")==="true" && (await panel.locator("#start_id").getAttribute("aria-describedby")).includes("start_id-error"), "numeric error association missing");
  await panel.locator("#start_id").fill("1");
  await panel.getByRole("button", {name:"Start scan"}).click();
  check(await panel.locator("#safety").evaluate((e)=>e===e.getRootNode().activeElement), "safety error not focused");
  check(await panel.locator("#safety").getAttribute("aria-invalid")==="true" && (await panel.locator("#safety").getAttribute("aria-describedby")).includes("safety-error"), "safety association missing");
  await capturePanel(page, "mocked-validation-desktop.png");

  for (const [width,height] of [[1280,1000],[360,900],[320,800]]) {
    await page.setViewportSize({width,height});
    check(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1), `${width}px page overflow`);
    const targets=await panel.locator(".banner a").evaluateAll((elements)=>elements.map((e)=>({w:e.getBoundingClientRect().width,h:e.getBoundingClientRect().height})));
    check(targets.every((box)=>box.w>=44&&box.h>=44), `${width}px banner target below 44px`);
    if(width<400) await capturePanel(page, `mocked-${width}px-help.png`);
  }
  await page.setViewportSize({width:1280,height:1000});
  const lightContrast = await panel.locator("#start_id").evaluate((e)=>{const s=getComputedStyle(e); return [s.borderTopWidth,s.borderTopColor,s.backgroundColor];});
  check(parseFloat(lightContrast[0])>=2 && contrast(lightContrast[1],lightContrast[2])>=3, "light control border contrast/width failed");
  await capturePanel(page, "mocked-light-desktop.png");
  await page.evaluate(() => { const r=document.documentElement.style; r.setProperty('--primary-background-color','#101218');r.setProperty('--card-background-color','#181b22');r.setProperty('--secondary-background-color','#242832');r.setProperty('--primary-text-color','#f4f6ff');r.setProperty('--secondary-text-color','#c7cedd');r.setProperty('--divider-color','#70798b');r.setProperty('--error-color','#ff8d86'); });
  const dark = await panel.locator("#start_id").evaluate((e)=>{const s=getComputedStyle(e),host=getComputedStyle(e.getRootNode().host);return {border:s.borderTopColor,bg:s.backgroundColor,width:s.borderTopWidth,surface:host.getPropertyValue('--surface'),divider:host.getPropertyValue('--line'),error:host.getPropertyValue('--error-color')};});
  check(parseFloat(dark.width)>=2&&contrast(dark.border,dark.bg)>=3, "dark control contrast failed");
  check(dark.surface.trim()&&dark.divider.trim(), "dark HA surfaces/dividers missing");
  const darkTheme=await panel.locator(".card").first().evaluate((e)=>{const card=getComputedStyle(e),host=getComputedStyle(e.getRootNode().host),error=getComputedStyle(e.getRootNode().querySelector('.error'));return {surface:card.backgroundColor,page:host.backgroundColor,divider:card.borderTopColor,error:error.color,text:host.color};});
  check(contrast(darkTheme.surface,darkTheme.page)>=1.05&&contrast(darkTheme.divider,darkTheme.surface)>=3&&contrast(darkTheme.error,darkTheme.surface)>=4.5&&contrast(darkTheme.text,darkTheme.surface)>=4.5, "dark surface/divider/error/text contrast failed");
  const disabledOpacity=Number(await panel.locator("#future-device").evaluate((e)=>getComputedStyle(e).opacity));
  check(disabledOpacity<1 && Number(await panel.locator(".future small").evaluate((e)=>getComputedStyle(e).opacity))===1, "only disabled control should fade");
  await page.evaluate(async () => { panel._operationGeneration++;panel._currentScanId=fixture.uuid;panel._status={scan_id:fixture.uuid,status:'running',phase:'running',progress_percent:25,completed_addresses:1,total_addresses:4,outcome_counts:{timeout:1}};panel._message=panel._text.started;await panel.updateComplete; });
  const dangerContrast=await panel.locator("button.danger").evaluate((e)=>{const button=getComputedStyle(e),icon=getComputedStyle(e.querySelector('ha-icon'));return {background:button.backgroundColor,text:button.color,icon:icon.color,borderWidth:button.borderTopWidth,borderStyle:button.borderTopStyle,disabled:e.disabled};});
  check(!dangerContrast.disabled&&contrast(dangerContrast.text,dangerContrast.background)>=4.5&&dangerContrast.icon===dangerContrast.text&&parseFloat(dangerContrast.borderWidth)>=2&&dangerContrast.borderStyle==='solid', "enabled dark danger button contrast/icon/border failed");
  await capturePanel(page, "mocked-dark-desktop.png");
  await page.evaluate(() => { document.documentElement.removeAttribute('style');panel._currentScanId='';panel._status=null; });

  // Normal running/results/sort states and screenshots.
  await panel.locator("#safety").check();
  await page.evaluate(() => { mode='hold'; polls=0; });
  await panel.getByRole("button", {name:"Start scan"}).click();
  await page.waitForTimeout(1100);
  await panel.getByText(/running/i).first().waitFor();
  await capturePanel(page, "mocked-running.png");
  await page.evaluate(() => mode='normal');
  await panel.getByRole("button", {name:"Refresh status"}).click();
  await panel.getByText(/results loaded automatically/).waitFor({timeout:5000});
  check(await panel.locator("tbody tr").count() === 2, "automatic results rows missing");
  check(await page.evaluate(() => calls.every((call)=>call.returnResponse === true)), "a service omitted returnResponse");
  check(await panel.locator("th").first().getAttribute("aria-sort")==="ascending", "aria-sort missing");
  await panel.getByRole("button", {name:/Sort by Address/}).click();
  check(await panel.locator("th").first().getAttribute("aria-sort")==="descending", "aria-sort direction missing");
  check((await panel.locator("tbody tr").first().locator("td").first().textContent()) === "3", "sortable evidence table failed");
  await page.setViewportSize({width:600,height:900});
  const tableOverflow=await panel.locator(".table-wrap").evaluate((e)=>({scrollWidth:e.scrollWidth,clientWidth:e.clientWidth}));
  check(tableOverflow.scrollWidth>tableOverflow.clientWidth, "horizontal-table screenshot viewport does not overflow");
  await panel.locator(".table-wrap").evaluate((e)=>{e.scrollLeft=e.scrollWidth-e.clientWidth;});
  check(await panel.locator(".table-wrap").evaluate((e)=>e.scrollLeft>0), "horizontal table did not scroll before screenshot");
  await capturePanel(page, "mocked-results-horizontal-table.png");
  await page.setViewportSize({width:1280,height:1000});

  // Unknown from running is centralized for poll/status/results/cancel and re-enables starts.
  await page.evaluate(() => { mode='unknown'; panel._operationGeneration++;panel._status={scan_id:fixture.uuid,status:'running'};panel._currentScanId=fixture.uuid;panel._schedulePoll(fixture.uuid,panel._operationGeneration); });
  await panel.getByText(/Unknown or expired scan ID/).waitFor({timeout:2500});
  check(await page.evaluate(() => panel._status.status==='unknown'&&panel._timer===undefined), "unknown poll was not centralized");
  await page.evaluate(() => { mode='hold'; panel._status={scan_id:fixture.uuid,status:'running'};panel._currentScanId=fixture.uuid; });
  await page.evaluate(() => mode='unknown');
  await panel.getByRole("button", {name:"Refresh status"}).click();
  await panel.getByText(/Unknown or expired scan ID/).waitFor();
  check(await page.evaluate(() => panel._status.status==='unknown' && panel._results===null && panel._timer===undefined), "unknown status was not centralized");
  check(!(await panel.getByRole("button", {name:"Start scan"}).isDisabled()), "start remained disabled after unknown");
  await page.evaluate(() => { mode='unknown';panel._status={scan_id:fixture.uuid,status:'running'};panel._currentScanId=fixture.uuid; });
  await panel.getByRole("button", {name:"Refresh results"}).click();
  check(await page.evaluate(() => panel._status.status==='unknown'), "unknown results not centralized");
  await page.evaluate(() => { panel._status={scan_id:fixture.uuid,status:'running'};panel._currentScanId=fixture.uuid; });
  await panel.getByRole("button", {name:"Cancel"}).click();
  check(await page.evaluate(() => panel._status.status==='unknown'), "unknown cancel not centralized");

  // Deferred stale status and result responses cannot overwrite a newer recent selection.
  await page.evaluate(() => { mode='deferredStatus'; panel._operationGeneration++;panel._currentScanId=fixture.uuid;panel._status={scan_id:fixture.uuid,status:'running'};panel._refreshStatus(); });
  await page.waitForFunction(() => statusDeferred.length===1);
  await page.evaluate(() => { panel._selectRecent({target:{value:fixture.uuid2}}); statusDeferred.shift().resolve({...fixture.result,scan_id:fixture.uuid}); });
  await page.waitForTimeout(0);
  check(await page.evaluate(() => panel._status.scan_id===fixture.uuid2&&panel._results===null), "stale deferred status overwrote selection");
  await page.evaluate(() => { mode='deferredResults'; panel._loadResults(fixture.uuid2); });
  await page.waitForFunction(() => resultsDeferred.length===1);
  await page.evaluate(() => { panel._selectRecent({target:{value:fixture.uuid}}); resultsDeferred.shift().resolve({response:{...fixture.result,scan_id:fixture.uuid2}}); });
  await page.waitForTimeout(0);
  check(await page.evaluate(() => panel._status.scan_id===fixture.uuid&&panel._results===null), "stale deferred results overwrote selection");

  // Deferred stale manual status/results/cancel rejections are swallowed without replacing the selection message.
  await page.evaluate(() => { mode='deferredStatus'; panel._operationGeneration++;panel._currentScanId=fixture.uuid;panel._status={scan_id:fixture.uuid,status:'running'};panel._refreshStatus(); });
  await page.waitForFunction(() => statusDeferred.length===1);
  await page.evaluate(() => { panel._selectRecent({target:{value:fixture.uuid2}});window.selectionMessage=panel._message;statusDeferred.shift().reject(new Error('Connection lost')); });
  await page.waitForFunction(() => panel._busy==='');
  check(await page.evaluate(() => panel._status.scan_id===fixture.uuid2&&panel._message===selectionMessage), "stale rejected manual status mutated the newer selection");
  await page.evaluate(() => { mode='deferredResults';panel._operationGeneration++;panel._currentScanId=fixture.uuid;panel._status={scan_id:fixture.uuid,status:'completed'};panel._loadResults(fixture.uuid); });
  await page.waitForFunction(() => resultsDeferred.length===1);
  await page.evaluate(() => { panel._selectRecent({target:{value:fixture.uuid2}});window.selectionMessage=panel._message;resultsDeferred.shift().reject(new Error('Connection lost')); });
  await page.waitForFunction(() => panel._busy==='');
  check(await page.evaluate(() => panel._status.scan_id===fixture.uuid2&&panel._results===null&&panel._message===selectionMessage), "stale rejected manual results mutated the newer selection");
  await page.evaluate(async () => { mode='deferredCancel';panel._operationGeneration++;panel._currentScanId=fixture.uuid;panel._status={scan_id:fixture.uuid,status:'running'};await panel.updateComplete; });
  await panel.getByRole("button", {name:"Cancel"}).click({noWaitAfter:true});
  await page.waitForFunction(() => cancelDeferred.length===1);
  await page.evaluate(() => { panel._selectRecent({target:{value:fixture.uuid2}});window.selectionMessage=panel._message;cancelDeferred.shift().reject(new Error('Connection lost')); });
  await page.waitForFunction(() => panel._busy==='');
  check(await page.evaluate(() => panel._status.scan_id===fixture.uuid2&&panel._results===null&&panel._message===selectionMessage), "stale rejected cancel mutated the newer selection");

  // Manual refresh invalidates an in-flight automatic poll and schedules one serial successor.
  await page.evaluate(() => { mode='deferredStatus'; statusDeferred.length=0;panel._operationGeneration++;panel._currentScanId=fixture.uuid;panel._status={scan_id:fixture.uuid,status:'running'};panel._schedulePoll(fixture.uuid,panel._operationGeneration); });
  await page.waitForTimeout(1050);
  await page.waitForFunction(() => statusDeferred.length===1);
  await panel.getByRole("button", {name:"Refresh status"}).click({noWaitAfter:true});
  await page.waitForFunction(() => statusDeferred.length===2);
  await page.evaluate(() => { const [oldPoll,manual]=statusDeferred.splice(0); oldPoll.resolve({scan_id:fixture.uuid,status:'completed'});manual.resolve({scan_id:fixture.uuid,status:'running'}); });
  await page.waitForTimeout(20);
  check(await page.evaluate(() => panel._status.status==='running'&&panel._timer!==undefined), "manual status did not serialize/reschedule correctly");
  await page.evaluate(() => panel._stopPolling());

  await page.evaluate(() => { mode='failure';panel._currentScanId=fixture.uuid;panel._status={scan_id:fixture.uuid,status:'running'}; });
  await panel.getByRole("button", {name:"Refresh status"}).click();
  await panel.locator(".notice.failure").filter({hasText:/another scan owns/i}).waitFor();
  await capturePanel(page, "mocked-failed-long-evidence.png");

  const menu = panel.getByRole("button", {name:"Open Home Assistant menu"});
  await menu.focus(); await page.keyboard.press("Enter");
  check(await page.evaluate(() => menuEvents === 1), "keyboard/menu event failed");
  check(await menu.evaluate((element)=>getComputedStyle(element).outlineStyle) !== "none", "focus indicator missing");

  // Storage restore and sanitization are exercised before constructor reads localStorage.
  const storagePage=await browser.newPage({viewport:{width:800,height:700}});
  await storagePage.addInitScript(() => {
    localStorage.setItem('woow-esphome-modbus-scanner.preferences.v1',JSON.stringify({advancedOpen:true,form:{provider:'evil',gateway_id:'secret',start_id:8,end_id:9,address:'7',timeout_ms:999999,retries:2,pause_normal_polling:'true',safety_confirmed:true,mock_profile:'obsolete',probe_type:'write',token:'secret'}}));
    localStorage.setItem('woow-esphome-modbus-scanner.recent.v1',JSON.stringify(['bad','33333333-3333-4333-8333-333333333333',42]));
  });
  await storagePage.goto(base);
  const stored=storagePage.locator('woow-esphome-modbus-scanner-panel');
  await stored.getByText('1 gateway available.').waitFor();
  check(await stored.locator('#start_id').inputValue()==='8'&&await stored.locator('#address').inputValue()==='1', 'valid restore or malformed sanitization failed');
  check(await stored.locator('details').getAttribute('open')!==null, 'advanced disclosure restore failed');
  check(await storagePage.evaluate(() => panel._form.provider==='mock'&&panel._form.gateway_id==='mock:rs485-gateway'&&panel._form.token===undefined&&panel._recent.length===1), 'storage allowlist/fixed mock/recent sanitization failed');
  await storagePage.close();

  // Traditional Chinese is selected from hass.locale.language and English-only labels disappear.
  const zhPage=await browser.newPage({viewport:{width:800,height:700}}); await zhPage.goto(base+'?lang=zh-Hant');
  const zh=zhPage.locator('woow-esphome-modbus-scanner-panel'); await zh.getByText('有 1 個閘道可用。').waitFor();
  await capturePanel(zhPage, 'mocked-zh-Hant-panel.png');
  await zh.getByRole('button',{name:'開始掃描'}).click();
  await zh.getByText('請修正標示的欄位。').waitFor();
  check(await zh.getByText(/預期終止狀態：完成/).count()===1, 'Traditional-Chinese detailed profile help missing');
  await zhPage.close();

  await page.evaluate(() => { mode='hold'; polls=0; calls.length=0; panel._form={...panel._form,safety_confirmed:true}; panel._start(false); });
  await page.waitForTimeout(1200); await page.evaluate(() => panel.remove());
  const before = await page.evaluate(() => calls.filter((call)=>call.service==='get_scan_status').length);
  await page.waitForTimeout(1300);
  const after = await page.evaluate(() => calls.filter((call)=>call.service==='get_scan_status').length);
  check(before === after, "poll continued after disconnect");
  if(errors.length) throw new Error(errors.join("\n"));
  console.log("Panel browser checks passed: localization, defaults/storage sanitization, help, focus/ARIA, contrast/targets, screenshots, status/results/cancel races, unknown handling, responsive states.");
} finally {
  if(browser) await browser.close();
  await new Promise((done)=>server.close(done));
}
