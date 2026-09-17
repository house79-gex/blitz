"""
Azionamento inclinazione teste.

Oggi: cilindri a due posizioni (0°/45°) via impulso EV.
Futuro: attuatori lineari sulla stessa corsa, angolo continuo 0–45°.
"""
from __future__ import annotations

from typing import Callable, Optional, Tuple

# Corsa misurata sui cilindri attuali (distanza tra perni, 0° → 45°).
DEFAULT_STROKE_MM = 85.0
MAX_TILT_DEG = 45.0


def snap_two_pos_deg(angle_deg: float, threshold_deg: float = 22.5) -> float:
    """Con i cilindri a due posizioni l'angolo va a 0° oppure 45°."""
    return 45.0 if float(angle_deg) >= float(threshold_deg) else 0.0


class HeadTiltDrive:
    """Interfaccia comune: pneumatico 2 pos o attuatore lineare."""

    mode = "none"

    def move_to_deg(self, sx: float, dx: float) -> Tuple[float, float]:
        return float(sx), float(dx)

    def close(self) -> None:
        return None


class PneumaticTwoPosDrive(HeadTiltDrive):
    """Impulso EV 0° / 45° per testa (modulo I/O #1 OUT1–OUT4)."""

    mode = "pneumatic_2pos"

    def __init__(
        self,
        pulse_fn: Callable[[str, bool], None],
        threshold_deg: float = 22.5,
    ):
        self._pulse = pulse_fn
        self.threshold_deg = float(threshold_deg)

    def move_to_deg(self, sx: float, dx: float) -> Tuple[float, float]:
        sx_cmd = snap_two_pos_deg(sx, self.threshold_deg)
        dx_cmd = snap_two_pos_deg(dx, self.threshold_deg)
        self._pulse("sx", sx_cmd >= 22.5)
        self._pulse("dx", dx_cmd >= 22.5)
        return sx_cmd, dx_cmd


def parse_stroke_mm(cfg: Optional[dict], default: float = DEFAULT_STROKE_MM) -> float:
    """Corsa attuatore in mm; fallback alla misura sui cilindri (85 mm)."""
    raw = (cfg or {}).get("stroke_mm", default)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return float(default)
    if value <= 0:
        return float(default)
    return value


def clamp_stroke_mm(mm: float, stroke_mm: float = DEFAULT_STROKE_MM) -> float:
    """Limita la corsa comandata tra 0 e lo stroke meccanico."""
    limit = max(0.0, float(stroke_mm))
    return max(0.0, min(limit, float(mm)))


def clamp_tilt_deg(angle_deg: float, max_deg: float = MAX_TILT_DEG) -> float:
    """Limita l'angolo testa all'intervallo meccanico 0–45°."""
    return max(0.0, min(float(max_deg), float(angle_deg)))


def feedforward_mm_for_deg(
    angle_deg: float,
    stroke_mm: float = DEFAULT_STROKE_MM,
    max_deg: float = MAX_TILT_DEG,
) -> float:
    """
    Prima stima lineare: 0° → 0 mm, 45° → corsa cilindro.

    Non è la legge di controllo: la corsa reale non è lineare con i gradi
    (leva/snodo). L'encoder di rotazione resta il feedback; questo valore
    serve solo come tetto di corsa e come feedforward iniziale.
    """
    span = float(max_deg) if float(max_deg) else MAX_TILT_DEG
    ratio = clamp_tilt_deg(angle_deg, span) / span
    return clamp_stroke_mm(float(stroke_mm) * ratio, stroke_mm)


class LinearActuatorTiltDrive(HeadTiltDrive):
    """
    Stub per i futuri attuatori lineari (stessa corsa/attacchi dei cilindri).

    Non comanda hardware: enabled resta False finché non c'è il driver.
    L'encoder di rotazione testa resta il feedback d'angolo (la corsa
    dell'attuatore non è lineare con i gradi).
    """

    mode = "linear_actuator"

    def __init__(self, cfg: Optional[dict] = None):
        self.cfg = cfg or {}
        self.enabled = bool(self.cfg.get("enabled", False))
        self.stroke_mm = parse_stroke_mm(self.cfg)

    def mm_for_deg(self, angle_deg: float) -> float:
        """Feedforward mm per un angolo (stima lineare, tetto = corsa 85 mm)."""
        return feedforward_mm_for_deg(angle_deg, self.stroke_mm)

    def move_to_deg(self, sx: float, dx: float) -> Tuple[float, float]:
        # Imbastitura: niente I/O finché non si sceglie il modello
        if not self.enabled:
            print("Warning: attuatori lineari teste non abilitati (scaffold)")
            return float(sx), float(dx)
        raise NotImplementedError(
            "Driver attuatori lineari teste da implementare "
            f"(corsa {self.stroke_mm:.0f} mm, forza, mappa mm→gradi). "
            "Vedi docs/HEAD_TILT_ACTUATORS.md"
        )


def create_head_tilt_drive(
    config: Optional[dict],
    pulse_fn: Optional[Callable[[str, bool], None]] = None,
) -> HeadTiltDrive:
    """Factory da hardware_config (head_tilt / head_tilt_actuators)."""
    cfg = config or {}
    tilt = cfg.get("head_tilt") or {}
    mode = str(tilt.get("mode") or "pneumatic_2pos").lower()
    if mode == "linear_actuator":
        return LinearActuatorTiltDrive(cfg.get("head_tilt_actuators") or {})
    if pulse_fn is None:
        return HeadTiltDrive()
    return PneumaticTwoPosDrive(
        pulse_fn,
        threshold_deg=float(tilt.get("threshold_deg", 22.5)),
    )
