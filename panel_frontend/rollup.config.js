import {readFileSync} from "node:fs";
import {nodeResolve} from "@rollup/plugin-node-resolve";

// The panel imports the bridge v2 contract file (ADR 0005); the bundle keeps only what it reads.
const contractJson = {
  name: "contract-json",
  load(id) {
    if (!id.replaceAll("\\", "/").endsWith("/modbus_scan/bridge_v2/contract.json")) return null;
    const {hard_limits, lease} = JSON.parse(readFileSync(id, "utf8"));
    const used = {hard_limits, lease: {idle_ms: lease.idle_ms, hard_limit_ms: lease.hard_limit_ms}};
    return `export default ${JSON.stringify(used)};`;
  },
};

export default {
  input: "src/woow-esphome-modbus-scanner-panel.js",
  output: {
    file: "dist/woow-esphome-modbus-scanner-panel.js",
    format: "es",
    sourcemap: false,
  },
  plugins: [contractJson, nodeResolve()],
};
