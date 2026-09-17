"""Finecorsa 0° teste: assestamento; zero encoder solo in homing."""
import time

from qt6_app.ui_qt.hardware.head_home_fc import HeadHomeLimitHelper
import json
from pathlib import Path

import pytest

from qt6_app.ui_qt.hardware.head_tilt_drive import (
    DEFAULT_STROKE_MM,
    LinearActuatorTiltDrive,
    PneumaticTwoPosDrive,
    clamp_stroke_mm,
    create_head_tilt_drive,
    feedforward_mm_for_deg,
    parse_stroke_mm,
    snap_two_pos_deg,
)
from qt6_app.ui_qt.machine.simulation_machine import SimulationMachine


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_does_not_zero_on_first_contact():
    zeros = []
    clock = _Clock()
    h = HeadHomeLimitHelper(
        zero_fn=lambda s: zeros.append(s),
        auto_zero=True,
        settle_ms=400,
        time_fn=clock,
    )
    assert h.update(True, False, sx_angle=8.0) == {"sx": False, "dx": False}
    assert zeros == []
    clock.t = 0.2
    assert h.update(True, False, sx_angle=3.0) == {"sx": False, "dx": False}
    assert zeros == []


def test_zeros_when_held_and_angle_stable():
    zeros = []
    clock = _Clock()
    h = HeadHomeLimitHelper(
        zero_fn=lambda s: zeros.append(s),
        auto_zero=True,
        settle_ms=400,
        time_fn=clock,
    )
    h.update(True, False, sx_angle=5.0)
    clock.t = 0.5
    assert h.update(True, False, sx_angle=1.0) == {"sx": False, "dx": False}
    clock.t = 1.0
    assert h.update(True, False, sx_angle=1.0) == {"sx": True, "dx": False}
    assert zeros == ["sx"]
    clock.t = 2.0
    assert h.update(True, False, sx_angle=1.0) == {"sx": False, "dx": False}
    assert zeros == ["sx"]


def test_drop_before_settle_cancels_zero():
    zeros = []
    clock = _Clock()
    h = HeadHomeLimitHelper(
        zero_fn=lambda s: zeros.append(s),
        auto_zero=True,
        settle_ms=400,
        time_fn=clock,
    )
    h.update(True, False)
    clock.t = 0.2
    h.update(False, False)
    clock.t = 1.0
    assert h.update(False, False) == {"sx": False, "dx": False}
    assert zeros == []


def test_settle_without_auto_zero_is_for_homing():
    zeros = []
    clock = _Clock()
    h = HeadHomeLimitHelper(
        zero_fn=lambda s: zeros.append(s),
        auto_zero=False,
        settle_ms=400,
        time_fn=clock,
    )
    h.update(True, True)
    clock.t = 0.4
    assert h.update(True, True) == {"sx": True, "dx": True}
    assert zeros == []
    assert h.settled_sx is True
    assert h.settled_dx is True


def test_auto_zero_disabled_still_tracks():
    zeros = []
    h = HeadHomeLimitHelper(
        zero_fn=lambda s: zeros.append(s),
        auto_zero=False,
        settle_ms=0,
    )
    h.update(True, True)
    assert zeros == []
    assert h.active_sx is True
    st = h.as_state()
    assert st["head_fc_zero_sx"] is True
    assert st["head_fc_zero_dx"] is True


def test_simulation_fc_at_mechanical_zero():
    m = SimulationMachine()
    m.command_set_head_angles(45.0, 45.0)
    m.tick()
    assert m.get_input("head_sx_zero") is False

    m.command_set_head_angles(0.0, 0.0)
    m.tick()
    assert m.get_input("head_sx_zero") is True
    assert m.get_input("head_dx_zero") is True
    m.command_sim_cut_pulse()
    assert m.get_input("blade_pulse") is True
    m.tick()
    assert m.get_input("blade_pulse") is False
    assert m.get_input("head_sx_zero") is True


def test_simulation_homing_zeros_heads_and_carriage():
    m = SimulationMachine()
    m.command_set_head_angles(45.0, 22.0)
    done = []
    m.do_homing(callback=lambda **kw: done.append(kw))
    for _ in range(40):
        if done:
            break
        time.sleep(0.05)
    assert done and done[0].get("success") is True
    assert m.machine_homed is True
    assert m.left_head_angle == 0.0
    assert m.right_head_angle == 0.0
    assert m.measured_left_head_angle == 0.0
    assert m.measured_right_head_angle == 0.0


def test_snap_two_pos_and_pneumatic_pulse():
    assert snap_two_pos_deg(0) == 0.0
    assert snap_two_pos_deg(22.4) == 0.0
    assert snap_two_pos_deg(22.5) == 45.0
    pulses = []
    drv = PneumaticTwoPosDrive(lambda side, to_45: pulses.append((side, to_45)))
    sx, dx = drv.move_to_deg(30.0, 10.0)
    assert sx == 45.0 and dx == 0.0
    assert pulses == [("sx", True), ("dx", False)]


def test_linear_actuator_scaffold_does_not_move():
    drv = LinearActuatorTiltDrive({"enabled": False})
    sx, dx = drv.move_to_deg(12.0, 33.0)
    assert sx == 12.0 and dx == 33.0
    factory = create_head_tilt_drive({"head_tilt": {"mode": "linear_actuator"}})
    assert factory.mode == "linear_actuator"
    assert factory.stroke_mm == DEFAULT_STROKE_MM


def test_cylinder_stroke_is_85_mm():
    """Corsa misurata sui cilindri: 85 mm (perni, 0°→45°)."""
    assert DEFAULT_STROKE_MM == 85.0
    assert parse_stroke_mm({}) == 85.0
    assert parse_stroke_mm({"stroke_mm": None}) == 85.0
    assert parse_stroke_mm({"stroke_mm": 0}) == 85.0
    assert parse_stroke_mm({"stroke_mm": "x"}) == 85.0
    assert parse_stroke_mm({"stroke_mm": 85}) == 85.0
    assert clamp_stroke_mm(-1) == 0.0
    assert clamp_stroke_mm(90) == 85.0
    assert feedforward_mm_for_deg(0) == 0.0
    assert feedforward_mm_for_deg(45) == 85.0
    assert feedforward_mm_for_deg(22.5) == 42.5
    assert feedforward_mm_for_deg(90) == 85.0

    drv = LinearActuatorTiltDrive({"enabled": False, "stroke_mm": 85})
    assert drv.stroke_mm == 85.0
    assert drv.mm_for_deg(45.0) == 85.0
    assert drv.mm_for_deg(0.0) == 0.0

    cfg_path = Path(__file__).resolve().parents[2] / "data" / "hardware_config.json"
    with cfg_path.open(encoding="utf-8") as fh:
        hw = json.load(fh)
    assert hw["head_tilt_actuators"]["stroke_mm"] == 85
    factory = create_head_tilt_drive(hw, pulse_fn=lambda *_args: None)
    assert factory.mode == "pneumatic_2pos"

    lin = create_head_tilt_drive(
        {
            "head_tilt": {"mode": "linear_actuator"},
            "head_tilt_actuators": hw["head_tilt_actuators"],
        }
    )
    assert lin.stroke_mm == 85.0


def test_linear_actuator_enabled_is_not_implemented():
    drv = LinearActuatorTiltDrive({"enabled": True, "stroke_mm": 85})
    with pytest.raises(NotImplementedError) as exc:
        drv.move_to_deg(10.0, 20.0)
    assert "85" in str(exc.value)
