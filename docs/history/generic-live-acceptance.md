# 0.5.0.dev1 通用掃描器實機驗收（#16 A 段）

> **狀態：完成，通過。** A3 已於 2026-11-13 以實體非冠傑設備補驗（見文末「A3 實體設備補驗」）。
> 操作順序見 [`docs/plans/2026-11-05-live-acceptance-runbook.md`](../plans/2026-11-05-live-acceptance-runbook.md) 步驟 0–1。
> 本輪以 **測試台** 執行：兩台單 Bus Gateway，Bus 上的設備由電腦上的模擬器扮演（見 runbook「0b. 測試台」）。

日期：2026-11-09　執行者：WOOWTECH 現場人員（燒錄按鍵、拔插網路線）＋ Claude Code（HA 操作、紀錄）

## 結論

- 結果：**通過**（A0、A1、A2、A2'、A3、多 Gateway 兩台皆通過；A3 以模擬器代替）
- bridge v1 相容碼：**可開始移除 bridge v1 相容碼**（兩台既有節點已從 v1 遷移到 v2，Repairs 提示消失；不必等 B 段）

## 環境

| 項目 | 值 |
|---|---|
| HA 版本 | 2026.7.2（測試機 .28，HAOS 16.1） |
| ESPHome 版本 | 步驟 0：2026.9.0（v1 冠傑元件只接受此版）；步驟 1：2026.10.0 |
| 整合版本／commit | `0.5.0.dev1`／`38547c1`（.28 上原有，32 個檔案與 `38547c1` 雜湊一致，未重裝） |
| firmware 元件版本／commit | `0.5.0.dev1`／`38547c1` |
| v1 韌體（步驟 0） | `38547c1` 的 `firmware/guanjie-scanner/guanjie-ind17.yaml`，複製為 `guanjie-x.yaml`／`guanjie-y.yaml`，只改 `name`、`friendly_name`、AP `ssid` |

## 測試台

| 項目 | 值 |
|---|---|
| 模擬器 | `tools/rtu_bench_simulator.py`／commit `b892ebc` |
| 模擬器設定 | `tools/bench_profiles/bench.json` |
| Gateway YAML | `tools/bench_profiles/gateway-x.yaml`（`git hash-object` `25907d7e6e0ff986164617ffcdf89c1b53cacd0d`）、`gateway-y.yaml`（`c9bcac5435e43e9f3268545cfe94590b1dcc65c3`） |
| 轉換器 A（X）晶片／COM | CH340／COM3 |
| 轉換器 B（Y）晶片／COM | CH340／COM4 |
| 模擬器 log | `bench-20261109.log`（repo 外保存）；Poller 每 2 s 一讀，Probe 間隔與設定相符 |

## 節點與 Bus

| 節點 | 板子型號 | Bus | 鮑率 | parity | stop bits | 設備型號 | 站號 |
|---|---|---|---|---|---|---|---|
| X | ESP32-D0WD-V3 rev 3.1（esp32dev，FTDI USB，需手動 BOOT+EN），MAC `5C:01:3B:45:9F:4C`，192.168.2.44 | rs485 | 9600 | NONE | 1 | 模擬器 line X | 1（Poller）、10、17 |
| Y | ESP32-D0WD-V3 rev 3.1（esp32dev，FTDI USB，需手動 BOOT+EN），MAC `5C:01:3B:46:FD:A8`，192.168.2.21 | rs485 | 9600 | NONE | 1 | 模擬器 line Y | 1（Poller）、20、33 |

非冠傑設備：**以模擬器代替**。站號 10、17、20、33 的 register 0 回 `0xA00A`、`0xA011`、`0xB014`、`0xB021`（`0xA0nn` 為 X、`0xB0nn` 為 Y）。實體設備補驗列在 #16。

## 驗收項目

