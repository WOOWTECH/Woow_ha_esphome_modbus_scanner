import {readFile} from "node:fs/promises";
import {resolve} from "node:path";
const built = await readFile(resolve("dist/woow-esphome-modbus-scanner-panel.js"));
const deployed = await readFile(resolve("../custom_components/woow_esphome_modbus_scanner/frontend/woow-esphome-modbus-scanner-panel.js"));
if (!built.equals(deployed)) {
  console.error("Generated integration bundle differs from panel_frontend/dist. Run npm run deploy.");
  process.exitCode = 1;
} else {
  console.log("Generated frontend bundle is current.");
}
