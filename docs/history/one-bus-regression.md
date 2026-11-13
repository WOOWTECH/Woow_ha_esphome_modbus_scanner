# 移除多 Bus 後的回歸驗收（#16 C 段，驗 #26）

> **狀態：完成，C 段四項全部通過。** 本段是合併前（`14396aa`）的結果；合併後的 main 已於 2026-11-13 重跑，見文末「在 main 上重跑」，#16 以那一段為準。
> 決定見 [ADR 0011](../adr/0011-one-bus-per-gateway.md)。測試台與 [`per-bus-live-acceptance.md`](per-bus-live-acceptance.md) 相同：兩台單 Bus Gateway，設備由模擬器扮演（見 runbook「0b. 測試台」）。

日期：2026-11-10　執行者：Claude Code（測試台已由現場人員接好，本輪不需要按鍵或換線）

## 結論

- 結果：**通過**（C1–C4）。
- 與 #16 C 段的差異：#16 寫「#26 合併後」執行；本輪在合併前，以 PR #27 的 head `14396aa` 執行。合併時若 `custom_components/`、`firmware/components/` 沒有再改，本紀錄仍然適用。
- #25：重燒前，`0.5.0.dev2` firmware 的 Info 是 256 字元，HA 重啟後 log 出現 1 次 `homeassistant.core` ERROR（state 超過 255 字元）。重燒成 `0.5.0.dev3` 後，Info 是 160 字元（1 個 Pausable Poller），沒有再出現。

## 環境

| 項目 | 值 |
|---|---|
| HA 版本 | 2026.7.2（測試機 .28，HAOS 16.1） |
| ESPHome 版本 | 2026.10.0（燒錄、兩個 `modbus_scanner:` 的 config 檢查） |
| 整合 | `0.5.0.dev3`／`14396aa`（Samba 安裝；32 個檔案與 `14396aa` 雜湊一致；舊版 `c84e40e` 移到 `/config/woow_backup_dev2`） |
| fw | `0.5.0.dev3`／`14396aa`，`tools/bench_profiles/gateway-x.yaml`、`gateway-y.yaml`（未修改）以 OTA 重燒 |
| YAML 雜湊（`git hash-object`） | X `25907d7e6e0ff986164617ffcdf89c1b53cacd0d`、Y `c9bcac5435e43e9f3268545cfe94590b1dcc65c3`，與 `14396aa` 相同 |
| 模擬器 | `tools/rtu_bench_simulator.py`，設定 `tools/bench_profiles/bench.json`；X = COM3、Y = COM4 |

## 節點與 Bus

| 節點 | MAC／IP | Bus | 序列參數 | 設備 | 站號 | Pausable Poller |
|---|---|---|---|---|---|---|
| X | `5C:01:3B:45:9F:4C`／192.168.2.44 | rs485 | 9600 NONE 1 | 模擬器 line X | 1、10、17 | `bench_poller`（站號 1） |
| Y | `5C:01:3B:46:FD:A8`／192.168.2.21 | rs485 | 9600 NONE 1 | 模擬器 line Y | 1、20、33 | `bench_poller`（站號 1） |

## 步驟（本機時間 +08:00）

| 時間 | 做什麼 |
|---|---|
| 13:26 | 啟動模擬器；兩條 line 都有站號 1 的 Normal Polling |
| 13:27 | 在 .28 換上 `0.5.0.dev3` 整合，重啟 HA |
| 13:28 | 額外：新版 HA 搭配仍是 `0.5.0.dev2` 的 X、Y，`check_gateway` 兩台都是 `verified`、`v2_signature_verified`、`buses: ["rs485"]` |
| 13:28–13:30 | X、Y 以 OTA 重燒 `0.5.0.dev3` |
| 13:31 | 兩台 `check_gateway` 後各跑一個 Scan |
| 13:34 | 額外：給錯的 `bus` 被拒絕 |
| 13:35 | 兩個 `modbus_scanner:` 的 YAML config 檢查、diagnostics、HA log |

## C1：重燒、entity 與版本 — 通過

- 兩台 YAML 沒有修改，用 #26 的元件編譯、OTA 重燒成功。
- 裝置資訊：`Bench-Gateway-X`、`Bench-Gateway-Y` 都是 `0.5.0.dev3 (ESPHome 2026.10.0)`（重燒前是 `0.5.0.dev2`）。
- 每台只剩 `Modbus Scanner v2 Info`／`Result`／`Lease` 三個 sensor。重燒前的 `Modbus Scanner v2 Result rs485`／`Lease rs485` 已從 HA 消失。
- 兩台的 Info：

  ```json
  {"v":1,"bridge":2,"buses":[{"bus":"rs485","serial":{"baud_rate":9600,"parity":"NONE","stop_bits":1},"pollers":[{"index":0,"name":"bench_poller","address":1}]}]}
  ```

  沒有 `result_sensor`、`lease_sensor`；`buses` 只有一條。

