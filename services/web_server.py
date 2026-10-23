# /home/mrak/projects/Python/fiona_brain/services/web_server.py

import http.server
import socketserver
import json
import threading
import logging
import os
from core.state import get_state
from services.fuel import FuelManager
from services.storage import StorageManager
import config

logger = logging.getLogger(__name__)
PORT = 8000
WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'web')

class WebRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, fuel_manager=None, storage=None, **kwargs):
        self.fuel_manager = fuel_manager
        self.storage = storage
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def do_GET(self):
        if self.path == '/api/telemetry':
            state = get_state()
            with state.lock():
                data = {
                    "rpm": int(state.rpmValue),
                    "speed": int(state.speedValue),
                    "coolant": int(state.tempValue),
                    "voltage": round(state.batValue, 1),
                    "fuel_liters": round(state.fuelValue, 1),
                    "range_km": int(state.rangeValue),
                    "lph": round(state.lphValue, 1),
                    "maf": round(state.mafValue, 1),
                    "odo_miles": int(state.odoMiles),
                    "calib_factor": round(state.current_fuel_calibration, 3),
                    "calib_active": state.calibration_active,
                    "calib_frozen": state.calibration_frozen,
                    "odo_needed": state.odo_calib_needed,
                    "fuel_needed": state.fuel_calib_needed,
                    "calib_preset": state.calibration_preset,
                    "is_emu": config.EMULATION_MODE
                }
            self._send_json(data)
        else:
            super().do_GET()

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)

        try:
            data = json.loads(post_data.decode('utf-8'))
        except json.JSONDecodeError:
            self._send_json({"status": "error", "message": "Invalid JSON"}, 400)
            return

        state = get_state()

        if self.path == '/api/refuel':
            liters = float(data.get('liters', 0))
            is_full = bool(data.get('is_full', False))
            price = float(data.get('price', 0.0))
            alias = str(data.get('alias', 'default'))
            # Пробег берем текущий из состояния, если не передан
            odo = int(data.get('odo', state.odoMiles))

            if liters <= 0:
                self._send_json({"status": "error", "message": "Liters must be > 0"}, 400)
                return

            self.fuel_manager.handle_refuel(liters, is_full, odo, price, alias)
            self.storage.request_save()
            self._send_json({"status": "ok", "message": f"Заправка {liters} л ({alias}) обработана"})

        elif self.path == '/api/calib_control':
            action = data.get('action')
            if action == 'toggle_freeze':
                with state.lock():
                    state.calibration_frozen = not state.calibration_frozen
                self._send_json({"status": "ok", "message": f"Заморозка: {state.calibration_frozen}"})
            elif action == 'cancel':
                self.fuel_manager.cancel_calibration()
                self._send_json({"status": "ok", "message": "Калибровка отменена"})

        elif self.path == '/api/set_fuel':
            liters = float(data.get('liters', 0))
            self.fuel_manager.set_fuel_level_direct(liters)
            self.storage.request_save()
            self._send_json({"status": "ok", "message": f"Уровень топлива установлен: {liters} л"})

        else:
            self._send_json({"status": "error", "message": "Unknown endpoint"}, 404)

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def log_message(self, format, *args):
        pass

class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True

class WebServer:
    def __init__(self, fuel_manager: FuelManager, storage: StorageManager):
        self._server = None
        self._thread = None
        self.fuel_manager = fuel_manager
        self.storage = storage

    def start(self):
        if not os.path.exists(WEB_DIR):
            os.makedirs(WEB_DIR)

        try:
            from functools import partial
            handler = partial(WebRequestHandler, fuel_manager=self.fuel_manager, storage=self.storage)
            self._server = ReusableTCPServer(("", PORT), handler)
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
            logger.info(f"Веб-сервер запущен на порту {PORT}")
        except OSError as e:
            logger.error(f"Не удалось запустить веб-сервер: {e}")

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
