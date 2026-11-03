import test from "node:test";
import assert from "node:assert/strict";
import {formatDecodedValues, hasDecodedValues} from "../src/model.js";

const ROW = {
  address: 3, outcome: "responded", register_address: 16, raw_values: [2301, 7, 65400, 9],
  decoded: [
    {register: 16, name: "Voltage", unit: "V", value: 230.1},
    {register: 18, name: "Current", unit: "A", value: -1.36},
    {register: 19, name: "Power factor", unit: null, value: 1},
  ],
};

test("decoded values are shown with their field name and unit", () => {
  assert.equal(formatDecodedValues(ROW), "Voltage = 230.1 V; Current = -1.36 A; Power factor = 1");
});

test("rows without decoded values show nothing, so a Generic scan stays raw-only", () => {
  assert.equal(formatDecodedValues({raw_values: [1]}), null);
  assert.equal(formatDecodedValues({decoded: []}), null);
  assert.equal(hasDecodedValues({responders: [{raw_values: [1]}]}), false);
  assert.equal(hasDecodedValues({responders: [{raw_values: [1]}, ROW]}), true);
  assert.equal(hasDecodedValues(null), false);
});

test("hostile decoded entries are dropped or truncated", () => {
  const row = {decoded: [
    {register: 1, name: "n".repeat(200), unit: "u".repeat(50), value: 2},
    {register: 2, name: "bad value", unit: "V", value: "2"},
    {register: 3, name: "infinite", value: Infinity},
    {register: 4, name: 42, value: 1},
    "x", null,
  ]};
  assert.equal(formatDecodedValues(row), `${"n".repeat(64)} = 2 ${"u".repeat(16)}`);
  assert.equal(formatDecodedValues({decoded: "not a list"}), null);
});