| # | 項目 | 節點 X | 節點 Y | 證據 |
|---|---|---|---|---|
| A0 | 步驟 0：燒 v1 冠傑韌體並以舊版 HA 註冊後，Repairs 出現 Legacy Gateway 提示 | 通過 | 通過 | 以手動步驟、`bridge: v1` 註冊（「ESPHome 裝置」選項固定 v2）。X：`legacy_bridge_bea42d8bdd48`（2026-11-09T08:50:52Z）；Y：`legacy_bridge_8cbc06209e50`（2026-11-09T09:07:06Z），severity `warning` |
| A1 | 重燒後 Repairs 提示消失、可正常 Scan | 通過 | 通過 | USB 重燒 `gateway-x/y.yaml` 後，依 Repairs 說明在「重新設定 → 從 ESPHome 裝置新增或更新閘道」改以 v2 登錄；兩則 `legacy_bridge_*` 消失。`check_gateway`：`api_status` `verified`、`bridge_status` `v2_signature_verified` |
| A2 | Scan 後 Normal Polling 恢復 | 通過 | 通過 | X：Poller 讀取 17:32:25.5 停、17:32:41.9 恢復（計數器 41 → 42）；Y：17:39:32.0 停、17:39:58.4 恢復（40 → 41）；lease `ended`／`released` |
| A2' | Scan 中停掉 HA，超過 lease idle 時限（5 s）後再啟動，Normal Polling 已由 Gateway 自己恢復 | 通過 | 通過 | 見下方「A2' 細節」。拔 .28 網路線約 17:50:31–33；最後一個 Probe 17:50:30.2；**Poller 恢復 17:50:38.0（X、Y 同時）**；HA 17:50:45.5 才判定 `API_TRANSPORT_ERROR`，lease `unconfirmed` |
| A3 | 非冠傑設備以 Generic Device Profile 被找到並顯示原始值（**本輪以模擬器代替**；實體設備見文末補驗） | 通過 | 通過 | 原始值與 `bench.json` 一致：X 站號 10 `0xA00A`、17 `0xA011`；Y 站號 20 `0xB014`、33 `0xB021`；站號 1 回 Poller 計數器 |
| 多 Gateway | X、Y 同時各跑一個 Scan，結果互不干擾 | 通過 | 通過 | 17:40:28 同時開始，站號 1–33；X 26.4 s、Y 26.4 s 完成，Responder 各自只有自己 line 的站號，沒有串線 |

### A2' 細節

第一次以 `homeassistant.restart` 重啟 HA Core（17:48:22.3）**不算 A2'**：HA 關機時先取消 Scan 並主動釋放 lease，Poller 0.4 s 後（17:48:22.7）就恢復，驗的是 HA 正常收尾，不是 Gateway 自己恢復。

正式的 A2' 用拔線讓 HA 突然消失：

| 時間（+08:00） | 事件 | 來源 |
|---|---|---|
| 17:50:16 | X、Y 同時開始 Scan（站號 1–32，`timeout_ms` 2000，`inter_request_delay_ms` 3000，pause） | HA 回應 |
| 17:50:30.2 | X、Y 最後一個 Probe（站號 4）；依 3 s 間隔下一個應在約 17:50:35，沒有出現 | 模擬器 log |
| 17:50:38.0 | X、Y 站號 1 讀取恢復（X 324、Y 312），之後每 2 s 一讀 | 模擬器 log |
| 17:50:45.5 | HA 判定 Scan `failed`：`API_TRANSPORT_ERROR`（phase `probe`），lease `unconfirmed`、`recovery_status` `unknown` | `get_scan_status` |
| 17:53:15 | 網路線插回後 `check_gateway` 兩台皆 `verified` | HA 回應 |

Gateway 恢復比 HA 發現斷線早 7.5 s，且期間 HA 連不到 Gateway，恢復只可能由 Gateway 自己完成（ADR 0007）。HA 沒有宣稱已恢復（`unconfirmed`），符合預期。

## Scan 紀錄

全部 FC03（holding register 0，`register_count` 1，`retries` 0，Generic Device Profile）。

