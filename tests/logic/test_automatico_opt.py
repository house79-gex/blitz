"""Calcoli Automatico: angoli 0/45 vs 90°, packing barre."""
from qt6_app.ui_qt.logic.angles import normalize_cut_tilt_deg
from qt6_app.ui_qt.logic.refiner import (
    _effective_piece_length,
    pack_bars_knapsack_ilp,
    bar_used_length,
)
from qt6_app.ui_qt.widgets.heads_view import normalize_head_tilt_deg


def test_normalize_90_is_square():
    assert normalize_cut_tilt_deg(90) == 0.0
    assert normalize_cut_tilt_deg(0) == 0.0
    assert normalize_cut_tilt_deg(45) == 45.0
    assert normalize_cut_tilt_deg(89.5) == 0.5
    assert normalize_head_tilt_deg(90) == 0.0


def test_effective_length_90_equals_square_not_zero():
    p90 = {"len": 1000.0, "ax": 90.0, "ad": 90.0}
    p0 = {"len": 1000.0, "ax": 0.0, "ad": 0.0}
    p45 = {"len": 1000.0, "ax": 45.0, "ad": 45.0}
    assert abs(_effective_piece_length(p90, 50.0) - 1000.0) < 0.01
    assert abs(_effective_piece_length(p0, 50.0) - 1000.0) < 0.01
    # tan(45°)=1 → sottrae lo spessore per lato
    assert abs(_effective_piece_length(p45, 50.0) - 900.0) < 0.01


def test_pack_two_pieces_on_one_bar():
    pieces = [
        {"len": 3000.0, "ax": 0.0, "ad": 0.0},
        {"len": 3000.0, "ax": 0.0, "ad": 0.0},
    ]
    bars, rem = pack_bars_knapsack_ilp(
        pieces, stock=6500.0, kerf_base=3.0, ripasso_mm=0.0,
        conservative_angle_deg=0.0, max_angle=60.0, max_factor=2.0,
        reversible=False, thickness_mm=0.0, angle_tol=0.5, per_bar_time_s=5,
    )
    assert len(bars) == 1
    assert len(bars[0]) == 2
    used = bar_used_length(bars[0], 3.0, 0.0, False, 0.0, 0.5, 60.0, 2.0)
    assert used <= 6500.0
    assert rem[0] >= 0.0


def test_pack_90_degree_pieces_same_as_square():
    pieces = [{"len": 2000.0, "ax": 90.0, "ad": 90.0} for _ in range(3)]
    bars, _ = pack_bars_knapsack_ilp(
        pieces, stock=6500.0, kerf_base=3.0, ripasso_mm=0.0,
        conservative_angle_deg=0.0, max_angle=60.0, max_factor=2.0,
        reversible=False, thickness_mm=40.0, angle_tol=0.5, per_bar_time_s=5,
    )
    total = sum(len(b) for b in bars)
    assert total == 3
    # Con tan(90) rotto i pezzi avrebbero lunghezza ~0 e starebbero tutti in 1 barra abusiva
    used0 = bar_used_length(bars[0], 3.0, 0.0, False, 40.0, 0.5, 60.0, 2.0)
    assert used0 > 1500.0
