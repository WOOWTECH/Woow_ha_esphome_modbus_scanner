# Info 感測器預設停用的實機驗收（#25）

> **狀態：完成。條件 2、3 通過；條件 1 只做了部分驗證（韌體端通過，HA 端「從沒見過的 Gateway」未能實機驗證），並發現 README 的錯誤說明，已修正。**
> 測試台與 [`one-bus-regression.md`](one-bus-regression.md) 相同的 Gateway X，但這次改在 Linux 電腦上燒錄與執行模擬器。另發現 Scan 會漏 Responder，原因是測試台的 RS-485 雜訊，與 #25 無關，記錄在 #28。

日期：2026-11-12　執行者：Claude Code（現場人員把 Gateway X 接上電，並把轉換器 A 改插到 Linux 電腦）

## 結論

- **條件 1（沒有 `longer than 255` 的 ERROR，Info entity 顯示停用）：部分驗證。**
  - 韌體端通過：X 經 ESPHome API 回報 Info 的 `disabled_by_default: true`，Result、Lease 為 `false`；Info 長 359 字元，仍完整發布。
  - HA 端未通過，原因是測試方法：X 先前已加入過 HA，移除再加入後，HA 從「已刪除 entity」紀錄還原了原本的啟用狀態（`disabled_by: null`），沒有套用 `disabled_by_default`，所以 HA 仍記錄了 1 次 ERROR。HA 2026.7.2 的 `homeassistant/helpers/entity_registry.py` 在 `async_get_or_create` 時以 `(domain, platform, unique_id)` 找已刪除紀錄並還原 `disabled_by`；已刪除紀錄保留 30 天（`ORPHANED_ENTITY_KEEP_SECONDS`）。ESPHome entity 的 unique_id 由 MAC 與名稱組成，Info 名稱由 contract 固定，所以同一台 Gateway 永遠是同一個 entity。
  - 從沒加入過 HA 的 Gateway：未實機驗證（手邊沒有新的板子；改 HA 內部的 entity registry 檔對借用機風險太高）。依據是 API 旗標正確，以及上述 HA 原始碼：沒有已刪除紀錄時，`disabled_by` 由 entity 的 `entity_registry_enabled_default` 決定，ESPHome 以 `disabled_by_default` 設定這個值。
  - README 原本寫「先前已加入的 Gateway 移除後重新加入即可」，是錯的；已改為「請手動停用 Info entity；30 天內移除再加入沒有用」。
- **條件 2（Enrollment、「檢查 Gateway」、Scan 含 Scan Lease）：通過。** Enrollment、「檢查 Gateway」（1 條 Bus、serial、5 個 Pausable Poller）、Scan Lease 暫停與恢復、diagnostics 的 Info 摘要都正確。Scan 漏掉部分 Responder，原因在測試台（見「發現的問題」），1 個 Pausable Poller 的基準比對也一樣會漏。
- **條件 3（`0.5.0.dev1` 整合搭新韌體）：通過。** dev1 載入同一個 config entry，沒有錯誤；「檢查 Gateway」讀到完整的 Info（dev1 不看 `disabled_by_default`）；Scan 的 Scan Lease 與 Result 正常。
- 原驗收條件 2 寫的 `probe_slots` 已由 #26 移除，這次不檢查。

## 環境

| 項目 | 值 |
|---|---|
| HA 版本 | 2026.7.2（測試機 .28，HAOS 16.1） |
| 燒錄、模擬器的電腦 | Linux；ESPHome 2026.10.0（scratch venv）；模擬器 pyserial 3.5，轉換器 A（CH340，`1a86:7523`）在 `/dev/ttyUSB0` |
| 整合 | `0.5.0.dev3`／`ed25cb5`（本分支，Samba 安裝，32 個檔案與 `ed25cb5` 雜湊一致）；條件 3 期間換成 `0.5.0.dev1`／`38547c1`（`git archive` 匯出，雜湊一致）。原本的 `14396aa` 移到 `/config/woow_backup_dev3_14396aa`，dev1 驗完移到 `/config/woow_backup_dev1_38547c1` |
| HA 備份 | 開始前建立 partial 備份 `pre-issue-25`（HA 設定）；`pre-loan-20261105` 未動 |
| fw（驗收） | `tools/bench_profiles/gateway-x-five-pollers.yaml`（`21880e0b`），元件來自 `ed25cb5`，OTA |
| fw（收尾） | `tools/bench_profiles/gateway-x.yaml`（`25907d7e`，未修改），元件來自 `ed25cb5`，OTA |
| 模擬器 | `tools/rtu_bench_simulator.py`，設定 `tools/bench_profiles/bench-five-pollers.json`（`20aa4206`） |

