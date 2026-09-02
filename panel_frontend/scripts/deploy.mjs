import {copyFile, mkdir} from "node:fs/promises";
import {dirname, resolve} from "node:path";
const source = resolve("dist/woow-esphome-modbus-scanner-panel.js");
const target = resolve("../custom_components/woow_esphome_modbus_scanner/frontend/woow-esphome-modbus-scanner-panel.js");
await mkdir(dirname(target), {recursive: true});
await copyFile(source, target);
console.log(`Deployed ${target}`);
