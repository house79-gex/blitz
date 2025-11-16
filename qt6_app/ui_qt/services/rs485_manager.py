from __future__ import annotations
from typing import List, Optional
from contextlib import suppress

# Dipendenze opzionali: pyserial, pymodbus
try:
    from serial.tools import list_ports
except Exception:
    list_ports = None

try:
    from pymodbus.client import ModbusSerialClient  # pymodbus>=3
    _HAS_PYMODBUS = True
except Exception:
    _HAS_PYMODBUS = False
    ModbusSerialClient = None  # type: ignore


def list_serial_ports_safe() -> List[str]:
    if list_ports is None:
        # fallback: prova path comuni
        return [
            "/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyAMA0",
            "COM3", "COM4", "COM5"
        ]
    try:
        return [p.device for p in list_ports.comports()]
    except Exception:
        return []


class RS485Manager:
    """
    Manager semplice per connessione RS485 con Modbus RTU (pymodbus se disponibile).
    Gestisce:
      - open/close
      - read_discrete_inputs (per 8 IN digitali)
      - read_coils / write_coil (per eventuali relè/uscite)
    Se pymodbus non è disponibile, opera in modalità 'stub' (ritorna tutti False).
    """
    def __init__(self):
        self._cli: Optional[ModbusSerialClient] = None
        self._connected: bool = False
        self._cfg = {
            "port": "",
            "baudrate": 115200,
            "parity": "N",
            "stopbits": 1,
            "timeout": 0.5,
        }

    def is_connected(self) -> bool:
        return bool(self._connected)

    def connect(self, port: str, baudrate: int = 115200, parity: str = "N", stopbits: int = 1, timeout: float = 0.5) -> bool:
        self._cfg.update({
            "port": str(port or ""),
            "baudrate": int(baudrate),
            "parity": str(parity or "N")[:1].upper(),
            "stopbits": int(stopbits),
            "timeout": float(timeout),
        })
        self.disconnect()
        if not _HAS_PYMODBUS:
            # Nessuna libreria Modbus -> modalità stub
            self._connected = True
            return True
        try:
            self._cli = ModbusSerialClient(
                method="rtu",
                port=self._cfg["port"],
                baudrate=self._cfg["baudrate"],
                parity=self._cfg["parity"],
                stopbits=self._cfg["stopbits"],
                timeout=self._cfg["timeout"],
                retry_on_empty=True,
                retries=2,
            )
            self._connected = bool(self._cli.connect())
        except Exception:
            self._cli = None
            self._connected = False
        return self._connected

    def disconnect(self):
        if self._cli:
            with suppress(Exception):
                self._cli.close()
        self._cli = None
        self._connected = False

    # ---- Letture IN/DISCRETE INPUTS (Waveshare 8 IN) ----
    def read_discrete_inputs(self, unit: int, address: int = 0, count: int = 8) -> List[bool]:
        """
        Legge ingressi discreti Modbus (function code 2).
        Restituisce lista di boolean (lunghezza 'count').
        """
        if not self._connected:
            return [False] * count
        if not _HAS_PYMODBUS or self._cli is None:
            # Modalità stub
            return [False] * count
        try:
            rr = self._cli.read_discrete_inputs(address=address, count=count, unit=int(unit))
            if hasattr(rr, "isError") and rr.isError():  # type: ignore
                return [False] * count
            bits = list(rr.bits) if hasattr(rr, "bits") else []  # type: ignore
            # Pad a count
            bits = (bits + [False] * count)[:count]
            return [bool(x) for x in bits]
        except Exception:
            return [False] * count

    # ---- Coils (eventuali uscite/relè) ----
    def read_coils(self, unit: int, address: int = 0, count: int = 8) -> List[bool]:
        if not self._connected:
            return [False] * count
        if not _HAS_PYMODBUS or self._cli is None:
            return [False] * count
        try:
            rr = self._cli.read_coils(address=address, count=count, unit=int(unit))
            if hasattr(rr, "isError") and rr.isError():  # type: ignore
                return [False] * count
            bits = list(rr.bits) if hasattr(rr, "bits") else []  # type: ignore
            bits = (bits + [False] * count)[:count]
            return [bool(x) for x in bits]
        except Exception:
            return [False] * count

    def write_coil(self, unit: int, address: int, value: bool) -> bool:
        if not self._connected:
            return False
        if not _HAS_PYMODBUS or self._cli is None:
            # In stub simuliamo successo
            return True
        try:
            rq = self._cli.write_coil(address=address, value=bool(value), unit=int(unit))
            if hasattr(rq, "isError") and rq.isError():  # type: ignore
                return False
            return True
        except Exception:
            return False
