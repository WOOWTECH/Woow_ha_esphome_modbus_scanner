# #16 實機驗收操作清單

> **已過時（僅供歷史參考）。** 一個 Gateway 只服務一條 Bus
> （[ADR 0011](../adr/0011-one-bus-per-gateway.md)，#26）：多 Bus、每條 Bus 的
> Result／Lease sensor、`probe_slots`（`per_bus`／`shared_slot_fallback`）與
> `concurrent_wait_max_ms` 都已移除，本清單的 B 段步驟不能再照做。目前的驗收是
> #16 C 段，見 [`docs/history/one-bus-regression.md`](../history/one-bus-regression.md)。

驗收項目與通過門檻以 #16 為準，本清單只列每一步要切的版本、燒錄與操作順序。
結果填入：

- A 段 → [`docs/history/generic-live-acceptance.md`](../history/generic-live-acceptance.md)
- B 段 → [`docs/history/per-bus-live-acceptance.md`](../history/per-bus-live-acceptance.md)

## 版本對照

| 代稱 | 版本號 | commit | 備註 |
|---|---|---|---|
| 舊版 HA ／ 舊版 fw | `0.5.0.dev1` | `38547c1`（#17） | |
| 新版 fw | `0.5.0.dev2` | `a426ddc`（#20）或 `c84e40e`（#22） | 兩者 firmware 完全相同 |
| 新版 HA | `0.5.0.dev2` | `c84e40e`（#22）或之後 | （已移除，見 ADR 0011）diagnostics 的 `probe_slots` 從 #21 才有；`a426ddc` 只能看 `check_gateway` 的 `health.probe_slots` |

`a426ddc` 與 `c84e40e` 的版本號都是 `0.5.0.dev2`，紀錄一律寫 commit SHA。

## 測試台版本（本輪）

本輪沒有實體 Modbus 設備，只有兩台 **單 Bus** Gateway 和兩個 USB-to-RS-485 轉換器。
設備由電腦上的模擬器扮演；需要同一 Gateway 兩條實體 Bus 的項目延後。下面各步驟以本節為準，
與後面原步驟衝突時照本節做。

### 0b. 測試台

接線（整輪不換接）：

| 轉換器 | 接到 | 模擬器 line | 回應的站號 |
|---|---|---|---|
| A | Gateway X 的 RS-485（A–A、B–B，建議共地） | `X` | 1（Poller）、10、17 |
| B | Gateway Y 的 RS-485 | `Y` | 1（Poller）、20、33 |

- Gateway 板子同 `guanjie-ind17`：UART TX GPIO32、RX GPIO35、DE/RE GPIO33，9600 8N1。
- 站號 10、17、20、33 的 register 0（holding 與 input）回 `0xA0nn`／`0xB0nn`（nn 為站號十六進位），
  從 HA 的原始值就看得出是哪台 Gateway 的哪個站號。站號 1 的 holding 0x0000 每讀一次加一，
  是 Pausable Poller 的讀取目標；log 裡它的讀取中斷就是暫停，重新出現就是恢復。
- 模擬器（需要 `pyserial`）：

  ```bash
  python tools/rtu_bench_simulator.py tools/bench_profiles/bench.json       --port X=COMa --port Y=COMb --log bench-$(date +%Y%m%d).log
  ```

  每個請求一行 JSON（時間戳、line、站號、FC、位址、結果）。未設定的站號不回應（`silent`）。
  整輪保持執行，log 作為 A2、A2'、B7 的證據。
- Gateway YAML：`tools/bench_profiles/gateway-x.yaml`、`gateway-y.yaml`。同一份檔案在步驟 1 與
  步驟 4 都不修改，只換指令列的 substitution（路徑相對於 YAML 所在目錄）：

  ```bash
  cd tools/bench_profiles
  # 舊版元件（步驟 1）
  esphome -s components_path ../../../scanner-old/firmware/components -s fw_version 0.5.0.dev1 run gateway-x.yaml
  # 新版元件（步驟 4）
  esphome -s components_path ../../../scanner-new/firmware/components -s fw_version 0.5.0.dev2 run gateway-x.yaml
  ```

  燒錄注意（2026-11-09 實測）：
  - 測試台 Gateway 的 FTDI USB 沒接自動重置：USB 燒錄前手動按住 BOOT、按一下 EN、放開 BOOT，
    esptool 加 `--before no-reset`；燒完要再按一次 EN，新韌體才會開始跑。
  - v1 冠傑元件只接受 ESPHome 2026.9.0；通用元件用 2026.10.0（需 Python ≥ 3.12）。
  - repo 路徑含中文且很深，編譯前設 `ESPHOME_DATA_DIR` 到短的英文路徑，否則 esp-idf 解壓失敗。
  - 步驟 1 從 v1（Arduino）換到 `gateway-x/y.yaml`（esp-idf）要用 USB 燒 `firmware.factory.bin`，
    不要 OTA（分割表可能不同）。步驟 2、4 兩邊都是 esp-idf，可以 OTA。
  - A2' 要讓 HA 突然消失：`homeassistant.restart` 會先取消 Scan 並釋放 lease，驗不到 Gateway 自己恢復；
    改拔 .28 的區網線（不要拔 `enp2s0`）。
  - 插拔 USB 可能讓模擬器某條 line 停止（不會自動重開 port），插拔後確認 log 兩條 line 都還有流量。

  `secrets.yaml` 放在 `tools/bench_profiles/`（已被 `.gitignore` 排除），需要 `wifi_ssid`、
  `wifi_password`、`api_encryption_key_x`、`api_encryption_key_y`。每次燒錄前記下
  `git hash-object gateway-x.yaml`，作為 B1「YAML 未修改」的證明。

