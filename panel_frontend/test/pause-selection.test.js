import test from "node:test";
import assert from "node:assert/strict";
import {SERVICES, outlastsScanLease, pollerChecklists, removedPollers, selectionPayload, supportsScanLease} from "../src/model.js";

const GATEWAY = {
  provider: "esphome", gateway_id: "esphome:aabbccddee01",
  capabilities: ["bridge_v2", "holding_register", "input_register", "multi_register"],
  supports_bus_selection: true, supports_scan_lease: true,
  poller_selection: {rs485: [
    {index: 0, name: "meter", address: 1, paused: true},
    {index: 1, name: "inverter", address: 2, paused: false},
  ]},
  removed_pollers: {rs485: [{index: 2, name: "chiller", address: 5}]},
};

test("the checklist names each Pausable Poller with its slave address and choice", () => {
  assert.deepEqual(pollerChecklists(GATEWAY), [{
    bus: "rs485",
    pollers: [
      {index: 0, label: "meter (1)", paused: true},
      {index: 1, label: "inverter (2)", paused: false},
    ],
    removed: ["chiller (5)"],
  }]);
});

test("no checklist for mock, legacy or unchecked gateways, and hostile data renders safely", () => {
  assert.deepEqual(pollerChecklists({provider: "mock", gateway_id: "mock:rs485-gateway"}), []);
  assert.deepEqual(pollerChecklists({...GATEWAY, poller_selection: undefined, removed_pollers: undefined}), []);
  assert.deepEqual(pollerChecklists({...GATEWAY, supports_scan_lease: false}), []);
  const [hostile] = pollerChecklists({...GATEWAY, removed_pollers: {rs485: "x"}, poller_selection: {rs485: [
    {index: 0, name: 42, address: 1, paused: "yes"}, "x", {index: -1, name: "bad", address: 1, paused: true},
    {index: 3, name: "a".repeat(200), address: 999, paused: false},
  ]}});
  assert.deepEqual(hostile.pollers, [
    {index: 0, label: "#0 (1)", paused: false},
    {index: 3, label: "a".repeat(64), paused: false},
  ]);
  assert.deepEqual(hostile.removed, []);
});

test("saving sends the indices left checked; unchecking all pauses none", () => {
  assert.ok(SERVICES.includes("set_pausable_pollers"));
  const [{pollers}] = pollerChecklists(GATEWAY);
  assert.deepEqual(selectionPayload(GATEWAY.gateway_id, "rs485", pollers, 1, true),
    {gateway_id: GATEWAY.gateway_id, bus: "rs485", pause_pollers: [0, 1]});
  assert.deepEqual(selectionPayload(GATEWAY.gateway_id, "rs485", pollers, 0, false).pause_pollers, []);
  assert.deepEqual(selectionPayload(GATEWAY.gateway_id, "rs485", pollers, "all", true).pause_pollers, [0, 1]);
  assert.deepEqual(selectionPayload(GATEWAY.gateway_id, "rs485", pollers, "all", false).pause_pollers, []);
});

test("a Scan names the chosen pollers the firmware no longer has", () => {
  assert.deepEqual(removedPollers({removed_pollers: [{index: 7, name: null, address: null},
    {index: 2, name: "chiller", address: 5}]}), ["#7", "chiller (5)"]);
  assert.deepEqual(removedPollers({}), []);
});

test("Scan Lease support is the capability HA publishes, not the Bridge Protocol name", () => {
  const leased = {...GATEWAY, capabilities: ["holding_register"], supports_scan_lease: true};
  const unleased = {...GATEWAY, supports_scan_lease: false};
  assert.equal(supportsScanLease(leased), true);
  assert.equal(pollerChecklists(leased).length, 1);
  assert.equal(outlastsScanLease(Number.MAX_SAFE_INTEGER, leased), true);
  assert.equal(supportsScanLease(unleased), false);
  assert.deepEqual(pollerChecklists(unleased), []);
  assert.equal(outlastsScanLease(Number.MAX_SAFE_INTEGER, unleased), false);
  assert.equal(supportsScanLease({...GATEWAY, supports_scan_lease: "yes"}), false);
});

test("only the Gateway's one Bus gets a checklist; saved keys of former Buses are not shown", () => {
  // A former multi-Bus (dev2) Gateway can leave saved selections for Buses it no longer has.
  const stale = {...GATEWAY,
    buses: [{bus: "rs485", serial: {baud_rate: 9600, parity: "NONE", stop_bits: 1}}],
    poller_selection: {...GATEWAY.poller_selection, line_b: [{index: 0, name: "old", address: 9, paused: true}]},
    removed_pollers: {...GATEWAY.removed_pollers, line_b: [{index: 4, name: "gone", address: 3}]},
  };
  assert.deepEqual(pollerChecklists(stale).map(({bus}) => bus), ["rs485"]);
  assert.deepEqual(pollerChecklists(stale)[0].removed, ["chiller (5)"]);
  // The reported Bus has no saved checklist: nothing to show, never another Bus's.
  assert.deepEqual(pollerChecklists({...stale, buses: [{bus: "line_c"}]}), []);
  // Bus not known yet (not checked since load): a single saved key can only be the one Bus, so it
  // is shown; several keys cannot be told apart, so none is shown until a check reports the Bus.
  assert.deepEqual(pollerChecklists({...GATEWAY, buses: []}).map(({bus}) => bus), ["rs485"]);
  assert.deepEqual(pollerChecklists({...stale, buses: undefined}), []);
  // More than one reported Bus breaks ADR 0011 (HA refuses such a Gateway): nothing to pick.
  assert.deepEqual(pollerChecklists({...stale, buses: [{bus: "rs485"}, {bus: "line_b"}]}), []);
});

test("a checklist is offered exactly when set_pausable_pollers would accept its Bus", () => {
  const rows = [{index: 0, name: "meter", address: 1, paused: true}];
  const offered = (gateway) => pollerChecklists({...GATEWAY, removed_pollers: {}, ...gateway}).map(({bus}) => bus);
  // One known Bus: HA accepts only that Bus.
  assert.deepEqual(offered({buses: [{bus: "rs485"}], poller_selection: {rs485: rows, line_b: rows}}), ["rs485"]);
  // Bus unknown (no check since a restart, or forgotten after MULTIPLE_BUSES) with one saved key:
  // HA accepts that key, validated against the saved checklist.
  assert.deepEqual(offered({buses: [], poller_selection: {rs485: rows}}), ["rs485"]);
  assert.deepEqual(offered({buses: undefined, poller_selection: {rs485: rows}}), ["rs485"]);
  // Bus unknown with several saved keys: HA cannot tell which is the Gateway's Bus and refuses them all.
  assert.deepEqual(offered({buses: [], poller_selection: {rs485: rows, line_b: rows}}), []);
  // Several Buses reported: no one Bus to save for.
  assert.deepEqual(offered({buses: [{bus: "rs485"}, {bus: "line_b"}], poller_selection: {rs485: rows}}), []);
});
