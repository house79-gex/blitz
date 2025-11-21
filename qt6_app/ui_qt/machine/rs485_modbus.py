from __future__ import annotations
import serial
import struct
import threading
from typing import List, Dict, Any

def _crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF

class ModbusRTUClient:
    """
    Client leggero Modbus RTU (solo funzioni base 0x01,0x02,0x05,0x0F).
    Attenzione: non thread-safe per scritture concorrenti → usa lock interno.
    """
    def __init__(self, port: str = "/dev/ttyUSB0", baudrate: int = 115200, timeout: float = 0.05):
        self._ser = serial.Serial(port=port, baudrate=baudrate, bytesize=8, parity='N', stopbits=1, timeout=timeout)
        self._lock = threading.Lock()

    def _tx_rx(self, pkt: bytes) -> bytes:
        with self._lock:
            self._ser.write(pkt)
            # lettura minimale: leggi almeno header + lunghezza stimata
            # per semplicità leggi tutto fino a timeout
            return self._ser.read(256)

    def read_coils(self, addr: int, start: int, count: int) -> List[bool]:
        fn = 0x01
        pdu = struct.pack(">B B H H", addr, fn, start, count)
        crc = _crc16(pdu[0:6])
        frame = pdu + struct.pack("<H", crc)
        resp = self._tx_rx(frame)
        # risposta: addr fn bytecount data... crc
        if len(resp) < 5 or resp[0] != addr or resp[1] != fn:
            return [False]*count
        bytecount = resp[2]
        bits = []
        for i in range(count):
            byte_index = 3 + (i // 8)
            bit_index = i % 8
            if byte_index < 3+bytecount:
                val = (resp[byte_index] >> bit_index) & 0x01
                bits.append(bool(val))
            else:
                bits.append(False)
        return bits

    def read_discrete_inputs(self, addr: int, start: int, count: int) -> List[bool]:
        fn = 0x02
        pdu = struct.pack(">B B H H", addr, fn, start, count)
        crc = _crc16(pdu[0:6])
        frame = pdu + struct.pack("<H", crc)
        resp = self._tx_rx(frame)
        if len(resp) < 5 or resp[0] != addr or resp[1] != fn:
            return [False]*count
        bytecount = resp[2]
        bits = []
        for i in range(count):
            byte_index = 3 + (i // 8)
            bit_index = i % 8
            if byte_index < 3+bytecount:
                val = (resp[byte_index] >> bit_index) & 0x01
                bits.append(bool(val))
            else:
                bits.append(False)
        return bits

    def write_single_coil(self, addr: int, coil: int, value: bool) -> bool:
        fn = 0x05
        out = 0xFF00 if value else 0x0000
        pdu = struct.pack(">B B H H", addr, fn, coil, out)
        crc = _crc16(pdu[0:6])
        frame = pdu + struct.pack("<H", crc)
        resp = self._tx_rx(frame)
        return len(resp) >= 8 and resp[0:6] == pdu[0:6]

    def write_multiple_coils(self, addr: int, start: int, values: List[bool]) -> bool:
        fn = 0x0F
        count = len(values)
        nbytes = (count + 7) // 8
        data_bytes = bytearray(nbytes)
        for i, v in enumerate(values):
            if v:
                data_bytes[i // 8] |= (1 << (i % 8))
        header = struct.pack(">B B H H B", addr, fn, start, count, nbytes)
        pdu = header + bytes(data_bytes)
        crc = _crc16(pdu)
        frame = pdu + struct.pack("<H", crc)
        resp = self._tx_rx(frame)
        return len(resp) >= 8 and resp[0] == addr and resp[1] == fn

    def close(self):
        try: self._ser.close()
        except Exception: pass
