# /home/mrak/projects/Python/fiona_brain/core/state.py

import threading
from dataclasses import dataclass
from contextlib import contextmanager
import config

# ============================================================================
#                         ВСПОМОГАТЕЛЬНЫЕ СТРУКТУРЫ
# ============================================================================

@dataclass
class TripStats:
    """Статистика одной поездки (Trip)."""
    start_time: int = 0
    status: int = 0
    duration_sec: int = 0
    pause_sec: int = 0
    pause_count: int = 0
    distance_m: int = 0
    fuel_x100: int = 0          # Расход в литрах * 100 (для точности)
    max_speed: int = 0
    max_lph_x100: int = 0
    warmup_sec: int = 0
    avg_throttle_rel_x100: int = 0
    max_throttle_rel: int = 0
    aggressive_count: int = 0
    full_throttle_count: int = 0
    moving_time_sec: int = 0
    valid: bool = False

@dataclass
class DayStats:
    """Статистика за сутки (с 00:00 до 23:59)."""
    date: int = 0
    valid_flag: int = 0
    engine_sec: int = 0
    distance_m: int = 0
    fuel_x100: int = 0
    max_speed: int = 0
    max_lph_x100: int = 0
    first_start_time: int = 0
    last_stop_time: int = 0
    trip_count: int = 0
    drive_count: int = 0
    avg_throttle_rel_x100: int = 0
    max_throttle_rel: int = 0
    warmup_sec: int = 0
    aggressive_count: int = 0
    full_throttle_count: int = 0
    moving_time_sec: int = 0
    valid: bool = False

@dataclass
class RefuelRecord:
    """Запись о конкретной заправке."""
    timestamp: int = 0
    liters: float = 0.0
    price: float = 0.0
    odo_km: int = 0
    cost: float = 0.0
    calibration: bool = False

@dataclass
class DriveCycle:
    """Цикл движения (от запуска двигателя до остановки)."""
    start_time: int = 0
    end_time: int = 0
    duration_sec: int = 0
    distance_m: int = 0
    fuel_x100: int = 0
    max_speed: int = 0
    max_lph_x100: int = 0
    avg_throttle_rel_x100: int = 0
    max_throttle_rel: int = 0
    aggressive_count: int = 0
    full_throttle_count: int = 0
    warmup_sec: int = 0
    moving_time_sec: int = 0
    valid: bool = False


# ============================================================================
#                         ГЛАВНЫЙ КЛАСС СОСТОЯНИЯ
# ============================================================================

