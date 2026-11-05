# 0.5.0.dev1 通用掃描器實機驗收（#16 A 段）

> **狀態：尚未執行。** 本檔是 #16 的紀錄骨架，`_待填_` 欄位在實機驗收時填入。
> 操作順序見 [`docs/plans/2026-11-05-live-acceptance-runbook.md`](../plans/2026-11-05-live-acceptance-runbook.md) 步驟 0–1。
> 本輪以 **測試台** 執行：兩台單 Bus Gateway，Bus 上的設備由電腦上的模擬器扮演（見 runbook「0b. 測試台」）。

日期：_待填_　執行者：_待填_

## 結論

- 結果：_待填（通過／未通過）_
- bridge v1 相容碼：_待填（A 段通過後註明「可開始移除 bridge v1 相容碼」）_

## 環境

| 項目 | 值 |
|---|---|
| HA 版本 | _待填_ |
| ESPHome 版本 | _待填_ |
| 整合版本／commit | `0.5.0.dev1`／`38547c1` |
| firmware 元件版本／commit | `0.5.0.dev1`／`38547c1` |
| v1 韌體（步驟 0） | `38547c1` 的 `firmware/guanjie-scanner/guanjie-ind17.yaml` |

## 測試台

| 項目 | 值 |
|---|---|
| 模擬器 | `tools/rtu_bench_simulator.py`／commit _待填_ |
| 模擬器設定 | `tools/bench_profiles/bench.json` |
| Gateway YAML | `tools/bench_profiles/gateway-x.yaml`、`gateway-y.yaml` |
| 轉換器 A（X）晶片／COM | _待填_ |
| 轉換器 B（Y）晶片／COM | _待填_ |
| 模擬器 log | _待填（檔名；回應延遲觀察值）_ |

## 節點與 Bus

| 節點 | 板子型號 | Bus | 鮑率 | parity | stop bits | 設備型號 | 站號 |
|---|---|---|---|---|---|---|---|
| X | _待填_ | rs485 | 9600 | NONE | 1 | 模擬器 line X | 1（Poller）、10、17 |
| Y | _待填_ | rs485 | 9600 | NONE | 1 | 模擬器 line Y | 1（Poller）、20、33 |

非冠傑設備：**以模擬器代替**。站號 10、17、20、33 的 register 0 回 `0xA00A`、`0xA011`、`0xB014`、`0xB021`（`0xA0nn` 為 X、`0xB0nn` 為 Y）。實體設備補驗列在 #16。

## 驗收項目

| # | 項目 | 節點 X | 節點 Y | 證據 |
|---|---|---|---|---|
| A0 | 步驟 0：燒 v1 冠傑韌體並以舊版 HA 註冊後，Repairs 出現 Legacy Gateway 提示 | _待填_ | _待填_ | |
| A1 | 重燒後 Repairs 提示消失、可正常 Scan | _待填_ | _待填_ | |
| A2 | Scan 後 Normal Polling 恢復 | _待填_ | _待填_ | |
| A2' | Scan 中停掉 HA，超過 lease idle 時限（5 s）後再啟動，Normal Polling 已由 Gateway 自己恢復 | _待填_ | _待填_ | 停 HA 與重啟的時間戳：_待填_；模擬器 log 中站號 1 讀取恢復的時間戳：_待填_ |
| A3 | 非冠傑設備以 Generic Device Profile 被找到並顯示原始值（**以模擬器代替**） | _待填_ | _待填_ | 原始值與 `bench.json` 一致：_待填_ |
| 多 Gateway | X、Y 同時各跑一個 Scan，結果互不干擾 | _待填_ | _待填_ | |

## Scan 紀錄

| 節點 | Bus | 位址範圍 | FC | `timeout_ms` | `inter_request_delay_ms` | pause_pollers | 耗時 | Responder |
|---|---|---|---|---|---|---|---|---|
| | | | | | | | | |

## 證據

每台節點附上 `check_gateway` 回應、diagnostics JSON（去掉金鑰）與相關 HA log 片段。

### 節點 X

```json
_待填：check_gateway 回應_
```

```json
_待填：diagnostics_
```

```text
_待填：HA log_
```

### 節點 Y

```json
_待填：check_gateway 回應_
```

```json
_待填：diagnostics_
```

```text
_待填：HA log_
```

## 發現的問題

_待填（無則寫「無」；有則附 issue 連結）_
