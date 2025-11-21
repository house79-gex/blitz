from __future__ import annotations
import time
from typing import Dict, Any, Optional, Callable
from ui_qt.machine.interfaces import MachineIO

class SimulationMachine(MachineIO):
    """
    Macchina simulata:
    - Movimento lineare semplice verso un target.
    - Stati per freno, frizione, pressori, inibizioni lama.
    - Impulsi simulati (blade_pulse, start_pressed, dx_blade_out).
    - Homing simulato (do_homing): posiziona alla minima dopo un breve ritardo.
    """

    def __init__(self, speed_mm_s: float = 2500.0):
        # Range macchina (ora esplicito per testa grafica e homing)
        self.min_distance = 250.0
        self.max_cut_length = 4000.0

        # Posizione / movimento
        self.encoder_position: float = self.min_distance
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

        # Inibizioni lame
        self.left_blade_inhibit = False
        self.right_blade_inhibit = False

        # Flag globali
        self.emergency_active = False
        self.machine_homed = False  # inizialmente NON azzerata per mostrare banner

        # Inputs simulati monofronto
        self._inputs: Dict[str, bool] = {
            "blade_pulse": False,
            "start_pressed": False,
            "dx_blade_out": False
        }

        self._last_tick = time.time()

    # --- Interfaccia MachineIO ---
    def get_position(self) -> Optional[float]:
        return self.encoder_position

    def is_positioning_active(self) -> bool:
        return self._moving

    def get_input(self, name: str) -> bool:
        return bool(self._inputs.get(name, False))

    def command_move(
        self,
        length_mm: float,
        ang_sx: float = 0.0,
        ang_dx: float = 0.0,
        profile: str = "",
        element: str = ""
    ) -> bool:
        if self.emergency_active or not self.machine_homed:
            return False
        self._target = max(self.min_distance, min(float(length_mm), self.max_cut_length))
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

    def do_homing(self, callback: Optional[Callable[..., None]] = None) -> None:
        """
        Simula la sequenza di homing: piccolo ritardo, posizione fissata alla minima,
        rilascio freno, frizione inserita, flag machine_homed True.
        """
        import threading, time
        def seq():
            if self.emergency_active:
                if callback: callback(success=False, msg="EMERGENZA")
                return
            time.sleep(0.6)
            self.encoder_position = self.min_distance
            self._target = self.min_distance
            self._moving = False
            self.brake_active = False
            self.clutch_active = True
            self.machine_homed = True
            if callback: callback(success=True, msg="HOMING OK")
        threading.Thread(target=seq, daemon=True).start()

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
                self.brake_active = True  # auto-lock
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
            "homed": self.machine_homed,
            "min_distance": self.min_distance,
            "max_cut_length": self.max_cut_length
        }

    def close(self) -> None:
        pass