## 節點與 Bus

| 節點 | MAC／IP | Bus | 序列參數 | 站號 | Pausable Poller |
|---|---|---|---|---|---|
| X | `5C:01:3B:45:9F:4C`／192.168.2.55（DHCP，之前是 .44） | rs485 | 9600 NONE 1 | 1–5、10、17 | `bench_poller_01`–`05`（站號 1–5）；收尾後回到 `bench_poller`（站號 1） |

Gateway Y 這次沒有開機，沒有使用。

## 步驟（本機時間 +08:00）

| 時間 | 做什麼 |
|---|---|
| 16:18 | 在 Linux 編譯 5 個 Pausable Poller 的韌體 |
| 16:30 | 讀 X 原本的狀態：`0.5.0.dev3`（11-10 編譯）、1 個 Poller、Info 160 字元、`disabled_by_default: false` |
| 16:30 | 建立 HA 備份 `pre-issue-25` |
| 16:31 | 用 Samba 換上 `ed25cb5` 整合，重啟 HA |
| 16:32–16:33 | 從本整合移除 X（reconfigure → `remove_gateway`，只選 X）；刪除 X 的 ESPHome config entry（entity 全部移除） |
| 16:33 | 啟動模擬器；OTA 燒錄 5 個 Poller 的韌體 |
| 16:34 | 經 ESPHome API 讀 Info：359 字元、`disabled_by_default: true` |
| 16:35 | 用 zeroconf 發現流程把 X 加回 HA 的 ESPHome；Info entity `disabled_by: null`；HA 記錄 1 次 `longer than 255` ERROR |
| 16:42 | Enrollment（reconfigure → `esphome_device`）、「檢查 Gateway」 |
| 16:43、16:44、16:46 | Scan 1–17，暫停全部 5 個 Poller（第 3 次同時錄 firmware log） |
| 16:48 | 換上 `0.5.0.dev1`，重啟 HA；「檢查 Gateway」、Scan 1–17 |
| 16:50 | 換回 `ed25cb5`，重啟 HA；「檢查 Gateway」；下載 diagnostics |
| 16:51 | OTA 燒回標準 `gateway-x.yaml`；「檢查 Gateway」；Scan 8–18 三次（基準比對） |

## 條件 1：Info entity 停用、沒有 ERROR — 部分驗證

| 項目 | 結果 |
|---|---|
| 重燒前（舊韌體） | Info entity `disabled_by: null`，HA 存了 160 字元的 state |
| API 回報（新韌體） | Info `disabled_by_default: true`；Result、Lease `false`；Info 359 字元，5 個 Pausable Poller 都在 |
| 編譯結果 | `main.cpp` 中 Info 以 `disabled_by_default` 旗標註冊，Result、Lease 沒有 |
| HA entity registry（重新加入後） | Info `disabled_by: null`（從已刪除紀錄還原），Result、Lease 也是 `null` |
| HA log | 16:35:09 `homeassistant.core` ERROR 1 次：`State {...} for sensor.bench_gateway_x_modbus_scanner_v2_info is longer than 255`；之後每次 HA 重啟、Info 重新發布都會再出現 |

## 條件 2：Enrollment、「檢查 Gateway」、Scan — 通過

「檢查 Gateway」：`api_status: verified`、`v2_signature_verified`、`bridge_version: 2`、1 條 Bus `rs485`（9600／NONE／1）、5 個 Pausable Poller（index 0–4、名稱、站號 1–5 都正確）、`supports_scan_lease: true`。

