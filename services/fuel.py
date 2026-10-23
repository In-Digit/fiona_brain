# /home/mrak/projects/Python/fiona_brain/services/fuel.py

import time
import math
import logging
import config
import json
import os
from core.state import get_state

logger = logging.getLogger(__name__)

USEFUL_TANK_LITERS = 55.0
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
PRESETS_FILE = os.path.join(DATA_DIR, "fuel_presets.json")

class FuelManager:
    """
    Виртуальный бак с продвинутой системой калибровки.
    Считает расход, интегрирует пробег, управляет пресетами заправок
    и использует "черепаший" алгоритм уменьшения погрешности.
    """
    def __init__(self):
        self._last_process_time = 0
        self._fuel_remainder_l = USEFUL_TANK_LITERS

        # Словарь для хранения текущего состава бака (алиас: литры)
        self.tank_mix = {}

        # Загружаем базу пресетов при старте
        self.presets = self._load_presets()

    def begin(self):
        """Инициализация при старте системы."""
        state = get_state()
        with state.lock():
            self._fuel_remainder_l = state.fuelValue

            # Если в баке уже есть топливо при старте, но мы не знаем его состав,
            # считаем, что это дефолтный бензин (коэффициент 1.0)
            if self._fuel_remainder_l > 0:
                self.tank_mix["default"] = self._fuel_remainder_l

            # Пересчитываем текущий коэффициент на основе состава бака
            self._update_mixed_calibration(state)

    def _load_presets(self) -> dict:
        """Загружает базу пресетов заправок из JSON."""
        if not os.path.exists(PRESETS_FILE):
            return {}
        try:
            with open(PRESETS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки пресетов: {e}")
            return {}

    def _save_presets(self):
        """Сохраняет базу пресетов в JSON."""
        try:
            # Убедимся, что папка существует
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(PRESETS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.presets, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Ошибка сохранения пресетов: {e}")

    def _update_mixed_calibration(self, state):
        """
        Вычисляет средневзвешенный коэффициент топлива для текущего содержимого бака.
        """
        total_liters = sum(self.tank_mix.values())
        if total_liters <= 0:
            state.current_fuel_calibration = 1.0
            return

        weighted_sum = 0.0
        for alias, liters in self.tank_mix.items():
            # Ищем коэффициент для этого алиаса. Если нет — 1.0 (дефолт)
            k = self.presets.get(alias, {}).get("calibration_factor", 1.0)
            weighted_sum += liters * k

        state.current_fuel_calibration = weighted_sum / total_liters

    def process(self):
        """
        Интеграция расхода и пробега. Вызывается каждую секунду.
        """
        state = get_state()
        now = time.time()

        if now - self._last_process_time < 1.0:
            return
        dt = now - self._last_process_time
        self._last_process_time = now

        with state.lock():
            # 1. Накопление расчетного пробега (только если едем и двигатель работает)
            if state.rpmValue > 100 and state.speedValue > 0:
                # speedValue в км/ч. Переводим в км/сек и умножаем на dt.
                dist_km = (state.speedValue / 3600.0) * dt
                state.calculatedDistanceSinceLastFull += dist_km

                # Если идет калибровка, накапливаем и общий пробег
                # (в реальной системе тут еще обновлялся бы суточный одометр)

            # 2. Расчет и вычитание топлива
            if state.rpmValue > 100:
                # Базовый "сырой" расход по MAF (без учета калибровки)
                raw_lps = state.lphValue / 3600.0

                # Сначала копим "сырой" расход для калибровки
                if state.calibration_active:
                    state.calculatedFuelSinceLastFull += (raw_lps * dt)

                # Применяем текущий смешанный коэффициент и вычитаем из бака
                actual_lps = raw_lps * state.current_fuel_calibration
                liters_to_subtract = actual_lps * dt

                if self._fuel_remainder_l >= liters_to_subtract:
                    self._fuel_remainder_l -= liters_to_subtract
                else:
                    self._fuel_remainder_l = 0.0
                    # УМНЫЙ ФЛАГ: Если бак пуст, но мы едем - значит расход считался неверно.
                    if state.speedValue > 0:
                        state.fuel_calib_needed = True

                # Обновляем значение в общем состоянии
                state.fuelValue = round(self._fuel_remainder_l, 2)
                state.fuelDirty = True

            # 3. Обновление запаса хода
            self._update_range(state)

    def _update_range(self, state):
        """Обновление запаса хода."""
        # Упрощенная логика: если есть средний расход, используем его, иначе мгновенный
        avg_l100km = state.lastAvgL100km
        if avg_l100km <= 0.0 and state.speedValue > 0 and state.lphValue > 0:
            avg_l100km = state.lphValue / (state.speedValue / 100.0)

        range_val = 500
        if avg_l100km > 0.0:
            range_val = int(state.fuelValue / avg_l100km * 100.0)
            range_val = max(0, min(500, range_val))

        if range_val != state.rangeValue:
            state.rangeValue = range_val
            state.rangeDirty = True

    def handle_refuel(self, liters: float, is_full_tank: bool, odo_miles: int, fuel_price: float, alias: str):
        """
        Обработка заправки.
        alias - это произвольное имя (например, "Газпром_Мира").
        """
        state = get_state()

        # Переводим мили в километры для расчетов
        entered_odo_km = int(odo_miles * 1.60934)

        with state.lock():
            # 1. Обновляем общий одометр (пользователь ввел новое значение)
            state.odoMiles = odo_miles
            state.odoKm = entered_odo_km
            state.odoDirty = True

            # 2. Проверка на "Умные флаги" ДО изменения бака
            # Если разница между введенным одометром и тем, что мы насчитали, велика:
            if not state.calibration_active:
                # Ожидаемый одометр (старый + то, что мы проехали с последнего ввода)
                # Примечание: в реальности нужно хранить last_entered_odo.
                # Пока используем логику: если мы ввели одометр, и он сильно отличается от того, что было + наши расчеты.
                pass # (Реализуем чуть позже, когда будет полный трекер пробега)

            # 3. Проверка на переполнение бака (Умный флаг)
            if self._fuel_remainder_l + liters > USEFUL_TANK_LITERS:
                state.fuel_calib_needed = True

            # 4. Логика калибровки (Запуск / Остановка)
            if is_full_tank:
                # Если калибровка заморожена, НО есть флаг "нужна калибровка", снимаем заморозку
                if state.calibration_frozen and (state.odo_calib_needed or state.fuel_calib_needed):
                    logger.info("Снята заморозка калибровки из-за активного флага расхождения.")
                    state.calibration_frozen = False

                if not state.calibration_frozen:
                    if not state.calibration_active:
                        # СТАРТ ЦИКЛА КАЛИБРОВКИ
                        self._start_calibration_cycle(state, alias, entered_odo_km)
                    else:
                        # КОНЕЦ ЦИКЛА КАЛИБРОВКИ
                        self._finish_calibration_cycle(state, alias, entered_odo_km, liters)

                # В любом случае при полной заправке бак становится полным
                self._fuel_remainder_l = USEFUL_TANK_LITERS
                self.tank_mix = {alias: USEFUL_TANK_LITERS}

                # Записываем "сырые" данные на случай, если следующая заправка начнет новый цикл
                state.calibration_start_km = entered_odo_km
                state.totalRefueledSinceLastFull = 0.0

            else:
                # ЧАСТИЧНАЯ ЗАПРАВКА
                # Если идет калибровка, копим реальные литры
                if state.calibration_active:
                    state.totalRefueledSinceLastFull += liters

                # Добавляем в бак (с учетом переполнения)
                self._fuel_remainder_l = min(USEFUL_TANK_LITERS, self._fuel_remainder_l + liters)

                # Обновляем состав смеси
                current_mix_liters = sum(self.tank_mix.values())
                # Если бак был неполным, а мы долили больше, чем влезает, пропорции чуть плывут,
                # но для простоты мы просто нормализуем.
                if current_mix_liters + liters > USEFUL_TANK_LITERS:
                    # Сжимаем старую смесь
                    scale = (USEFUL_TANK_LITERS - liters) / current_mix_liters if current_mix_liters > 0 else 0
                    for k in self.tank_mix:
                        self.tank_mix[k] *= scale

                if alias in self.tank_mix:
                    self.tank_mix[alias] += liters
                else:
                    self.tank_mix[alias] = liters

            # 5. Обновляем цену и фиксируем изменения
            state.fuelPrice = fuel_price
            state.fuelValue = self._fuel_remainder_l
            state.fuelDirty = True

            # Пересчитываем коэффициент смеси для бака
            self._update_mixed_calibration(state)

            # Сохраняем обновленные пресеты на диск
            self._save_presets()

            logger.info(f"Заправка ({alias}): {liters:.1f} Л. В баке: {self._fuel_remainder_l:.1f} Л. Текущий K: {state.current_fuel_calibration:.3f}")

    def _start_calibration_cycle(self, state, alias, start_odo_km):
        """Начинает новый цикл калибровки."""
        state.calibration_active = True
        state.calibration_preset = alias
        state.calibration_start_km = start_odo_km

        # Сбрасываем накопители
        state.calculatedDistanceSinceLastFull = 0.0
        state.calculatedFuelSinceLastFull = 0.0
        state.totalRefueledSinceLastFull = 0.0 # Сюда попадут только промежуточные доливы

        logger.info(f"=== СТАРТ КАЛИБРОВКИ ({alias}) ===")

    def _finish_calibration_cycle(self, state, alias, end_odo_km, final_liters):
        """Завершает цикл калибровки, вычисляет коэффициенты."""
        # Считаем реальные значения
        state.totalRefueledSinceLastFull += final_liters # Добавляем последнюю заправку
        fact_dist_km = end_odo_km - state.calibration_start_km
        fact_fuel_l = state.totalRefueledSinceLastFull

        logger.info(f"=== КОНЕЦ КАЛИБРОВКИ ===")
        logger.info(f"Пробег факт/расчет: {fact_dist_km} / {state.calculatedDistanceSinceLastFull:.1f} км")
        logger.info(f"Топливо факт/расчет: {fact_fuel_l:.1f} / {state.calculatedFuelSinceLastFull:.1f} л")

        # 1. Вычисляем сырые коэффициенты (если деление на ноль не случится)
        k_dist_raw = 1.0
        if state.calculatedDistanceSinceLastFull > 0 and fact_dist_km > 0:
            k_dist_raw = fact_dist_km / state.calculatedDistanceSinceLastFull

        k_fuel_raw = 1.0
        if state.calculatedFuelSinceLastFull > 0 and fact_fuel_l > 0:
            k_fuel_raw = fact_fuel_l / state.calculatedFuelSinceLastFull

        # 2. Обновляем коэффициент топлива (с учетом EMA и допусков)
        self._apply_calibration_math(state, k_fuel_raw, alias)

        # 3. Обновляем допуски (Зенон)
        state.odo_tolerance = max(0.01, state.odo_tolerance * 0.75) # Минимум 1%
        state.fuel_tolerance = max(0.01, state.fuel_tolerance * 0.75)

        logger.info(f"Новые допуски: Одометр {state.odo_tolerance*100:.1f}%, Топливо {state.fuel_tolerance*100:.1f}%")

        # 4. Сбрасываем флаги и состояние
        state.calibration_active = False
        state.odo_calib_needed = False
        state.fuel_calib_needed = False
        state.calibration_frozen = True # Возвращаем заморозку
        state.calibration_preset = ""

    def _apply_calibration_math(self, state, k_raw, alias):
        """Применяет математику мёртвой зоны и EMA к коэффициенту топлива."""
        # Получаем текущий коэффициент для этого алиаса (или глобальный, если нет)
        preset_data = self.presets.get(alias, {"calibration_factor": 1.0, "system_stars": 0, "user_stars": 0})
        k_old = preset_data["calibration_factor"]

        # Мёртвая зона
        if abs(k_raw - k_old) < state.fuel_tolerance:
            logger.info(f"Калибровка пропущена (в пределах допуска {state.fuel_tolerance*100:.1f}%): raw {k_raw:.3f}, old {k_old:.3f}")
            return

        # EMA и ограничение [0.7, 1.3]
        k_new = k_old + 0.2 * (k_raw - k_old)
        k_new = max(0.7, min(1.3, k_new))

        logger.info(f"Калибровка обновлена для '{alias}': raw {k_raw:.3f} -> new {k_new:.3f} (old {k_old:.3f})")

        # Сохраняем в пресеты
        if alias not in self.presets:
            self.presets[alias] = {"calibration_factor": 1.0, "system_stars": 0, "user_stars": 0, "total_liters": 0.0, "total_km": 0.0}

        self.presets[alias]["calibration_factor"] = k_new
        self.presets[alias]["total_liters"] += state.totalRefueledSinceLastFull

        # (Опционально: обновляем системные звезды здесь)

    def set_fuel_level_direct(self, fuel_liters: float):
        """Установить уровень топлива вручную."""
        state = get_state()
        with state.lock():
            self._fuel_remainder_l = min(USEFUL_TANK_LITERS, max(0.0, fuel_liters))
            self.tank_mix = {"default": self._fuel_remainder_l}
            state.fuelValue = self._fuel_remainder_l
            state.fuelDirty = True
            self._update_mixed_calibration(state)
            logger.info(f"Уровень топлива установлен вручную: {self._fuel_remainder_l:.1f} л")

    def cancel_calibration(self):
        """Принудительная отмена калибровки."""
        state = get_state()
        with state.lock():
            if state.calibration_active:
                state.calibration_active = False
                state.calibration_preset = ""
                state.calibration_frozen = True
                logger.warning("Калибровка отменена пользователем.")
