import test from "node:test";
import assert from "node:assert/strict";
import {MOCK_SCENARIOS, OUTCOMES, evidenceExport} from "../src/model.js";
import {stringsFor} from "../src/i18n.js";

// Story 52: the outcomes a 0.5.0 Scan reports. FC43 device identification is out of scope.
const SPEC_OUTCOMES = ["responded", "modbus_exception", "timeout", "possible_collision", "gateway_error"];
const LANGUAGES = [{language: "en"}, {language: "zh-Hant"}];

test("the panel counts and explains only the spec outcomes", () => {
  assert.deepEqual([...OUTCOMES], SPEC_OUTCOMES);
  for (const hass of LANGUAGES) {
    assert.equal(stringsFor(hass).help.identified, undefined);
  }
});

test("Mock Scenario descriptions never claim a device identification", () => {
  for (const hass of LANGUAGES) {
    const details = stringsFor(hass).mockScenarioDetails;
    for (const scenario of MOCK_SCENARIOS) {
      assert.doesNotMatch(details[scenario], /identif|識別/i, `${hass.language} ${scenario}`);
    }
  }
});

test("a 0.4.x Scan history row with an identified outcome is still exported as such", () => {
  const results = {provider: "mock", status: "completed", responders: [{address: 1, outcome: "identified", latency_ms: 5}]};
  assert.equal(evidenceExport({}, results).responders[0].outcome, "identified");
});