## C2：`check_gateway`、Scan 與 Normal Polling — 通過

`check_gateway`：兩台都是 `api_status: verified`、`bridge_status: v2_signature_verified`、`buses: ["rs485"]`、Pausable Poller `bench_poller`。

| 節點 | 範圍 | `timeout_ms` | `inter_request_delay_ms` | pause_pollers | `bus` 參數 | 耗時 | 結果 | Responder（原始值） |
|---|---|---|---|---|---|---|---|---|
| X | 8–18 | 500 | 100 | `[0]` | 省略 | 9.6 s | completed，lease `ended` | 10（`40970` = `0xA00A`）、17（`40977` = `0xA011`） |
| Y | 19–34 | 500 | 100 | `[0]` | `rs485` | 14.5 s | completed，lease `ended` | 20（`45076` = `0xB014`）、33（`45089` = `0xB021`） |

其他位址都是 `timeout`，沒有 `gateway_error`。

模擬器 log 中站號 1（Pausable Poller）的讀取：

| 節點 | 第一個到最後一個 Probe | 其間的 Poller 讀取 | Scan 前最後一次 | Scan 後第一次 |
|---|---|---|---|---|
| X | 13:31:03.360 → 13:31:11.171 | 0 | 13:31:02.714 | 13:31:12.473 |
| Y | 13:31:13.812 → 13:31:25.705 | 0 | 13:31:13.149 | 13:31:27.092 |

Scan 期間 Normal Polling 暫停，Scan 結束後約 1.3–1.4 s 恢復。

額外：對 X 以 `bus: "rs485_b"` 呼叫 `start_scan`，服務以 `service_validation_error` 拒絕：「Gateway esphome:5c013b459f4c has no Bus rs485_b; its Bus is rs485」，模擬器 log 沒有任何 Probe。

## C3：兩個 `modbus_scanner:` 編譯失敗 — 通過

`esphome config firmware/tests/two-modbus-scanners.yaml`（ESPHome 2026.10.0）exit 2，錯誤訊息：

```text
A node supports only one modbus_scanner; scan a second RS-485 line with another node.
```

（ESPHome 2026.9.0 的同一檢查也在本機與 CI 執行並失敗。）

## C4：HA log — 通過

本整合的 logger（`custom_components.woow_esphome_modbus_scanner`）沒有任何紀錄。system log 的 ERROR：

| logger | 次數 | 時間 | 說明 |
|---|---|---|---|
| `homeassistant.core` | 2 | 13:28:00 | #25：重燒前 `0.5.0.dev2` 的 Info 256 字元。X、Y 在 13:29–13:30 重燒後沒有再出現 |
| `aiohttp.server`、`websocket_api` | 4、1 | 13:30–13:34 | 本輪刻意送出的無效服務呼叫（未帶 `provider`、錯的 `bus`）被 `ServiceValidationError` 拒絕；HA REST API 對有回應的服務把它記成 ERROR |
| `homeassistant.helpers.translation` | 1 | 13:27:52 | ESPHome 核心整合的 zh-Hant 字串，與本整合無關 |

diagnostics 已下載，沒有 `probe_slots`，也沒有金鑰或密碼。

## 證據

原始檔在 repo 外的 `../bench-logs/`：`bench-20261110-c.log`（模擬器）、`stepC-pre-*-check_gateway.json`、`stepC-*-check_gateway.json`、`stepC-*-scan.json`、`stepC-5c013b459f4c-bus-mismatch.json`、`stepC-flash-gateway-*.yaml.log`、`stepC-two-modbus-scanners.log`、`stepC-diagnostics.json`。

## 在 main 上重跑（2026-11-13）

> **結果：C1–C4 全部通過。** 上面那一輪是在合併前用 `14396aa` 跑的。合併前又經過三輪 review，`custom_components/` 與 `firmware/` 改了 14 個檔，所以在合併後的 main 上重跑一次。

日期：2026-11-13　執行者：WOOWTECH 現場人員（接線、量測）＋ Claude Code（燒錄、HA 操作、紀錄）

### 環境

| 項目 | 值 |
|---|---|
| HA 版本 | 2026.7.2（測試機 .28，HAOS 16.1） |
| 整合 | `0.5.0.dev3`／main `aa4afea`（產品程式碼與 `ed25cb5` 相同；32 個檔案經 Samba 比對雜湊一致） |
| fw | `0.5.0.dev3`／main `aa4afea`，ESPHome 2026.10.0，在 Linux 編譯，OTA |
| YAML 雜湊（`git hash-object`） | X `25907d7e6e0ff986164617ffcdf89c1b53cacd0d`、Y `c9bcac5435e43e9f3268545cfe94590b1dcc65c3`，與上一輪相同（未修改） |
| 模擬器 | `tools/rtu_bench_simulator.py`，`tools/bench_profiles/bench.json`；X = 轉換器 A（`/dev/ttyUSB1`），Y = 轉換器 B（`/dev/ttyUSB0`），都在 Linux 電腦 |

