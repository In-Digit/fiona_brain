# /home/mrak/projects/Python/fiona_telemetry/elm327.py

import serial
import time
import logging

# Настраиваем базовое логирование, чтобы видеть, что происходит
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ELM327:
    """
    Класс для работы с адаптером ELM327 через последовательный порт (Bluetooth SPP).
    """
    def __init__(self, port: str = "/dev/rfcomm0", baudrate: int = 38400, timeout: float = 1.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None

    def connect(self) -> bool:
        """
        Открывает последовательный порт.
        """
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout,
                write_timeout=self.timeout,
                rtscts=False,
                dsrdtr=False,
            )
            logger.info(f"Порт {self.port} успешно открыт на {self.baudrate} бод.")
            return True
        except serial.SerialException as e:
            logger.error(f"Ошибка открытия порта {self.port}: {e}")
            return False

    def disconnect(self):
        """
        Закрывает последовательный порт.
        """
        if self.ser and self.ser.is_open:
            self.ser.close()
            logger.info("Порт закрыт.")

    def send_command(self, cmd: str, wait_prompt: bool = True, timeout: float = None) -> str:
        """
        Отправляет AT-команду или PID и читает ответ.

        :param cmd: Команда (например, "ATZ" или "010C").
        :param wait_prompt: Ждать ли символ '>' (признак конца ответа ELM327).
        :param timeout: Переопределить стандартный таймаут.
        :return: Очищенная строка ответа.
        """
        if not self.ser or not self.ser.is_open:
            logger.error("Порт не открыт.")
            return ""

        if timeout is None:
            timeout = self.timeout

        # Очищаем буфер перед отправкой
        self.ser.reset_input_buffer()

        # Небольшая пауза перед отправкой, чтобы порт "успокоился"
        time.sleep(0.05)

        # Отправляем команду с символом возврата каретки
        full_cmd = f"{cmd}\r".encode('ascii')
        logger.debug(f"Отправка: {cmd}")
        self.ser.write(full_cmd)

        # Читаем ответ
        start_time = time.time()
        response = b""

        while (time.time() - start_time) < timeout:
            if self.ser.in_waiting:
                chunk = self.ser.read(self.ser.in_waiting)
                response += chunk

                # Если дождались промпта, можем прекращать чтение
                if wait_prompt and b'>' in response:
                    break
            else:
                # Небольшая пауза, чтобы не грузить процессор вхолостую
                time.sleep(0.01)

        # Декодируем и очищаем ответ
        raw_str = response.decode('ascii', errors='ignore')
        return self._clean_response(raw_str, cmd)

    def _clean_response(self, raw: str, cmd: str) -> str:
        """
        Очищает ответ от эха, служебных строк SEARCHING, переводов строк и промпта.
        """
        # Убираем служебные строки
        clean = raw.replace('SEARCHING...', '')

        # Убираем промпт и переводы строк
        clean = clean.replace('\r', '').replace('\n', '').replace('>', '')

        # Убираем эхо самой команды
        if clean.upper().startswith(cmd.upper()):
            clean = clean[len(cmd):]

        # Убираем все пробелы
        clean = clean.replace(' ', '').strip()

        logger.debug(f"Очищенный ответ: {clean}")
        return clean

    def initialize(self) -> bool:
        """
        Инициализация адаптера. Сброс, отключение эха, отключение пробелов, авто-протокол.
        Возвращает True, если адаптер ответил.
        """
        logger.info("Инициализация ELM327...")

        # 1. Сброс (может занять до 3 секунд)
        # Первый раз после подключения адаптер может «промолчать», это нормально.
        res = self.send_command("ATZ", timeout=4.0)
        if "ELM327" not in res:
            logger.warning("ATZ не вернул версию адаптера. Пробуем еще раз...")
            res = self.send_command("ATZ", timeout=4.0)
            if "ELM327" not in res:
                logger.error("Адаптер не отвечает на ATZ.")
                return False

        logger.info(f"Адаптер: {res}")

        # 2. Отключаем эхо
        self.send_command("ATE0")
        time.sleep(0.1)

        # 3. Отключаем пробелы в ответах
        self.send_command("ATS0")
        time.sleep(0.1)

        # 4. Отключаем перевод строки
        self.send_command("ATL0")
        time.sleep(0.1)

        # 5. Устанавливаем автоматическое определение протокола
        self.send_command("ATSP0")
        time.sleep(0.1)

        logger.info("Инициализация завершена.")
        return True

    def test_connection(self) -> bool:
        """
        Проверяет связь с ЭБУ, запрашивая поддерживаемые PID'ы (0100).
        """
        logger.info("Проверка связи с ЭБУ...")
        # Увеличиваем таймаут для первого запроса, так как ЭБУ и адаптер могут "думать"
        res = self.send_command("0100", timeout=3.0)

        # Теперь ищем "41" в строке, так как ответ может быть с префиксом
        if "41" in res:
            logger.info(f"ЭБУ на связи. Ответ: {res}")
            return True
        else:
            logger.error(f"ЭБУ не ответил или ответ некорректен: {res}")
            return False

# Блок для быстрого тестирования при запуске файла напрямую
if __name__ == "__main__":
    elm = ELM327()
    if elm.connect():
        if elm.initialize():
            elm.test_connection()
        elm.disconnect()
