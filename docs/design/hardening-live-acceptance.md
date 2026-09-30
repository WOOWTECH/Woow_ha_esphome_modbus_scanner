# 三階段 hardening 實作與實機驗收

日期：2026-09-30。分支：`feature/esphome-guanjie-readonly-bridge`。
部署：HA 整合 `0.4.0.dev1`／前端 `0.4.0-dev.1`；兩台裝置皆為
ESPHome 2026.9.0 原生編譯、各自設定的加密韌體。這仍是實驗分支，不是上游正式版。

## 結果與授權

A／B／C 的功能實作及本報告列出的目標驗收已完成。依使用者決定，
**所有啟用中的 HA 使用者與既有內部自動化都可操作**，沒有管理員限定或
自動化 opt-in。設定／金鑰管理仍遵守 HA 自身的管理權限。

先部署 HA 支援並確認舊韌體相容，再以裝置 2 做 canary；13 個暫存器、
1–32、取消、加密、正常輪詢復原通過後，才對裝置 1 做 application-only OTA。
原生 HA ESPHome 與 Scanner 的兩份金鑰均已同步。裝置 1 的 UART GPIO33
修復、`diagnostic_read_only: false`、既有控制及兩台各自設定均保留。

## 可核對的驗收範圍

| 層級／項目 | 結果 |
|---|---:|
| 隔離 HA 2026.7.2 framework | 195 passed；statement coverage 90.35% |
| 前端 model | 15 passed |
| 模擬 HA Chromium regression | 通過；不當作實機證據 |
| 獨立 fake-provider | 12 passed；aioesphomeapi 45.3.1 |
| Portable C++17／UBSan | scanner 與 hardening 皆通過 |
| 原生 ESPHome 編譯／連結 | 兩台 device-specific 專案皆成功 |
| 兩台 canary／遷移驗收 | 30/30：各 13 暫存器、1–32、取消與新正常輪詢 |
| 實際 HA 欄位／安全拒絕 | 65/65；這些是拒絕檢查，不是 65 次 RTU 成功 |
| 同時掃描／互斥／重試／延遲 | 11/11 |
| 裝置對應、reload、Core restart、歷程 | 19/19；含以 mock jobs 測 20 筆容量上限 |
| 真正帳密登入的 HA UI／WebSocket | 36/36：一般、唯讀群組、管理員各 12 |
| 最終兩台 HA UI／WebSocket 回歸 | 8/8；此組使用 Supervisor 系統身分 |
| 真實錯誤／缺少金鑰、錯 MAC、正確連線 | 8/8；API-only，沒有假裝 RTU 測試 |
| 真實 Repairs／重新認證 | 7/7 |
| API client 中途斷線 | 兩台皆通過；MCU 完成一次讀取並恢復新正常輪詢 |
| 真實 context-free automation | 通過，觀察到 scanner call 的 `context.user_id == null` |

以上實際 HA／裝置／UI 檢查合計 **187 個通過判定**，其中包含拒絕檢查、
API-only、UI 與 mock 歷程容量項目，**不是 187 次實體 Modbus 交易**。
一般／唯讀／管理員測試是同一暫時帳號分別切換群組後，使用全新瀏覽器
實際登入；沒有以 Supervisor token 取代該帳號。暫時帳號、憑證、自動化及
測試代理已清除；原始自動化檔已逐位元還原。

## 本次實際確認

- 全部 13 個允許的 FC03 暫存器都有 typed raw-value 證據；兩台 1–32
  掃描只有 slave 1 回應，空位址 timeout 不會冒充 ESP 離線或產生持續 Repairs。
- 新 nonce／profile hash／boot ID／core sequence／資料 age 共同驗證復原，
  不只看 busy 解除。舊韌體相容測試的 recovery 正確維持 `unknown`。
- API-only check 不更新「新匯流排回應」時間。未加密／錯誤金鑰無法使用
  已加密裝置；錯誤 MAC 在探測前拒絕，沒有退回 plaintext 或 mock。
- 真實錯誤 Scanner 金鑰會產生 Repair 與 reauth；錯誤替換不保存，正確
  替換先 API 驗證再保存；後續有效讀取清除 Repair。原生 ESPHome 金鑰未被
  此錯誤注入測試修改。
- Dedicated API socket 在讀取進行中斷線後，ESP 仍完成單次 slave 32 timeout，
  保持同一 boot ID、恢復 address 1 及新的正常輪詢。
- Reload 與 Core restart 期間，兩台工作都協作取消、驗證復原、關閉 socket，
  終止歷程保存且不自動重播；ESP 沒有因此重啟。
