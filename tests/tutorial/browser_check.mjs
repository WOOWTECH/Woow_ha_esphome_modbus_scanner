#!/usr/bin/env node
/** Rendered accessibility/responsive/print smoke check. Requires Playwright. */
import {createReadStream} from 'node:fs';
import {createServer} from 'node:http';
import {resolve, sep} from 'node:path';
import {tmpdir} from 'node:os';
import {chromium} from 'playwright';

const root = resolve(process.cwd());
const tutorialPath = '/docs/tutorial/woow-esphome-modbus-scanner-v0.1.0-zh-TW.html';
const server = createServer((request, response) => {
  const pathname = new URL(request.url, 'http://127.0.0.1').pathname;
  const path = resolve(root, `.${pathname}`);
  if (!path.startsWith(`${root}${sep}`)) {
    response.writeHead(403).end('Forbidden');
    return;
  }
  response.setHeader('Content-Type', path.endsWith('.html') ? 'text/html; charset=utf-8' : 'application/octet-stream');
  const stream = createReadStream(path);
  stream.on('error', () => response.writeHead(404).end('Not found'));
  stream.pipe(response);
});

function check(condition, message) {
  if (!condition) throw new Error(message);
}

await new Promise((ready) => server.listen(0, '127.0.0.1', ready));
const address = server.address();
const url = `http://127.0.0.1:${address.port}${tutorialPath}`;
let browser;
try {
  browser = await chromium.launch({headless: true});
  const context = await browser.newContext({permissions: ['clipboard-read', 'clipboard-write']});
  const page = await context.newPage();
  const errors = [];
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(`console: ${message.text()}`);
  });
  page.on('pageerror', (error) => errors.push(`page: ${error.message}`));

  for (const viewport of [
    {name: 'desktop', width: 1440, height: 1000},
    {name: 'mobile-360', width: 360, height: 800},
    {name: 'mobile-320', width: 320, height: 720},
  ]) {
    await page.setViewportSize({width: viewport.width, height: viewport.height});
    await page.goto(url, {waitUntil: 'load'});
    check(await page.locator('h1:visible').count() === 1, `${viewport.name}: expected one visible h1`);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    check(overflow <= 1, `${viewport.name}: page overflows horizontally by ${overflow}px`);
    check(await page.locator('.search:visible').count() === 1, `${viewport.name}: installed search enhancement is hidden`);
    check(await page.locator('.copy:visible').count() > 0, `${viewport.name}: installed copy enhancement is hidden`);
    await page.screenshot({path: `${tmpdir()}/woow-tutorial-${viewport.name}.png`, fullPage: true});
  }

  // Keyboard path begins with the skip link, then reaches desktop TOC controls.
  await page.setViewportSize({width: 1440, height: 1000});
  await page.goto(url, {waitUntil: 'load'});
  await page.keyboard.press('Tab');
  check(await page.evaluate(() => document.activeElement?.classList.contains('skip-link')), 'Keyboard path does not start at skip link');
  const focusOutline = await page.locator('.skip-link').evaluate((element) => getComputedStyle(element).outlineStyle);
  check(focusOutline !== 'none', 'Skip link has no visible keyboard focus outline');
  await page.keyboard.press('Tab');
  check(await page.evaluate(() => document.activeElement?.matches('.toc a')), 'Keyboard path does not continue into the desktop TOC');
  await page.keyboard.press('Enter');
  check(page.url().endsWith('#scope'), 'Keyboard-activated TOC link did not update fragment');

  await page.locator('.copy').first().click();
  await page.locator('#copy-status').getByText(/已複製/).waitFor();
  const search = page.locator('#page-search');
  await search.fill('REST API');
  check(await page.locator('.searchable[hidden]').count() > 0, 'Search did not filter sections');
  await page.locator('#clear-search').click();
  check(await page.locator('.searchable[hidden]').count() === 0, 'Search reset did not restore all sections');

  // Native mobile disclosure works by keyboard, and overflow regions accept keyboard scrolling.
  await page.setViewportSize({width: 320, height: 720});
  await page.goto(url, {waitUntil: 'load'});
  const toc = page.locator('details.toc');
  const summary = toc.locator('summary');
  check(await summary.isVisible(), 'Mobile TOC summary is not visible');
  check(await toc.getAttribute('open') === null, 'Enhanced mobile TOC is not initially collapsed');
  await summary.focus();
  await page.keyboard.press('Enter');
  check(await toc.getAttribute('open') !== null, 'Mobile TOC did not open from keyboard');
  await page.keyboard.press('Space');
  check(await toc.getAttribute('open') === null, 'Mobile TOC did not close from keyboard');
  await page.keyboard.press('Enter');
  check(await toc.getAttribute('open') !== null, 'Mobile TOC did not reopen for overflow checks');

  const tableRegion = page.locator('.table-wrap').first();
  check(await tableRegion.evaluate((element) => element.scrollWidth > element.clientWidth), 'Expected a horizontally overflowing table at 320px');
  await tableRegion.focus();
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('ArrowRight');
  await page.waitForTimeout(150);
  check(await tableRegion.evaluate((element) => element.scrollLeft > 0), 'Table overflow region did not keyboard-scroll');

  const overflowingPreIndex = await page.locator('pre').evaluateAll((elements) => elements.findIndex((element) => element.scrollWidth > element.clientWidth));
  check(overflowingPreIndex >= 0, 'Expected a horizontally overflowing code region at 320px');
  const codeRegion = page.locator('pre').nth(overflowingPreIndex);
  await codeRegion.focus();
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('ArrowRight');
  await page.waitForTimeout(150);
  check(await codeRegion.evaluate((element) => element.scrollLeft > 0), 'Code overflow region did not keyboard-scroll');

  const searchBorder = await page.locator('#page-search').evaluate((element) => {
    const style = getComputedStyle(element);
    return {color: style.borderTopColor, width: style.borderTopWidth};
  });
  check(searchBorder.color === 'rgb(94, 104, 121)', `Search boundary contrast color drifted: ${searchBorder.color}`);
  check(searchBorder.width === '2px', `Search boundary is too thin: ${searchBorder.width}`);

  // Print must remain black-on-white without printed backgrounds and preserve table headers.
  await page.setViewportSize({width: 1440, height: 1000});
  await page.goto(url, {waitUntil: 'load'});
  await page.emulateMedia({media: 'print'});
  check(await page.evaluate(() => matchMedia('print').matches), 'Print media did not activate');
  const printStyles = await page.evaluate(() => {
    const styles = (selector) => getComputedStyle(document.querySelector(selector));
    return {
      bannerColor: styles('.mock-banner').color,
      bannerBackground: styles('.mock-banner').backgroundColor,
      strongColor: styles('.mock-banner strong').color,
      preColor: styles('pre').color,
      preBackground: styles('pre').backgroundColor,
      cardColor: styles('.card').color,
      cardBackground: styles('.card').backgroundColor,
      dangerColor: styles('.danger').color,
      dangerBackground: styles('.danger').backgroundColor,
      noteBackground: styles('.note').backgroundColor,
      cautionBackground: styles('.caution').backgroundColor,
      eyebrowBackground: styles('.eyebrow').backgroundColor,
      inlineCodeColor: styles('p code').color,
      inlineCodeBackground: styles('p code').backgroundColor,
      ledeColor: styles('.lede').color,
      searchMessageColor: styles('.search-message').color,
      footerColor: styles('.footer').color,
      captionBackground: styles('caption').backgroundColor,
      headerBackground: styles('th').backgroundColor,
      theadDisplay: styles('thead').display,
      sectionBreak: styles('.section').breakInside,
      rowBreak: styles('tbody tr').breakInside,
    };
  });
  check(printStyles.bannerColor === 'rgb(0, 0, 0)', `Print banner text is not black: ${printStyles.bannerColor}`);
  check(printStyles.bannerBackground === 'rgb(255, 255, 255)', `Print banner is not white: ${printStyles.bannerBackground}`);
  check(printStyles.strongColor === 'rgb(0, 0, 0)', `Print banner strong is not black: ${printStyles.strongColor}`);
  check(printStyles.preColor === 'rgb(0, 0, 0)', `Print code is not black: ${printStyles.preColor}`);
  check(printStyles.preBackground === 'rgb(255, 255, 255)', `Print code is not white: ${printStyles.preBackground}`);
  check(printStyles.cardColor === 'rgb(0, 0, 0)', `Print card text is not black: ${printStyles.cardColor}`);
  check(printStyles.cardBackground === 'rgb(255, 255, 255)', `Print card is not white: ${printStyles.cardBackground}`);
  check(printStyles.dangerColor === 'rgb(0, 0, 0)', `Print warning text is not black: ${printStyles.dangerColor}`);
  for (const [name, value] of Object.entries({
    danger: printStyles.dangerBackground,
    note: printStyles.noteBackground,
    caution: printStyles.cautionBackground,
    eyebrow: printStyles.eyebrowBackground,
    inlineCode: printStyles.inlineCodeBackground,
    caption: printStyles.captionBackground,
    tableHeader: printStyles.headerBackground,
  })) {
    check(value === 'rgb(255, 255, 255)', `Print ${name} surface is not white: ${value}`);
  }
  check(printStyles.inlineCodeColor === 'rgb(0, 0, 0)', `Print inline code is not black: ${printStyles.inlineCodeColor}`);
  for (const [name, value] of Object.entries({
    lede: printStyles.ledeColor,
    searchMessage: printStyles.searchMessageColor,
    footer: printStyles.footerColor,
  })) {
    check(value === 'rgb(0, 0, 0)', `Print ${name} text is not black: ${value}`);
  }
  check(printStyles.theadDisplay === 'table-header-group', `Print thead will not repeat: ${printStyles.theadDisplay}`);
  check(printStyles.sectionBreak === 'auto', `Print sections cannot fragment sanely: ${printStyles.sectionBreak}`);
  check(printStyles.rowBreak === 'avoid', `Print table rows can fragment: ${printStyles.rowBreak}`);
  await page.screenshot({path: `${tmpdir()}/woow-tutorial-print-preview.png`, fullPage: true});
  await page.pdf({path: `${tmpdir()}/woow-tutorial-print-no-backgrounds.pdf`, format: 'A4', printBackground: false});

  // With JavaScript disabled, enhancement-only controls stay hidden while all content and native TOC remain usable.
  const noScriptContext = await browser.newContext({javaScriptEnabled: false});
  const noScriptPage = await noScriptContext.newPage();
  await noScriptPage.setViewportSize({width: 1440, height: 1000});
  await noScriptPage.goto(url, {waitUntil: 'load'});
  const desktopToc = noScriptPage.locator('details.toc');
  check(await desktopToc.locator('a:visible').count() === 15, 'No-JS desktop TOC is not fully visible');
  const desktopTocGeometry = await desktopToc.evaluate((element) => {
    const bounds = element.getBoundingClientRect();
    return {position: getComputedStyle(element).position, top: bounds.top, bottom: bounds.bottom};
  });
  check(desktopTocGeometry.position === 'sticky', 'No-JS desktop TOC is not sticky');
  check(desktopTocGeometry.top >= 0 && desktopTocGeometry.bottom <= 1000, 'No-JS desktop TOC does not fit in the viewport');
  await noScriptPage.setViewportSize({width: 320, height: 720});
  await noScriptPage.goto(url, {waitUntil: 'load'});
  const noScriptSections = await noScriptPage.locator('main section').count();
  check(noScriptSections === await noScriptPage.locator('main section:visible').count(), 'Content was hidden when JavaScript was disabled');
  check(await noScriptPage.locator('.search:visible,.copy:visible').count() === 0, 'Enhancement controls are visible without JavaScript listeners');
  const noScriptToc = noScriptPage.locator('details.toc');
  await noScriptToc.locator('summary').click();
  check(await noScriptToc.getAttribute('open') === null, 'No-JS native mobile TOC disclosure did not toggle');
  await noScriptContext.close();

  if (errors.length) throw new Error(errors.join('\n'));
  console.log(`Browser checks passed: ${url}`);
  console.log(`Screenshots: ${tmpdir()}/woow-tutorial-{desktop,mobile-360,mobile-320}.png`);
  console.log(`Print preview: ${tmpdir()}/woow-tutorial-print-preview.png`);
  console.log(`Print PDF (backgrounds disabled): ${tmpdir()}/woow-tutorial-print-no-backgrounds.pdf`);
} finally {
  if (browser) await browser.close();
  await new Promise((done) => server.close(done));
}
