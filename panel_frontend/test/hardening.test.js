import test from "node:test";
import assert from "node:assert/strict";
import {DEFAULTS, boundsFor, selectGateway, serviceYaml, supportedGateway, evidenceExport} from "../src/model.js";
import {LEGACY_GATEWAY} from "./gateways.js";

test("a physical Gateway that reports no limits fails closed", () => {
  assert.equal(supportedGateway({provider:"esphome"}), false);
  assert.equal(supportedGateway({provider:"esphome",profile:{profile_hash:"wrong"}}), false);
  assert.equal(supportedGateway({provider:"esphome",limits:[]}), false);
  assert.equal(supportedGateway(LEGACY_GATEWAY), true);
});

test("physical controls and service YAML share the Gateway's reported defaults", () => {
  const form = selectGateway(DEFAULTS, LEGACY_GATEWAY);
  assert.deepEqual(boundsFor(form).timeout_ms, [700,700]);
  assert.throws(() => serviceYaml(form));
  const yaml = serviceYaml({...form,safety_confirmed:true});
  assert.match(yaml, /register_address: 25089/);
  assert.match(yaml, /timeout_ms: 700/);
  assert.match(yaml, /pause_normal_polling: true/);
  assert.doesNotMatch(yaml, /mock_profile|noise_psk/);
  assert.throws(() => serviceYaml({...form,safety_confirmed:true,register_count:2}));
});

test("evidence export retains typed numeric evidence, not identities or free text", () => {
  const result = evidenceExport({recovery_status:"unknown"}, {provider:"esphome",status:"completed",gateway_id:"PRIVATE",noise_psk:"PRIVATE",responders:[{address:1,outcome:"responded",register_address:25089,raw_value:0,detail:"PRIVATE",identity:{vendor:"PRIVATE"}}]});
  assert.doesNotMatch(JSON.stringify(result), /PRIVATE|noise_psk/);
  assert.equal(result.responders[0].raw_value, 0);
  assert.equal(result.uniqueness_guaranteed, false);
});