- 實際 HA 側欄驗證了預設參數、API-only、掃描、歷程、事件、非執行式 YAML、
  去識別 JSON 匯出與手機選單。原生 ESPHome 的 API-only status action 亦對
  三種群組開放，符合本次決定；不宣稱另有裝置層 per-user 限制。
- 新增診斷下載不包含 host、MAC、金鑰、原始回覆或使用者識別。部署檔案已
  逐檔比對 repository SHA256；兩份 HA credential consumer 與各裝置私有金鑰一致。

## 最終觀察與保留映像

兩台另完成 **600 秒連續加密 API 觀察**：沒有非預期斷線，觀察到的 Online
均為 true。期間各有兩筆掃描 slave 2／3 的預期 Modbus timeout warning，
與實際 UI 1–3 掃描一致，沒有隱藏這些紀錄。之後另做 **60 秒無掃描觀察**，
兩台 warning 均為 0，polling health 均為 `All polling data fresh`。
這是有界觀察，不是多日耐久驗證。

最終兩台 active／target address 都是 **1**，模式仍 **OFF**；目標濕度仍為
裝置 1 **53%**、裝置 2 **67%**。原生 entries 均 loaded，無待處理 reauth、
Scanner Repairs 或殘留暫時帳號／自動化。

| 私有 application image | SHA256 |
|---|---|
| 新裝置 1 | `11441a9b3a3550ae134e94a64cfb2729c96cd1f4cb27782874e96464035b3515` |
| 新裝置 2 | `3f2e5f871113db4ddf57375334b7ce8dc71fe96b6155889dc2fc164dcbcafee4` |
| 裝置 1 舊 bridge 回復映像 | `f7753e48f1e96378c50ac90826a48024c2372b2204e86ce3796940cf3ef017d4` |
| 裝置 2 舊 bridge 回復映像 | `cb4cffb9987d3750f36ffd4060e515db2a6ef5375079e7afb3009a8791106417` |

二進位與匹配的 device-specific source、secrets、相關 HA entry 備份只在私有區保留。

## 狀態／事件的界線

背景輪詢不再覆寫歷史控制結果。部署前裝置 2 同時呈現 Online 與舊的
`Stale data; awaiting poll`；部署後使用獨立 polling health，控制欄為
`No control command recorded`。本次沒有發出控制命令，因此 control-result
uptime 為 unknown 是正確的，不是漏記。其數值為 32-bit millis 的開機相對秒數，
約 49.7 天循環，不是假造 UTC。

Job 保留 UTC 起訖、最多 32 筆 elapsed phase events，UI 顯示最近 8 筆。
History 最多 20 筆；突然中斷的 start checkpoint 會標成 `INTERRUPTED`，
之後進度未知且不重播。突然斷電與損壞儲存的路徑是隔離測試，不是本次
對 HA 做斷電破壞測試。

## 發現、修正與保留的失敗

- 真實 reload 首次回歸發現 immediate task cancellation 會跳過 host recovery
  驗證，雖然 MCU 已自行恢復，紀錄只能誠實顯示 unknown。已改為最多 35 秒
  協作等待，再使用 forced cancellation，新增測試並重新部署；reload／Core
  restart 複驗通過。
- 新 stop listener 揭露兩個測試 fixture 的 class-wide shutdown monkeypatch
  範圍過大；改為 instance-only 後重跑完整測試。
- 實測 harness 初次用了錯誤的 REST flow context、reauth 額外 host 欄位、
  YAML `pre` selector，且管理用 WebSocket 閒置後失效。均保留失敗紀錄並修正；
  正確金鑰及暫時帳號清理已重新確認。這些不冒充產品缺陷或刪除失敗證據。

## 運維提醒

部署末端 HA 檔案系統約剩 **1.5 GB（使用率 95%）**。沒有擅自刪除既有資料、
編譯快取或回復映像；後續大量編譯／備份前，應另行安排容量整理。
目前 GitHub workflow 只在 main push／對 main 的 PR 觸發；本分支的驗證是
上述本機／隔離／實機結果，沒有宣稱未執行的遠端 CI 成功。

## 未做／不宣稱

沒有 FC06/FC16 scanner actions、啟動除濕機、改寫持久 slave address、
Wi-Fi reset、factory reset 或自動重播／重啟。沒有實際卡死 UART、注入
畸形串列訊框、拔電、失敗 OTA／rollback 演練或多日耐久測試。Watchdog、
wraparound、無回應 cleanup 等未在真機誘發的路徑，以 portable／fake／HA
framework 證據標示；不宣稱 HA quality-scale 認證。

[升級與回復](hardening-upgrade-rollback.md)包含私有 recovery artifacts 的操作原則。
完整去密證據位於交付工作區 `diagnostics/hardening-live/`；私有設定、PSK、
HA entry 備份及韌體二進位不在 repository 或公開報告包內。