### 本輪各步驟

| 步驟 | 做什麼 | 測項 |
|---|---|---|
| 0 | 舊版 HA；X、Y 燒 v1 冠傑韌體（`../scanner-old/firmware/guanjie-scanner/guanjie-ind17.yaml`，在同一目錄各複製一份並改 `name`，secrets 需要 `scanner_api_key`、`guanjie_ota_password`，Wi-Fi 經 captive portal 設定），註冊到 HA | A0：Repairs 出現 Legacy Gateway 提示 |
| 1 | X、Y 改燒 `gateway-x/y.yaml`（舊版元件） | A1、A2、A2'、A3（註明以模擬器代替）、多 Gateway（X、Y 同時 Scan） |
| 2 | 只重燒 Y（新版元件） | B7 |
| 3 | HA 升新版；X 不動 | B6 只驗模式：X 為 `shared_slot_fallback`，Y 為 `per_bus`（已移除，見 ADR 0011） |
| 4 | 重燒 X（新版元件，YAML 不改） | B1（單 Bus 部分）、B1a |

延後（需同一 Gateway 兩條實體 Bus）：B1 多 Bus、B2–B5、B3 對照組與反向對照、B6 輪流送 Probe
與側邊欄提示、B8。A3 的實體非冠傑設備補驗也延後。這些在 #16 另列，#16 維持開啟。

## 0. 事前準備

- [ ] 備份 HA（含 `.storage`），並記下兩台節點目前的 YAML 與 firmware 版本。
- [ ] 確認節點 X 接了兩條實體 RS-485 Bus，每條至少一台會回應的設備，且至少一條有 Pausable Poller。
- [ ] 確認非冠傑設備型號、站號、鮑率／parity／stop bits，並填入兩份紀錄的「設備」表。
- [ ] 在 repo 外準備兩份 worktree，避免來回 checkout 時燒錯版本：

  ```bash
  git fetch origin
  git worktree add ../scanner-old 38547c1
  git worktree add ../scanner-new c84e40e
  ```

  節點實際使用的 YAML 若以 `type: local` 引用元件，把 `path` 指到對應 worktree 的
  `firmware/components`；YAML 本身不要改其他內容（B1 要求不修改即可編譯）。

## 步驟 1：HA 舊版、X 舊版、Y 舊版 → A 段

- [ ] HA 安裝 `../scanner-old/custom_components/woow_esphome_modbus_scanner`，重啟 HA；裝置資訊顯示 `0.5.0.dev1`。
- [ ] 節點 X、Y 以 `../scanner-old` 的元件編譯、重燒。
- [ ] A1：兩台 Repairs 提示消失、可正常 Scan。
- [ ] A2：Scan 後 Normal Polling 恢復。
- [ ] A2 中斷情境：Scan 跑到一半停掉 HA，等 **超過 5 s**（建議 ≥ 15 s）再啟動，確認 Normal Polling 已由 Gateway 自己恢復（看 HA log 時間戳與 Poller 實際讀值）。
- [ ] A3：非冠傑設備以 Generic Device Profile 被找到並顯示原始值。
- [ ] 每台記下 `check_gateway` 回應、diagnostics JSON（去金鑰）、相關 log。
- [ ] 寫入 `generic-live-acceptance.md`，並註明可開始移除 bridge v1 相容碼。A 段到此結束，不必等 B 段。

## 步驟 2：HA 舊版、X 舊版、Y 新版 → B7

- [ ] 只重燒節點 Y，改用 `../scanner-new` 的元件。HA 不動。
- [ ] B7：節點 Y 正常 Scan（舊 HA 讀共用 sensor 的鏡像），勾選 pause_pollers 時 Pausable Poller 有暫停，Scan 結束後恢復。
- [ ] 節點 Y 只接一條 Bus 就夠；要在多 Bus 驗 B7，Y 也要接兩條 Bus。

