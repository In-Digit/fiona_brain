# /home/mrak/projects/Python/fiona_brain/services/udp_server.py

import socket
import threading
import time
import logging
from core.state import get_state
from core.protocol import (
    FionaProtocol, MAGIC_STREAM, MAGIC_MODULE, MAGIC_CMD,
    ID_PC, ID_BROADCAST, ID_UNDERHOOD, ID_CABIN
)

logger = logging.getLogger(__name__)

PORT_LISTEN = 5000
PORT_BROADCAST = 5000

class UDPServer:
    def __init__(self):
        self.state = get_state()
        self.running = False
        self._thread = None
        self._seq = 0  # Счетчик пакетов для стрима

        # Создаем UDP-сокет
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, 'SO_REUSEPORT'):
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.bind(('', PORT_LISTEN))
        self.sock.setblocking(False)

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info(f"UDP-сервер запущен на порту {PORT_LISTEN}")

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        self.sock.close()
        logger.info("UDP-сервер остановлен.")

    def _run_loop(self):
        last_stream_time = 0.0

        while self.running:
            try:
                # 1. Прием данных
                try:
                    data, addr = self.sock.recvfrom(1024)
                    self._process_incoming_packet(data, addr)
                except BlockingIOError:
                    pass

                # 2. Отправка стрима (раз в 100 мс)
                now = time.time()
                if now - last_stream_time >= 0.1:
                    last_stream_time = now
                    self._send_stream()

            except Exception as e:
                logger.error(f"Ошибка в UDP-цикле: {e}")
                time.sleep(0.1)

    def _process_incoming_packet(self, data: bytes, addr: tuple):
        """Разбор входящего пакета (данные от модуля или команда)."""
        if not data:
            return

        magic = data[0]

        # Если это данные от модуля (например, подкапотня прислала температуру)
        if magic == MAGIC_MODULE:
            src_id, seq, parsed_data = FionaProtocol.unpack_module_data(data)

            if src_id > 0 and parsed_data:
                # Обновляем наше состояние полученными данными
                with self.state.lock():
                    if src_id == ID_UNDERHOOD:
                        if "rad_temp" in parsed_data: self.state.ntcHeaterOut = parsed_data["rad_temp"]
                        if "outside_temp" in parsed_data: self.state.ntcCabin = parsed_data["outside_temp"]
                        if "fan1_pwm" in parsed_data: self.state.fanCurrentPWM1 = parsed_data["fan1_pwm"]
                        if "fan2_pwm" in parsed_data: self.state.fanCurrentPWM2 = parsed_data["fan2_pwm"]

                    elif src_id == ID_CABIN:
                        if "cabin_temp" in parsed_data: self.state.cabin_temp = parsed_data["cabin_temp"]
                        if "humidity" in parsed_data: self.state.climate_humidity = parsed_data["humidity"]
                        if "door_bits" in parsed_data:
                            # Пример сохранения битов концевиков (поле нужно добавить в state.py)
                            pass

                # Логируем факт приема (с ограничением, чтобы не спамить)
                # logger.debug(f"RX from {src_id}: {parsed_data}")

        # Если это команда (но сервер ноута обычно команды не принимает, только шлет)
        elif magic == MAGIC_CMD:
            # Заглушка на будущее (если модули начнут слать команды ноуту)
            pass

    def _send_stream(self):
        """Формирует и рассылает пакет со стримом от ноута (0xAA)."""
        self._seq = (self._seq + 1) & 0xFF

        with self.state.lock():
            # Собираем битовую маску флагов (Бит 7 в карте полей)
            flags = 0
            if self.state.rpmValue > 100: flags |= (1 << 0)
            if self.state.calibration_active: flags |= (1 << 1)
            if self.state.calibration_frozen: flags |= (1 << 2)
            if self.state.fuel_calib_needed: flags |= (1 << 3)
            if self.state.odo_calib_needed: flags |= (1 << 4)

            # Формируем словарь с данными для отправки
            data_to_send = {
                "rpm": self.state.rpmValue,
                "speed": self.state.speedValue,
                "coolant": self.state.tempValue,
                "voltage": self.state.batValue,
                "fuel": self.state.fuelValue,
                "range_km": self.state.rangeValue,
                "odo_km": self.state.odoKm,
                "flags": flags,
                "drive_mode": 1,      # Заглушка (город)
                "driving_style": 1,   # Заглушка (спокойно)
                "maf": self.state.mafValue,
                "timestamp": int(time.time())
            }

        # Упаковываем пакет через наш протокол
        packet = FionaProtocol.pack_stream(data_to_send, self._seq)

        # Отправляем Broadcast на все интерфейсы
        try:
            self.sock.sendto(packet, ('255.255.255.255', PORT_BROADCAST))
        except Exception:
            pass
