# /home/mrak/projects/Python/fiona_telemetry/telemetry_sender.py

import socketio
import logging

logger = logging.getLogger(__name__)

class TelemetrySender:
    """
    Класс для отправки телеметрии в LIVI по протоколу Socket.IO.
    LIVI слушает порт 4000 на localhost.
    """
    def __init__(self, url="http://127.0.0.1:4000"):
        self.url = url
        self.sio = socketio.Client(logger=False, engineio_logger=False)
        self._register_events()

    def _register_events(self):
        @self.sio.event
        def connect():
            logger.info("Успешно подключено к LIVI (Socket.IO)")

        @self.sio.event
        def connect_error(data):
            logger.error(f"Ошибка подключения к LIVI: {data}")

        @self.sio.event
        def disconnect():
            logger.info("Отключено от LIVI")

    def connect(self) -> bool:
        try:
            # wait_timeout=2 означает, что если LIVI не отвечает за 2 сек, будет ошибка
            self.sio.connect(self.url, wait_timeout=2)
            return True
        except Exception as e:
            logger.error(f"Не удалось подключиться к LIVI: {e}")
            return False

    def send(self, payload: dict):
        """
        Отправляет словарь с данными в LIVI.
        Согласно документации, событие называется 'telemetry:push'.
        """
        if self.sio.connected:
            self.sio.emit('telemetry:push', payload)
        else:
            logger.warning("Попытка отправить данные, но нет связи с LIVI.")
