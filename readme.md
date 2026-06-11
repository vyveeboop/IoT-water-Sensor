# 物聯網水質監測系統（Water Quality IoT Monitoring System）

這是一個基於 MQTT 協定的輕量級水質監測系統，專為水產養殖場景（如養蝦池）設計。

系統包含兩個主要部分：

1. **邊緣感測節點（Edge Node）**
   負責採集實體環境數據，包含溫度、ORP（氧化還原電位）與 pH 值。

2. **後台伺服器（Backend Server）**
   負責接收感測資料、監控異常狀態、寫入資料庫，並定期產出 Excel 統計報表。

---

## 系統架構

### 邊緣節點（MicroPython）

邊緣節點運行於支援 MicroPython 的微控制器，例如 Raspberry Pi Pico W 或 ESP32。

主要功能包含：

* 讀取溫度、ORP 與 pH 感測資料
* 透過 Wi-Fi 連線至 MQTT Broker
* 將感測資料發布至指定 MQTT Topic
* 透過 Watchdog 機制提升系統穩定性

### 後台伺服器（Python 3）

後台伺服器運行於一般 PC、Raspberry Pi 或雲端主機。

主要功能包含：

* 訂閱 MQTT Topic
* 接收並解析邊緣節點上傳的感測資料
* 即時檢查資料是否超出安全閾值
* 將正常資料寫入 SQLite 資料庫
* 定期匯出 Excel 統計報表

---

## 1. 邊緣感測節點（Edge Node）

### 硬體接線定義

| 裝置             | 腳位 / 介面 | 說明                    |
| -------------- | ------- | --------------------- |
| 狀態指示燈（LED）     | 板載 LED  | 腳位依開發板而定              |
| 溫度感測器（DS18B20） | GPIO 1  | 使用 OneWire 協定         |
| ORP 感測器        | GPIO 27 | ADC 類比輸入              |
| pH 感測器         | GPIO 26 | 透過 `Surveyor_pH` 模組讀取 |

---

### 軟體與依賴庫

請確保微控制器已安裝以下 MicroPython 函式庫：

* `umqtt.simple`
* `onewire`
* `ds18x20`
* `surveyor_ph`

---

### 設定方式

請於邊緣節點程式碼頂部修改 Wi-Fi 與 MQTT 相關設定：

```python
WIFI_SSID = "您的_WIFI_名稱"
WIFI_PASS = "您的_WIFI_密碼"

MQTT_BROKER = "您的_MQTT_伺服器_IP"
TOPIC = "shrimp"
```

---

### 執行方式

將邊緣節點程式命名為：

```text
main.py
```

並燒錄至 MicroPython 開發板。

通電後，系統將自動執行以下流程：

1. 連線至 Wi-Fi
2. 連線至 MQTT Broker
3. 讀取溫度、ORP 與 pH 感測資料
4. 每 3 秒將資料發布至 MQTT Topic
5. 若發生網路斷線或系統異常，Watchdog 將自動重啟裝置

---

## 2. 後台伺服器（Backend Server）

### 環境需求

請確保系統已安裝：

* Python 3.8 或以上版本
* MQTT Broker，例如 Mosquitto

---

### 安裝 Python 套件

請執行以下指令安裝所需套件：

```bash
pip install paho-mqtt pandas openpyxl
```

> `sqlite3` 與 `json` 為 Python 內建模組，無需額外安裝。

---

### 設定檔 `config.json`

伺服器啟動前，請在與程式相同的目錄下建立 `config.json` 檔案。

範例設定如下：

```json
{
  "database": {
    "path": "water_quality.db"
  },
  "mqtt": {
    "broker": "127.0.0.1",
    "port": 1883,
    "topic": "shrimp"
  },
  "thresholds": {
    "temp_max": 32.0,
    "temp_min": 22.0,
    "orp_max": 400,
    "orp_min": 150,
    "ph_max": 8.5,
    "ph_min": 6.5
  },
  "surge_protection": {
    "enabled": true,
    "window_size": 5,
    "orp_surge_limit": 50.0
  },
  "report": {
    "days_to_keep": 7,
    "save_folder": "./reports"
  }
}
```

---

### 設定項目說明

| 設定區塊               | 參數                      | 說明              |
| ------------------ | ----------------------- | --------------- |
| `database`         | `path`                  | SQLite 資料庫檔案路徑  |
| `mqtt`             | `broker`                | MQTT Broker 位址  |
| `mqtt`             | `port`                  | MQTT Broker 連接埠 |
| `mqtt`             | `topic`                 | 訂閱的 MQTT Topic  |
| `thresholds`       | `temp_max` / `temp_min` | 溫度安全範圍          |
| `thresholds`       | `orp_max` / `orp_min`   | ORP 安全範圍        |
| `thresholds`       | `ph_max` / `ph_min`     | pH 安全範圍         |
| `surge_protection` | `enabled`               | 是否啟用突波保護        |
| `surge_protection` | `window_size`           | 判斷突波的資料視窗大小     |
| `surge_protection` | `orp_surge_limit`       | ORP 突波變化上限      |
| `report`           | `days_to_keep`          | 報表保留或統計天數       |
| `report`           | `save_folder`           | Excel 報表輸出資料夾   |

---

### 執行前準備

請確認以下事項：

1. MQTT Broker 已啟動並正常運行。
2. `config.json` 已建立並設定完成。
3. `reports` 資料夾已建立，用於存放 Excel 報表。
4. SQLite 資料庫中已存在 `sensor_data` 資料表。

---

### 執行方式

請執行以下指令啟動後台伺服器：

```bash
python server_main.py
```

程式啟動後將進入監聽迴圈，並於終端機顯示：

* 即時接收到的感測資料
* 資料是否通過安全閾值檢查
* 資料庫寫入狀態
* 報表輸出狀態

---

## 報表產生機制

系統會每隔 12 小時自動將歷史資料匯出為 Excel 統計報表。

預設匯出間隔：

```text
43200 秒
```

報表將儲存於 `config.json` 中指定的資料夾：

```json
"save_folder": "./reports"
```

---

## MQTT Topic

預設使用的 MQTT Topic 為：

```text
shrimp
```

邊緣節點會將感測資料發布至此 Topic，後台伺服器則會訂閱相同 Topic 以接收資料。

---

## 系統流程

```text
感測器資料讀取
        ↓
邊緣節點資料處理
        ↓
透過 Wi-Fi 連線至 MQTT Broker
        ↓
發布資料至 MQTT Topic
        ↓
後台伺服器訂閱並接收資料
        ↓
檢查資料是否超出安全閾值
        ↓
正常資料寫入 SQLite 資料庫
        ↓
定期匯出 Excel 統計報表
```

---

## 專案檔案建議結構

```text
water-quality-iot/
├── edge-node/
│   └── main.py
│
├── backend-server/
│   ├── server_main.py
│   ├── config.json
│   ├── water_quality.db
│   └── reports/
│
└── README.md
```

---

## 注意事項

* 邊緣節點與後台伺服器必須使用相同的 MQTT Topic。
* `config.json` 中的 MQTT Broker 位址需依實際環境修改。
* 若使用遠端 MQTT Broker，請確認防火牆與連接埠設定允許連線。
* 啟動後台伺服器前，請先確認 MQTT Broker 已正常運行。
* 若 `reports` 資料夾不存在，請先手動建立或在程式中加入自動建立資料夾邏輯。
* 若資料庫尚未建立 `sensor_data` 資料表，請先完成資料表初始化。
