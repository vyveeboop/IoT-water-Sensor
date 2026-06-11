import paho.mqtt.client as mqtt
import sqlite3
import datetime
import json
import random
import os
import time
import pandas as pd
from collections import deque

# --- 設定檔路徑 ---
CONFIG_FILE = "config.json"

def load_config():
    if not os.path.exists(CONFIG_FILE):
        print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 錯誤：找不到 {CONFIG_FILE}")
        return None
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 錯誤：設定檔格式錯誤: {e}")
        return None

# --- 讀取設定 ---
CONFIG = load_config()
if CONFIG is None:
    input("按 Enter 鍵結束...")
    exit()

DB_PATH = CONFIG['database']['path']
orp_history = deque(maxlen=CONFIG['surge_protection']['window_size'])

# --- 狀態 ---
is_paused = False 

# --- 功能函式 ---
def check_surge(new_val, history, limit, name):
    history.append(new_val)
    if len(history) < history.maxlen: return None
    delta = abs(new_val - history[0])
    if delta > limit:
        return f"{name} 警報！變化: {delta:.2f} (閾值: {limit})"
    return None

def generate_report():
    current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n[{current_time}] 正在生成報表...")
    try:
        conn = sqlite3.connect(DB_PATH)
        query = f"SELECT * FROM sensor_data WHERE timestamp >= datetime('now', '-{CONFIG['report']['days_to_keep']} day')"
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if df.empty:
            print(f"[{current_time}]    -> 沒有新數據，跳過生成")
            return

        # [修改點 1]：將 ph 加入統計欄位
        stats = df[['temp', 'orp', 'do', 'ph']].describe() 
        filename = f"水質報表_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        full_path = os.path.join(CONFIG['report']['save_folder'], filename)
        
        with pd.ExcelWriter(full_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='原始數據', index=False)
            stats.to_excel(writer, sheet_name='統計分析')
        print(f"[{current_time}]    -> 報表已儲存至: {full_path}")
    except Exception as e:
        print(f"[{current_time}]    -> 生成報表失敗: {e}")

# [修改點 2]：傳入參數增加 ph
def save_to_db(pool_id, temp, psu, do, orp, ph, timestamp): 
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # [修改點 3]：SQL 語法加回 ph 欄位
        cursor.execute('''
            INSERT INTO sensor_data (pool_id, temp, psu, do, orp, ph, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (pool_id, temp, psu, do, orp, ph, timestamp))
        conn.commit()
        conn.close()
        # [修改點 4]：顯示資訊加回 pH
        print(f"[{timestamp}] [DB] T={temp} ORP={orp} DO={do} pH={ph}")
    except sqlite3.Error as e:
        print(f"[{timestamp}] 資料庫寫入錯誤: {e}")

# --- MQTT 處理 ---
def on_connect(client, userdata, flags, rc):
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{current_time}] 已連線 MQTT Broker，監聽: {CONFIG['mqtt']['topic']}")
    client.subscribe(CONFIG['mqtt']['topic'])

def on_message(client, userdata, msg):
    global is_paused
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") # 取得當下時間
    try:
        data = json.loads(msg.payload.decode('utf-8'))
        temp = float(data.get('temp', 0))
        orp = float(data.get('orp', 0))
        do = float(data.get('do', 0))
        # [修改點 5]：從 MQTT JSON 解析 ph 數值
        ph = float(data.get('ph', 0)) 

        error_sensors = []
        th = CONFIG['thresholds']

        if temp > th['temp_max'] or temp < th['temp_min']: 
            error_sensors.append(f"溫度異常 ({temp})")
        
        if orp > th['orp_max'] or orp < th['orp_min']:
            error_sensors.append(f"ORP 異常 ({orp})")
            
        # [修改點 6]：加入 pH 閾值檢查 (安全寫法，若設定檔沒寫 ph_min/max 也不會報錯)
        if 'ph_min' in th and 'ph_max' in th:
            if ph < th['ph_min'] or ph > th['ph_max']:
                error_sensors.append(f"pH 異常 ({ph})")
        # ----------------------------------

        if CONFIG['surge_protection']['enabled']:
            surge_msg = check_surge(orp, orp_history, CONFIG['surge_protection']['orp_surge_limit'], "ORP")
            if surge_msg: error_sensors.append(surge_msg)

        if error_sensors:
            if not is_paused:
                print(f"[{current_time}] 偵測到異常: {', '.join(error_sensors)}，已停止寫入資料庫。")
                is_paused = True
        else:
            if is_paused:
                print(f"[{current_time}] 數值恢復正常，恢復寫入。")
                is_paused = False
            
            # [修改點 7]：將 ph 變數傳給 save_to_db
            save_to_db(1, temp, 0, do, orp, ph, current_time) 

    except Exception as e:
        print(f"[{current_time}] 訊息解析錯誤: {e}")

# --- 主程式 ---
if __name__ == "__main__":
    start_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{start_time}] --- 系統啟動中 ---")
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(CONFIG['mqtt']['broker'], CONFIG['mqtt']['port'], 60)
    except Exception as e:
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{current_time}] 無法連線 MQTT Broker: {e}")
        input("按 Enter 鍵結束...")
        exit()

    last_report_time = time.time()
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{current_time}] --- 進入監聽迴圈 (Ctrl+C 結束) ---")

    try:
        while True:
            client.loop(timeout=0.1)
            # 定時產報表
            if time.time() - last_report_time > 43200:
                generate_report()
                last_report_time = time.time()
    except KeyboardInterrupt:
        end_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{end_time}] 程式手動停止。")