class FionaState:
    """
    Цифровой двойник автомобиля. Полный аналог CarData из C++.
    Поля сгруппированы по категориям для удобства.
    """
    def __init__(self):
        # Мьютекс для потокобезопасного доступа (как в C++)
        self._lock = threading.RLock()

        # ====================================================================
        # 1. НАСТРАИВАЕМЫЕ ЦВЕТА И ПОРОГИ (GUI)
        # ====================================================================
        self.colorCyan = config.COLOR_CYAN
        self.colorOrange = config.COLOR_ORANGE
        self.colorRed = config.COLOR_RED
        self.colorGreen = config.COLOR_GREEN
        self.colorBlue = config.COLOR_BLUE
        self.colorYellow = config.COLOR_YELLOW

        # Пороги смены цветов (для спидометра, тахометра и т.д.)
        self.fuelRedThreshold = config.FUEL_RED_THRESHOLD
        self.fuelYellowThreshold = config.FUEL_YELLOW_THRESHOLD
        self.battLowThreshold = config.BATT_LOW_THRESHOLD
        self.battHighThreshold = config.BATT_HIGH_THRESHOLD
        self.tempCold = config.TEMP_COLD
        self.tempNormal = config.TEMP_NORMAL
        self.tempWarm = config.TEMP_WARM
        self.tempHot = config.TEMP_HOT
        self.speedLow = config.SPEED_LOW
        self.speedMidLow = config.SPEED_MID_LOW
        self.speedMidHigh = config.SPEED_MID_HIGH
        self.speedHighLow = config.SPEED_HIGH_LOW
        self.speedHighHigh = config.SPEED_HIGH_HIGH
        self.speedVHighLow = config.SPEED_VHIGH_LOW
        self.speedVHighHigh = config.SPEED_VHIGH_HIGH
        self.rpmBlueMax = config.RPM_BLUE_MAX
        self.rpmCyanMax = config.RPM_CYAN_MAX
        self.rpmYellowMax = config.RPM_YELLOW_MAX
        self.lphBlueMax = config.LPH_BLUE_MAX
        self.lphCyanMax = config.LPH_CYAN_MAX
        self.lphYellowMax = config.LPH_YELLOW_MAX

        # Диапазоны шкал (для отрисовки)
        self.fuelMin, self.fuelMax, self.fuelStep = config.FUEL_MIN, config.FUEL_MAX, config.FUEL_STEP
        self.rangeMin, self.rangeMax, self.rangeStep = config.RANGE_MIN, config.RANGE_MAX, config.RANGE_STEP
        self.battMin, self.battMax, self.battStep = config.BATT_MIN, config.BATT_MAX, config.BATT_STEP
        self.tempMin, self.tempMax, self.tempStep = config.TEMP_MIN, config.TEMP_MAX, config.TEMP_STEP
        self.speedMin, self.speedMax, self.speedStep = config.SPEED_MIN, config.SPEED_MAX, config.SPEED_STEP
        self.rpmMin, self.rpmMax, self.rpmStep = config.RPM_MIN, config.RPM_MAX, config.RPM_STEP
        self.tripMMin, self.tripMMax, self.tripMStep = config.TRIPM_MIN, config.TRIPM_MAX, config.TRIPM_STEP
        self.lphMin, self.lphMax, self.lphStep = config.LPH_MIN, config.LPH_MAX, config.LPH_STEP

        # ====================================================================
        # 2. ДАННЫЕ ОТ ELM327 (OBD-II)
        # ====================================================================
        self.mafValue = 0.0         # Массовый расход воздуха (г/с) (PID 0110)
        self.speedValue = 0         # Скорость (км/ч) (PID 010D)
        self.rpmValue = 0           # Обороты (об/мин) (PID 010C)
        self.tempValue = 0          # Температура ОЖ (°C) (PID 0105)
        self.batValue = 0.0         # Напряжение бортсети (В) (ATRV)
        self.intakeTemp = 0.0       # Температура впускного воздуха (PID 010F)
        self.loadValue = 0.0        # Нагрузка на двигатель (PID 0104)
        self.throttlePos = 0.0      # Положение дросселя (PID 0111)
        self.stft = 0.0             # Краткосрочная топливная коррекция (PID 0106)
        self.ltft = 0.0             # Долгосрочная топливная коррекция (PID 0107)
        self.fuelPressure = 0.0     # Давление топлива (PID 0142)

        # Флаги изменений (dirty flags) - нужны для оптимизации отправки
        self.mafDirty = False
        self.speedDirty = False
        self.rpmDirty = False
        self.tempDirty = False
        self.batDirty = False
        self.intakeTempDirty = False
        self.loadDirty = False
        self.throttleDirty = False
        self.stftDirty = False
        self.ltftDirty = False
        self.fuelPressureDirty = False

        # ====================================================================
        # 3. ВЫЧИСЛЯЕМЫЕ ЗНАЧЕНИЯ (ТОПЛИВО И ПРОБЕГ)
        # ====================================================================
        self.lphValue = 0.0             # Мгновенный расход (л/ч)
        self.fuelValue = 50.0           # Остаток топлива в баке (л)
        self.rangeValue = 0             # Запас хода (км)
        self.l100kmValue = 0.0          # Средний расход (л/100км)

        self.odoMiles = 0               # Общий пробег в МИЛЯХ (вводится вручную)
        self.odoKm = 200000             # Общий пробег в КМ (вычисляется)

        self.tripValue = 0              # Время в пути (сек)
        self.tripPauseValue = 0         # Время стоянки (сек)
        self.tripDistanceKm = 0.0       # Пробег за поездку (км)
        self.tripMValue = 0.0           # Пробег за поездку (мили)
        self.tripState = False          # Активна ли поездка
        self.tripFuelUsed = 0.0         # Топливо, потраченное за поездку

        # Флаги изменений
        self.lphDirty = False
        self.fuelDirty = False
        self.rangeDirty = False
        self.odoDirty = False
        self.tripTimeDirty = False
        self.tripPauseDirty = False
        self.tripDistDirty = False
        self.tripCostDirty = False
        self.tripStateDirty = False
        self.tripFuelDirty = False

        # ====================================================================
        # 4. КАЛИБРОВКА (ПРОГРЕССИВНАЯ И ПРЕСЕТЫ)
        # ====================================================================
        # Текущие глобальные коэффициенты
        self.fuelCalibrationFactor = 1.0    # Коэфф. коррекции расхода топлива
        self.current_fuel_calibration = 1.0 # Текущий (смешанный) коэффициент

        # Допуски (прогрессивно уменьшаются после каждой калибровки)
        self.odo_tolerance = 0.10           # Допуск по одометру (старт: 10%)
        self.fuel_tolerance = 0.05          # Допуск по топливу (старт: 5%)

        # Управление калибровкой
        self.calibration_frozen = True      # По умолчанию калибровка заморожена
        self.odo_calib_needed = False       # Требуется калибровка одометра
        self.fuel_calib_needed = False      # Требуется калибровка топлива

        # Состояние текущего цикла калибровки
        self.calibration_active = False     # Идет ли сейчас цикл
        self.calibration_preset = ""        # Алиас текущей заправки (например, "Газпром_Мира")
        self.calibration_start_km = 0       # Одометр (км) на старте цикла

        # Накопители за цикл калибровки (сбрасываются при старте нового цикла)
        self.calculatedDistanceSinceLastFull = 0.0  # Сколько насчитали по скорости (км)
        self.totalRefueledSinceLastFull = 0.0       # Сколько реально залито (л)
        self.calculatedFuelSinceLastFull = 0.0      # Сколько насчитали по MAF (л)

        # Старые поля калибровки (для совместимости)
        self.fuelPrice = 63.7
        self.fuelManualSetTimeMs = 0
        self.fuel_calib_flags = config.FUEL_CALIB_NONE
        self.lastFullOdoKm = 0
        self.hasFirstFullTank = False
        self.initialOdoKm = 0
        self.initialFuel = 0.0
        self.calibrationNeeded = False

        # ====================================================================
        # 5. ВРЕМЯ И ТАЙМАУТЫ
        # ====================================================================
        self.systemTime = 0
        self.lastObdUpdate = 0
        self.lastPresetUpdate = 0
        self.lastApiResponse = 0
        self.time_synced = False
        self.time_received_this_boot = False
        self.time_set_manually = False

        self.tripAutoStopTimeout = config.TRIP_AUTO_STOP_TIMEOUT
        self.lastManualStopTime = 0
        self.sleepTimeout = config.SLEEP_TIMEOUT

        # ====================================================================
        # 6. СЕТЕВЫЕ НАСТРОЙКИ И СТАТУСЫ
        # ====================================================================
        self.wifiSsid1, self.wifiPass1 = config.WIFI_SSID1, config.WIFI_PASS1
        self.wifiSsid2, self.wifiPass2 = config.WIFI_SSID2, config.WIFI_PASS2
        self.wifiSsid3, self.wifiPass3 = config.WIFI_SSID3, config.WIFI_PASS3
        self.apSsid, self.apPass = config.AP_SSID, config.AP_PASS
        self.btName = config.BT_NAME
        self.btMac = config.BT_MAC
        self.btPin = config.BT_PIN

        self.obdConnected = False
        self.wifiConnected = False
        self.wifiRSSI = 0
        self.wifiRSSIDirty = False
        self.internetAvailable = False
        self.internetDirty = False
        self.uartArduinoAlive = False
        self.uartEsp32Alive = False

        # ====================================================================
        # 7. СУТОЧНАЯ СТАТИСТИКА И ПОЕЗДКИ (ЗАДЕЛ НА БУДУЩЕЕ)
        # ====================================================================
        self.lastTripStats = TripStats()
        self.lastDayStats = DayStats()
        self.lastRefuel = RefuelRecord()

        self.dayOdometerMeters = 0
        self.dayFuelUsed = 0.0
        self.dayDriveSeconds = 0
        self.dayMaxSpeed = 0
        self.lastAvgL100km = 0.0

        self.trip_stats_pending = False
        self.day_stats_pending = False
        self.day_requested_today = False

        self.trip_rx = {"data": TripStats(), "expected_count": 0, "received_count": 0, "active": False}
        self.day_rx = {"data": DayStats(), "expected_count": 0, "received_count": 0, "active": False}

        self.receivedDriveCycles = [DriveCycle() for _ in range(15)]
        self.receivedDriveCycleCount = 0
        self.drive_cycles_rx_active = False
        self.drive_cycles_pending = False

        # ====================================================================
        # 8. ЭКРАН, СВЕТ И ИНТЕРФЕЙС
        # ====================================================================
        self.backlight_brightness = 80
        self.backlight_min_brightness = 5
        self.light_threshold_dark = 20
        self.light_threshold_bright = 80
        self.ambient_light_pct = 100
        self.ambient_light_synth = 50
        self.ambient_light_raw = 0
        self.bg_theme = 0
        self.screensaver_timeout_sec = 300

        self.color_tone_neutral = 0x9EEFFC
        self.color_tone_funny   = 0xFFB6C1
        self.color_tone_serious = 0x00FF00

        # ====================================================================
        # 9. ДАТЧИКИ (АКСЕЛЕРОМЕТР, ГИРОСКОП, GPS)
        # ====================================================================
        self.accel_x = 0.0
        self.accel_y = 0.0
        self.accel_z = 0.0
        self.gyro_x  = 0.0
        self.gyro_y  = 0.0
        self.gyro_z  = 0.0
        self.tilt_roll  = 0
        self.tilt_pitch = 0
        self.calib_status = 0
        self.max_pos_accel_g = 0.0
        self.max_neg_accel_g = 0.0

        self.accelDirty = False
        self.gyroDirty  = False
        self.tiltDirty  = False

        self.gps_lat = 0.0
        self.gps_lon = 0.0
        self.gps_speed = 0.0
        self.gps_satellites = 0
        self.gps_valid = False
        self.gps_last_nmea = ""
        self.gps_nmea_buf = [""] * 10
        self.gps_nmea_buf_idx = 0
        self.gps_nmea_buf_count = 0

        # ====================================================================
        # 10. КОНФИГУРАЦИЯ UART (ДЛЯ БУДУЩИХ МОДУЛЕЙ)
        # ====================================================================
        self.gw_rx_pin = 47
        self.gw_tx_pin = 46
        self.gw_baud_rate = 921600
        self.gw_configured = False

        self.arduino_rx_pin = 33
        self.arduino_tx_pin = 32
        self.arduino_baud_rate = 115200
        self.arduino_configured = False

        self.gps_rx_pin = 27
        self.gps_tx_pin = 26
        self.gps_baud_rate = 9600
        self.gps_configured = False

        # ====================================================================
        # 11. ПОЕЗДКИ (ТЕКУЩИЕ)
        # ====================================================================
        self.trip_active = False
        self.force_trip_active = False
        self.trip_start_time = 0
        self.trip_elapsed_sec = 0
        self.trip_pause_sec = 0
        self.trip_distance_m = 0
        self.trip_fuel_liters = 0.0
        self.trip_max_speed = 0
        self.trip_max_lph_x10 = 0
        self.trip_aggressive_count = 0
        self.trip_full_throttle_count = 0
        self.trip_moving_sec = 0
        self.trip_auto_stop_enabled = True

        self.trip_start_fuel = 0.0
        self.trip_start_odo = 0
        self.cycle_start_fuel = 0.0
        self.cycle_start_odo = 0

        self.drive_cycles = [DriveCycle() for _ in range(15)]
        self.drive_cycle_count = 0
        self.drive_cycle_last_save_time = 0

        self.engine_cycle_max_speed = 0
        self.engine_cycle_avg_speed = 0
        self.engine_cycle_avg_consumption_x10 = 0
        self.engine_cycle_distance_m = 0
        self.engine_cycle_moving_sec = 0
        self.engine_cycle_fuel_used = 0.0
        self.engine_cycle_valid = False

        self.odoManualSetTimeMs = 0
        self.day_max_speed = 0
        self.day_avg_speed = 0
        self.day_avg_consumption_x10 = 0
        self.day_stats_valid = False

        self.trip_force_active = False
        self.last_valid_coolant_temp = -2147483648

        # ====================================================================
        # 12. ИНТЕРНЕТ-РЕЖИМ
        # ====================================================================
        self.internet_mode_active = False
        self.ftp_server_active = False

        # ====================================================================
        # 13. КЛИМАТ-КОНТРОЛЬ (ЗАДЕЛ НА БУДУЩЕЕ)
        # ====================================================================
        self.ntcHeaterOut = 0.0
        self.ntcCabin     = 0.0
        self.ntcDriverFeet = 0.0
        self.ntcPassengerFeet = 0.0
        self.ntcTrunk = 0.0
        self.ntcCabinCenter = 0.0

        self.ntcHeaterOutDirty = False
        self.ntcCabinDirty = False
        self.ntcDriverFeetDirty = False
        self.ntcPassengerFeetDirty = False
        self.ntcTrunkDirty = False
        self.ntcCabinCenterDirty = False

        self.fanCurrentPWM1 = 0
        self.fanCurrentPWM2 = 0
        self.climateCurrentPWM = 0
        self.trunkFanPWM = 0
        self.damperPosition = 0
        self.airDirection = 0

        self.fan1Dirty = False
        self.fan2Dirty = False
        self.heaterDirty = False
        self.trunkFanDirty = False
        self.damperDirty = False
        self.airDirDirty = False

        self.fanAutoMode = True
        self.climateAutoMode = True
        self.damperAutoMode = True
        self.fanManualPWM = 0
        self.climateManualPWM = 0

        self.fanModeDirty = False
        self.climateModeDirty = False
        self.damperModeDirty = False

        self.arduino_coolant_temp = 0.0
        self.arduino_coolant_dirty = False
        self.arduino_fan_mode = 1
        self.arduino_mode_from_screen = False
        self.arduino_temp_offset = 0.0
        self.arduino_offset_received = False
        self.arduino_offset_pending = False

        self.climate_target_temp = 22.0
        self.cabin_temp = 22.0
        self.heater_pwm = 0
        self.climate_target_dirty = False
        self.cabin_temp_dirty = False
        self.heater_pwm_dirty = False

        self.fanSetpoint = 95.5
        self.fanKp = 30.0
        self.fanKi = 2.0
        self.fanKd = 5.0
        self.climateSetpoint = 22.0

        self.climateCalibStartPoint = 0
        self.climateCalibStopPoint = 0
        self.climateCalibNoiseLow = 0
        self.climateCalibNoiseHigh = 0

        self.climate_cabin_temp = 22.0
        self.climate_humidity = 50.0
        self.climate_ntc_driver_feet = 25.0
        self.climate_ntc_outlet = 30.0
        self.climate_ntc_outside = 10.0
        self.climate_flow_angle = 90
        self.climate_temp_angle = 90
        self.climate_auto_mode = 1
        self.climate_preset = 1
        self.climate_inlet_relay = 0
        self.climate_data_updated = False
        self.last_module01_packet_time = 0

        self.climate_target_pending = False
        self.heater_pwm_pending = False
        self.climate_auto_pending = False
        self.climate_auto_value = 0

        # ====================================================================
        # 14. СЛУЖЕБНЫЕ ФЛАГИ
        # ====================================================================
        self.configDirty = False
        self.requestConfigSync = False
        self.apiRequestPending = False
        self.apiRequestId = 0
        self.apiResponseValid = False

        self.activePresetId = 0
        self.presetPending = False

    # ========================================================================
    #                           МЕТОДЫ ДОСТУПА
    # ========================================================================

    def lock(self, timeout: float = -1.0):
        """
        Контекстный менеджер для потокобезопасного доступа.
        Использование:
        with state.lock():
            state.rpmValue = 1000
        """
        return self._lock_context(timeout)

    @contextmanager
    def _lock_context(self, timeout: float):
        acquired = self._lock.acquire(timeout=timeout)
        try:
            yield acquired
        finally:
            if acquired:
                self._lock.release()

    # ========================================================================
    #                           ЦВЕТА ИНТЕРФЕЙСА
    # ========================================================================

    def getFuelColor(self) -> int:
        if self.fuelValue < self.fuelRedThreshold: return self.colorRed
        if self.fuelValue < self.fuelYellowThreshold: return self.colorYellow
        return self.colorGreen

    def getBatteryColor(self) -> int:
        if self.batValue < self.battLowThreshold or self.batValue > self.battHighThreshold:
            return self.colorRed
        return self.colorGreen

    def getTempColor(self) -> int:
        if self.tempValue < self.tempCold: return self.colorBlue
        if self.tempValue <= self.tempNormal: return self.colorGreen
        if self.tempValue <= self.tempWarm: return self.colorCyan
        if self.tempValue <= self.tempHot: return self.colorYellow
        return self.colorRed

    def getSpeedColor(self) -> int:
        s = self.speedValue
        if 0 <= s <= self.speedLow: return self.colorBlue
        if (self.speedMidLow <= s <= self.speedMidHigh) or (self.speedHighLow <= s <= self.speedHighHigh):
            return self.colorOrange
        if self.speedVHighLow <= s <= self.speedVHighHigh: return self.colorYellow
        if s > self.speedVHighHigh: return self.colorRed
        return self.colorCyan

    def getRPMColor(self) -> int:
        if self.rpmValue <= self.rpmBlueMax: return self.colorBlue
        if self.rpmValue <= self.rpmCyanMax: return self.colorCyan
        if self.rpmValue <= self.rpmYellowMax: return self.colorYellow
        return self.colorRed

    def getLPHColor(self) -> int:
        if self.lphValue <= self.lphBlueMax: return self.colorBlue
        if self.lphValue <= self.lphCyanMax: return self.colorCyan
        if self.lphValue <= self.lphYellowMax: return self.colorYellow
        return self.colorRed

    @staticmethod
    def formatTimeHMS(totalSeconds: int) -> str:
        """Форматирует секунды в строку HH:MM:SS."""
        hours = totalSeconds // 3600
        minutes = (totalSeconds % 3600) // 60
        seconds = totalSeconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

# ============================================================================
#                         СИНГЛТОН (ГЛОБАЛЬНЫЙ ДОСТУП)
# ============================================================================

_instance = FionaState()

def get_state() -> FionaState:
    """
    Возвращает глобальный экземпляр состояния.
    Любой модуль может импортировать эту функцию и получить доступ к данным.
    """
    return _instance
