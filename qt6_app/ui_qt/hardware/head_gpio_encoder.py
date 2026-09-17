"""
Lettura encoder inclinazione teste SX/DX via GPIO Raspberry Pi.

Percorso elettrico:
  Encoder NPN 12 V → cavo schermato → AL-ZARD (isolamento) → GPIO 3,3 V

Non collegare A/B a 12 V sui pin del Pi: l'optoaccoppiatore è obbligatorio.
ESP32 e RS485 non servono in questa topologia.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional, Protocol

try:
    import pigpio
    PIGPIO_AVAILABLE = True
except ImportError:
    pigpio = None
    PIGPIO_AVAILABLE = False


def pulses_to_degrees(pulses: int, ppr: int = 360, quadrature: int = 4) -> float:
    """Converte conteggi quadratura in gradi (1:1 con l'asse testa)."""
    denom = max(1, int(ppr) * int(quadrature))
    return (float(pulses) / float(denom)) * 360.0


class PulseReader(Protocol):
    """Contratto minimo di un encoder AB (pigpio o fake nei test)."""

    def get_pulse_count(self) -> int: ...
    def reset(self) -> None: ...
    def is_connected(self) -> bool: ...
    def close(self) -> None: ...


class QuadratureDecoder:
    """Macchina a stati quadratura x4, identica all'encoder carro."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.count = 0
        self.last_a = 0
        self.last_b = 0

    def set_levels(self, level_a: int, level_b: int) -> None:
        with self._lock:
            self.last_a = int(level_a)
            self.last_b = int(level_b)

    def feed(self, a_changed: bool, level_a: int, level_b: int) -> int:
        """
        Aggiorna il conteggio su un fronte.

        A che anticipa B = incremento (testa in un verso).
        B che anticipa A = decremento.
        """
        with self._lock:
            if a_changed and level_a != self.last_a:
                if level_a != level_b:
                    self.count += 1
                else:
                    self.count -= 1
                self.last_a = level_a
            elif (not a_changed) and level_b != self.last_b:
                if level_a == level_b:
                    self.count += 1
                else:
                    self.count -= 1
                self.last_b = level_b
            return self.count

    def get_count(self) -> int:
        with self._lock:
            return self.count

    def reset(self, value: int = 0) -> None:
        with self._lock:
            self.count = int(value)


class PigpioAbEncoder:
    """Encoder incrementale AB su due GPIO, interrupt pigpio."""

    def __init__(self, gpio_a: int, gpio_b: int, invert: bool = False):
        self.gpio_a = int(gpio_a)
        self.gpio_b = int(gpio_b)
        self.invert = bool(invert)
        self._decoder = QuadratureDecoder()
        self._pi = None
        self._connected = False
        self._cb_a = None
        self._cb_b = None
        self.logger = logging.getLogger("blitz.head_gpio_encoder")

        if not PIGPIO_AVAILABLE:
            self.logger.warning("pigpio non disponibile: encoder testa in modalità offline")
            return

        try:
            self._pi = pigpio.pi()
            if not self._pi.connected:
                self.logger.error("Impossibile connettersi a pigpiod")
                self._pi = None
                return

            self._pi.set_mode(self.gpio_a, pigpio.INPUT)
            self._pi.set_mode(self.gpio_b, pigpio.INPUT)
            self._pi.set_pull_up_down(self.gpio_a, pigpio.PUD_UP)
            self._pi.set_pull_up_down(self.gpio_b, pigpio.PUD_UP)

            level_a = self._pi.read(self.gpio_a)
            level_b = self._pi.read(self.gpio_b)
            self._decoder.set_levels(level_a, level_b)

            self._cb_a = self._pi.callback(
                self.gpio_a, pigpio.EITHER_EDGE, self._on_edge
            )
            self._cb_b = self._pi.callback(
                self.gpio_b, pigpio.EITHER_EDGE, self._on_edge
            )
            self._connected = True
            self.logger.info(
                "Encoder testa AB su GPIO %s/%s", self.gpio_a, self.gpio_b
            )
        except Exception as e:
            self.logger.error("Init encoder testa fallito: %s", e)
            self._pi = None

    def _on_edge(self, gpio, level, tick) -> None:
        if not self._pi:
            return
        try:
            level_a = self._pi.read(self.gpio_a)
            level_b = self._pi.read(self.gpio_b)
            self._decoder.feed(gpio == self.gpio_a, level_a, level_b)
        except Exception as e:
            self.logger.error("Callback quadratura testa: %s", e)

    def get_pulse_count(self) -> int:
        count = self._decoder.get_count()
        return -count if self.invert else count

    def reset(self) -> None:
        self._decoder.reset(0)

    def is_connected(self) -> bool:
        return self._connected and self._pi is not None

    def close(self) -> None:
        if self._pi:
            try:
                if self._cb_a:
                    self._cb_a.cancel()
                    self._cb_a = None
                if self._cb_b:
                    self._cb_b.cancel()
                    self._cb_b = None
                self._pi.stop()
            except Exception as e:
                self.logger.error("Cleanup encoder testa: %s", e)
            finally:
                self._pi = None
                self._connected = False


class HeadAngleGpioService:
    """
    Stesso contratto di HeadAngleEncoderService (poll / zero / as_state),
    ma i conteggi arrivano dai GPIO dopo l'AL-ZARD.
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        sx_reader: Optional[PulseReader] = None,
        dx_reader: Optional[PulseReader] = None,
    ):
        cfg = dict(config or {})
        gpio_cfg = dict(cfg.get("gpio") or {})
        self.enabled = bool(cfg.get("enabled", True))
        self.ppr = int(cfg.get("ppr", 360))
        self.quadrature = int(cfg.get("quadrature", 4))
        self.zero_offset_sx = float(cfg.get("zero_offset_sx_deg", 0.0))
        self.zero_offset_dx = float(cfg.get("zero_offset_dx_deg", 0.0))
        self.invert_sx = bool(cfg.get("invert_sx", False))
        self.invert_dx = bool(cfg.get("invert_dx", False))

        self.sx_deg: Optional[float] = None
        self.dx_deg: Optional[float] = None
        self.online_sx = False
        self.online_dx = False
        self.last_error: str = ""
        self.mode = "gpio"

        if sx_reader is not None:
            self._sx = sx_reader
        else:
            self._sx = PigpioAbEncoder(
                gpio_a=int(gpio_cfg.get("sx_a", 5)),
                gpio_b=int(gpio_cfg.get("sx_b", 6)),
            )
        if dx_reader is not None:
            self._dx = dx_reader
        else:
            self._dx = PigpioAbEncoder(
                gpio_a=int(gpio_cfg.get("dx_a", 19)),
                gpio_b=int(gpio_cfg.get("dx_b", 26)),
            )

        if not self._sx.is_connected() and sx_reader is None:
            self.last_error = "pigpio non disponibile o pigpiod fermo (encoder SX)"
        if not self._dx.is_connected() and dx_reader is None:
            suffix = "encoder DX"
            self.last_error = (
                f"{self.last_error}; {suffix}" if self.last_error else
                f"pigpio non disponibile o pigpiod fermo ({suffix})"
            )

    def _apply_offset(self, raw_deg: float, side: str) -> float:
        offset = self.zero_offset_sx if side == "sx" else self.zero_offset_dx
        return raw_deg + offset

    def _deg_from(self, reader: PulseReader, side: str) -> float:
        pulses = int(reader.get_pulse_count())
        if (side == "sx" and self.invert_sx) or (side == "dx" and self.invert_dx):
            pulses = -pulses
        return pulses_to_degrees(pulses, self.ppr, self.quadrature)

    def poll(self) -> Dict[str, Any]:
        if not self.enabled:
            return self.as_state()

        self.online_sx = bool(self._sx.is_connected())
        self.online_dx = bool(self._dx.is_connected())
        if self.online_sx:
            self.sx_deg = self._apply_offset(self._deg_from(self._sx, "sx"), "sx")
        if self.online_dx:
            self.dx_deg = self._apply_offset(self._deg_from(self._dx, "dx"), "dx")
        if self.online_sx or self.online_dx:
            # Un canale vivo: non mascherare l'altro con un errore pigpio globale
            if self.online_sx and self.online_dx:
                self.last_error = ""
        return self.as_state()

    def zero(self, side: str = "both") -> bool:
        if not self.enabled:
            return False
        side = (side or "both").lower()
        ok = True
        if side in ("sx", "both"):
            try:
                self._sx.reset()
                self.sx_deg = self._apply_offset(0.0, "sx")
            except Exception:
                ok = False
        if side in ("dx", "both"):
            try:
                self._dx.reset()
                self.dx_deg = self._apply_offset(0.0, "dx")
            except Exception:
                ok = False
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

    def close(self) -> None:
        for reader in (self._sx, self._dx):
            try:
                reader.close()
            except Exception:
                pass


__all__ = [
    "HeadAngleGpioService",
    "PigpioAbEncoder",
    "QuadratureDecoder",
    "pulses_to_degrees",
]
