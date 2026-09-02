import {nodeResolve} from "@rollup/plugin-node-resolve";

export default {
  input: "src/woow-esphome-modbus-scanner-panel.js",
  output: {
    file: "dist/woow-esphome-modbus-scanner-panel.js",
    format: "es",
    sourcemap: false,
  },
  plugins: [nodeResolve()],
};
