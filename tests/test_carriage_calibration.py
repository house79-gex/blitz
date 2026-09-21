"""Test calibrazione lineare carro a due punti."""
from ui_qt.logic.carriage_calibration import (
    compute_two_point_correction,
    apply_correction_to_position,
)


def test_two_point_ideal():
    res = compute_two_point_correction(400.0, 3600.0, 400.0, 3600.0, 84.880)
    assert res.ok
    assert abs(res.correction_factor - 1.0) < 1e-9
    assert abs(res.pulses_per_mm_effective - 84.880) < 1e-6


def test_two_point_encoder_overreads():
    # Encoder dice 3200 di corsa, misura reale 3180
    res = compute_two_point_correction(400.0, 3600.0, 400.0, 3580.0, 84.880)
    assert res.ok
    assert res.correction_factor < 1.0
    assert res.pulses_per_mm_effective > 84.880


def test_two_point_span_too_small():
    res = compute_two_point_correction(400.0, 420.0, 400.0, 420.0, 84.880)
    assert not res.ok


def test_apply_correction():
    assert abs(apply_correction_to_position(1000.0, 1.002) - 1002.0) < 1e-9
