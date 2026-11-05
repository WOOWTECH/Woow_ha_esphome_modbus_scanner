# 0.5.0.dev1 通用掃描器實機驗收（#16 A 段）

> **狀態：尚未執行。** 本檔是 #16 的紀錄骨架，`_待填_` 欄位在實機驗收時填入。
> 操作順序見 [`docs/plans/2026-11-05-live-acceptance-runbook.md`](../plans/2026-11-05-live-acceptance-runbook.md) 步驟 1。

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

## 節點與 Bus

| 節點 | 板子型號 | Bus | 鮑率 | parity | stop bits | 設備型號 | 站號 |
|---|---|---|---|---|---|---|---|
| X | _待填_ | _待填_ | | | | | |
| X | | _待填_ | | | | | |
| Y | _待填_ | _待填_ | | | | | |

非冠傑設備：_待填（型號、站號、使用的 Generic Device Profile 設定）_

## 驗收項目

| # | 項目 | 節點 X | 節點 Y | 證據 |
|---|---|---|---|---|
| A1 | 重燒後 Repairs 提示消失、可正常 Scan | _待填_ | _待填_ | |
| A2 | Scan 後 Normal Polling 恢復 | _待填_ | _待填_ | |
| A2' | Scan 中停掉 HA，超過 lease idle 時限（5 s）後再啟動，Normal Polling 已由 Gateway 自己恢復 | _待填_ | _待填_ | 停 HA 與重啟的時間戳：_待填_ |
| A3 | 非冠傑設備以 Generic Device Profile 被找到並顯示原始值 | _待填_ | _待填_ | |

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