| 節點 | MAC／IP | 備註 |
|---|---|---|
| X | `5C:01:3B:45:9F:4C`／192.168.2.55 | **板子有瑕疵（#28）**：每次放開 DE 都會在 Bus 上產生一個 `0x40`，設備回應快的時候會把回應弄壞。所以 X 只驗燒錄、`check_gateway`、Scan 完成與 Normal Polling 恢復，Responder 正確性以 Y 為準 |
| Y | `5C:01:3B:46:FD:A8`／192.168.2.16（DHCP，之前是 .21） | — |

### C1：重燒、entity 與版本 — 通過

- 兩台以未修改的 YAML 從 main 編譯、OTA 重燒；經 ESPHome API 讀到 `project_version` `0.5.0.dev3`、ESPHome 2026.10.0。
- HA 中每台只有 `Modbus Scanner v2 Info`／`Result`／`Lease`，沒有 per-Bus sensor。
- Info 160 字元，只有一條 Bus `rs485`；Info 的 `disabled_by_default: true`（#25）。

### C2：`check_gateway`、Scan 與 Normal Polling — 通過

`check_gateway`：兩台都是 `verified`、`v2_signature_verified`、`buses: ["rs485"]`、Pausable Poller `bench_poller`。

| 節點 | 範圍 | `timeout_ms` | `inter_request_delay_ms` | pause_pollers | `bus` 參數 | 耗時 | 結果 | Responder |
|---|---|---|---|---|---|---|---|---|
| X | 8–18 | 500 | 100 | `[0]` | 省略 | 11.0 s | completed，lease `ended`／`released` | 10（`40970`）、17（`40977`） |
| Y | 19–34 | 500 | 100 | `[0]` | `rs485` | 13.1 s | completed，lease `ended`／`released` | 20（`45076`）、33（`45089`） |

模擬器 log 中站號 1（Pausable Poller）的讀取：

| 節點 | 第一個到最後一個 Probe | 其間的 Poller 讀取 | Scan 前最後一次 | Scan 後第一次 |
|---|---|---|---|---|
| X | 16:00:56.568 → 16:01:04.790 | 1（16:00:57.211，見下） | 16:00:55.563 | 16:01:05.816 |
| Y | 16:01:07.049 → 16:01:18.915 | 0 | 16:01:06.426 | 16:01:19.920 |

- 兩台的 Normal Polling 都在 Scan 結束後約 1.0 s 恢復。
- X 那 1 次 Scan 期間的 Poller 讀取：Scan Lease 開始時，Poller 有一個 frame 正在等回應。它的回應被 X 的 `0x40` 弄壞後，`modbus_controller` 重送，這次重送不受 Scan Lease 控制。在 Y 上讓 Poller 的設備不回應，可以穩定重現（3 次 Scan 期間各送出 3–4 次），已開 **#30**；這個行為在 #26 之前就存在，不擋 C 段。
- X 另外重跑 3 次 8–18（加錄韌體 log），Poller 都沒有在 Scan 期間讀取；Responder 分別找到 0、1、2 個，是 #28 的板子瑕疵。
- #28 修正驗證時，Y 另跑過 3 次 19–34，每次都找到 20、33，韌體 log 沒有 `parse failed`／`partial response`。

### C3：兩個 `modbus_scanner:` 編譯失敗 — 通過

`esphome config firmware/tests/two-modbus-scanners.yaml`（ESPHome 2026.10.0，main `aa4afea`）exit 2：

```text
A node supports only one modbus_scanner; scan a second RS-485 line with another node.
```

### C4：HA log — 通過

本整合的 logger 從 HA 啟動（11-12 16:50）到 11-13 16:05 都沒有任何紀錄。system log 只剩 11-12 的兩則 ERROR（#25 的 Info 長度、ESPHome 核心整合的 zh-Hant 字串），11-13 沒有新的 ERROR。

### 證據

原始檔在 repo 外的 `../bench-logs/`：`stage0-compile-*.log`、`stage0-c3-two-modbus-scanners.log`、`stage2-flash-gateway-y.log`、`issue28-x-restore-flash.log`、`stage2-c1-*`、`stage2-c2-*`、`stage2-c2x-retry-*`、`stage2-lease-silent-poller-*`、`bench-20261113-c.log`（模擬器）、`stage2-c4-system-log.json`。
