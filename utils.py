import binascii

def bytes_to_bits(data: bytes) -> list:
    bits = []
    for b in data:
        for i in range(8):
            bits.append((b >> (7 - i)) & 1)
    return bits

def bits_to_bytes(bits: list) -> bytes:
    b = bytearray()
    for i in range(0, len(bits), 8):
        byte = 0
        for j in range(8):
            if i + j < len(bits) and bits[i + j]:
                byte |= 1 << (7 - j)
        b.append(byte)
    return bytes(b)

def crc32_bytes(data: bytes) -> int:
    return binascii.crc32(data) & 0xFFFFFFFF
