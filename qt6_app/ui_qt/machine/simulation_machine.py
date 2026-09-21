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
        speed_mm_s: float = 600.0
    ):
        self.min_distance = min_distance
        self.max_cut_length = max_cut_length
        self.speed_mm_s = speed_mm_s

        self. encoder_position = min_distance
        self._target:  Optional[float] = None
        self._moving = False

        self.left_head_angle = 0.0
        self.right_head_angle = 0.0
        self.measured_left_head_angle = 0.0
        self.measured_right_head_angle = 0.0

        self. brake_active = False
        self. clutch_active = True
        self.left_morse_locked = False
        self.right_morse_locked = False
        self.left_blade_inhibit = False
        self.right_blade_inhibit = False

        self.machine_homed = False
        self.emergency_active = False
        self.homing_in_progress = False

        # Tracking modalità per controllo morse
        self._software_morse_control_enabled = False
        self._current_mode = "idle"
        self._current_piece_length = 0.0
        self._bar_stock_length = 6500.0

        self._inputs:  Dict[str, bool] = {
            "blade_pulse": False,
            "start_pressed":  False,
            "dx_blade_out": False,
            "head_sx_zero": False,
            "head_dx_zero": False,
        }
        from ..hardware.head_home_fc import HeadHomeLimitHelper
        self._head_home = HeadHomeLimitHelper(
            zero_fn=None,
            auto_zero=False,
            settle_ms=0,
        )

        self._last_tick = time.time()
        self._lock_brake_on_stop = True

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
        self._lock_brake_on_stop = True
        self._target = max(self.min_distance, min(float(length_mm), self.max_cut_length))
        self._moving = True
        self. left_head_angle = float(ang_sx)
        self.right_head_angle = float(ang_dx)
        self.measured_left_head_angle = float(ang_sx)
        self.measured_right_head_angle = float(ang_dx)
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
        self.measured_left_head_angle = float(sx)
        self.measured_right_head_angle = float(dx)
        return True

    def command_zero_head_encoder(self, side: str = "both") -> bool:
        """In simulazione l'azzeramento allinea la misura al comando 0°."""
        side = (side or "both").lower()
        if side in ("sx", "both"):
            self.measured_left_head_angle = 0.0
            self.left_head_angle = 0.0
        if side in ("dx", "both"):
            self.measured_right_head_angle = 0.0
            self.right_head_angle = 0.0
        return True

    def set_mode_context(self, mode: str, piece_length_mm: float = 0.0, 
                         bar_length_mm: float = 6500.0):
        """Imposta contesto modalità (simulata)."""
        self._current_mode = str(mode)
        self._current_piece_length = float(piece_length_mm)
        self._bar_stock_length = float(bar_length_mm)
        # Frizione sempre inserita tranne in Manuale
        if (self._current_mode or "").lower() == "manual":
            self.command_set_clutch(False)
        else:
            self.command_set_clutch(True)
        self._update_morse_control_mode()

    def _update_morse_control_mode(self):
        """Decide se abilitare controllo software morse (simulata)."""
        was_enabled = self._software_morse_control_enabled
        
        mode = (self._current_mode or "").lower()
        if mode == "manual":
            self._software_morse_control_enabled = False
        elif mode.startswith("ultra_long") or mode in (
            "plan", "semi", "semi_auto", "normal",
            "out_of_quota", "ultra_short", "extra_long",
        ):
            self._software_morse_control_enabled = True
        else:
            self._software_morse_control_enabled = mode not in ("idle", "")
        
        if was_enabled != self._software_morse_control_enabled: 
            mode_str = "SOFTWARE" if self._software_morse_control_enabled else "PULSANTIERA"
            print(f"🔧 [SIM] Controllo morse:  {mode_str}")

    def command_set_morse(self, left_locked: bool, right_locked: bool) -> bool:
        """Comanda morse solo se controllo software abilitato."""
        if not self._software_morse_control_enabled: 
            return False
        
        self. left_morse_locked = bool(left_locked)
        self.right_morse_locked = bool(right_locked)
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
            self._lock_brake_on_stop = False
            self._moving = False
            self.command_set_head_angles(0.0, 0.0)
            self.command_zero_head_encoder("both")
            time.sleep(0.6)
            self. encoder_position = self.min_distance
            self._target = self. min_distance
            self. brake_active = False
            self. clutch_active = True
            self.machine_homed = True
            self.homing_in_progress = False
            # Il freno si blocca solo nelle sequenze Auto/Semi/Manuale, non a fine homing
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
                if self._lock_brake_on_stop:
                    self.command_lock_brake()
            else:
                step = self.speed_mm_s * dt
                if dist > 0:
                    self.encoder_position += min(step, dist)
                else:
                    self.encoder_position += max(-step, dist)

        for key in ("blade_pulse", "start_pressed", "dx_blade_out"):
            self._inputs[key] = False

        # Blocco meccanico 0°: il FC è attivo con la testa appoggiata
        sx_fc = abs(float(self.left_head_angle)) < 0.5
        dx_fc = abs(float(self.right_head_angle)) < 0.5
        self._inputs["head_sx_zero"] = sx_fc
        self._inputs["head_dx_zero"] = dx_fc
        self._head_home.update(sx_fc, dx_fc)

        # In simulazione la misura encoder segue il comando (nessun ritardo)
        self.measured_left_head_angle = self.left_head_angle
        self.measured_right_head_angle = self.right_head_angle

    def get_state(self) -> Dict[str, Any]:
        return {
            "homed":  self.machine_homed,
            "position_mm": self. encoder_position,
            "target_mm": self._target,
            "moving": self._moving,
            "homing_in_progress": self.homing_in_progress,
            "brake_active": self.brake_active,
            "clutch_active":  self.clutch_active,
            "left_morse_locked": self.left_morse_locked,
            "right_morse_locked": self.right_morse_locked,
            "left_blade_inhibit": self.left_blade_inhibit,
            "right_blade_inhibit": self.right_blade_inhibit,
            "emergency_active": self.emergency_active,
            "left_head_angle": self.left_head_angle,
            "right_head_angle": self.right_head_angle,
            "measured_left_head_angle": self.measured_left_head_angle,
            "measured_right_head_angle": self.measured_right_head_angle,
            "head_encoder_online": True,
            "head_encoder_online_sx": True,
            "head_encoder_online_dx": True,
            "head_fc_zero_sx": bool(self._head_home.active_sx),
            "head_fc_zero_dx": bool(self._head_home.active_dx),
        }

    def close(self) -> None:
        self._moving = False

    def reset(self):
        self.machine_homed = False
        self.homing_in_progress = False
        self.encoder_position = self.min_distance
        self. brake_active = False
        self.emergency_active = False
