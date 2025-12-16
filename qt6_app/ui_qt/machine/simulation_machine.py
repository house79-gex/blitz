from __future__ import annotations
import time
from typing import Optional, Dict, Any, Callable

from ui_qt.machine.interfaces import MachineIO


class SimulationMachine(MachineIO):
    """
    Macchina simulata per test senza hardware reale.
    """

    def __init__(
        self,
        min_distance: float = 250.0,
        max_cut_length: float = 4000.0,
        speed_mm_s: float = 2000.0
    ):
        self.min_distance = min_distance
        self.max_cut_length = max_cut_length
        self.speed_mm_s = speed_mm_s

        self. encoder_position = min_distance
        self._target:  Optional[float] = None
        self._moving = False

        self.left_head_angle = 0.0
        self.right_head_angle = 0.0

        self. brake_active = False
        self. clutch_active = True
        self.left_presser_locked = False
        self.right_presser_locked = False
        self.left_blade_inhibit = False
        self.right_blade_inhibit = False

        self.machine_homed = False
        self.emergency_active = False
        self.homing_in_progress = False

        # Tracking modalità per controllo pressori
        self._software_presser_control_enabled = False
        self._current_mode = "idle"
        self._current_piece_length = 0.0
        self._bar_stock_length = 6500.0

        self._inputs:  Dict[str, bool] = {
            "blade_pulse": False,
            "start_pressed":  False,
            "dx_blade_out": False
        }

        self._last_tick = time.time()

    def get_position(self) -> Optional[float]:
        return self.encoder_position

    def is_positioning_active(self) -> bool:
        return self._moving

    def get_input(self, name: str) -> bool:
        return bool(self._inputs. get(name, False))

    def command_move(
        self,
        length_mm: float,
        ang_sx: float = 0.0,
        ang_dx: float = 0.0,
        profile: str = "",
        element: str = ""
    ) -> bool:
        if self.emergency_active or not self.machine_homed or self.homing_in_progress:
            return False
        self._target = max(self.min_distance, min(float(length_mm), self.max_cut_length))
        self._moving = True
        self. left_head_angle = float(ang_sx)
        self.right_head_angle = float(ang_dx)
        self.brake_active = False
        return True

    def command_lock_brake(self) -> bool:
        self.brake_active = True
        return True

    def command_release_brake(self) -> bool:
        self.brake_active = False
        return True

    def command_set_clutch(self, active: bool) -> bool:
        """Controlla frizione (simulata)."""
        self.clutch_active = bool(active)
        return True

    def command_set_head_angles(self, sx:  float, dx: float) -> bool:
        self.left_head_angle = float(sx)
        self.right_head_angle = float(dx)
        return True

    def set_mode_context(self, mode: str, piece_length_mm: float = 0.0, 
                         bar_length_mm: float = 6500.0):
        """Imposta contesto modalità (simulata)."""
        self._current_mode = str(mode)
        self._current_piece_length = float(piece_length_mm)
        self._bar_stock_length = float(bar_length_mm)
        self._update_presser_control_mode()

    def _update_presser_control_mode(self):
        """Decide se abilitare controllo software pressori (simulata)."""
        was_enabled = self._software_presser_control_enabled
        
        if self._current_mode.startswith("ultra_long"):
            self._software_presser_control_enabled = True
        elif self._current_mode == "manual": 
            self._software_presser_control_enabled = False
        elif self._current_mode in ("plan", "semi"):
            is_out_of_quota = self._current_piece_length > self._bar_stock_length
            is_ultra_short = 0 < self._current_piece_length < 500.0
            self._software_presser_control_enabled = (is_out_of_quota or is_ultra_short)
        else:
            self._software_presser_control_enabled = False
        
        if was_enabled != self._software_presser_control_enabled: 
            mode_str = "SOFTWARE" if self._software_presser_control_enabled else "PULSANTIERA"
            print(f"🔧 [SIM] Controllo pressori:  {mode_str}")

    def command_set_pressers(self, left_locked: bool, right_locked: bool) -> bool:
        """Comanda pressori solo se controllo software abilitato."""
        if not self._software_presser_control_enabled: 
            return False
        
        self. left_presser_locked = bool(left_locked)
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

    def do_homing(self, callback: Optional[Callable[..., None]] = None) -> None:
        import threading, time
        def seq():
            if self.emergency_active:
                if callback: callback(success=False, msg="EMERGENZA")
                return
            self.homing_in_progress = True
            self._moving = False
            time.sleep(0.6)
            self. encoder_position = self.min_distance
            self._target = self. min_distance
            self. brake_active = False
            self. clutch_active = True
            self.machine_homed = True
            self.homing_in_progress = False
            if callback: callback(success=True, msg="HOMING OK")
        threading.Thread(target=seq, daemon=True).start()

    def tick(self) -> None:
        now = time.time()
        dt = now - self._last_tick
        self._last_tick = now

        if self._moving and self._target is not None:
            dist = self._target - self.encoder_position
            if abs(dist) < 1.0:
                self.encoder_position = self._target
                self._moving = False
            else:
                step = self.speed_mm_s * dt
                if dist > 0:
                    self.encoder_position += min(step, dist)
                else:
                    self.encoder_position += max(-step, dist)

        for key in list(self._inputs.keys()):
            self._inputs[key] = False

    def get_state(self) -> Dict[str, Any]:
        return {
            "homed":  self.machine_homed,
            "position_mm": self. encoder_position,
            "target_mm": self._target,
            "moving": self._moving,
            "homing_in_progress": self.homing_in_progress,
            "brake_active": self.brake_active,
            "clutch_active":  self.clutch_active,
            "left_presser_locked": self.left_presser_locked,
            "right_presser_locked": self.right_presser_locked,
            "left_blade_inhibit": self.left_blade_inhibit,
            "right_blade_inhibit": self.right_blade_inhibit,
            "emergency_active": self.emergency_active,
            "left_head_angle": self.left_head_angle,
            "right_head_angle": self.right_head_angle
        }

    def close(self) -> None:
        self._moving = False

    def reset(self):
        self.machine_homed = False
        self.homing_in_progress = False
        self.encoder_position = self.min_distance
        self. brake_active = False
        self.emergency_active = False