| 節點 | Bus | 位址範圍 | FC | `timeout_ms` | `inter_request_delay_ms` | pause_pollers | 耗時 | Responder |
|---|---|---|---|---|---|---|---|---|
| X | rs485 | 1–20 | 03 | 500 | 100 | 是 | 約 16 s | 1、10、17 |
| Y | rs485 | 1–33（`large_range_confirmed`） | 03 | 500 | 100 | 是 | 約 26 s | 1、20、33 |
| X | rs485 | 1–33（與 Y 並行） | 03 | 500 | 100 | 是 | 26.4 s | 1、10、17 |
| Y | rs485 | 1–33（與 X 並行） | 03 | 500 | 100 | 是 | 26.4 s | 1、20、33 |
| X | rs485 | 1–32（HA 重啟，不計） | 03 | 500 | 1000 | 是 | `cancelled` | — |
| Y | rs485 | 1–32（HA 重啟，不計） | 03 | 500 | 1000 | 是 | `cancelled` | — |
| X | rs485 | 1–32（A2' 拔線） | 03 | 2000 | 3000 | 是 | `failed` 於 29.0 s | 1（站號 2–4 逾時） |
| Y | rs485 | 1–32（A2' 拔線） | 03 | 2000 | 3000 | 是 | `failed` 於 29.0 s | 1（站號 2–4 逾時） |

## 證據

完整 JSON（`check_gateway`、Scan 結果、diagnostics）與模擬器 log 保存在 repo 外的 `bench-logs/`；diagnostics 已確認不含 API 金鑰或 Wi-Fi 密碼。以下為摘錄。

### 節點 X

```json
{"gateway_id": "esphome:5c013b459f4c",
 "health": {"api_status": "verified", "bus_status": "unverified", "recovery_status": "unknown",
            "encrypted": true, "bridge_status": "v2_signature_verified", "buses": ["rs485"],
            "pausable_pollers": {"rs485": [{"index": 0, "name": "bench_poller", "address": 1}]},
            "error_info": null, "cleanup_status": "closed"},
 "buses": [{"bus": "rs485", "serial": {"baud_rate": 9600, "parity": "NONE", "stop_bits": 1}}],
 "supports_scan_lease": true}
```

```json
{"integration_version": "0.5.0.dev1", "reference": "gateway-3", "provider": "esphome", "encrypted": true,
 "api_status": "verified", "bridge_status": "v2_signature_verified", "bus_status": "responded",
 "recovery_status": "unknown", "cleanup_status": "closed", "error_code": null}
```

```text
17:50:45 Scan 6e0d600d… failed: ESPHome transport failed or response deadline exceeded
         (API_TRANSPORT_ERROR, phase probe, retryable), lease_status unconfirmed
```

### 節點 Y

```json
{"gateway_id": "esphome:5c013b46fda8",
 "health": {"api_status": "verified", "encrypted": true, "bridge_status": "v2_signature_verified",
            "buses": ["rs485"],
            "pausable_pollers": {"rs485": [{"index": 0, "name": "bench_poller", "address": 1}]},
            "cleanup_status": "closed"}}
```

```json
{"integration_version": "0.5.0.dev1", "reference": "gateway-4", "provider": "esphome", "encrypted": true,
 "api_status": "verified", "bridge_status": "v2_signature_verified", "bus_status": "responded",
 "recovery_status": "unknown", "cleanup_status": "closed", "error_code": null}
```

```text
17:50:45 Scan 2201285b… failed: ESPHome transport failed or response deadline exceeded
         (API_TRANSPORT_ERROR, phase probe, retryable), lease_status unconfirmed
```

## 發現的問題

