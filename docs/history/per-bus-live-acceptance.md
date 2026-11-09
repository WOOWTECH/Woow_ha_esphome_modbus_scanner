# Per-Bus Probe 實機驗收（#16 B 段，驗 #18）

> **狀態：本輪（測試台）完成；本輪可驗項目全部通過，多 Bus 項目延後。**
> 操作順序見 [`docs/plans/2026-11-05-live-acceptance-runbook.md`](../plans/2026-11-05-live-acceptance-runbook.md) 步驟 2–4。
> 本輪以 **測試台** 執行：兩台 **單 Bus** Gateway，設備由模擬器扮演（見 runbook「0b. 測試台」）。
> 需要同一 Gateway 兩條實體 Bus 的項目本輪不驗，標「延後」，在 #16 等有兩條 Bus 的 Gateway 再驗。

日期：2026-11-09　執行者：WOOWTECH 現場人員 ＋ Claude Code

## 結論

- 結果：**本輪可驗項目通過**（B7、B6 模式、B1 單 Bus、B1a）。
- 不符或待追的項目：新版 firmware 的 Info sensor 超過 HA 255 字元 state 上限，HA log 出現 `ERROR`、該 entity 為 `unknown`（不影響掃描，見「發現的問題」，待開 issue）。延後項目（B1 多 Bus、B2–B5、B3 對照組與反向對照、B6 輪流與側邊欄提示、B8）需要同一 Gateway 接兩條實體 Bus，留在 #16。

## 環境

| 項目 | 值 |
|---|---|
| HA 版本 | 2026.7.2（測試機 .28，HAOS 16.1） |
| ESPHome 版本 | 2026.10.0 |
| 舊版整合／fw | `0.5.0.dev1`／`38547c1` |
| 新版 fw | `0.5.0.dev2`／`c84e40e` |
| 新版整合 | `0.5.0.dev2`／`c84e40e`（Samba 安裝，33 個檔案與 `c84e40e` 雜湊一致） |
| 模擬器 | `tools/rtu_bench_simulator.py`／commit `b892ebc`；設定 `tools/bench_profiles/bench.json` |
| 轉換器 A（X）／B（Y）晶片 | CH340（COM3）／CH340（COM4） |

## 節點與 Bus

| 節點 | 板子型號 | Bus | 鮑率 | parity | stop bits | 設備型號 | 站號 | Pausable Poller |
|---|---|---|---|---|---|---|---|---|
| X | ESP32-D0WD-V3 rev 3.1，MAC `5C:01:3B:45:9F:4C`，192.168.2.44 | rs485 | 9600 | NONE | 1 | 模擬器 line X | 1、10、17 | `bench_poller`（站號 1） |
| Y | ESP32-D0WD-V3 rev 3.1，MAC `5C:01:3B:46:FD:A8`，192.168.2.21 | rs485 | 9600 | NONE | 1 | 模擬器 line Y | 1、20、33 | `bench_poller`（站號 1） |

## 各步驟版本組合

| 步驟 | HA | 節點 X | 節點 Y | 測項 | 執行時間 |
|---|---|---|---|---|---|
| 2 | 舊版 | 舊版 fw | 新版 fw | B7 | 2026-11-09 17:54–17:57（Y 以 OTA 重燒） |
| 3 | 新版 | 舊版 fw | 新版 fw | B6（只驗模式） | 2026-11-09 17:57–17:59（Samba 安裝整合、重啟 HA） |
| 4 | 新版 | 新版 fw | 新版 fw | B1（單 Bus）、B1a | 2026-11-09 17:59–18:00（X 以 OTA 重燒） |

## 驗收項目

