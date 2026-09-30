# Woow ESPHome Modbus Scanner

> **實驗版 0.4.0.dev1 已部署至 HA 與兩台既有 ESP32。**
> 所有啟用中的 HA 使用者及內部自動化皆可操作。兩台裝置均使用獨立 API
> 加密金鑰，且原生 ESPHome 與本整合已同步更新。已實作新輪詢復原驗證、
> 有界歷程／事件、診斷、Repairs 及重新認證。請看[本次實測驗收](docs/design/hardening-live-acceptance.md)、
> [授權邊界](docs/design/authorization-boundary.md)與[升級／回復程序](docs/design/hardening-upgrade-rollback.md)。
> 這不是上游正式發行版，也不是所有硬體／長期耐久情境的認證。

> **歷史基線 0.3.0.dev3：**新增限定貫捷 IN-D17 的 FC03 韌體橋接及
> ESPHome provider。請看[實體橋接契約與測試方式](docs/adr/0004-experimental-guanjie-fc03-bridge.md)。
> 這不是上游發行版。側欄已支援實體閘道、正確 FC03 預設值、真機警告及
> 閘道記憶；舊教學仍是模擬版。HACS 更新可能覆蓋這些本機修改。
> [介面復驗報告：124/124](docs/design/ui-reacceptance.md)。

### 實驗版真機側欄操作

更新後請強制重新整理 HA。選擇已登錄的 ESPHome 閘道，即可直接按「測試位址」，
不用手動修改進階參數。預設 FC03、暫存器 25089（0x6201）、數量 1、逾時 700 毫秒，
自動暫停及恢復輪詢。範圍掃描請勾選警告後按「開始掃描」，預設 1–3、最多 32。
重新整理會保留閘道及有效數值，但須重新勾選範圍掃描確認；儲存閘道不可用時
禁止讀取，不會自動退回模擬。結果表會標明自身來源，避免混淆歷史與下一次掃描。
所有登入的 HA 使用者都能發出實體讀取；此版本尚非正式安全認證版本。
下方 ESPHome 識別欄只顯示已選閘道，不需要第二次選擇裝置。

**以下章節是上游 v0.2.0 模擬版文件，並非上述實體分支的功能限制。**

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

**全使用者政策：**目前八個服務與側欄開放給啟用中的已驗證 HA 使用者，
不區分管理員／一般角色；既有內部自動化亦可使用。已停用或不存在的具名
使用者不能操作實機。使用者可產生唯讀匯流排流量並查看回應證據，因此仍須
管控 HA 帳號。`check_gateway` 只查 API；`get_history` 讀取有界保存快照。
API 加密不代表另外對原生 ESPHome 動作施加 per-user 限制。

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
