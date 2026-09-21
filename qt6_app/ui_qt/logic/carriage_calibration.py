"""
Calibrazione lineare carro: correzione su due punti (quota encoder vs misura reale).

Formula (come sul vecchio CNC):
  correction_factor = delta_misurato / delta_encoder
  quota_corretta = quota_encoder * correction_factor

Equivalentemente si aggiorna pulses_per_mm:
  ppm_eff = ppm_nom / correction_factor
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class TwoPointCalibrationResult:
    encoder_near_mm: float
    encoder_far_mm: float
    measured_near_mm: float
    measured_far_mm: float
    encoder_span_mm: float
    measured_span_mm: float
    correction_factor: float
    pulses_per_mm_nominal: float
    pulses_per_mm_effective: float
    ok: bool
    message: str


def compute_two_point_correction(
    encoder_near_mm: float,
    encoder_far_mm: float,
    measured_near_mm: float,
    measured_far_mm: float,
    pulses_per_mm_nominal: float,
) -> TwoPointCalibrationResult:
    """
    Calcola il moltiplicatore di correzione da due punti di misura.
    I punti devono essere ben distanziati (es. ~400 mm e ~3600 mm).
    """
    enc_span = float(encoder_far_mm) - float(encoder_near_mm)
    meas_span = float(measured_far_mm) - float(measured_near_mm)
    ppm = float(pulses_per_mm_nominal) if pulses_per_mm_nominal else 0.0

    if abs(enc_span) < 50.0:
        return TwoPointCalibrationResult(
            encoder_near_mm=encoder_near_mm,
            encoder_far_mm=encoder_far_mm,
            measured_near_mm=measured_near_mm,
            measured_far_mm=measured_far_mm,
            encoder_span_mm=enc_span,
            measured_span_mm=meas_span,
            correction_factor=1.0,
            pulses_per_mm_nominal=ppm,
            pulses_per_mm_effective=ppm,
            ok=False,
            message="Span encoder troppo piccolo (< 50 mm): allontana i due punti.",
        )
    if abs(meas_span) < 50.0:
        return TwoPointCalibrationResult(
            encoder_near_mm=encoder_near_mm,
            encoder_far_mm=encoder_far_mm,
            measured_near_mm=measured_near_mm,
            measured_far_mm=measured_far_mm,
            encoder_span_mm=enc_span,
            measured_span_mm=meas_span,
            correction_factor=1.0,
            pulses_per_mm_nominal=ppm,
            pulses_per_mm_effective=ppm,
            ok=False,
            message="Span misurato troppo piccolo (< 50 mm): verifica le misure.",
        )
    if ppm <= 0:
        return TwoPointCalibrationResult(
            encoder_near_mm=encoder_near_mm,
            encoder_far_mm=encoder_far_mm,
            measured_near_mm=measured_near_mm,
            measured_far_mm=measured_far_mm,
            encoder_span_mm=enc_span,
            measured_span_mm=meas_span,
            correction_factor=1.0,
            pulses_per_mm_nominal=ppm,
            pulses_per_mm_effective=ppm,
            ok=False,
            message="pulses_per_mm nominale non valido.",
        )

    # correction > 1 se l'encoder sottostima la corsa reale
    factor = meas_span / enc_span
    if factor < 0.90 or factor > 1.10:
        return TwoPointCalibrationResult(
            encoder_near_mm=encoder_near_mm,
            encoder_far_mm=encoder_far_mm,
            measured_near_mm=measured_near_mm,
            measured_far_mm=measured_far_mm,
            encoder_span_mm=enc_span,
            measured_span_mm=meas_span,
            correction_factor=factor,
            pulses_per_mm_nominal=ppm,
            pulses_per_mm_effective=ppm / factor,
            ok=False,
            message=(
                f"Correzione {factor:.6f} fuori tolleranza ±10%: "
                "ricontrolla misure o punti prima di applicare."
            ),
        )

    ppm_eff = ppm / factor
    err_mm = abs(meas_span - enc_span)
    return TwoPointCalibrationResult(
        encoder_near_mm=encoder_near_mm,
        encoder_far_mm=encoder_far_mm,
        measured_near_mm=measured_near_mm,
        measured_far_mm=measured_far_mm,
        encoder_span_mm=enc_span,
        measured_span_mm=meas_span,
        correction_factor=factor,
        pulses_per_mm_nominal=ppm,
        pulses_per_mm_effective=ppm_eff,
        ok=True,
        message=(
            f"OK: fattore={factor:.6f}, errore span={err_mm:.2f} mm, "
            f"ppm {ppm:.4f} → {ppm_eff:.4f}"
        ),
    )


def apply_correction_to_position(raw_mm: float, correction_factor: float) -> float:
    """Applica il moltiplicatore a una quota encoder grezza."""
    return float(raw_mm) * float(correction_factor or 1.0)


__all__ = [
    "TwoPointCalibrationResult",
    "compute_two_point_correction",
    "apply_correction_to_position",
]
