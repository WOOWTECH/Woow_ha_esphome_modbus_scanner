# 介面修正後的雙 ESP 復驗 — 0.3.0.dev3

本次已部署到實際 HA，兩台沿用已安裝的橋接韌體，沒有重刷 ESP。
**本輪 124 項通過、0 項失敗。** 這是介面與指定實體操作的驗收，不是安全或全硬體功能認證。

## 修復內容

1. 實體／模擬模式分開標示；不再對真機宣稱「MOCK ONLY／不接觸硬體」。
2. 真機禁用 mock 下拉選單與全部六顆情境按鈕，不傳送 mock_profile。
3. 站號限定 1–32；FC04 與識別選項禁用；數量 1、逾時 700ms 為唯讀。
   暫停輪詢固定開啟，13 個允許的 FC03 暫存器在呼叫服務前驗證。
4. 選實體閘道自動帶入 FC03、25089（0x6201）、count1、700ms、retries0、
   delay250、pause=true，預設範圍 1–3；不必手動補參數。
5. 重新整理保留 provider 與 gateway。儲存的閘道缺席時禁止讀取，不退回 mock。
6. 有效的 DOM 整數字串轉為數字後保存。以非預設值 register24833、retries2、
   delay750、end8 實際重載復測，不以剛好等於預設值的欄位掩蓋保存問題。
7. 追加發現並修復：非同步插入選項後，原生 select 的顯示可能與內部值不同。
   gateway/profile option 明確設定 selected；有永久瀏覽器回歸測試及實際 HA 復驗。

範圍確認不跨 reload 保存，必須重新勾選。切換閘道清空舊證據；歷史結果另標出
自己的 provider/gateway，不能把 mock 結果誤認成目前選擇的真機。

## 本輪矩陣

|測試組|通過|測試層|
|---|---:|---|
|只選 ESP、直接測試|2/2|HA 服務與實體回應|
|按鈕／欄位主矩陣|86/86|已部署元件、真實 HA 服務；含明列的 mock 情境|
|新增介面防護|28/28|唯讀欄位、白名單、錯誤輸入阻擋、儲存與顯示一致性|
|完整 HA 原生介面|8/8|HA frontend/WebSocket、雙機單點與 1–3、reload、手機側欄、JS 例外|

不能把 124 項全部稱為硬體交易。前輪 226 項及其 6 個失敗保留為歷史紀錄，
不把前輪未重跑的後端測試冒充本輪新證據。

### 真正 HA 原生介面

不是只有最小瀏覽器殼：另載入真正 HA frontend、原生側欄、圖示與 WebSocket
服務介面，兩台分別完成：

- 選 gateway 後直接按 Test address，站號 1 收到 FC03 回應。
- 預設 1–3 完成 3/3，站號 1 回應，2/3 逾時。
- HA 整頁 reload 後，顯示與內部選擇均仍是指定 ESP。
- 390px 手機版選單確實開啟原生 HA drawer；以開關前後座標及完成動畫截圖確認。

此測試透過 loopback-only 認證代理使用既有 Supervisor 系統帳號。
HTTP、WebSocket、HA 服務及實體回應均為真實資料，沒有建立新使用者或長效 token。
**不代表帳密登入流程或非管理員權限已驗證。** 代理只供本次測試，測後關閉。

### 測後狀態

最後原生介面操作結束後另觀察 60 秒。兩台持續 Online，正常通訊狀態分別更新
105、106 次，沒有 WARN/ERROR 日誌，目標及生效站號仍 1，控制設定未變。
韌體保留的最後 Command Result 文本仍是 `Stale data; awaiting poll`，不可單獨
當成即時健康狀態；原始紀錄沒有隱去。Scanner Result 最後的站號 3 timeout 則是
1–3 掃描的預期結果，不代表 ESP 離線。

## 使用方式與回報的 FC03 錯誤

更新後強制重新整理整個 HA 網頁（Ctrl+Shift+R）。選 ESP 後應看到
「實驗功能 — 實體 MODBUS」，按「測試位址」不需手動修改進階欄位。
範圍掃描需要勾選確認。

**既有服務 YAML 不會自動改寫。** 從 HA 開發者工具或自動化直接呼叫服務時，
仍須明確提供橋接參數；不支援的請求仍應被後端拒絕。

```yaml
action: woow_esphome_modbus_scanner.start_scan
data:
  provider: esphome
  gateway_id: esphome:5c013b472b24
  start_id: 1
  end_id: 3
  probe_type: holding_register
  register_address: 25089
  register_count: 1
  timeout_ms: 700
  retries: 0
  inter_request_delay_ms: 250
  pause_normal_polling: true
  safety_confirmed: true
```

另一台 gateway_id：`esphome:5c013b473b60`。

## 軟體回歸與證據

不加進 124 項的軟體檢查：12 個 frontend model tests、12 個 provider unittest
（aioesphomeapi 45.3.1）、模擬瀏覽器完整回歸與新增選項還原案例、面板 source
contract、Ruff、bundle drift 都通過。完整 HA pytest/coverage 本輪未重跑。

已從 HA 取回並逐 byte 核對的 bundle SHA256：
`2ed15e9affe87ee5b6b889b9c6da52439d36b43d3777e024db127bb1f40b5ba9`。

完整中文 Markdown/HTML、124 項 JSON、實際 scan_id、截圖、健康觀察及原始工具
失敗／修正紀錄另交付本機報告包。初始失敗包含瀏覽器路徑／工作目錄、錯等隱藏
option、按鈕索引誤選；另有真正的 select 顯示 bug，已修產品並增補回歸。
不覆寫歷史失敗以偽造一次全過，也不公開認證或韌體 binary。

未做破壞性拔線、實體碰撞／CRC 注入、24/72h 耐久、安全稽核或其他 Modbus
型號驗收；mock 情境不能代替這些證據。ESPHome API 仍未加密，且所有已驗證
HA 使用者均可呼叫實體掃描，尚未做 admin-only 防護。
