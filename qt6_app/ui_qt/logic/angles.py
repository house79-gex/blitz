"""
Convenzione angoli taglio BLITZ.

0° = taglio quadro (teste verticali).
45° = inclinazione massima.
Valori ~90° (vecchia convenzione «lama perpendicolare») si trattano come 0°.
"""
from __future__ import annotations


def normalize_cut_tilt_deg(raw) -> float:
    """Riporta un angolo testa/cutlist nell'intervallo 0–45°."""
    try:
        a = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if a > 45.0:
        a = abs(90.0 - a)
    return max(0.0, min(45.0, a))
