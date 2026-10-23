# /home/mrak/projects/Python/fiona_telemetry/parser.py

import logging

logger = logging.getLogger(__name__)

class FordFocus2001Parser:
    """
    Парсер ответов ELM327 для Ford Focus 2001 (2.0 Zetec AT).

    Этот класс перенесён 1:1 из проверенного C++ кода (FordFocus2001_Parser.cpp).
    Он учитывает все особенности ответов данного ЭБУ и адаптеров ELM327.
    Все методы сделаны статическими, так как класс не хранит состояния.
    """

    @staticmethod
    def parse_elm327_response(raw_response: str, pid: str) -> float:
        """
        Главный роутер. Принимает сырую строку ответа от ELM327 и PID.
        Возвращает физическую величину (float).
        """
        # Сразу отсекаем заведомо ошибочные ответы
        if not FordFocus2001Parser.is_valid_response(raw_response):
            return 0.0

        # --- ОСОБЫЙ СЛУЧАЙ: Напряжение (ATRV) ---
        # ELM327 возвращает его не в HEX, а в виде строки "14.2V" или "14.2"
        if pid == "ATRV":
            cleaned = raw_response
            # Убираем символы напряжения и мусор
            cleaned = cleaned.replace("V", "").replace("v", "").replace(">", "")
            cleaned = cleaned.strip()

            try:
                # Пытаемся преобразовать в float
                return float(cleaned)
            except ValueError:
                # Если строка пустая или содержит не число (например, после очистки осталось "")
                return 0.0

        # --- СТАНДАРТНАЯ ОБРАБОТКА HEX-ОТВЕТОВ ---
        clean_hex = FordFocus2001Parser.clean_response(raw_response)

        # Отрезаем первые два символа PID'а (например, из "0110" получаем "10")
        # Это нужно, потому что ЭБУ отвечает "41 10 ...", и нам нужно найти именно "10"
        pid_code = pid[2:]

        # Ищем, с какого индекса в очищенной строке начинаются сами данные
        data_start = FordFocus2001Parser.find_data_start(clean_hex, pid_code)

        if data_start == -1:
            return 0.0

        # --- РАЗБОР ОДНОБАЙТОВЫХ ПАРАМЕТРОВ ---
        # Сюда относятся: Температура, Скорость, Проценты (нагрузка/дроссель), Топливные коррекции
        if pid in ("0105", "010F", "010D", "0104", "0111", "0106", "0107"):
            # Проверяем, что данных достаточно (2 символа на 1 байт)
            if data_start + 2 <= len(clean_hex):
                data_byte = FordFocus2001Parser.parse_hex_byte(clean_hex, data_start)

                if pid in ("0105", "010F"):
                    return FordFocus2001Parser.parse_temperature(data_byte)
                if pid == "010D":
                    return FordFocus2001Parser.parse_speed(data_byte)
                if pid in ("0104", "0111"):
                    return FordFocus2001Parser.parse_percentage(data_byte)
                if pid in ("0106", "0107"):
                    return FordFocus2001Parser.parse_fuel_trim(data_byte)

        # --- РАЗБОР ДВУХБАЙТОВЫХ ПАРАМЕТРОВ ---
        # Сюда относятся: Обороты, MAF, Давление топлива (не используется в текущей версии, но заложено)
        elif pid in ("010C", "0110", "0142"):
            # Проверяем, что данных достаточно (4 символа на 2 байта)
            if data_start + 4 <= len(clean_hex):
                high_byte = FordFocus2001Parser.parse_hex_byte(clean_hex, data_start)
                low_byte = FordFocus2001Parser.parse_hex_byte(clean_hex, data_start + 2)

                if pid == "010C":
                    return FordFocus2001Parser.parse_rpm(high_byte, low_byte)
                if pid == "0110":
                    return FordFocus2001Parser.parse_maf(high_byte, low_byte)
                if pid == "0142":
                    # Формула давления топлива (не используется в текущей прошивке шлюза, но оставлена для совместимости)
                    raw = (high_byte << 8) | low_byte
                    return raw / 1000.0

        return 0.0

    @staticmethod
    def parse_temperature(data_byte: int) -> float:
        """Формула OBD-II: A - 40 (для ОЖ и температуры воздуха)."""
        return float(data_byte - 40)

    @staticmethod
    def parse_speed(data_byte: int) -> float:
        """Формула OBD-II: A (скорость в км/ч)."""
        return float(data_byte)

    @staticmethod
    def parse_maf(high_byte: int, low_byte: int) -> float:
        """Формула OBD-II: (A*256 + B) / 100 (расход воздуха в г/с)."""
        raw = (high_byte << 8) | low_byte
        return raw / 100.0

    @staticmethod
    def parse_rpm(high_byte: int, low_byte: int) -> float:
        """Формула OBD-II: (A*256 + B) / 4 (обороты двигателя)."""
        raw = (high_byte << 8) | low_byte
        return raw / 4.0

    @staticmethod
    def parse_percentage(data_byte: int) -> float:
        """Формула OBD-II: A * 100 / 255 (нагрузка или положение дросселя)."""
        return (100.0 * data_byte) / 255.0

    @staticmethod
    def parse_fuel_trim(data_byte: int) -> float:
        """Формула OBD-II: (A - 128) * 100 / 128 или (A - 128) * 0.78125 (топливная коррекция)."""
        return (data_byte - 128.0) * 0.78125

    @staticmethod
    def is_valid_response(response: str) -> bool:
        """
        Проверяет ответ на наличие ошибок.
        Если ЭБУ не отвечает или адаптер не понял команду, возвращает False.
        """
        if ("NO DATA" in response or
            "?" in response or
            "UNABLE" in response or
            "ERROR" in response):
            return False

        # Минимальная длина осмысленного ответа
        return len(response) >= 4

    @staticmethod
    def extract_data_bytes(raw_response: str, pid: str) -> str:
        """
        Вспомогательный метод (в C++ использовался для отладки).
        Извлекает только байты данных в виде строки HEX.
        """
        clean_hex = FordFocus2001Parser.clean_response(raw_response)
        pid_code = pid[2:]
        data_start = FordFocus2001Parser.find_data_start(clean_hex, pid_code)

        if data_start == -1:
            return ""

        # Для RPM, MAF и 0142 нужно 4 символа, для остальных — 2
        data_length = 4 if pid in ("010C", "0110", "0142") else 2

        if data_start + data_length <= len(clean_hex):
            return clean_hex[data_start:data_start + data_length]

        return ""

    @staticmethod
    def clean_response(raw_response: str) -> str:
        """
        Очищает ответ от служебных символов ELM327.
        Убирает 'SEARCHING...', пробелы, возвраты каретки и символ '>'.
        Приводит к верхнему регистру для удобства поиска.
        """
        result = raw_response
        result = result.replace("SEARCHING...", "")
        result = result.replace(" ", "")
        result = result.replace("\r", "")
        result = result.replace("\n", "")
        result = result.replace(">", "")  # Удаляем символ '>' в конце ответов
        return result.upper()

    @staticmethod
    def find_data_start(clean_hex: str, pid_code: str) -> int:
        """
        Ищет индекс начала полезных данных в очищенной строке.
        Сначала пытается найти полный паттерн "41" + pidCode (например, "410C").
        Если не находит — ищет просто pidCode (на случай, если ЭБУ ответил без префикса 41).
        """
        pattern = "41" + pid_code
        pos = clean_hex.find(pattern)
        if pos != -1:
            return pos + len(pattern)

        # Запасной вариант: ищем просто код PID'а
        pos = clean_hex.find(pid_code)
        if pos != -1:
            return pos + len(pid_code)

        return -1

    @staticmethod
    def hex_char_to_byte(c: str) -> int:
        """Преобразует один HEX-символ в число (0-15)."""
        if '0' <= c <= '9':
            return ord(c) - ord('0')
        if 'A' <= c <= 'F':
            return ord(c) - ord('A') + 10
        if 'a' <= c <= 'f':
            return ord(c) - ord('a') + 10
        return 0

    @staticmethod
    def parse_hex_byte(hex_str: str, start_pos: int) -> int:
        """Преобразует два HEX-символа в байт (0-255)."""
        if start_pos + 2 > len(hex_str):
            return 0
        high = hex_str[start_pos]
        low = hex_str[start_pos + 1]
        return (FordFocus2001Parser.hex_char_to_byte(high) << 4) | FordFocus2001Parser.hex_char_to_byte(low)


# Блок для быстрого тестирования (аналогично C++ тестам)
if __name__ == "__main__":
    # Тестовые строки (имитация ответов ELM327)
    tests = [
        ("010C", "410C1AF8\r\r>"),        # 1726 RPM
        ("010D", "410D32\r\r>"),          # 50 km/h
        ("0110", "41100A00\r\r>"),        # 25.6 g/s
        ("0105", "41055A\r\r>"),          # 50 C
        ("ATRV", "14.2V\r\r>")            # 14.2 V
    ]

    for pid, raw in tests:
        val = FordFocus2001Parser.parse_elm327_response(raw, pid)
        print(f"PID: {pid}, Raw: {repr(raw)} -> Parsed: {val}")
