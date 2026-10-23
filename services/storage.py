# /home/mrak/projects/Python/fiona_brain/services/storage.py

import json
import os
import time
import logging
import config
from core.state import get_state

logger = logging.getLogger(__name__)

# Путь к папке с данными и файлам
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
STATE_FILE = os.path.join(DATA_DIR, "state.json")
TEMP_FILE = os.path.join(DATA_DIR, "state.tmp")
PRESETS_FILE = os.path.join(DATA_DIR, "fuel_presets.json")


class StorageManager:
    def __init__(self):
        self._last_save_time = 0
        self._save_interval = 10.0
        self._dirty = False

        # Создаем папку data, если ее нет (при первом запуске)
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)

    def load_state(self) -> bool:
        """Загружает состояние из файла при старте."""
        if not os.path.exists(STATE_FILE):
            logger.info("Файл состояния не найден. Используем значения по умолчанию.")
            return False

        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            state = get_state()
            with state.lock():
                # --- Общие данные ---
                state.fuelValue = data.get("fuelValue", state.fuelValue)
                state.odoMiles = data.get("odoMiles", state.odoMiles)
                state.odoKm = data.get("odoKm", state.odoKm)

                # --- Калибровочные коэффициенты и допуски ---
                state.fuelCalibrationFactor = data.get("fuelCalibrationFactor", state.fuelCalibrationFactor)
                state.odo_tolerance = data.get("odo_tolerance", state.odo_tolerance)
                state.fuel_tolerance = data.get("fuel_tolerance", state.fuel_tolerance)

                # --- Флаги калибровки ---
                state.calibration_frozen = data.get("calibration_frozen", state.calibration_frozen)
                state.odo_calib_needed = data.get("odo_calib_needed", state.odo_calib_needed)
                state.fuel_calib_needed = data.get("fuel_calib_needed", state.fuel_calib_needed)

                # --- Состояние текущего цикла калибровки ---
                state.calibration_active = data.get("calibration_active", state.calibration_active)
                state.calibration_preset = data.get("calibration_preset", state.calibration_preset)
                state.calibration_start_km = data.get("calibration_start_km", state.calibration_start_km)

                # --- Накопители за цикл калибровки ---
                state.calculatedDistanceSinceLastFull = data.get("calculatedDistanceSinceLastFull", state.calculatedDistanceSinceLastFull)
                state.totalRefueledSinceLastFull = data.get("totalRefueledSinceLastFull", state.totalRefueledSinceLastFull)
                state.calculatedFuelSinceLastFull = data.get("calculatedFuelSinceLastFull", state.calculatedFuelSinceLastFull)

                # --- Старые поля калибровки ---
                state.lastFullOdoKm = data.get("lastFullOdoKm", state.lastFullOdoKm)
                state.hasFirstFullTank = data.get("hasFirstFullTank", state.hasFirstFullTank)
                state.calibrationNeeded = data.get("calibrationNeeded", state.calibrationNeeded)
                state.fuel_calib_flags = data.get("fuel_calib_flags", state.fuel_calib_flags)

            logger.info(f"Состояние загружено. Бак: {state.fuelValue:.1f} Л, Одометр: {state.odoMiles} миль")
            return True

        except Exception as e:
            logger.error(f"Ошибка загрузки состояния: {e}")
            return False

    def request_save(self):
        """Помечает состояние как измененное (для отложенного сохранения)."""
        self._dirty = True

    def save_state(self, force: bool = False):
        """
        Сохраняет состояние на диск (атомарно).
        В режиме эмуляции НИЧЕГО не сохраняет, чтобы не затереть реальные данные!
        """
        # ЗАЩИТА: В режиме эмуляции ничего не пишем на диск
        if config.EMULATION_MODE:
            return

        now = time.time()
        if not force and (not self._dirty or (now - self._last_save_time < self._save_interval)):
            return

        state = get_state()
        data_to_save = {}

        with state.lock():
            data_to_save = {
                "fuelValue": state.fuelValue,
                "odoMiles": state.odoMiles,
                "odoKm": state.odoKm,
                "fuelCalibrationFactor": state.fuelCalibrationFactor,
                "odo_tolerance": state.odo_tolerance,
                "fuel_tolerance": state.fuel_tolerance,
                "calibration_frozen": state.calibration_frozen,
                "odo_calib_needed": state.odo_calib_needed,
                "fuel_calib_needed": state.fuel_calib_needed,
                "calibration_active": state.calibration_active,
                "calibration_preset": state.calibration_preset,
                "calibration_start_km": state.calibration_start_km,
                "calculatedDistanceSinceLastFull": state.calculatedDistanceSinceLastFull,
                "totalRefueledSinceLastFull": state.totalRefueledSinceLastFull,
                "calculatedFuelSinceLastFull": state.calculatedFuelSinceLastFull,
                "lastFullOdoKm": state.lastFullOdoKm,
                "hasFirstFullTank": state.hasFirstFullTank,
                "calibrationNeeded": state.calibrationNeeded,
                "fuel_calib_flags": state.fuel_calib_flags,
            }

        try:
            # Атомарная запись: пишем в tmp, потом переименовываем
            with open(TEMP_FILE, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=2, ensure_ascii=False)

            os.replace(TEMP_FILE, STATE_FILE)

            self._last_save_time = now
            self._dirty = False
            logger.debug("Состояние успешно сохранено на диск.")

        except Exception as e:
            logger.error(f"Ошибка сохранения состояния: {e}")

    # ========================================================================
    #                         РАБОТА С ПРЕСЕТАМИ
    # ========================================================================

    def load_presets(self) -> dict:
        """Загружает пресеты заправок из JSON."""
        if not os.path.exists(PRESETS_FILE):
            return {}
        try:
            with open(PRESETS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки пресетов: {e}")
            return {}

    def save_presets(self, presets: dict):
        """
        Сохраняет пресеты заправок.
        В режиме эмуляции НИЧЕГО не сохраняет!
        """
        # ЗАЩИТА: В режиме эмуляции ничего не пишем на диск
        if config.EMULATION_MODE:
            return

        try:
            # Убедимся, что папка существует
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(PRESETS_FILE, 'w', encoding='utf-8') as f:
                json.dump(presets, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Ошибка сохранения пресетов: {e}")
