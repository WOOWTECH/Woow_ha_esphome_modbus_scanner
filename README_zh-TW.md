# Woow ESPHome Modbus Scanner

> **0.5.0.dev1 開發中**（分支 `epic/generic-scanner`）。這不是正式發行版，
> 尚未部署，也尚未完成實機驗收。最後一次部署的版本是 0.4.0.dev1，請見
> [歷史](#歷史)。

從 Home Assistant 透過 ESPHome 節點，以唯讀、盡力而為（best-effort）的方式
找出 RS-485 Bus 上有哪些 Modbus RTU 站號會回應。專案分成兩部分：

- Home Assistant 自訂整合（`custom_components/woow_esphome_modbus_scanner`），
  含側邊欄工作台、公開動作、Device Profile 與模擬 provider；
- 廠牌中立的 ESPHome external component `modbus_scanner`
  （`firmware/components/modbus_scanner`），可讓任何具 Modbus RTU hub 的
  ESPHome 節點成為掃描 **Gateway**。

English: [README.md](README.md) · 術語：[GLOSSARY.md](GLOSSARY.md)

## 教學

本版繁體中文 HTML 教學為單一離線檔：
**[檢視 0.5.0 教學原始檔](https://github.com/WOOWTECH/Woow_ha_esphome_modbus_scanner/blob/main/docs/tutorial/woow-esphome-modbus-scanner-v0.5.0-zh-TW.html)** ·
**[Raw 0.5.0 HTML](https://raw.githubusercontent.com/WOOWTECH/Woow_ha_esphome_modbus_scanner/main/docs/tutorial/woow-esphome-modbus-scanner-v0.5.0-zh-TW.html)**。
舊的模擬版教學列在[歷史](#歷史)。

## 運作方式

- **Gateway** 是已登錄、執行 `modbus_scanner` 的 ESPHome 節點。節點上每個
  設有 `modbus_scanner` 項目的 Modbus hub 就是一條 **Bus**。
- **Scan** 是在一條 Bus 上依序對一段站號送出唯讀 **Probe**（FC03 保持暫存器或
  FC04 輸入暫存器）。有回應的站號稱為 **Responder**；這不代表該站號背後恰好
  只有一台實體設備。
- Home Assistant 中的 **Device Profile** 描述一類現場設備可讀的暫存器、預設值
  與限制。內建的 **Generic Device Profile** 允許任何暫存器。Profile 也可為
  暫存器命名，結果便會在原始值旁顯示解碼值。
- 同一條 Bus 上其他輪詢元件（例如每個 `modbus_controller`）是 **Pausable
  Poller**，在韌體編譯時自動找出。Scan 期間 Gateway 以 **Scan Lease** 暫停
  你選定的輪詢元件，並自行恢復。

設計決策：
[ADR 0005：廠牌中立元件與 Device Profile](docs/adr/0005-vendor-neutral-scanner-component-and-device-profiles.md)、
[ADR 0006：Pausable Poller 的探索與選擇](docs/adr/0006-codegen-discovery-and-runtime-selection-of-pausable-pollers.md)、
[ADR 0007：由 Gateway 自行恢復的 Scan Lease](docs/adr/0007-per-scan-lease-with-gateway-owned-recovery.md)、
[ADR 0008：掃描服務清單與持久保存的歷史](docs/adr/0008-scanner-service-set-and-persisted-history.md)、
[ADR 0010：每條 Bus 各自的 Result 與 Lease 感測器](docs/adr/0010-per-bus-result-and-lease-sensors.md)。
ADR 0001–0003 說明 provider／coordinator 分離、單一設定項目生命週期與全使用者側邊欄。

## 安全與存取

掃描只讀取、盡力而為。逾時不代表該位址沒人使用，有回應也不代表該站號只對應一台
實體設備。韌體拒絕所有寫入功能碼（FC05、FC06、FC15、FC16、FC22、FC23），並自行
強制硬性限制：站號 1–247、FC03／FC04、1–4 個暫存器、逾時 100–2000 ms、每條 Bus
同時只有一個 Probe。

- `start_scan` 只接受字面布林值 `safety_confirmed: true`；字串與數字都會被拒絕。
- 超過 32 個站號的 Scan（Large Range）另需 `large_range_confirmed: true`。
  側邊欄會先顯示預估時間（站號數 × 嘗試次數 ×（逾時 + Gateway 每次額外時間）+ 間隔，與 Scan 的 `estimated_worst_case_ms` 相同）再要求確認。
- 暫停的輪詢元件在 Scan 期間，其 HA 實體值會過時。請見
  [Pausable Poller 與 Scan Lease](#pausable-poller-與-scan-lease)。

**存取政策：**側邊欄與所有動作開放給每位啟用中的 HA 使用者及內部自動化，沒有
管理員限制。實際上，任何啟用中的 Home Assistant 使用者都能對任一已登錄 Bus 的 1–247 站號產生唯讀流量
（在所選 Device Profile 的範圍內），並看到 Responder 證據。停用或未知的使用者
會被拒絕。請管控 HA 帳號。原生 ESPHome 動作是另一條路徑，本整合不加以管制；
API 加密驗證的是用戶端，不是 HA 使用者。見[授權邊界](docs/design/authorization-boundary.md)。

## 需求

- 含 ESPHome 整合的 Home Assistant（本整合依賴它）。
- 韌體需 **ESPHome 2026.9.0 或更新版本**。較舊版本會在設定驗證時失敗，訊息為
  「requires at least ESPHome version 2026.9.0」。
- ESP32（或其他 ESPHome 目標），UART 接 RS-485 收發器，並設有 `modbus:` hub 與
  原生 `api:`（建議啟用加密）。

## 1. 在 ESPHome 節點加入掃描元件

保留現有的 `uart`、`modbus` 與 `modbus_controller` 設定，加入 external component
與一個指定 hub 的 `modbus_scanner` 項目：

```yaml
esphome:
  name: my-modbus-node
  min_version: 2026.9.0

api:
  encryption:
    key: !secret api_encryption_key

external_components:
  - source:
      type: git
      url: https://github.com/WOOWTECH/Woow_ha_esphome_modbus_scanner
      path: firmware/components
    components: [modbus_scanner]

uart:
  id: rs485_uart
  tx_pin: GPIO17
  rx_pin: GPIO16
  baud_rate: 9600

modbus:
  id: rs485
  uart_id: rs485_uart

modbus_controller:
  - id: meter
    modbus_id: rs485
    address: 1
    update_interval: 10s

modbus_scanner:
  - modbus_id: rs485
```

元件會註冊唯讀探測與 lease 釋放動作（`modbus_scanner_v2_probe`、
`modbus_scanner_v2_release`）、三個共用診斷文字感測器（`Modbus Scanner v2 Info`、
`Result`、`Lease`），以及每條 Bus 的 `Modbus Scanner v2 Result <bus>` 與
`Modbus Scanner v2 Lease <bus>`；不需要 `api: custom_services`，這些感測器都不用在
YAML 宣告。綁在同一 hub 的每個
`PollingComponent`（此例為 `meter`）會自動成為 Pausable Poller；之後新增需重新編譯。
完整範例：[`firmware/examples/generic-modbus-scanner.yaml`](firmware/examples/generic-modbus-scanner.yaml)，
以及一個節點兩條 RS-485 線的
[`firmware/examples/multi-bus-modbus-scanner.yaml`](firmware/examples/multi-bus-modbus-scanner.yaml)。

**一個 Gateway 多條 Bus：**每個 hub 加一個 `modbus_scanner` 項目，可用 `bus:` 命名
（1–32 個 `0-9 A-Z a-z _ -` 字元；預設為 hub id）。每個 hub 只能有一個掃描元件。
每條 Bus 各有自己的 Pausable Poller 表，並回報鮑率、同位元與停止位元。探測動作與
文字感測器每個節點只有一組。

傳輸協定（Bridge Protocol v2）定義在單一機器可讀檔
[`bridge_v2/contract.json`](custom_components/woow_esphome_modbus_scanner/modbus_scan/bridge_v2/contract.json)，
HA adapter、測試用假 Gateway 與韌體主機測試都讀取它。

## 2. 安裝整合

**HACS：**將本儲存庫加入為 **Integration** 類型的自訂儲存庫，安裝
**Woow ESPHome Modbus Scanner**，重新啟動 Home Assistant。

**手動：**將 `custom_components/woow_esphome_modbus_scanner` 複製到 HA 的
`custom_components` 目錄後重新啟動。

接著到 **設定 → 裝置與服務 → 新增整合**。本整合只有一個設定項目，設定選單提供：

- **從 ESPHome 裝置新增 Gateway**（建議）：列出 HA ESPHome 整合中已知 MAC 的節點，
  沿用其主機、連接埠與 API 金鑰，並透過 API 驗證 MAC 與 Bridge Protocol v2 簽章，不送出任何
  Modbus 封包。失敗時會指出原因：缺少掃描元件、Bridge Protocol 不符、身分不符、認證或連線。
  之後每次連線都會重新讀取該 ESPHome 項目的主機、連接埠與金鑰，所以 IP 變更或金鑰
  更換後不需重新加入。
- **手動新增 Gateway**（進階）：輸入主機、MAC 與 API 金鑰，檢查相同。可選 Bridge Protocol v2，
  或尚未重刷節點用的 Bridge Protocol v1。
- **目前只用模擬 Gateway。**

**重新設定**可新增、更新（取得新的主機或金鑰）或移除 Gateway，數量不限。
**重新認證**一次驗證一個 Gateway。已儲存的金鑰不會顯示。

## 3. 使用側邊欄

開啟 **Modbus Scanner**（`mdi:radar`，路徑 `/woow-esphome-modbus-scanner`），所有 HA
使用者都看得到。更新後請強制重新整理瀏覽器。

1. 選擇 Gateway；若 Gateway 有多條 Bus，再選 Bus（會顯示其序列參數）。
2. 選擇 Device Profile。它的預設值會填入表單，其限制與 Gateway 限制取交集後約束
   每個欄位。
3. 檢查 Gateway，讓 Pausable Poller 卡片依名稱與站號列出每個輪詢元件。預設全部
   勾選；選擇依 Bus 儲存。
4. 確認盡力而為警告（超過 32 個站號另需確認 Large Range），按 **Start scan**；
   或用 **Test address** 測單一站號。

面板每秒不重疊地輪詢一次狀態，結束時載入結果，顯示 Scan Lease 狀態與值已過時的
暫停設備，並列出 Responder 的原始值（十進位與十六進位）；Device Profile 有定義
欄位時，另顯示帶單位的解碼值。每筆結果都標明其 Gateway、Bus 與 Device Profile。

## Device Profile

Device Profile 是 `schema_version` 1 的 JSON 文件，以 `list_device_profiles`、
`import_device_profile`、`export_device_profile`、`delete_device_profile` 或側邊欄的
Device Profile 卡片管理。匯入的 profile 存在 HA storage，會納入 HA 備份。匯入相同
`id` 會取代舊的。無效文件會被拒絕，並逐欄列出錯誤。內建 `generic` profile 不能刪除；
執行中 Scan 正在使用的 profile 要等該 Scan 結束才能刪除，已完成的結果保留當時的
profile 名稱。

| 鍵 | 必要 | 意義 |
|---|---|---|
| `schema_version` | 是 | `1` |
| `id` | 是 | 1–64 個 `a-z 0-9 _ -`，以字母或數字開頭；`generic` 保留 |
| `name`、`vendor`、`model` | 是 | 非空文字，最多 64 字元 |
| `version` | 是 | 非空文字，最多 32 字元 |
| `function_codes` | 是 | 由 `3`（保持）與 `4`（輸入）組成的非空清單；寫入功能碼一律拒絕 |
| `defaults` | 否 | `slave_start` + `slave_end`（須同時提供）、`function_code`、`register`、`count`（1–4）、`timeout_ms`（100–2000）、`inter_request_delay_ms`、`retries` |
| `allowed_registers` | 否 | 最多 1024 個暫存器位址；有設定時只能讀取這些 |
| `fields` | 否 | 最多 256 個 `{register, name, unit?, scale?, data_type?}`；`data_type` 為 `u16`（預設）或 `s16`，`scale` 為有限非零數字 |

完整範例為
[`examples/device_profiles/guanjie-ind17.json`](examples/device_profiles/guanjie-ind17.json)，
是一份有暫存器允許清單、具名欄位的 FC03 對照表。可在側邊欄匯入，或使用：

```yaml
action: woow_esphome_modbus_scanner.import_device_profile
data:
  profile: >-
    {"schema_version": 1, "id": "my-meter", "name": "My meter", "vendor": "Acme",
     "model": "M1", "version": "1", "function_codes": [4],
     "defaults": {"function_code": 4, "register": 0, "count": 2},
     "fields": [{"register": 0, "name": "Voltage", "unit": "V", "scale": 0.1}]}
```

## Pausable Poller 與 Scan Lease

Scan 會暫停你在該 Bus 選定的 Pausable Poller，避免其流量與 Probe 交錯。可用
`set_pausable_pollers`（或側邊欄勾選清單）依 Bus 儲存選擇，或在單次 Scan 傳入
`pause_pollers`（`check_gateway` 列出的索引清單）。空清單表示不暫停任何元件。
韌體已不存在的輪詢元件會被移除並回報於 `removed_pollers`，絕不會送出。

暫停是由 Gateway 持有的 Scan Lease，不是由 Home Assistant 持有：

- 從 Scan 的第一個 Probe 開始；選定的輪詢元件停止，hub 中這些站號排隊的封包會被清除；
- Scan 完成、取消或失敗時，HA 釋放 lease；
- 若 HA 或連線消失，Gateway 在 **5 秒**沒有 Probe 後自行結束 lease，且無論如何在
  **10 分鐘**後結束（更長的 Scan 後續 Probe 不再暫停）。Bridge Protocol v2 的位址間隔上限為
  3000 ms，所以 Scan 自己的間隔不會達到閒置時間；
- 每一種結束方式，Gateway 都會恢復輪詢元件。

需要預先考量兩點：清除暫停元件的佇列，也會丟掉它待送的寫入（Scan 期間請勿調整
暫停設備的設定）；lease 結束後，恢復的輪詢元件第一次取得新讀值，最多可能要等它的
一個 `update_interval`。Scan 狀態會回報 `lease_status`（`none`、`active`、`ended`、
`unconfirmed`）與 `lease_end_reason`（`released`、`idle`、`hard_limit`、`superseded`）。

**多條 Bus：**同一 Gateway 不同 Bus 的 Scan 可同時進行，每條 Bus 一次一個 Scan。
目前版本的 `modbus_scanner` 元件會為每條 Bus 自動建立自己的結果與 lease 感測器
（`Modbus Scanner v2 Result <bus>`、`Modbus Scanner v2 Lease <bus>`；重刷 Gateway
即可，YAML 不用改）。此時每條 Bus 各有自己在途的 Probe，Scan 只等自己的
`inter_request_delay_ms`；`check_gateway` 會回報 `health.probe_slots: per_bus`
（ADR 0010）。

沒有這些感測器的 firmware 會改用 Shared-slot fallback：所有 Bus 的 Probe 輪流送出，所以每個
Gateway 一次只有一個 Probe 在途：所有 Bus 共用
節點的結果感測器，否則 ESPHome API 可能丟掉同時發布的兩筆結果之一。因此一個 Scan
在兩個 Probe 之間，要等自己的 `inter_request_delay_ms`，再加上同一 Gateway 每個其他
執行中 Scan 的一個 Probe（`timeout_ms` + 約 300 ms）。若任何會暫停 Normal Polling 的
Scan 這段等待會超過 3000 ms，新的 Scan 會在開始時被拒絕，因為更長的間隔可能讓它的
Scan Lease 因閒置而結束。預設值（間隔 100 ms、逾時 1000 ms）下可同時掃描三條 Bus；
要再多，請調低 `timeout_ms` 或 `inter_request_delay_ms`，或等其他 Scan 結束。

## 公開動作

Domain 為 `woow_esphome_modbus_scanner`。所有動作開放給每位啟用中的使用者（實體操作
需啟用中的使用者或內部自動化）。

| 動作 | 用途 |
|---|---|
| `list_gateways` | 列出 Gateway：provider、Bus、限制（`probes_take_turns`：各 Bus 是否輪流使用同一個 Probe Slot）、健康狀態、Pausable Poller 清單、`running_buses`（目前正在 Scan 的 Bus）與 `can_operate` |
| `check_gateway` | 驗證一個 Gateway 的 MAC 與 Bridge Protocol 簽章並讀取其 Bus 與輪詢元件，不送 Modbus 封包 |
| `set_pausable_pollers` | 儲存一條 Bus 的 Scan 要暫停哪些 Pausable Poller（`gateway_id`、`bus`、`pause_pollers`） |
| `start_scan` | 開始範圍 Scan，立即回傳 `scan_id` |
| `test_address` | 掃描單一站號（`address`）；隱含範圍確認 |
| `get_scan_status` | 進度、階段、lease 狀態、錯誤與恢復證據 |
| `get_scan_results` | Responder 證據，含原始值與解碼值 |
| `cancel_scan` | 合作式取消；已在線上的封包會先完成 |
| `get_history` | 最多 20 筆終態快照，存在 HA storage、重新啟動後仍在；中斷的 Scan 記為失敗，絕不重跑 |
| `list_device_profiles` | Generic 與匯入的 Device Profile 及其限制 |
| `import_device_profile` | 驗證並儲存 Device Profile（`profile`：物件或 JSON 文字） |
| `export_device_profile` | 回傳一個 profile 可再匯入的文件（`profile_id`） |
| `delete_device_profile` | 刪除匯入的 profile（`profile_id`） |

`start_scan` 的欄位（`test_address` 改用 `address` 取代範圍，且不需確認）。省略的欄位
先取 Device Profile 預設值，再取 Gateway 預設值；下表為 Bridge Protocol v2 Gateway 的預設值
（模擬 Gateway 預設為 `holding_register`、500 ms、重試 1 次、不暫停）：

| 欄位 | 預設 | 說明 |
|---|---|---|
| `provider` | `mock` | `mock` 或 `esphome` |
| `gateway_id` | `mock:rs485-gateway` | 取自 `list_gateways`，例如 `esphome:aabbccddeeff` |
| `bus` | — | Gateway 有多條 Bus 時必填 |
| `esphome_device_id` | — | 選用；與 HA ESPHome 裝置的 MAC 再交叉核對 |
| `device_profile_id` | `generic` | 其預設值填入省略欄位；其限制與 Gateway 限制同時適用 |
| `start_id`、`end_id` | profile 預設 | 1–247；profile 未定義站號範圍時必填 |
| `probe_type` | `holding_register` | `holding_register`（FC03）或 `input_register`（FC04） |
| `register_address`、`register_count` | 0、1 | Bridge Protocol v2 數量 1–4；區塊結尾不得超過 65535 |
| `timeout_ms` | 1000 | Bridge Protocol v2 為 100–2000，在 Gateway 上逐個 Probe 套用 |
| `retries`、`inter_request_delay_ms` | 0、100 | 逾時後重試 0–5 次；Bridge Protocol v2 位址間隔 0–3000 ms（低於 lease 的 5 秒閒置時間），Legacy Gateway 為 0–5000 ms |
| `pause_normal_polling` | `true` | `false` 表示掃描時不暫停任何元件 |
| `pause_pollers` | 已儲存的選擇 | 僅用於本次 Scan 的 Pausable Poller 索引 |
| `mock_scenario` | `found_default` | 僅限模擬 provider |
| `safety_confirmed` | 必填 | 必須恰為 `true` |
| `large_range_confirmed` | — | 範圍超過 32 個站號時必須恰為 `true` |

範例：在一條 Bus 上實際掃描站號 1–10：

```yaml
action: woow_esphome_modbus_scanner.start_scan
data:
  provider: esphome
  gateway_id: esphome:aabbccddeeff   # 取自 list_gateways
  bus: rs485
  start_id: 1
  end_id: 10
  probe_type: holding_register
  register_address: 0
  register_count: 1
  safety_confirmed: true
response_variable: started
```

以回傳的 `scan_id` 呼叫 `get_scan_status` 與 `get_scan_results`。每條 Bus 同時只能有一個
Scan；第二個會因 busy 被拒絕。

## 模擬 provider

`provider: mock` 不需硬體，也不開任何連線。提供 `mock:rs485-gateway`（一條 Bus）與
`mock:multi-bus-gateway`（Bus `rs485_a` 與 `rs485_b`）。`mock_scenario` 選擇一組固定結果：
`found_default`、`all_offline`、`partial_timeout`、`modbus_exception`、
`possible_collision`、`gateway_disconnect`。模擬的暫存器讀取會對 FC03／FC04 回傳原始值。
舊欄位名稱 `mock_profile` 仍可作為**已棄用**的別名；兩者同時傳入會被拒絕。

```yaml
action: woow_esphome_modbus_scanner.start_scan
data:
  provider: mock
  gateway_id: mock:rs485-gateway
  start_id: 1
  end_id: 12
  mock_scenario: found_default
  safety_confirmed: true
response_variable: started
```

## Legacy Gateway（Bridge Protocol v1）

0.5.0 之前登錄、仍執行廠牌專用 Bridge Protocol v1 韌體的 Gateway 可繼續使用，但維持其凍結的
限制（站號 1–32、FC03、數量 1、一個允許清單內的暫存器、700 ms、必須暫停輪詢、不支援
`bus`）。每個這類 Gateway 都會產生 **Repairs** 警告。遷移方式：依上文在節點 YAML 加入
`modbus_scanner` 並重刷，開啟整合的**重新設定**，對該節點選擇「從 ESPHome 裝置新增或
更新 Gateway」（或手動選項並選 Bridge Protocol v2）；若需要舊的暫存器對照表，再匯入範例
Device Profile。Gateway 以 Bridge Protocol v2 登錄後，Repairs 問題會自動消失。Legacy 支援將在
未來版本移除。

## 開發

```bash
uv venv --python 3.14
uv pip install -r requirements-test.txt
ruff check .
pytest --cov=custom_components/woow_esphome_modbus_scanner \
  --cov-report=term-missing --cov-fail-under=90
g++ -std=c++20 -Wall -Wextra -Werror firmware/tests/scanner_core_test.cpp -o /tmp/scanner-core
/tmp/scanner-core custom_components/woow_esphome_modbus_scanner/modbus_scan/bridge_v2/contract.json
cd panel_frontend && npm ci --include=dev && npm test && npm run check:drift
npx playwright install chromium && npm run test:browser
cd .. && node tests/tutorial/browser_check.mjs
```

CI（`.github/workflows/ci.yml`）另以 ESPHome 2026.9.0 驗證並編譯兩個韌體範例，並確認
ESPHome 2026.8.2 會拒絕它們。Home Assistant 測試框架無法在 Windows 執行，請用 Linux、
WSL 或 Docker。[`tests/live/README.md`](tests/live/README.md) 說明選用的 REST 冒煙測試，
只對執行中的 HA 呼叫模擬 provider。

## 歷史

本專案起初是僅限模擬的教學版，之後加入為單一廠牌設備打造的實體橋接。以下歷史僅供
參考，不代表目前設計。

- **0.1.0／0.2.0（僅限 MOCK 模擬）：**以 provider 為邊界的模擬掃描與側邊欄。模擬版
  教學仍可取得：
  [檢視 v0.2.0 原始檔](https://github.com/WOOWTECH/Woow_ha_esphome_modbus_scanner/blob/main/docs/tutorial/woow-esphome-modbus-scanner-v0.2.0-zh-TW.html) ·
  [Raw v0.2.0 HTML](https://raw.githubusercontent.com/WOOWTECH/Woow_ha_esphome_modbus_scanner/main/docs/tutorial/woow-esphome-modbus-scanner-v0.2.0-zh-TW.html) ·
  [在 GitHub 檢視原始檔（v0.1.0）](https://github.com/WOOWTECH/Woow_ha_esphome_modbus_scanner/blob/main/docs/tutorial/woow-esphome-modbus-scanner-v0.1.0-zh-TW.html) ·
  [下載 v0.1.0 教學 HTML release asset](https://github.com/WOOWTECH/Woow_ha_esphome_modbus_scanner/releases/download/v0.1.0/woow-esphome-modbus-scanner-v0.1.0-zh-TW.html) ·
  [Raw v0.1.0 HTML](https://raw.githubusercontent.com/WOOWTECH/Woow_ha_esphome_modbus_scanner/main/docs/tutorial/woow-esphome-modbus-scanner-v0.1.0-zh-TW.html) ·
  [下載 v0.1.0 原始碼封存檔](https://github.com/WOOWTECH/Woow_ha_esphome_modbus_scanner/archive/refs/tags/v0.1.0.zip)。
  這些教學只描述模擬行為，不是 ESPHome 韌體。
- **0.3.0.dev1–0.3.0.dev3：**為冠傑（Guanjie）IN-D17 打造的實驗性 FC03 橋接
  （站號 1–32、13 個允許暫存器、700 ms），見
  [ADR 0004](docs/adr/0004-experimental-guanjie-fc03-bridge.md)（已由 ADR 0005 取代）、
  [首次實機驗收](docs/history/guanjie-live-acceptance.md)、
  [雙節點驗證](docs/history/dual-node-live-acceptance.md)與
  [介面復驗 124/124](docs/history/ui-reacceptance.md)。
- **0.4.0.dev1（最後部署版本）：**加密 API 金鑰、韌體健康狀態與 watchdog、輪詢恢復驗證、
  持久化歷史、診斷、Repairs 與重新認證，部署於兩個節點。見
  [實測驗收](docs/history/hardening-live-acceptance.md)、
  [升級與回復](docs/history/hardening-upgrade-rollback.md)、
  [軟體檢查點](docs/history/hardening-software-checkpoint.md)與
  [實作階段](docs/history/implementation-phases.md)。
  其韌體 `firmware/guanjie-scanner/` 執行 Bridge Protocol v1，會保留到這些節點重刷為止。
- 較早的設計筆記：[0.2.0 動作與安全模型](docs/history/service-and-safety-model.md)、
  [0.2.0 測試策略](docs/history/testing.md)。以上文件都在 `docs/history/`。

## 授權

MIT，見 [LICENSE](LICENSE)。
