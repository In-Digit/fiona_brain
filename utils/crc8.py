# /home/mrak/projects/Python/fiona_brain/utils/crc8.py

def calculate_crc8(data: bytes) -> int:
    """
    Вычисляет CRC8 с полиномом 0x8C (как в твоем C++ коде).
    Используется для проверки целостности UDP-пакетов.
    """
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x01:
                crc = (crc >> 1) ^ 0x8C
            else:
                crc >>= 1
    return crc
