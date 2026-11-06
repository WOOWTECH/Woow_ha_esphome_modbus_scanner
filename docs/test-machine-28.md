# 測試機 192.168.2.28 借用規則

本專案短期借用 woow-addon-pipeline 的參考實機 .28 當測試機。借用由 woow-addon-pipeline 的 issue 162 授權並記錄。借出前已拍完整快照，歸還後會整機還原。

## 這台機器

- 監督式 Home Assistant OS 16.1，amd64（J6412），記憶體 16 GB。
- 借出時：Core 2026.7.2，裝有 28 個 addon（都是停止狀態），其中包含 ESPHome（`local_esphome` 2026.10.0）。
- 使用方式：HA 網頁介面 `http://192.168.2.28:8123`。

## 可以做的事

- 在 HA 裡建使用者、完成 onboarding、改設定、加 integration（包含用 HACS 或 Samba 裝本專案的 `custom_components/woow_esphome_modbus_scanner`）、加 ESPHome 裝置。
- 安裝、移除、設定 addon；更新 Core 或 addon。
- 歸還時這些變動都會被整機還原蓋掉。要保留的東西（例如 Gateway YAML、diagnostics、驗收紀錄）請存回本專案。

## 不可以做的事

- **不要更新 HAOS（作業系統）。** 還原備份不會把 OS 降回來，而且 B 槽是壞的，沒有退路。
- **不要重灌 HAOS，也不要原廠重設。** 重灌會換主機金鑰，控制通道會斷掉，只能由負責人到現場用 USB 救回。
- **不要改主機網路。** 尤其是 `enp2s0`（`192.168.50.1/24`），這是 .170 控制 .28 用的直連線。
- **不要動主機層 SSH**（port 22222）的金鑰。
- **不要停用或刪除 `local-registry` 容器。** 它直接跑在主機的 docker 上，不在 HA 備份裡。
- **不要刪除名為 `pre-loan-20261105` 的備份。** 這是歸還時要還原的快照（.28 以外另有一份）。

## 時間與歸還

- 不設期限。借用期間 woow-addon-pipeline 不會在 .28 上跑重做；要提早收回時，負責人會先通知。
- 用完通知負責人。負責人會從快照整機還原、比對主機設定，並在 issue 162 結案。
- 曾登入 .28 的手機 App 等裝置，歸還後要登出或刪除該伺服器。還原後原本的 token 會失效，不處理的話會一直用無效 token 重試（上次借用時發生過）。
