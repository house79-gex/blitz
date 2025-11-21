from __future__ import annotations
import time
from typing import Dict, Any, Optional
from ui_qt.machine.interfaces import MachineIO

class SimulationMachine(MachineIO):
    def __init__(self, speed_mm_s: float = 2500.0):
        self.encoder_position: float = 0.0
        self._target: Optional[float] = None
        self._speed_mm_s = speed_mm_s
        self._moving = False

        # Stati base
        self.brake_active = False
        self.clutch_active = True
        self.left_presser_locked = False
        self.right_presser_locked = False

        # Angoli teste
        self.left_head_angle = 0.0
        self.right_head_angle = 0.0

        # Inibizioni lama
        self.left_blade_inhibit = False
        self.right_blade_inhibit = False

        # Flag globali
        self.emergency_active = False
        self.machine_homed = True

        # Inputs simulati
        self._inputs: Dict[str, bool] = {
            "blade_pulse": False,
            "start_pressed": False,
            "dx_blade_out": False
        }

        self._last_tick = time.time()

    def get_position(self) -> Optional[float]:
        return self.encoder_position

    def is_positioning_active(self) -> bool:
        return self._moving

    def get_input(self, name: str) -> bool:
        return bool(self._inputs.get(name, False))

    def command_move(self, length_mm: float, ang_sx: float = 0.0, ang_dx: float = 0.0,
                     profile: str = "", element: str = "") -> bool:
        if self.emergency_active:
            return False
        self._target = max(0.0, float(length_mm))
        self._moving = True
        self.left_head_angle = float(ang_sx)
        self.right_head_angle = float(ang_dx)
        self.brake_active = False
        return True

    def command_lock_brake(self) -> bool:
        self.brake_active = True
        return True

    def command_release_brake(self) -> bool:
        self.brake_active = False
        return True

    def command_set_head_angles(self, sx: float, dx: float) -> bool:
        self.left_head_angle = float(sx)
        self.right_head_angle = float(dx)
        return True

    def command_set_pressers(self, left_locked: bool, right_locked: bool) -> bool:
        self.left_presser_locked = bool(left_locked)
        self.right_presser_locked = bool(right_locked)
        return True

    def command_set_blade_inhibit(self, left: Optional[bool] = None, right: Optional[bool] = None) -> bool:
        if left is not None:
            self.left_blade_inhibit = bool(left)
        if right is not None:
            self.right_blade_inhibit = bool(right)
        return True

    def command_sim_cut_pulse(self) -> None:
        self._inputs["blade_pulse"] = True

    def command_sim_start_pulse(self) -> None:
        self._inputs["start_pressed"] = True

    def command_sim_dx_blade_out(self, on: bool) -> None:
        self._inputs["dx_blade_out"] = bool(on)

    def tick(self) -> None:
        now = time.time()
        dt = max(1e-4, now - self._last_tick)
        self._last_tick = now

        if self._moving and self._target is not None:
            diff = self._target - self.encoder_position
            direction = 1.0 if diff >= 0 else -1.0
            step = self._speed_mm_s * dt
            if abs(diff) <= step:
                self.encoder_position = self._target
                self._moving = False
                self.brake_active = True
            else:
                self.encoder_position += direction * step

        # Reset impulsi monofronto
        if self._inputs.get("blade_pulse"):
            self._inputs["blade_pulse"] = False
        if self._inputs.get("start_pressed"):
            self._inputs["start_pressed"] = False

    def get_state(self) -> Dict[str, Any]:
        return {
            "position_mm": self.encoder_position,
            "target_mm": self._target,
            "moving": self._moving,
            "brake_active": self.brake_active,
            "clutch_active": self.clutch_active,
            "left_presser_locked": self.left_presser_locked,
            "right_presser_locked": self.right_presser_locked,
            "left_blade_inhibit": self.left_blade_inhibit,
            "right_blade_inhibit": self.right_blade_inhibit,
            "head_angles": {
                "sx": self.left_head_angle,
                "dx": self.right_head_angle
            },
            "inputs": dict(self._inputs),
            "emergency_active": self.emergency_active,
            "homed": self.machine_homed
        }

    def close(self) -> None:
        pass
