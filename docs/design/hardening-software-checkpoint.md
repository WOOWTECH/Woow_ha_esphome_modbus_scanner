# 0.4.0.dev1：離線實作檢查點（歷史紀錄）

> 以下保留的是部署前狀態，不代表目前狀態。後續已依使用者決定採全使用者／
> 既有自動化開放政策並部署兩台裝置；請以[實測驗收](hardening-live-acceptance.md)為準。

## 狀態

三階段**尚未全部完成**。工作樹已有核心實作，但沒有更新正式 HA、
沒有 OTA、沒有遷移任何真實金鑰，也沒有執行新的實機 Modbus 交易。
已驗收部署基線仍是 0.3.0.dev3；本次不宣稱重新確認兩台設備目前的健康。

## 已接上的程式

- 共用版本化 profile 及 Python／JS／C++ 生成物，CI 檢查漂移。
  v1 硬體限制與正常控制暫存器排列另有不可任意擴張的生成檢查。
- 背景 polling freshness 與歷史控制結果分離；optional 資料恢復後不再留下
  永久 stale 訊息。掃描 watchdog 也不覆寫歷史控制結果。
- 實機服務省略參數時採用合法 FC03 預設，明確不支援的參數仍拒絕。
- API 身分／橋接檢查、PSK 傳遞、結構化錯誤、分階段進度與操作預算。
  關閉連線有期限及強制關閉後備路徑；不以 cleanup 例外蓋掉主要錯誤。
- 韌體健康快照使用新 nonce、profile hash、boot ID、poll sequence、uptime、
  核心資料 age、作用中／目標位址。復原成功必須觀察到快照基線之後的
  新核心輪詢資料；舊 v1 無健康快照時保持 unknown，不假稱 verified。
- 10 秒 scanner watchdog 是 fail-closed 保護：傳輸狀態不明時封鎖後續操作，
  經 cooldown 恢復 hub 位址，但不謊稱正常 polling 已恢復；須人工維護。
- 去識別 HA diagnostics、可處理的 Repairs、認證失敗的 reauth、最多 20 筆
  終止快照及中斷檢查點。歷程絕不自動重播；啟動檢查點採延遲保存，
  突然斷電前最後一秒的 checkpoint 不保證落盤。
- 面板能力／權限阻擋、API-only 檢查、復原／清理狀態、保存歷程、合法
  服務 YAML，以及省略識別與自由文字的數值證據 JSON 匯出。
- 金鑰表單不顯示既有值；相同 MAC 留空保留，清除必須明確勾選。

## 已執行的軟體驗證

| 驗證層 | 結果 | 不代表甚麼 |
|---|---|---|
| 隔離 HA 2026.7.2 / Python 3.14.7 pytest | **180 通過**；statement coverage **90.45%** | 不是正式 HA UI 或實機驗收 |
| 前端資料模型 | **15 通過** | 不是瀏覽器／實機連線證據 |
| 模擬 HA 的 Chromium 瀏覽器回歸 | 通過；含新增能力與唯讀權限阻擋、API-only、YAML、歷程 | 使用合成服務回覆，不是真正 HA 登入 |
| aioesphomeapi 45.3.1 standalone provider suite | **12 通過** | fake transport；與其他測試可能有功能重疊，不加總成實機案例 |
| portable C++17 + UBSan | scanner state machine、freshness／控制結果保留、poll sequence、watchdog／rollover 通過 | 尚未完成 ESPHome 原生韌體編譯／連結，更沒有 OTA |
| Ruff、profile drift、前端 bundle drift | 通過 | 不等於部署驗收 |

權限測試使用隔離 HA 裡建立的 owner、admin、一般與停用使用者，以及
有／無 context 的服務呼叫。它證明此整合的 handler 判斷；不是正式環境
非管理員登入或原生 ESPHome 服務權限驗收。

測試保留第一次失敗與重跑記錄。修正包含舊版 six-service/mock-only 測試
契約、測試 HA 依賴範圍、首次建立使用者會成為 owner 的 fixture 行為、
缺少 capability／permission 的舊瀏覽器 fixture，以及測試自身的 await／
預設值取得錯誤。沒有把失敗改名為實機成功。

## 下一階段門檻

1. **先確認授權政策與範圍**，見 [authorization-boundary.md](authorization-boundary.md)。
   現有 native ESPHome v1 probe action 沒有逐次簽章；只擋本整合服務不能宣稱
   所有原生呼叫路徑都受同一管理員政策保護。若要求設備端不可繞過，須先設計、
   實作及驗收新協定，不可只隱藏按鈕。
2. 尚需完整命令時間資訊／有限事件時間軸等收尾，以及更多失敗注入與重啟情境。
3. 編譯真實、各自保留差異的兩份韌體，尤其裝置 1 UART GPIO33 修復。
4. 完成正式 HA UI、非管理員實際存取、兩台復原證據驗收，再進行逐台 PSK 遷移。
5. 長時間運轉、破壞性硬體故障及設備重設仍未測試／執行。

上述部署門檻未通過前，不將此檢查點稱為三階段完成，也不發布正式版。
