# #16 實機驗收操作清單

驗收項目與通過門檻以 #16 為準，本清單只列每一步要切的版本、燒錄與操作順序。
結果填入：

- A 段 → [`docs/history/generic-live-acceptance.md`](../history/generic-live-acceptance.md)
- B 段 → [`docs/history/per-bus-live-acceptance.md`](../history/per-bus-live-acceptance.md)

## 版本對照

| 代稱 | 版本號 | commit | 備註 |
|---|---|---|---|
| 舊版 HA ／ 舊版 fw | `0.5.0.dev1` | `38547c1`（#17） | |
| 新版 fw | `0.5.0.dev2` | `a426ddc`（#20）或 `c84e40e`（#22） | 兩者 firmware 完全相同 |
| 新版 HA | `0.5.0.dev2` | `c84e40e`（#22）或之後 | diagnostics 的 `probe_slots` 從 #21 才有；`a426ddc` 只能看 `check_gateway` 的 `health.probe_slots` |

`a426ddc` 與 `c84e40e` 的版本號都是 `0.5.0.dev2`，紀錄一律寫 commit SHA。

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

- [ ] HA 換成 `../scanner-new/custom_components/woow_esphome_modbus_scanner`，重啟 HA；裝置資訊顯示 `0.5.0.dev2`。
- [ ] 節點 X 不重燒（仍是舊版 fw）。
- [ ] B6：對 X 執行 `woow_esphome_modbus_scanner.check_gateway`（開發者工具 → 動作，勾選回傳回應），`health.probe_slots` 為 `shared_slot_fallback`；之後下載 diagnostics，`probe_slots` 也是 `shared_slot_fallback`（`check_gateway` 之前是 `null`，屬正常）。
- [ ] B6：兩條 Bus 同時 Scan 時輪流送 Probe；側邊欄顯示「預估未包含其他 Scan 的 Probe」，zh-TW 與 en 各截一次圖。
- [ ] B3 對照組：每條 Bus 先單獨 Scan、再兩條並行 Scan，記錄耗時（預期並行約慢 1.8–2 倍）。範圍、`timeout_ms`、`inter_request_delay_ms` 要和步驟 4 完全相同。
- [ ] B3 反向對照（建議）：兩條 Bus 都用 `inter_request_delay_ms` 3000、`timeout_ms` 2000 同時 Scan，確認第二個 Scan 被 `concurrent_wait_max_ms` 拒絕，記下錯誤訊息。
- [ ] 節點 Y 順便確認 `probe_slots` 為 `per_bus`。

## 步驟 4：HA 新版、X 新版、Y 新版 → B1–B5、B8

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
