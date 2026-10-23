# /home/mrak/projects/Python/fiona_brain/core/engine.py

import time
import logging
from core.state import get_state
from hardware.elm327 import ELM327
from hardware.parser import FordFocus2001Parser

logger = logging.getLogger(__name__)

class DataEngine:
    """
    Двигатель опроса OBD-II.
    Управляет таймингами, приоритетами и сглаживанием данных.
    """
    def __init__(self, elm: ELM327):
        self.elm = elm
        self.state = get_state()

        # Словарь с PID'ами и интервалами (в миллисекундах)
        self.pids = {
            "0110": {"interval": 300,  "last_req": 0.0, "priority": 1}, # MAF (высший)
            "010D": {"interval": 300,  "last_req": 0.0, "priority": 2}, # Скорость
            "010C": {"interval": 500,  "last_req": 0.0, "priority": 3}, # Обороты
            "0105": {"interval": 1000, "last_req": 0.0, "priority": 4}, # Температура ОЖ
            "ATRV": {"interval": 500,  "last_req": 0.0, "priority": 4}, # Напряжение
            "0106": {"interval": 1000, "last_req": 0.0, "priority": 5}, # STFT
            "0107": {"interval": 1000, "last_req": 0.0, "priority": 5}, # LTFT
        }

        # --- Переменные для сглаживания Скорости ---
        self._speed_raw_history = [0.0, 0.0, 0.0]
        self._speed_times = [0.0, 0.0, 0.0]
        self._speed_history_idx = 0
        self._speed_smoothed = 0.0
        self._last_speed_smooth_time = 0.0

        # --- Переменные для сглаживания Оборотов ---
        self._rpm_raw_history = [0.0, 0.0, 0.0]
        self._rpm_times = [0.0, 0.0, 0.0]
        self._rpm_history_idx = 0
        self._rpm_smoothed = 0.0
        self._last_rpm_smooth_time = 0.0

    def process(self):
        """
        Главный цикл опроса. Вызывается регулярно из main.py.
        """
        now = time.time() * 1000.0  # Время в миллисекундах

        # 1. Выбираем следующий периодический PID
        selected_pid = None
        max_delay = 0.0

        # Гарантия MAF: если он просрочен, выбирается всегда
        maf_data = self.pids["0110"]
        if now - maf_data["last_req"] >= maf_data["interval"]:
            selected_pid = "0110"
        else:
            # Ищем самый просроченный среди остальных
            for pid, data in self.pids.items():
                if pid == "0110":
                    continue
                elapsed = now - data["last_req"]
                if elapsed >= data["interval"]:
                    if elapsed > max_delay:
                        max_delay = elapsed
                        selected_pid = pid

        if selected_pid:
            # Запрашиваем данные (таймаут 500 мс)
            raw_response = self.elm.send_command(selected_pid, timeout=0.5)

            # Парсим
            value = FordFocus2001Parser.parse_elm327_response(raw_response, selected_pid)

            # Обновляем время последнего запроса
            self.pids[selected_pid]["last_req"] = now

            # Обрабатываем полученное значение
            if raw_response and "NO DATA" not in raw_response:
                with self.state.lock():
                    if selected_pid == "0110":
                        self.state.mafValue = value
                        self.state.mafDirty = True
                        # Пересчет LPH (базовый, без коррекций)
                        self.state.lphValue = value * 0.32653
                        self.state.lphDirty = True

                    elif selected_pid == "010D":
                        self.state.speedValue = int(value)
                        self.state.speedDirty = True
                        self._add_speed_sample(value, now)

                    elif selected_pid == "010C":
                        self.state.rpmValue = int(value)
                        self.state.rpmDirty = True
                        self._add_rpm_sample(value, now)

                    elif selected_pid == "0105":
                        self.state.tempValue = int(value)
                        self.state.tempDirty = True

                    elif selected_pid == "ATRV":
                        if 8.0 <= value <= 16.0: # Защита от мусора
                            self.state.batValue = value
                            self.state.batDirty = True

                    elif selected_pid == "0106":
                        self.state.stft = value
                        self.state.stftDirty = True

                    elif selected_pid == "0107":
                        self.state.ltft = value
                        self.state.ltftDirty = True

        # 2. Сглаживание
        self._smooth_values()

    # ========================================================================
    #                         ЛОГИКА СГЛАЖИВАНИЯ
    # ========================================================================
    def _add_speed_sample(self, value: float, timestamp: float):
        self._speed_raw_history[self._speed_history_idx] = value
        self._speed_times[self._speed_history_idx] = timestamp
        self._speed_history_idx = (self._speed_history_idx + 1) % 3
        self._speed_smoothed = value

    def _add_rpm_sample(self, value: float, timestamp: float):
        self._rpm_raw_history[self._rpm_history_idx] = value
        self._rpm_times[self._rpm_history_idx] = timestamp
        self._rpm_history_idx = (self._rpm_history_idx + 1) % 3
        self._rpm_smoothed = value

    def _calculate_trend_step(self, history: list, times: list, idx: int) -> float:
        i0 = (idx + 2) % 3
        i1 = (idx + 1) % 3
        i2 = (idx + 0) % 3

        if times[i1] == 0 or times[i2] == 0:
            return 0.0

        if times[i0] != 0:
            diff1 = history[i1] - history[i0]
            diff2 = history[i2] - history[i1]
            if diff1 * diff2 < 0:
                return 0.0
            return (diff1 + diff2) / 2.0 / 5.0
        else:
            return (history[i2] - history[i1]) / 5.0

    def _smooth_values(self):
        now = time.time() * 1000.0
        with self.state.lock():
            if self._last_speed_smooth_time == 0:
                self._last_speed_smooth_time = now
            if now - self._last_speed_smooth_time >= 50:
                step = self._calculate_trend_step(self._speed_raw_history, self._speed_times, self._speed_history_idx)
                if abs(step) > 0.001:
                    self._speed_smoothed += step
                    last_real = self._speed_raw_history[(self._speed_history_idx + 2) % 3]
                    if (step > 0 and self._speed_smoothed > last_real) or \
                       (step < 0 and self._speed_smoothed < last_real):
                        self._speed_smoothed = last_real
                    new_speed = int(round(self._speed_smoothed))
                    if new_speed != self.state.speedValue:
                        self.state.speedValue = new_speed
                        self.state.speedDirty = True
                self._last_speed_smooth_time = now

            if self._last_rpm_smooth_time == 0:
                self._last_rpm_smooth_time = now
            if now - self._last_rpm_smooth_time >= 50:
                step = self._calculate_trend_step(self._rpm_raw_history, self._rpm_times, self._rpm_history_idx)
                if abs(step) > 0.001:
                    self._rpm_smoothed += step
                    last_real = self._rpm_raw_history[(self._rpm_history_idx + 2) % 3]
                    if (step > 0 and self._rpm_smoothed > last_real) or \
                       (step < 0 and self._rpm_smoothed < last_real):
                        self._rpm_smoothed = last_real
                    new_rpm = int(round(self._rpm_smoothed))
                    if new_rpm != self.state.rpmValue:
                        self.state.rpmValue = new_rpm
                        self.state.rpmDirty = True
                self._last_rpm_smooth_time = now