| # | 項目 | 結果 | 證據／備註 |
|---|---|---|---|
| B7 | 舊 HA + 新 fw（節點 Y）正常 Scan，Pausable Poller 暫停與恢復正常 | 通過 | 裝置資訊 Y `0.5.0.dev2 (ESPHome 2026.10.0)`、X `0.5.0.dev1`。`gateway-y.yaml` 未改（`c9bcac54…`）。站號 1–33 完成 26.5 s，Responder 1、20（`0xB014`）、33（`0xB021`），lease `released`；Poller 17:55:58.0 停、17:56:24.6 恢復（469 → 470） |
| B6 | 新 HA + 舊 fw（節點 X）：`probe_slots` 為 `shared_slot_fallback` | 通過 | HA 重啟後、`check_gateway` 前 diagnostics 的 `probe_slots`：X、Y 皆 `null`（符合預期）。`check_gateway` 後：X `shared_slot_fallback`、Y `per_bus`（回應的 `health.probe_slots` 與 diagnostics 一致） |
| B6 | 兩條 Bus 輪流送 Probe | 延後 | 需同一 Gateway 兩條 Bus |
| B6 | 側邊欄顯示「預估未包含其他 Scan 的 Probe」 | 延後 | 提示只在同一 Gateway 另有 Scan 時出現 |
| B3 反向 | 舊 fw 下，3000／2000 設定的第二個並行 Scan 被 `concurrent_wait_max_ms` 拒絕（建議項） | 延後 | 需同一 Gateway 兩條 Bus |
| B1 | **單 Bus**：`gateway-x.yaml` 不修改即可用新版元件編譯、重燒；有 `Modbus Scanner v2 Result rs485`／`Lease rs485`，共用 sensor 仍在；裝置資訊 `0.5.0.dev2` | 通過 | YAML 未修改：步驟 1 與 4 的 `git hash-object gateway-x.yaml` 皆 `25907d7e6e0ff986164617ffcdf89c1b53cacd0d`。entity：`Modbus Scanner v2 Info`、`Result`、`Lease`、`Result rs485`、`Lease rs485`、`Bench poller counter`。裝置資訊 `0.5.0.dev2 (ESPHome 2026.10.0)` |
| B1 | 多 Bus YAML 不修改即可編譯、重燒 | 延後 | 沒有多 Bus Gateway |
| B1a | 重燒後先 `check_gateway`，`health.probe_slots` 為 `per_bus` | 通過 | 重燒後第一個動作即 `check_gateway`（2026-11-09T09:59:48Z）：`per_bus`；之後 diagnostics X、Y 皆 `per_bus`。全新版本下 X、Y 並行 Scan（站號 1–33）分別 26.5 s、26.8 s 完成，Responder 正確 |
| B2 | 並行 Scan 的 Responder 清單與單獨 Scan 一致，沒有遺失或串 Bus | 延後 | 需同一 Gateway 兩條 Bus |
| B3 | 每條 Bus 並行耗時 ≤ 單獨耗時 × 1.2；3000／2000 設定可開始 Scan | 延後 | 需同一 Gateway 兩條 Bus |
| B4 | 兩個 pause_pollers Scan 各自只暫停自己 Bus 的 Poller；幾乎同時結束時兩則 lease 結束訊息都到 HA，Normal Polling 都恢復 | 延後 | 需同一 Gateway 兩條 Bus |
| B5 | 一條 Bus 每個 Probe 都逾時（總時間 > 5 s），另一條 Bus 的 Scan Lease 不因 idle 結束，Scan 正常完成 | 延後 | 需同一 Gateway 兩條 Bus |
| B8 | v0.5.0 zh-TW 教學的「獨立 vs 輪流」與實機相符 | 延後 | 需同一 Gateway 兩條 Bus |

## B3 耗時

本輪延後（需同一 Gateway 兩條 Bus）。

兩次量測的位址範圍、`timeout_ms`、`inter_request_delay_ms` 要相同。每條 Bus 只跟自己的單獨耗時比。

| Bus | 位址範圍 | `timeout_ms` | `inter_request_delay_ms` | 步驟 3 單獨 | 步驟 3 並行 | 步驟 3 倍率 | 步驟 4 單獨 | 步驟 4 並行 | 步驟 4 倍率 | ≤ 1.2？ |
|---|---|---|---|---|---|---|---|---|---|---|
| _待填_ | | | | | | | | | | |
| _待填_ | | | | | | | | | | |

每個 Probe 平均耗時（給 B4 回推範圍用）：_待填_。參考：單 Bus、`timeout_ms` 500、`inter_request_delay_ms` 100 時，站號 1–33 約 26.5 s，平均每個 Probe 約 0.8 s（多數為逾時）。

## Scan 紀錄

全部 FC03（holding register 0，`register_count` 1，`retries` 0，Generic Device Profile）。

| 步驟 | 節點 | Bus | 位址範圍 | FC | `timeout_ms` | `inter_request_delay_ms` | pause_pollers | 單獨／並行 | 耗時 | Responder |
|---|---|---|---|---|---|---|---|---|---|---|
| 2 | Y | rs485 | 1–33 | 03 | 500 | 100 | 是 | 單獨 | 26.5 s | 1、20、33 |
| 4 | X | rs485 | 1–33 | 03 | 500 | 100 | 是 | 與 Y 並行（不同 Gateway） | 26.5 s | 1、10、17 |
| 4 | Y | rs485 | 1–33 | 03 | 500 | 100 | 是 | 與 X 並行（不同 Gateway） | 26.8 s | 1、20、33 |

