# Per-Bus Probe 實機驗收（#16 B 段，驗 #18）

> **狀態：尚未執行。** 本檔是 #16 的紀錄骨架，`_待填_` 欄位在實機驗收時填入。
> 操作順序見 [`docs/plans/2026-11-05-live-acceptance-runbook.md`](../plans/2026-11-05-live-acceptance-runbook.md) 步驟 2–4。
> 本輪以 **測試台** 執行：兩台 **單 Bus** Gateway，設備由模擬器扮演（見 runbook「0b. 測試台」）。
> 需要同一 Gateway 兩條實體 Bus 的項目本輪不驗，標「延後」，在 #16 等有兩條 Bus 的 Gateway 再驗。

日期：_待填_　執行者：_待填_

## 結論

- 結果：_待填（通過／未通過）_
- 不符或待追的項目：_待填（附 issue 連結）_

## 環境

| 項目 | 值 |
|---|---|
| HA 版本 | _待填_ |
| ESPHome 版本 | _待填_ |
| 舊版整合／fw | `0.5.0.dev1`／`38547c1` |
| 新版 fw | `0.5.0.dev2`／_待填（`a426ddc` 或 `c84e40e`，兩者 firmware 相同）_ |
| 新版整合 | `0.5.0.dev2`／_待填（`c84e40e` 或之後）_ |
| 模擬器 | `tools/rtu_bench_simulator.py`／commit _待填_；設定 `tools/bench_profiles/bench.json` |
| 轉換器 A（X）／B（Y）晶片 | _待填_ |

## 節點與 Bus

| 節點 | 板子型號 | Bus | 鮑率 | parity | stop bits | 設備型號 | 站號 | Pausable Poller |
|---|---|---|---|---|---|---|---|---|
| X | _待填_ | rs485 | 9600 | NONE | 1 | 模擬器 line X | 1、10、17 | `bench_poller`（站號 1） |
| Y | _待填_ | rs485 | 9600 | NONE | 1 | 模擬器 line Y | 1、20、33 | `bench_poller`（站號 1） |

## 各步驟版本組合

| 步驟 | HA | 節點 X | 節點 Y | 測項 | 執行時間 |
|---|---|---|---|---|---|
| 2 | 舊版 | 舊版 fw | 新版 fw | B7 | _待填_ |
| 3 | 新版 | 舊版 fw | 新版 fw | B6（只驗模式） | _待填_ |
| 4 | 新版 | 新版 fw | 新版 fw | B1（單 Bus）、B1a | _待填_ |

## 驗收項目

| # | 項目 | 結果 | 證據／備註 |
|---|---|---|---|
| B7 | 舊 HA + 新 fw（節點 Y）正常 Scan，Pausable Poller 暫停與恢復正常 | _待填_ | |
| B6 | 新 HA + 舊 fw（節點 X）：`probe_slots` 為 `shared_slot_fallback` | _待填_ | `check_gateway` 前 diagnostics 的 `probe_slots`：_待填（預期 `null`）_；節點 Y 為 `per_bus`：_待填_ |
| B6 | 兩條 Bus 輪流送 Probe | 延後 | 需同一 Gateway 兩條 Bus |
| B6 | 側邊欄顯示「預估未包含其他 Scan 的 Probe」 | 延後 | 提示只在同一 Gateway 另有 Scan 時出現 |
| B3 反向 | 舊 fw 下，3000／2000 設定的第二個並行 Scan 被 `concurrent_wait_max_ms` 拒絕（建議項） | 延後 | 需同一 Gateway 兩條 Bus |
| B1 | **單 Bus**：`gateway-x.yaml` 不修改即可用新版元件編譯、重燒；有 `Modbus Scanner v2 Result rs485`／`Lease rs485`，共用 sensor 仍在；裝置資訊 `0.5.0.dev2` | _待填_ | YAML 未修改的證明（步驟 1 與 4 的 `git hash-object`）：_待填_ |
| B1 | 多 Bus YAML 不修改即可編譯、重燒 | 延後 | 沒有多 Bus Gateway |
| B1a | 重燒後先 `check_gateway`，`health.probe_slots` 為 `per_bus` | _待填_ | |
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

每個 Probe 平均耗時（給 B4 回推範圍用）：_待填_

## Scan 紀錄

| 步驟 | 節點 | Bus | 位址範圍 | FC | `timeout_ms` | `inter_request_delay_ms` | pause_pollers | 單獨／並行 | 耗時 | Responder |
|---|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | | |

## 證據

每個步驟附上 `check_gateway` 回應、diagnostics JSON（去掉金鑰）與相關 HA log 片段。

### 步驟 2（節點 Y）

```json
_待填_
```

### 步驟 3（節點 X、Y）

```json
_待填_
```

### 步驟 4（節點 X）

```json
_待填_
```

```text
_待填：HA log_
```

## 發現的問題

_待填（無則寫「無」；有則附 issue 連結）_
