"""Test lettura angoli in HeadsView (bug: stato senza head_angles.sx/dx)."""
from qt6_app.ui_qt.widgets.heads_view import (
    HeadsView,
    normalize_head_tilt_deg,
    step_tilt_animation,
)


def test_normalize_head_tilt_deg():
    assert normalize_head_tilt_deg(0) == 0.0
    assert normalize_head_tilt_deg(45) == 45.0
    assert normalize_head_tilt_deg(90) == 0.0
    assert normalize_head_tilt_deg(None) == 0.0
    assert normalize_head_tilt_deg(60) == 30.0  # 90-60


def test_heads_view_reads_left_right_from_state(qapp, mock_machine):
    mock_machine.left_head_angle = 45.0
    mock_machine.right_head_angle = 22.5
    view = HeadsView(mock_machine)
    sx, sx_meas = view._get_angle(left=True)
    dx, dx_meas = view._get_angle(left=False)
    assert sx == 45.0
    assert dx == 22.5
    assert sx_meas is False
    assert dx_meas is False


def test_heads_view_prefers_commanded_when_encoder_online(qapp):
    class _M:
        min_distance = 250.0
        max_cut_length = 4000.0
        left_head_angle = 45.0
        right_head_angle = 22.5

        def get_state(self):
            return {
                "left_head_angle": 45.0,
                "right_head_angle": 22.5,
                "measured_left_head_angle": 0.0,
                "measured_right_head_angle": 0.0,
                "head_encoder_online": True,
                "head_encoder_online_sx": True,
                "head_encoder_online_dx": True,
            }

        def get_position(self):
            return 1000.0

    view = HeadsView(_M())
    sx, sx_meas = view._get_angle(left=True)
    dx, dx_meas = view._get_angle(left=False)
    assert sx == 45.0
    assert dx == 22.5
    assert sx_meas is True
    assert dx_meas is True


def test_step_tilt_animation_reaches_target():
    assert step_tilt_animation(0.0, 45.0, 4.0, speed_deg_s=12.0) == 45.0
    mid = step_tilt_animation(0.0, 45.0, 1.0, speed_deg_s=12.0)
    assert abs(mid - 12.0) < 0.01
    assert step_tilt_animation(40.0, 45.0, 0.1, speed_deg_s=12.0) == 41.2


def test_step_travel_animation_moves_linearly():
    from qt6_app.ui_qt.widgets.heads_view import step_travel_animation
    assert step_travel_animation(0.0, 1000.0, 1.0, speed_mm_s=500.0) == 500.0
    assert step_travel_animation(900.0, 1000.0, 1.0, speed_mm_s=500.0) == 1000.0
