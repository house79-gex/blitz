"""
Finecorsa 0° delle teste (pistone, due fermi 0°/45°).

L'encoder si azzera in homing, non a ogni passaggio sul FC.
Il FC può accendersi prima del fermo: 'settled' è FC tenuto + angolo fermo.
"""
from __future__ import annotations

import time
from typing import Callable, Dict, Optional


class _SideTrack:
    """Stato di un lato (SX o DX) tra un avvicinamento e il successivo."""

    def __init__(self):
        self.active = False
        self.pending = False
        self.settled = False
        self.t_active = 0.0
        self.t_stable = 0.0
        self.last_angle: Optional[float] = None


class HeadHomeLimitHelper:
    """Rileva testa ferma sul blocco 0°. Lo zero encoder è compito dell'homing."""

    def __init__(
        self,
        zero_fn: Optional[Callable[[str], bool]] = None,
        enabled: bool = True,
        auto_zero: bool = False,
        settle_ms: int = 400,
        stable_deg: float = 0.2,
        time_fn: Optional[Callable[[], float]] = None,
    ):
        self.enabled = bool(enabled)
        self.auto_zero = bool(auto_zero)
        self.settle_s = max(0.0, float(settle_ms) / 1000.0)
        self.stable_deg = max(0.0, float(stable_deg))
        self._zero_fn = zero_fn
        self._now = time_fn or time.monotonic
        self._sx = _SideTrack()
        self._dx = _SideTrack()

    @property
    def active_sx(self) -> bool:
        return self._sx.active

    @property
    def active_dx(self) -> bool:
        return self._dx.active

    @property
    def settled_sx(self) -> bool:
        return self._sx.settled

    @property
    def settled_dx(self) -> bool:
        return self._dx.settled

    def reset(self) -> None:
        """Nuovo ciclo di homing: riaspetta l'assestamento sul fermo 0°."""
        self._sx = _SideTrack()
        self._dx = _SideTrack()

    def update(
        self,
        sx_active: bool,
        dx_active: bool,
        sx_angle: Optional[float] = None,
        dx_angle: Optional[float] = None,
    ) -> Dict[str, bool]:
        """
        Aggiorna i FC. Ritorna quali lati sono appena assestati.
        Se auto_zero è True, azzera anche l'encoder (solo per test / fallback).
        """
        now = float(self._now())
        return {
            "sx": self._step(self._sx, "sx", bool(sx_active), sx_angle, now),
            "dx": self._step(self._dx, "dx", bool(dx_active), dx_angle, now),
        }

    def _step(
        self,
        track: _SideTrack,
        side: str,
        active: bool,
        angle: Optional[float],
        now: float,
    ) -> bool:
        if not active:
            track.active = False
            track.pending = False
            track.settled = False
            track.last_angle = None
            return False

        if not track.active:
            track.active = True
            track.pending = True
            track.settled = False
            track.t_active = now
            track.t_stable = now
            track.last_angle = angle

        if angle is not None:
            if track.last_angle is None or abs(float(angle) - float(track.last_angle)) > self.stable_deg:
                track.t_stable = now
            track.last_angle = float(angle)

        if not self.enabled or not track.pending or track.settled:
            return False

        held_ok = (now - track.t_active) >= self.settle_s
        stable_ok = (now - track.t_stable) >= self.settle_s
        if not (held_ok and stable_ok):
            return False

        track.pending = False
        track.settled = True
        if self.auto_zero and self._zero_fn:
            self._zero_fn(side)
        return True

    def as_state(self) -> Dict[str, bool]:
        return {
            "head_fc_zero_sx": self._sx.active,
            "head_fc_zero_dx": self._dx.active,
            "head_fc_settled_sx": self._sx.settled,
            "head_fc_settled_dx": self._dx.settled,
        }
