# /home/mrak/projects/Python/fiona_brain/main.py

import time
import logging
import sys

from core.state import get_state
from hardware.elm327 import ELM327
from core.engine import DataEngine
from services.fuel import FuelManager
from services.telemetry import TelemetrySender
from services.storage import StorageManager
from services.udp_server import UDPServer
from services.web_server import WebServer
import config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

def main():
    state = get_state()

    # 0. Инициализация хранилища и загрузка состояния (до всего остального!)
    storage = StorageManager()
    storage.load_state()

    # 1. Инициализация логики топлива (после загрузки состояния, чтобы знать текущий бак)
    fuel_manager = FuelManager()
    fuel_manager.begin()

    # 2. Инициализация сети
    udp_server = UDPServer()
    udp_server.start()

    # 3. Инициализация веб-сервера (передаем ему менеджеры для управления)
    web_server = WebServer(fuel_manager, storage)
    web_server.start()

    # 4. Инициализация железа
    if config.EMULATION_MODE:
        from hardware.emulator import Emulator
        elm = Emulator()
        logger.info(">>> ЗАПУСК В РЕЖИМЕ ЭМУЛЯЦИИ <<<")
    else:
        elm = ELM327()

    if not elm.connect():
        logger.error("Не удалось подключиться к ELM327.")
        udp_server.stop(); web_server.stop(); sys.exit(1)

    if not elm.initialize():
        logger.error("Не удалось инициализировать ELM327.")
        elm.disconnect(); udp_server.stop(); web_server.stop(); sys.exit(1)

    if not elm.test_connection():
        logger.error("ЭБУ не отвечает.")
        elm.disconnect(); udp_server.stop(); web_server.stop(); sys.exit(1)

    # 5. Движок и отправка в LIVI
    engine = DataEngine(elm)

    sender = TelemetrySender()
    if not sender.connect():
        logger.warning("Работаем без LIVI.")

    logger.info("Все системы запущены. Начинаем главный цикл...")

    last_telemetry_time = 0.0

    try:
        while True:
            engine.process()
            fuel_manager.process()

            now = time.time()
            if now - last_telemetry_time >= 0.1:
                last_telemetry_time = now

                if sender.sio.connected:
                    with state.lock():
                        payload = {
                            "ts": int(now * 1000),
                            "rpm": int(state.rpmValue),
                            "speedKph": float(state.speedValue),
                            "ambientC": float(state.tempValue),
                            "voltage": float(state.batValue),
                            "maf": float(state.mafValue),
                            "fuelLiters": float(state.fuelValue),
                            "rangeKm": int(state.rangeValue),
                            "lph": float(state.lphValue)
                        }
                    sender.send(payload)

            storage.save_state()
            time.sleep(0.01)

    except KeyboardInterrupt:
        logger.info("\nПолучен сигнал остановки (Ctrl+C).")
    except Exception as e:
        logger.exception(f"Критическая ошибка: {e}")
    finally:
        logger.info("Завершение работы...")
        udp_server.stop()
        web_server.stop()
        storage.save_state(force=True)
        elm.disconnect()
        if sender.sio.connected:
            sender.sio.disconnect()
        logger.info("Программа остановлена.")

if __name__ == "__main__":
    main()