| Scan | 範圍 | 模擬器有回應 | 整合記錄的 Responder | Scan Lease |
|---|---|---|---|---|
| 16:43 | 1–17 | 1–5、10、17 | 1、3、5、10、17 | `active` → `ended`，5 個 Poller 暫停 |
| 16:44 | 1–17 | 同上 | 1、3、4、5 | 同上 |
| 16:46 | 1–17 | 同上 | 1、5、10 | 同上（`released`） |

- 模擬器 log：Scan 期間 5 個 Poller 都沒有讀取，Scan Lease 結束後立刻恢復。
- 漏掉的位址，Gateway 韌體自己發布的 Result 就是 `timeout`，同一時間 hub 記錄 `Clearing buffer of 8 bytes - parse failed`；HA 照實轉述。見「發現的問題」。

Diagnostics（`ed25cb5`）：X 的 `info` 是 `{"bridge_version": 2, "serial": {"baud_rate": 9600, "parity": "NONE", "stop_bits": 1}, "pausable_poller_count": 5}`；沒開機的 Y 和 mock Gateway 是 `null`，沒有錯誤。下載檔中沒有 Bus 名稱、Poller 名稱、MAC、IP。

## 條件 3：`0.5.0.dev1` 整合搭新韌體 — 通過

- dev1 載入 `ed25cb5` 建立的 config entry，狀態 `loaded`，沒有遷移（兩版都是 `VERSION = 1`，儲存檔版本相同）。
- 「檢查 Gateway」：`verified`、`v2_signature_verified`、`buses: ["rs485"]`、5 個 Pausable Poller。dev1 依類型與名稱找 Info，不看 `disabled_by_default`。
- Scan 1–17：`completed`，Scan Lease `active` → `ended`（`released`），5 個 Poller 暫停；Responder 1、2（其餘漏失，同一個 RS-485 問題）。
- HA log：dev1 本身沒有 ERROR；只有 Info entity 仍啟用造成的 `longer than 255`（條件 1 的原因）。

## 證據

測試台本機的 `bench-logs/`（不在 repo 內）：

| 檔案 | 內容 |
|---|---|
| `step25-0-gateway-x-before.txt` | 重燒前 X 的版本、entity 旗標、Info |
| `step25-3-registry-x-before.json` | 移除前 X 的 entity registry |
| `step25-4-flash.log`、`step25-4-gateway-x-info.txt` | 5 個 Poller 韌體的 OTA；新 Info 與 API 旗標 |
| `step25-4-registry-x-after.json`、`step25-4-system-log.json` | 重新加入後的 entity registry；HA system log（含 ERROR） |
| `step25-4-simulator.log` | 整段驗收的模擬器 log |
| `step25-5-*`、`step25-5b-*`、`step25-6-scan-results.json` | 條件 2 的「檢查 Gateway」與三次 Scan |
| `step25-6-gateway-x-firmware.log` | 16:45–16:52 的 Gateway firmware log（含 hub 警告） |
| `step25-7-dev1-*` | 條件 3 的「檢查 Gateway」、Scan、HA system log |
| `step25-8-diagnostics.json` | `ed25cb5` 的 diagnostics 下載檔 |
| `step25-9-*` | 燒回標準韌體與三次基準 Scan |

## 發現的問題

1. **重新加入不會套用 `disabled_by_default`**（本輪修正文件）：HA 會還原已刪除 entity 的 `disabled_by` 30 天。README 原本建議「移除後重新加入」，已改為手動停用 Info entity。Issue #25 的 Agent Brief 也有同樣的假設，已在 issue 留言說明。
2. **Scan 漏掉 Responder（#28）**：Gateway 每次送出後都多收 1 個 byte（`partial response`，連沒有裝置回應的位址也有），落進回應 frame 時就 `parse failed`。1 個 Pausable Poller 的基準 Scan 8–18 跑 3 次，有 2 次漏掉站號 10，所以跟 Poller 數量與 #25 無關。上次在 Windows 測試台沒有這種警告；這次換成 Linux 電腦接轉換器。
3. ESPHome 2026.10 的 Modbus hub 在 5 個 2 秒輪詢的 Poller 下，平時就會記錄 `Frame already active ... refused`／`Poll refused by hub`，屬於 hub 正常的排隊行為，不影響 Scan（Scan 期間 Poller 暫停）。
