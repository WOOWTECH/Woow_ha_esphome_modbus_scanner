# Comprehensive HTML Tutorial Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Publish a comprehensive, downloadable Traditional-Chinese single-file HTML tutorial for Woow ESPHome Modbus Scanner v0.1.0 and expose direct view/download links from the repository README.

**Architecture:** The tutorial is one self-contained static HTML document with inline CSS, inline SVG icons, and lightweight progressive JavaScript for navigation/search/copy helpers. Its content is generated from the integration's actual service schemas, models, mock fixtures, lifecycle rules, official Home Assistant/ESPHome documentation, and primary Modbus specifications; it must distinguish current mock behavior from future physical-provider design on every relevant section.

**Tech Stack:** Semantic HTML5, inline CSS/JavaScript, WoowTech brand tokens, Material Design Icons as inline SVG paths, Markdown README links, Python static checks, Playwright browser validation.

---

### Task 1: Build the tutorial content and semantic HTML

**Files:**
- Create: `docs/tutorial/woow-esphome-modbus-scanner-v0.1.0-zh-TW.html`
- Create: `tests/tutorial/test_html_tutorial.py`

**Steps:**
1. Write failing static tests for required sections, one H1, semantic landmarks, exact six service names, mock-only warnings, source links, no legacy coupling, and version consistency.
2. Run the focused test and verify RED.
3. Implement a complete Traditional-Chinese tutorial covering purpose, architecture, Modbus principles, installation, verification, terminology, all fields/defaults/ranges, six-service labs, status/result payloads, six mock profiles, automation/REST examples, troubleshooting, future provider contract, security, maintenance, testing, and glossary.
4. Use precise current-action terminology and preserve API field names.
5. Run focused tests and verify GREEN.

### Task 2: Apply self-contained WoowTech visual design and usability

**Files:**
- Modify: `docs/tutorial/woow-esphome-modbus-scanner-v0.1.0-zh-TW.html`
- Modify: `tests/tutorial/test_html_tutorial.py`

**Steps:**
1. Add failing tests for no external runtime assets, brand palette tokens, required radii, skip link, visible focus styles, reduced-motion support, table captions, copy buttons, print CSS, and responsive overflow containment.
2. Implement inline brand CSS: `#6183FC` spot color, white/gray quiet surfaces, 20px cards, 12px chips, pill controls, generous spacing, Poppins/Outfit/Noto Sans TC system fallbacks, no emoji, no gradients, MDI-derived inline SVG icons.
3. Add sticky table of contents, section search/filter, code-copy buttons with an aria-live status, back-to-top, print/download guidance, and progressive behavior that leaves all content available without JavaScript.
4. Add responsive rules for 320px/360px and print layouts.
5. Run focused tests.

### Task 3: Add README download and reading entry points

**Files:**
- Modify: `README.md`
- Modify: `README_zh-TW.md`
- Test: `tests/tutorial/test_html_tutorial.py`

**Steps:**
1. Add failing tests for canonical GitHub blob link, raw download link, release source link, visible mock-only label, and correct file path.
2. Add a prominent documentation block near the top of each README:
   - open tutorial in repository;
   - download raw HTML;
   - download v0.1.0 source;
   - clarify that HTML is tutorial documentation, not ESPHome firmware.
3. Keep English README copy concise and Traditional-Chinese README copy task-oriented.
4. Run tests.

### Task 4: Validate rendered desktop/mobile/print behavior

**Files:**
- Create: `tests/tutorial/browser_check.mjs`
- Create: `artifacts/tutorial/` screenshots only if appropriate for repository documentation; otherwise keep verification screenshots outside Git.

**Steps:**
1. Serve the repository over loopback HTTP.
2. Use Playwright/Chromium to open the tutorial at desktop, 360px, and 320px widths.
3. Assert no horizontal page overflow, no console/page errors, one visible H1, working table-of-contents links, copy-button status updates, search filtering/reset, and print media availability.
4. Capture desktop/mobile screenshots for inspection.
5. Inspect the rendered artifact and fix brand/accessibility/layout defects.

### Task 5: Full verification and publication

**Steps:**
1. Run `ruff check .`.
2. Run full pytest with coverage and tutorial tests.
3. Run HTML parser/link/static checks and `git diff --check`.
4. Run browser validation.
5. Request independent spec and visual/accessibility review; fix required findings and re-review.
6. Commit on `docs/html-tutorial`, push, merge to `main` only after verification, then verify raw download and GitHub links return successfully.
7. Do not alter the live Home Assistant integration runtime because this change is documentation-only.
