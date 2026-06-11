import machine, onewire, ds18x20, time, network, json, gc
from umqtt.simple import MQTTClient
from machine import WDT  

from surveyor_ph import Surveyor_pH

# ==========================================
WIFI_SSID = "yourwifi"
WIFI_PASS = "yourpassword"
MQTT_BROKER = "yourIP"
MQTT_PORT   = 1883
TOPIC       = "shrimp"

EMA_ALPHA = 0.5
# ==========================================

led = machine.Pin("LED", machine.Pin.OUT)

# 感測器腳位設定
ds_pin = machine.Pin(1)
ds_sensor = ds18x20.DS18X20(onewire.OneWire(ds_pin))

orp_adc_pin = machine.ADC(27) # ORP 使用 GP27

# 初始化 pH 感測器 
ph_sensor = Surveyor_pH(pin=26) 

def get_balanced_voltage(adc_pin):
    raw_data = []
    sample_count = 100
    for _ in range(sample_count):
        val = adc_pin.read_u16() >> 4
        raw_data.append(val)
        time.sleep_ms(1)
    raw_data.sort()
    cut_len = 10
    clean_data = raw_data[cut_len : -cut_len]
    if not clean_data:
        average_raw = sum(raw_data) / len(raw_data)
    else:
        average_raw = sum(clean_data) / len(clean_data)
    return (average_raw / 4095) * 3.3

def calc_orp(v):
    return ((30 * 3.3 * 1000) - (75 * v * 1000)) / 75

def connect_wifi(wdt=None):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print(f"連線 WiFi: {WIFI_SSID} ...")
        wlan.connect(WIFI_SSID, WIFI_PASS)
        timeout = 10
        while not wlan.isconnected() and timeout > 0:
            time.sleep(1)
            timeout -= 1
            if wdt: wdt.feed()
            
    if wlan.isconnected(): 
        print(f"WiFi 連線成功")
        return wlan
    else: 
        print(" WiFi 連線失敗")
        return None

def connect_mqtt():
    try:
        client = MQTTClient("Pico_Shrimp_Stabilized", MQTT_BROKER, port=MQTT_PORT)
        client.connect()
        return client
    except: return None

def main():
    # 1. 啟動看門狗 (8秒沒餵就重開)
    wdt = WDT(timeout=8000)
    print("--- WDT已啟動 (Timeout=8s) ---")

    wdt.feed() # 先餵一口
    connect_wifi(wdt) 
    client = connect_mqtt()
    
    # 如果 MQTT 失敗，重試一次 (中間也要餵狗)
    if client is None:
        wdt.feed()
        time.sleep(2)
        client = connect_mqtt()

    print(f"--- 開始監測 (Sample=100, Smoothing={EMA_ALPHA}) ---")
    
    last_orp_vol = None
    error_count = 0 

    while True:
        wdt.feed() 
        gc.collect() 
        
        try:
            # 正常狀態燈：短閃一下
            led.on()
            time.sleep_ms(100) 
            led.off()
            
            # 1. 讀取溫度
            try:
                roms = ds_sensor.scan()
                if len(roms) > 0:
                    ds_sensor.convert_temp()
                    time.sleep_ms(750)
                    temp = ds_sensor.read_temp(roms[0])
                else: temp = -127.0
            except: temp = -127.0

            # 2. 讀取 ORP
            curr_orp_vol = get_balanced_voltage(orp_adc_pin)
            if last_orp_vol is None:
                last_orp_vol = curr_orp_vol
            else:
                last_orp_vol = (last_orp_vol * (1 - EMA_ALPHA)) + (curr_orp_vol * EMA_ALPHA)
            orp_val = calc_orp(last_orp_vol)

            # 3. 讀取 pH 值 
            ph_volts = ph_sensor.read_voltage()
            ph_val = ph_sensor.read_ph(ph_volts)

            # 終端機顯示
            print(f"Temp: {temp:.1f}C | ORP: {orp_val:.0f} | pH: {ph_val:.2f} | Err: {error_count}")

            # 打包 JSON 與發送 MQTT
            if client:
                data = {
                    "temp": round(temp, 1),
                    "orp": int(orp_val),
                    "ph": round(ph_val, 2) # 將 pH 值加入發送封包，保留小數點後兩位
                }
                msg = json.dumps(data)
                client.publish(TOPIC, msg)
                error_count = 0 
            else:
                raise OSError("MQTT Client is None")
            
        except Exception as e:
            print(f" 錯誤: {e}")
            error_count += 1
            
            # 錯誤狀態燈：快閃 3 次
            for _ in range(3):
                led.toggle()
                time.sleep_ms(100)
            
            if error_count > 5:
                print("嘗試重啟網路...")
                try:
                    if client: client.disconnect()
                except: pass
                
                wdt.feed() 
                connect_wifi(wdt) 
                client = connect_mqtt()
                error_count = 0 

        # 等待 3 秒再進行下一次測量
        time.sleep(3)

if __name__ == "__main__":
    main()