## 證據

完整 JSON 保存在 repo 外的 `bench-logs/`（`step2-*`、`step3-*`、`step4-*`），diagnostics 已確認不含金鑰。以下為摘錄。

### 步驟 2（節點 Y）

```json
{"gateway_id": "esphome:5c013b46fda8",
 "health": {"api_status": "verified", "bus_status": "responded", "encrypted": true,
            "bridge_status": "v2_signature_verified", "buses": ["rs485"],
            "pausable_pollers": {"rs485": [{"index": 0, "name": "bench_poller", "address": 1}]},
            "cleanup_status": "closed", "error_info": null}}
```

舊版 HA（`0.5.0.dev1`）的 `check_gateway` 沒有 `probe_slots`，屬預期。

### 步驟 3（節點 X、Y）

```text
diagnostics（HA 重啟後、check_gateway 前）: integration_version 0.5.0.dev2
  gateway-3 (X) probe_slots = null   bridge_status unchecked
  gateway-4 (Y) probe_slots = null   bridge_status unchecked
check_gateway:
  X health.probe_slots = shared_slot_fallback  api verified  bridge v2_signature_verified  buses [rs485]
  Y health.probe_slots = per_bus               api verified  bridge v2_signature_verified  buses [rs485]
diagnostics（check_gateway 後）:
  gateway-3 (X) probe_slots = shared_slot_fallback
  gateway-4 (Y) probe_slots = per_bus
```

### 步驟 4（節點 X）

```text
check_gateway（重燒後第一個動作，2026-11-09T09:59:48Z）:
  X health.probe_slots = per_bus  api verified  bridge v2_signature_verified
裝置資訊: Bench-Gateway-X  0.5.0.dev2 (ESPHome 2026.10.0)
entity:
  sensor.bench_gateway_x_modbus_scanner_v2_info          Modbus Scanner v2 Info
  sensor.bench_gateway_x_modbus_scanner_v2_result        Modbus Scanner v2 Result
  sensor.bench_gateway_x_modbus_scanner_v2_lease         Modbus Scanner v2 Lease
  sensor.bench_gateway_x_modbus_scanner_v2_result_rs485  Modbus Scanner v2 Result rs485
  sensor.bench_gateway_x_modbus_scanner_v2_lease_rs485   Modbus Scanner v2 Lease rs485
  sensor.bench_gateway_x_bench_poller_counter            Bench poller counter
diagnostics: gateway-3 (X) probe_slots = per_bus, gateway-4 (Y) probe_slots = per_bus
```

```text
ERROR (homeassistant.core, core.py:2439) State {"v":1,"bridge":2,"buses":[{"bus":"rs485","serial":{"baud_rate":9600,"parity":"NONE","stop_bits":1},"result_sensor":"Modbus Scanner v2 Result rs485","lease_sensor":"Modbus Scanner v2 Lease rs485","pollers":[{"index":0,"name":"bench_poller","address":1}]}]} for sensor.bench_gateway_x_modbus_scanner_v2_info is longer than 255, falling back to unknown
（節點 Y 同一則，entity 為 sensor.bench_gateway_y_modbus_scanner_v2_info）
```

## 發現的問題

- **產品端：新版 firmware 的 Info sensor 超過 HA 的 255 字元 state 上限**（#18 引入，需開新 issue）。
  `0.5.0.dev2` 的 Info JSON 每條 Bus 多了 `result_sensor`、`lease_sensor`，單 Bus 就約 257 字元；
  HA 每次收到 Info 都記一則 `ERROR`，`sensor.*_modbus_scanner_v2_info` 變成 `unknown`。
  掃描功能不受影響：`check_gateway` 仍讀到 `probe_slots`、Bus 與 Pausable Poller（整合經 ESPHome API
  拿到完整值，不經 HA state）。多 Bus 時 JSON 更長。`0.5.0.dev1` firmware 的 Info 沒有這兩個欄位，
  步驟 1 的 HA log 沒有此錯誤。可能的方向：縮短 Info（例如 sensor 名稱改由規則推導）、或讓 Info
  sensor 不建立 HA entity（`internal`）而只供 API 讀取；需由開發端決定。
- 測試台：見 `generic-live-acceptance.md`「發現的問題」（模擬器遇 USB 重新列舉會停止、板子不會自動重置）。