## 步驟 3：HA 新版、X 舊版、Y 新版 → B6 + B3 對照組

> **已過時。** 本步驟驗的 `probe_slots`、`per_bus`／`shared_slot_fallback`、每條 Bus 的
> sensor 與 `concurrent_wait_max_ms` 已由 [ADR 0011](../adr/0011-one-bus-per-gateway.md)
> 移除，不要再照做；改看 #16 C 段
> （[`docs/history/one-bus-regression.md`](../history/one-bus-regression.md)）。

- [ ] HA 換成 `../scanner-new/custom_components/woow_esphome_modbus_scanner`，重啟 HA；裝置資訊顯示 `0.5.0.dev2`。
- [ ] 節點 X 不重燒（仍是舊版 fw）。
- [ ] B6：對 X 執行 `woow_esphome_modbus_scanner.check_gateway`（開發者工具 → 動作，勾選回傳回應），`health.probe_slots` 為 `shared_slot_fallback`；之後下載 diagnostics，`probe_slots` 也是 `shared_slot_fallback`（`check_gateway` 之前是 `null`，屬正常）。
- [ ] B6：兩條 Bus 同時 Scan 時輪流送 Probe；側邊欄顯示「預估未包含其他 Scan 的 Probe」，zh-TW 與 en 各截一次圖。
- [ ] B3 對照組：每條 Bus 先單獨 Scan、再兩條並行 Scan，記錄耗時（預期並行約慢 1.8–2 倍）。範圍、`timeout_ms`、`inter_request_delay_ms` 要和步驟 4 完全相同。
- [ ] B3 反向對照（建議）：兩條 Bus 都用 `inter_request_delay_ms` 3000、`timeout_ms` 2000 同時 Scan，確認第二個 Scan 被 `concurrent_wait_max_ms` 拒絕，記下錯誤訊息。
- [ ] 節點 Y 順便確認 `probe_slots` 為 `per_bus`。

## 步驟 4：HA 新版、X 新版、Y 新版 → B1–B5、B8

> **已過時。** 本步驟驗的 `probe_slots`、`per_bus`／`shared_slot_fallback`、每條 Bus 的
> sensor 與 `concurrent_wait_max_ms` 已由 [ADR 0011](../adr/0011-one-bus-per-gateway.md)
> 移除，不要再照做；改看 #16 C 段
> （[`docs/history/one-bus-regression.md`](../history/one-bus-regression.md)）。

- [ ] B1：節點 X **實際使用中** 的多 Bus YAML 不修改，用 `../scanner-new` 的元件編譯、重燒；HA 有每條 Bus 的 `Modbus Scanner v2 Result <bus>` 與 `Modbus Scanner v2 Lease <bus>`，共用的 Info／Result／Lease sensor 仍在；裝置資訊顯示 `0.5.0.dev2`。
- [ ] B1a：**先** 對 X 執行 `check_gateway`，確認 `health.probe_slots` 為 `per_bus`，再下載 diagnostics 記錄。沒做這步不要往下。
- [ ] B2：兩條 Bus 各自單獨 Scan，再同時 Scan；並行時的 Responder 清單與單獨時一致，沒有遺失或串到另一條 Bus。
- [ ] B3：用與步驟 3 相同的設定量單獨／並行耗時；每條 Bus 都要符合並行 ≤ 單獨 × 1.2。再用 3000／2000 的設定確認能開始 Scan（步驟 3 是被拒絕）。
- [ ] B4：兩個並行 Scan 都勾 pause_pollers；用 B3 的每個 Probe 平均耗時回推位址範圍，讓兩個 Scan 幾乎同時結束。每條 Bus 只暫停自己的 Poller，兩則 lease 結束訊息都到 HA，兩條 Bus 的 Normal Polling 都恢復。
- [ ] B5：一條 Bus 掃沒有設備的範圍，`timeout_ms` 2000、`inter_request_delay_ms` 3000，總時間明顯超過 5 s；另一條 Bus 同時 Scan，其 Scan Lease 不因 idle 結束，Scan 正常完成。
- [ ] B8：對照 `docs/tutorial/woow-esphome-modbus-scanner-v0.5.0-zh-TW.html` 的「獨立 vs 輪流」描述與實機觀察；不符處回報到 #18 或開新 issue。
- [ ] 寫入 `per-bus-live-acceptance.md`。

## 收尾

- [ ] 移除暫用 worktree：`git worktree remove ../scanner-old`、`git worktree remove ../scanner-new`。
- [ ] 確認兩份紀錄沒有 API 金鑰、Wi-Fi 密碼或其他私密資訊，再開 PR 並勾選 #16 的驗收項目。
