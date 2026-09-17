"""
Lettura angoli teste da encoder incrementali via Modbus RTU (ESP32 + MAX485).

Due topologie supportate:
- combined: un ESP32 legge entrambi gli encoder (slave unico)
- split: un ESP32 + MAX485 per testa (due slave sul bus)

Mappa registri (valori firmati, angolo in centesimi di grado):
  combined: HR0 = SX*100, HR1 = DX*100
  split:    HR0 = angolo*100 sullo slave della testa
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# Scala default: registro holding contiene gradi × 100 (es. 4500 = 45.00°)
ANGLE_SCALE = 100.0


def _s16(value: int) -> int:
    """Interpreta un uint16 come int16 two's complement."""
    v = int(value) & 0xFFFF
    return v - 0x10000 if v >= 0x8000 else v


class HeadAngleEncoderService:
    """
    Polling encoder inclinazione teste su RS485 Modbus.

    Non possiede il bus: riusa il client Modbus già usato da RealMachine.
    """

    def __init__(self, client, config: Optional[Dict[str, Any]] = None):
        cfg = dict(config or {})
        self.client = client
        self.enabled = bool(cfg.get("enabled", True))
        self.mode = str(cfg.get("mode", "combined")).strip().lower()
        if self.mode not in ("combined", "split"):
            self.mode = "combined"
        self.combined_addr = int(cfg.get("combined_addr", 20))
        self.sx_addr = int(cfg.get("sx_addr", 20))
        self.dx_addr = int(cfg.get("dx_addr", 21))
        self.scale = float(cfg.get("angle_scale", ANGLE_SCALE) or ANGLE_SCALE)
        self.zero_offset_sx = float(cfg.get("zero_offset_sx_deg", 0.0))
        self.zero_offset_dx = float(cfg.get("zero_offset_dx_deg", 0.0))
        self.invert_sx = bool(cfg.get("invert_sx", False))
        self.invert_dx = bool(cfg.get("invert_dx", False))
        self.ppr = int(cfg.get("ppr", 360))
        self.quadrature = int(cfg.get("quadrature", 4))

        self.sx_deg: Optional[float] = None
        self.dx_deg: Optional[float] = None
        self.online_sx = False
        self.online_dx = False
        self.last_error: str = ""

    def _apply_cal(self, raw_deg: float, side: str) -> float:
        invert = self.invert_sx if side == "sx" else self.invert_dx
        offset = self.zero_offset_sx if side == "sx" else self.zero_offset_dx
        val = -raw_deg if invert else raw_deg
        return val + offset

    def _read_holding(self, addr: int, start: int, count: int):
        if self.client is None or not hasattr(self.client, "read_holding_registers"):
            return None
        try:
            return self.client.read_holding_registers(addr, start, count)
        except Exception as e:
            self.last_error = str(e)
            return None

    def _write_coil(self, addr: int, coil: int, value: bool) -> bool:
        if self.client is None or not hasattr(self.client, "write_single_coil"):
            return False
        try:
            return bool(self.client.write_single_coil(addr, coil, value))
        except Exception as e:
            self.last_error = str(e)
            return False

    def poll(self) -> Dict[str, Any]:
        """
        Aggiorna le misure. Ritorna un dict pronto per get_state().
        """
        if not self.enabled:
            return self.as_state()

        if self.mode == "combined":
            regs = self._read_holding(self.combined_addr, 0, 2)
            if regs and len(regs) >= 2:
                self.sx_deg = self._apply_cal(_s16(regs[0]) / self.scale, "sx")
                self.dx_deg = self._apply_cal(_s16(regs[1]) / self.scale, "dx")
                self.online_sx = True
                self.online_dx = True
                self.last_error = ""
            else:
                self.online_sx = False
                self.online_dx = False
        else:
            regs_sx = self._read_holding(self.sx_addr, 0, 1)
            if regs_sx and len(regs_sx) >= 1:
                self.sx_deg = self._apply_cal(_s16(regs_sx[0]) / self.scale, "sx")
                self.online_sx = True
            else:
                self.online_sx = False
            regs_dx = self._read_holding(self.dx_addr, 0, 1)
            if regs_dx and len(regs_dx) >= 1:
                self.dx_deg = self._apply_cal(_s16(regs_dx[0]) / self.scale, "dx")
                self.online_dx = True
            else:
                self.online_dx = False

        return self.as_state()

    def zero(self, side: str = "both") -> bool:
        """
        Azzera il conteggio sull'ESP32 (coil 0 = SX, coil 1 = DX).
        Da usare con la testa meccanicamente a 0°.
        """
        if not self.enabled:
            return False
        side = (side or "both").lower()
        ok = True
        if self.mode == "combined":
            if side in ("sx", "both"):
                ok = self._write_coil(self.combined_addr, 0, True) and ok
            if side in ("dx", "both"):
                ok = self._write_coil(self.combined_addr, 1, True) and ok
        else:
            if side in ("sx", "both"):
                ok = self._write_coil(self.sx_addr, 0, True) and ok
            if side in ("dx", "both"):
                ok = self._write_coil(self.dx_addr, 0, True) and ok
        return ok

    def as_state(self) -> Dict[str, Any]:
        return {
            "measured_left_head_angle": self.sx_deg,
            "measured_right_head_angle": self.dx_deg,
            "head_encoder_online": bool(self.online_sx or self.online_dx),
            "head_encoder_online_sx": self.online_sx,
            "head_encoder_online_dx": self.online_dx,
            "head_encoder_error": self.last_error,
            "head_encoder_mode": self.mode,
        }


__all__ = ["HeadAngleEncoderService"]
