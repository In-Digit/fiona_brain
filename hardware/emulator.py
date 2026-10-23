# /home/mrak/projects/Python/fiona_brain/hardware/emulator.py

import time
import random
import logging

logger = logging.getLogger(__name__)

class Emulator:
    """
    Эмулятор ELM327 для тестирования без машины.
    Имитирует работу двигателя и возвращает ответы в формате ELM327.
    """
    def __init__(self):
        self._connected = False
        self._state = "STOPPED" # STOPPED, ACCEL, CRUISE, DECEL
        self._state_start_time = time.time()

        # Текущие значения
        self._rpm = 800.0
        self._speed = 0.0
        self._coolant = 20.0
        self._voltage = 14.0
        self._maf = 2.0

        # Константы для имитации движения
        self._accel_rate = 2.5
        self._decel_rate = 2.0
        self._cruise_speed = 100.0

    def connect(self) -> bool:
        logger.info("[EMU] Подключение к эмулятору ELM327...")
        self._connected = True
        return True

    def disconnect(self):
        logger.info("[EMU] Отключение от эмулятора.")
        self._connected = False

    def initialize(self) -> bool:
        logger.info("[EMU] Инициализация эмулятора...")
        return True

    def test_connection(self) -> bool:
        logger.info("[EMU] Проверка связи с эмулятором ЭБУ...")
        return True

    def send_command(self, cmd: str, wait_prompt: bool = True, timeout: float = None) -> str:
        if not self._connected:
            return ""

        # Обновляем состояние (как в OBDEngine::updateEmulation)
        self._update_emulation()

        # Формируем ответ в HEX-формате
        if cmd == "010C": # RPM
            raw_rpm = int(self._rpm * 4)
            byte_a = (raw_rpm >> 8) & 0xFF
            byte_b = raw_rpm & 0xFF
            return f"410C{byte_a:02X}{byte_b:02X}\r\r>"

        elif cmd == "010D": # Speed
            byte_a = int(self._speed) & 0xFF
            return f"410D{byte_a:02X}\r\r>"

        elif cmd == "0105": # Coolant
            byte_a = (int(self._coolant) + 40) & 0xFF
            return f"4105{byte_a:02X}\r\r>"

        elif cmd == "0110": # MAF
            raw_maf = int(self._maf * 100)
            byte_a = (raw_maf >> 8) & 0xFF
            byte_b = raw_maf & 0xFF
            return f"4110{byte_a:02X}{byte_b:02X}\r\r>"

        elif cmd == "ATRV": # Voltage
            return f"{self._voltage:.1f}V\r\r>"

        elif cmd == "0106": # STFT (Short Term Fuel Trim)
            # 0% коррекции = 128 (0x80)
            return "410680\r\r>"

        elif cmd == "0107": # LTFT (Long Term Fuel Trim)
            # 0% коррекции = 128 (0x80)
            return "410780\r\r>"

        return "NO DATA\r\r>"

    def _update_emulation(self):
        now = time.time()
        dt = now - self._state_start_time
        if dt <= 0 or dt > 1.0:
            dt = 0.05
        self._state_start_time = now

        if self._state == "STOPPED":
            self._speed = 0
            self._rpm = 800.0 + 50.0 * random.random() # Легкое покачивание
            self._coolant += (20.0 - self._coolant) * 0.005 * dt

            # Случайно начинаем движение
            if random.random() < 0.01:
                self._state = "ACCEL"

        elif self._state == "ACCEL":
            self._speed += self._accel_rate * dt
            if self._speed >= self._cruise_speed:
                self._speed = self._cruise_speed
                self._state = "CRUISE"

            self._rpm = 800.0 + self._speed * 35.0
            if self._rpm > 3800: # Переключение передачи
                self._rpm = 2200.0
            self._coolant += (90.0 - self._coolant) * 0.03 * dt

        elif self._state == "CRUISE":
            self._speed = self._cruise_speed
            self._rpm = 2600.0 + 300.0 * random.random()
            self._coolant += (95.0 - self._coolant) * 0.01 * dt

            if random.random() < 0.005: # Редкое торможение
                self._state = "DECEL"

        elif self._state == "DECEL":
            self._speed -= self._decel_rate * dt
            if self._speed <= 0:
                self._speed = 0
                self._state = "STOPPED"

            self._rpm = 800.0 + self._speed * 20.0
            if self._rpm < 800: self._rpm = 800.0
            self._coolant += (85.0 - self._coolant) * 0.005 * dt

        # MAF зависит от оборотов
        self._maf = (self._rpm / 800.0) * 1.8 + 0.5
        # Напряжение плавает
        self._voltage = 14.0 + 0.2 * random.random()