- **測試台模擬器遇到 USB 重新列舉會停止**：插拔 Gateway 的 USB 時，`rtu_bench_simulator.py` 的 line Y 執行緒收到 `SerialException`（`GetOverlappedResult failed`, PermissionError）後結束，不會重開 port，之後該 line 不再回應。驗收中以重啟模擬器處理；待修，不影響產品。
- **板子不會自動重置**：FTDI 的 RTS／DTR 沒接到 EN／IO0，USB 燒錄前要手動 BOOT+EN，燒完要再按一次 EN（esptool 的「Hard resetting via RTS」無效）。已記入 runbook。
- **從 Arduino（v1）換到 esp-idf（通用元件）以 USB 燒 factory.bin**，不用 OTA，避免分割表不相容。
- 產品端：無。

## A3 實體設備補驗（2026-11-13）

> **結果：通過。** 實體第三方設備以 Generic Device Profile 被找到，原始值正確，而且會跟著設備的值改變。

日期：2026-11-13　執行者：WOOWTECH 現場人員（接線、操作設備）＋ Claude Code（燒錄、HA 操作、紀錄）

### 設備與接線

- 設備：**VRV-To-Modbus-Controller**（把 VRV 空調系統轉成 Modbus RTU 的第三方轉換器），開啟它內建的 VRV 冷氣模擬功能。站號 1，9600 8E1（手冊預設）。
- register 對照（設備手冊）：內機 `AA-BB` 的狀態區塊是 holding register `(AA*32+BB)*6` 起的 6 個，`+1` 是設定溫度。內機 1-1 的設定溫度在 **register 199**（`0x00C7`）。
- Gateway：**Y**（`5C:01:3B:46:FD:A8`，192.168.2.16）。X 有 #28 的板子瑕疵，不用來判斷 Responder。Bus 上只接這台設備。
- 韌體：`tools/bench_profiles/gateway-y-vrv.yaml`（`git hash-object` `0e19d427`），元件來自 main `aa4afea`，`0.5.0.dev3`，ESPHome 2026.10.0，OTA。跟 `gateway-y.yaml` 的差異：parity `EVEN`，沒有 Pausable Poller（`bench_poller` 讀站號 1，會撞到這台設備）。
- HA：2026.7.2（.28），整合 `0.5.0.dev3`／main `aa4afea`（32 個檔案與 `aa4afea` 雜湊一致）。

### 結果

`check_gateway`：`verified`、`v2_signature_verified`，Bus `rs485` 的序列參數為 `9600 EVEN 1`，沒有 Pausable Poller。

| 時間 | 範圍 | FC／register | `timeout_ms`／`inter_request_delay_ms` | 耗時 | Responder（原始值） | 其他位址 |
|---|---|---|---|---|---|---|
| 16:11 | 1–5 | FC03／199 | 500／100 | 4.0 s | 1（`26`，延遲 40 ms） | 2–5 `timeout` |
| 16:12 | 1–5 | FC03／199 | 500／100 | 4.0 s | 1（`26`） | 2–5 `timeout` |
| 16:12 | 1–5 | FC03／199 | 500／100 | 4.0 s | 1（`26`） | 2–5 `timeout` |
| 現場把內機 1-1 設定溫度改成 25 °C 後 | 1–5 | FC03／199 | 500／100 | 4.0 s | 1（`25`），detail `FC03 register 0x00C7 x1 = [25]` | 2–5 `timeout` |

- 原始值與設備上的設定溫度一致（26 °C → `26`，改成 25 °C 後 → `25`），證明讀到的是設備的即時值，不是快取。
- 韌體 log 沒有 `parse failed`／`partial response`。
- 驗完把 Y 燒回 `gateway-y.yaml`，`check_gateway` 回到 `9600 NONE 1`，`bench_poller` 恢復。

### 證據

原始檔在 repo 外的 `../bench-logs/`：`stage3-flash-gateway-y-vrv.log`、`stage3-a3-try1-*.json`、`stage3-a3-*.json`、`stage3-a3-after-change-*.json`、`stage3-a3-probe1-firmware.log`、`stage3-a3-firmware.log`、`stage4-flash-gateway-y.log`。
