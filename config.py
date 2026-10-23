# /home/mrak/projects/Python/fiona_brain/config.py

# ============================================================================
#                              ЦВЕТА И ПОРОГИ
# ============================================================================
COLOR_CYAN    = 0x00f3ff
COLOR_ORANGE  = 0xff7800
COLOR_RED     = 0xff3333
COLOR_GREEN   = 0x00ff00
COLOR_BLUE    = 0x0000ff
COLOR_YELLOW  = 0xffff00

# Топливо
FUEL_RED_THRESHOLD       = 5
FUEL_YELLOW_THRESHOLD    = 10
# Напряжение
BATT_LOW_THRESHOLD       = 10.5
BATT_HIGH_THRESHOLD      = 14.7
# Температура
TEMP_COLD                = 85
TEMP_NORMAL              = 98
TEMP_WARM                = 103
TEMP_HOT                 = 110
# Скорость
SPEED_LOW                = 20
SPEED_MID_LOW            = 35
SPEED_MID_HIGH           = 40
SPEED_HIGH_LOW           = 55
SPEED_HIGH_HIGH          = 60
SPEED_VHIGH_LOW          = 110
SPEED_VHIGH_HIGH         = 130
# Обороты
RPM_BLUE_MAX             = 650
RPM_CYAN_MAX             = 2700
RPM_YELLOW_MAX           = 3300
# Расход (л/ч)
LPH_BLUE_MAX             = 5
LPH_CYAN_MAX             = 10
LPH_YELLOW_MAX           = 20

# ============================================================================
#                         ДИАПАЗОНЫ ШКАЛ (GUI)
# ============================================================================
FUEL_MIN, FUEL_MAX, FUEL_STEP = 0, 50, 1
RANGE_MIN, RANGE_MAX, RANGE_STEP = 0, 500, 1
BATT_MIN, BATT_MAX, BATT_STEP = 7.0, 16.5, 0.1
TEMP_MIN, TEMP_MAX, TEMP_STEP = -30, 130, 1
SPEED_MIN, SPEED_MAX, SPEED_STEP = 0, 220, 1
RPM_MIN, RPM_MAX, RPM_STEP = 0, 7000, 1
TRIPM_MIN, TRIPM_MAX, TRIPM_STEP = 0, 3000, 1
LPH_MIN, LPH_MAX, LPH_STEP = 0, 30, 0.1

# ============================================================================
#                         ФЛАГИ КАЛИБРОВКИ ТОПЛИВА
# ============================================================================
FUEL_CALIB_NONE          = 0x00
FUEL_CALIB_NO_FIRST_FULL = 0x01
FUEL_CALIB_ACCUMULATING  = 0x02
FUEL_CALIB_DONE          = 0x04
FUEL_CALIB_LIMITED       = 0x08

# ============================================================================
#                         НАСТРОЙКИ СЕТИ И ЖЕЛЕЗА
# ============================================================================
# Bluetooth-адаптер ELM327
BT_MAC = "00:1D:A5:07:05:17"
BT_PIN = "1234"

# Сетевые настройки по умолчанию (из CarData.c)
WIFI_SSID1, WIFI_PASS1 = "Tri-Al(m)", "Ford-Fiona"
WIFI_SSID2, WIFI_PASS2 = "Tri-AL", "Aq1Sw2De3Fr4"
WIFI_SSID3, WIFI_PASS3 = "KbKb", "1234567890"
AP_SSID, AP_PASS       = "Fiona-WiFi", "Ford-Fiona"

# MAC-адрес для модуля P4
BT_NAME = "Fiona-BT"

# Таймауты
TRIP_AUTO_STOP_TIMEOUT = 60  # секунд
SLEEP_TIMEOUT = 15           # минут

# Режим отладки (эмуляция)
EMULATION_MODE = True       # Поставь False True, если хочешь запустить без машины
