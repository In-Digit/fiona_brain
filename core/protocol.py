# /home/mrak/projects/Python/fiona_brain/core/protocol.py

import struct
import logging
from utils.crc8 import calculate_crc8

logger = logging.getLogger(__name__)

# Магические байты
MAGIC_STREAM = 0xAA    # Стрим от ноута (Broadcast)
MAGIC_MODULE = 0xDD    # Данные от модуля к ноуту
MAGIC_CMD = 0xBB       # Команда от ноута к модулю

# Константы ID
ID_HUD = 0
ID_PC = 1
ID_UNDERHOOD = 2
ID_CABIN = 3
ID_BROADCAST = 0xFF

# ============================================================================
# КАРТА ПОЛЕЙ ДЛЯ СТРИМА ОТ НОУТА (0xAA, 64 бита)
# Формат: { бит: (имя_поля, формат_struct, множитель, смещение) }
# ============================================================================
STREAM_MAP = {
    0: ("rpm", "<H", 1, 0),                 # uint16 (2 байта)
    1: ("speed", "<B", 1, 0),               # uint8 (1 байт)
    2: ("coolant", "<b", 1, -40),           # int8 (1 байт), в пакете хранится temp+40
    3: ("voltage", "<B", 10, 0),            # uint8 (1 байт), в пакете 142, реально 14.2В
    4: ("fuel", "<B", 1, 0),                # uint8 (1 байт)
    5: ("range_km", "<H", 1, 0),            # uint16 (2 байта)
    6: ("odo_km", "<I", 1, 0),              # uint32 (4 байта)
    7: ("flags", "<B", 1, 0),               # uint8 (1 байт, битовая маска)
    8: ("drive_mode", "<B", 1, 0),          # uint8 (1 байт)
    9: ("driving_style", "<B", 1, 0),       # uint8 (1 байт)
    10: ("maf", "<H", 100, 0),              # uint16 (2 байта), в пакете 1542, реально 15.42
    11: ("timestamp", "<I", 1, 0),          # uint32 (4 байта, Unix time)
}

# ============================================================================
# КАРТА ПОЛЕЙ ДЛЯ МОДУЛЕЙ (0xDD, 16 бит)
# ============================================================================
MODULE_MAPS = {
    ID_UNDERHOOD: { # Подкапотня
        0: ("rad_temp", "<b", 1, -40),      # Температура радиатора
        1: ("outside_temp", "<b", 1, -40),  # Температура за бортом
        2: ("fan1_pwm", "<B", 1, 0),        # ШИМ вентилятора 1
        3: ("fan2_pwm", "<B", 1, 0),        # ШИМ вентилятора 2
    },
    ID_CABIN: { # Салон
        0: ("cabin_temp", "<b", 1, -40),    # Температура в салоне
        1: ("humidity", "<B", 1, 0),        # Влажность
        2: ("door_bits", "<B", 1, 0),       # Байт концевиков
    }
}


class FionaProtocol:
    """
    Класс для сборки и разборки бинарных UDP-пакетов Fiona-Net.
    """

    @staticmethod
    def pack_stream(data_dict: dict, seq: int) -> bytes:
        """
        Собирает пакет 0xAA (Стрим от ноута) для Broadcast.
        """
        mask = bytearray(8) # 64 бита
        payload = bytearray()

        for bit, (name, fmt, scale, offset) in STREAM_MAP.items():
            if name in data_dict and data_dict[name] is not None:
                # Устанавливаем бит в маске
                byte_idx = bit // 8
                bit_idx = bit % 8
                mask[byte_idx] |= (1 << bit_idx)

                # Формируем данные
                val = data_dict[name]
                if scale != 1:
                    val = val * scale
                if offset != 0:
                    val = val + offset

                # Упаковываем в байты
                payload.extend(struct.pack(fmt, int(val)))

        # Собираем заголовок
        header = bytearray()
        header.append(MAGIC_STREAM)
        header.append(ID_PC)
        header.append(ID_BROADCAST)
        header.append(seq & 0xFF)
        header.append(len(mask)) # MASK_LEN = 8
        header.extend(mask)

        packet = header + payload
        crc = calculate_crc8(packet)
        packet.append(crc)

        return bytes(packet)

    @staticmethod
    def unpack_module_data(data: bytes) -> tuple[int, int, dict]:
        """
        Разбирает пакет 0xDD (Данные от модуля).
        Возвращает: (src_id, seq, dict_с_данными) или (0, 0, {}) при ошибке.
        """
        if len(data) < 6:
            return 0, 0, {}

        if data[0] != MAGIC_MODULE:
            return 0, 0, {}

        src_id = data[1]
        seq = data[3]
        mask_len = data[4]

        if len(data) < 5 + mask_len + 1: # Заголовок + Маска + CRC
            return 0, 0, {}

        # Проверка CRC
        expected_crc = data[-1]
        if calculate_crc8(data[:-1]) != expected_crc:
            logger.warning(f"CRC mismatch from module {src_id}")
            return 0, 0, {}

        mask = data[5:5+mask_len]
        payload = data[5+mask_len:-1]

        result = {}
        payload_idx = 0

        # Если для этого модуля есть карта полей
        if src_id in MODULE_MAPS:
            module_map = MODULE_MAPS[src_id]

            for bit, (name, fmt, scale, offset) in module_map.items():
                byte_idx = bit // 8
                bit_idx = bit % 8

                # Если бит установлен в маске
                if byte_idx < len(mask) and (mask[byte_idx] & (1 << bit_idx)):
                    size = struct.calcsize(fmt)

                    if payload_idx + size <= len(payload):
                        raw_val = struct.unpack(fmt, payload[payload_idx:payload_idx+size])[0]

                        # Применяем обратное масштабирование
                        real_val = raw_val
                        if offset != 0:
                            real_val = real_val - offset
                        if scale != 1:
                            real_val = real_val / scale

                        result[name] = real_val
                        payload_idx += size
                    else:
                        logger.warning(f"Module {src_id}: payload too short for {name}")
                        break

        return src_id, seq, result

    @staticmethod
    def pack_command(dst_id: int, cmd_id: int, payload: bytes, seq: int) -> bytes:
        """
        Собирает пакет 0xBB (Команда от ноута к модулю).
        """
        header = bytearray()
        header.append(MAGIC_CMD)
        header.append(ID_PC)
        header.append(dst_id)
        header.append(seq & 0xFF)
        header.append(1) # MASK_LEN = 1 (тут длина payload, а не маски)
        header.append(cmd_id) # Вместо маски - ID команды

        packet = header + payload
        crc = calculate_crc8(packet)
        packet.append(crc)

        return bytes(packet)

    @staticmethod
    def unpack_command(data: bytes) -> tuple[int, int, bytes]:
        """
        Разбирает пакет 0xBB (Команда). Нужен для модулей.
        Возвращает: (cmd_id, seq, payload) или (0, 0, b'') при ошибке.
        """
        if len(data) < 7:
            return 0, 0, b''

        if data[0] != MAGIC_CMD:
            return 0, 0, b''

        dst_id = data[2]
        seq = data[3]
        cmd_id = data[5]

        expected_crc = data[-1]
        if calculate_crc8(data[:-1]) != expected_crc:
            return 0, 0, b''

        payload = data[6:-1]
        return cmd_id, seq, payload
