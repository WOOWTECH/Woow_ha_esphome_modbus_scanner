# Woow ESPHome Modbus Scanner

這是一個可由 HACS 安裝的 Home Assistant 自訂整合，用於安全、以提供者為
邊界的 Modbus 位址盡力掃描。**0.2.0** 僅包含可重現的
`MockGatewayProvider`；不會連線 ESPHome，也不會開啟 Modbus 實體傳輸。

English: [README.md](README.md)

## 下載版繁體中文完整教學

**[檢視 v0.2.0 原始檔](https://github.com/WOOWTECH/Woow_ha_esphome_modbus_scanner/blob/main/docs/tutorial/woow-esphome-modbus-scanner-v0.2.0-zh-TW.html)** · **[Raw v0.2.0 HTML](https://raw.githubusercontent.com/WOOWTECH/Woow_ha_esphome_modbus_scanner/main/docs/tutorial/woow-esphome-modbus-scanner-v0.2.0-zh-TW.html)** · **[在 GitHub 檢視原始檔（v0.1.0）](https://github.com/WOOWTECH/Woow_ha_esphome_modbus_scanner/blob/main/docs/tutorial/woow-esphome-modbus-scanner-v0.1.0-zh-TW.html)** · **[下載 v0.1.0 教學 HTML release asset](https://github.com/WOOWTECH/Woow_ha_esphome_modbus_scanner/releases/download/v0.1.0/woow-esphome-modbus-scanner-v0.1.0-zh-TW.html)** · **[Raw v0.1.0 HTML](https://raw.githubusercontent.com/WOOWTECH/Woow_ha_esphome_modbus_scanner/main/docs/tutorial/woow-esphome-modbus-scanner-v0.1.0-zh-TW.html)** · **[下載 v0.1.0 原始碼封存檔](https://github.com/WOOWTECH/Woow_ha_esphome_modbus_scanner/archive/refs/tags/v0.1.0.zip)**

> **v0.2.0 僅限 MOCK 模擬：**HTML 是教學文件，不是 ESPHome 韌體；本版不會
> 連線 ESPHome，也不會掃描實體硬體。

## 版本範圍與安全語意

目前版本適合開發自動化、服務呼叫端、生命週期測試與結果語意驗證，尚不是
實體匯流排掃描器。

掃描是唯讀且盡力而為。逾時不代表位址未使用；有回應也不代表 Slave ID
唯一對應一台實體設備。雜訊或重複 ID 可能呈現為「可能碰撞」。未來即使只做
唯讀探測，實體掃描仍可能干擾一般輪詢。

因此 `start_scan` 的 `safety_confirmed` 只接受真正的布林值 `true`，不接受
數字或字串形式的 truthy 值。

**永久全使用者政策：**六個掃描服務與側邊欄刻意不做 admin/user 權限檢查，
所有已驗證 HA 使用者都能操作。這方便目前 mock 工作台，但對未來實體 provider
是明確風險：任一使用者可能產生匯流排流量、干擾正常輪詢或看到 responder
證據。安裝者必須管控 HA 帳號，啟用實體硬體前也必須重新評估此政策。

## 安裝

### HACS 自訂儲存庫

1. 在 HACS 將此儲存庫加入 **Integration** 類型的自訂儲存庫。
2. 安裝 **Woow ESPHome Modbus Scanner**。
3. 重新啟動 Home Assistant。
4. 到 **設定 → 裝置與服務 → 新增整合**，新增一次本整合。
5. 從側邊欄開啟 **Modbus Scanner**（`mdi:radar`）；所有 HA 使用者都看得到。

### 手動安裝

將 `custom_components/woow_esphome_modbus_scanner` 複製到 Home Assistant 的
`custom_components` 目錄，重新啟動後新增整合。設定流程是 singleton，第二個
設定項目會被拒絕。

## 側邊欄掃描工作台

獨立路徑為 `/woow-esphome-modbus-scanner`。先重新整理 gateway，選六種 mock
quick profile 之一，填 1–247 含頭尾範圍並勾選盡力掃描確認。進階欄位完整對應
probe、register 位址／數量、timeout、retry、delay 與未來暫停輪詢旗標；由於
沒有實體 provider，ESPHome selector 會停用並解釋原因。

**Start scan** 後每秒做一次不重疊狀態輪詢，進入終態自動取結果；Cancel、Test
address、Refresh status/results 都直接對應六服務。畫面顯示進度、六種 outcome
計數、錯誤與可排序 responder 證據表。表單偏好、展開狀態與最近 scan ID 只放
瀏覽器 `localStorage`，不保存 token、host、frame、憑證或服務回應。整合重載或
重啟後，記憶體歷史消失，舊 ID 可能變 unknown。詳細 outcome 與疑難排解請看
上方 v0.2.0 HTML 教學。

## 公開服務

Domain 為 `woow_esphome_modbus_scanner`，公開服務**只有**：

- `list_gateways`
- `start_scan`
- `get_scan_status`
- `get_scan_results`
- `cancel_scan`
- `test_address`

模擬掃描範例：

```yaml
service: woow_esphome_modbus_scanner.start_scan
data:
  provider: mock
  gateway_id: mock:rs485-gateway
  start_id: 1
  end_id: 12
  probe_type: device_identification
  inter_request_delay_ms: 0
  mock_profile: found_default
  safety_confirmed: true
response_variable: started
```

使用回傳的 `scan_id` 呼叫 `get_scan_status` 與 `get_scan_results`。
`test_address` 走相同協調器，但只測一個位址。每個 provider/gateway 同時只允許
一個掃描。終止歷史預設最多保留 20 筆於記憶體，重新載入後不保存。

服務表單包含選用的 `esphome_device_id`，其裝置 selector 只顯示 Home
Assistant ESPHome 整合的裝置。這是未來介面保留欄位；0.2.0 可接收它，但模擬
結果不變，也不會接觸所選裝置。

## 模擬情境

`found_default`、`all_offline`、`partial_timeout`、`modbus_exception`、
`possible_collision`、`gateway_disconnect` 都是固定且可重現的情境。

結果會正規化識別回應、一般回應、協定例外、逾時、可能碰撞與閘道錯誤。
逾時會計數，但不會當成 responder 詳細資料保存。

## 未來 ESPHome adapter 契約

0.2.0 **沒有** ESPHome adapter。未來提供者必須實作
[`docs/design/provider-contract.md`](docs/design/provider-contract.md) 所定義的
`GatewayProvider`：列出自身擁有的閘道，以非同步方式執行一個已驗證請求，
逐筆發出正規化的 `ProbeResult`，並支援合作式取消。它也必須把 HA 裝置明確
映射至閘道、只使用唯讀探測、逐閘道序列化、在 `finally` 恢復暫停的輪詢，並把
傳輸中斷轉成 `GatewayProviderError`。驗證、生命週期、歷史與公開回應格式仍由
協調器負責。

ESPHome 裝置 selector 不表示 Home Assistant 或 ESPHome 已提供本契約所需的
低階序列交易 API。在確認可行性與上游 API 前，本專案不宣稱支援實體提供者。

## 開發與驗證

`pytest --collect-only -q` 是測試數量事實來源，目前收集 **131 個 Python
測試**；另有 **7 個 frontend Node unit**、bundle drift 與 panel／tutorial
Playwright mocked-HA 瀏覽器情境。

```bash
uv venv --python 3.13.2
uv pip install -r requirements-test.txt
.venv/bin/ruff check .
.venv/bin/pytest --collect-only -q
.venv/bin/pytest --cov=custom_components/woow_esphome_modbus_scanner \
  --cov-report=term-missing --cov-fail-under=90
.venv/bin/python -m compileall -q custom_components tests/live
cd panel_frontend && npm ci --include=dev && npm test && npm run check:drift
npx playwright install chromium && npm run test:browser
```

外部 Home Assistant 的選用 mock-only smoke script 說明位於
[`tests/live/README.md`](tests/live/README.md)。

## 授權

MIT，詳見 [LICENSE](LICENSE)。
