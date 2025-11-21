from __future__ import annotations
from typing import Optional, Dict, Any
from ui_qt.machine.interfaces import MachineIO

class MachineAdapter:
    def __init__(self, raw_machine: MachineIO):
        self._raw = raw_machine

    def get_position(self) -> Optional[float]:
        return self._raw.get_position()

    def is_positioning_active(self) -> bool:
        return self._raw.is_positioning_active()

    def get_input(self, name: str) -> bool:
        try:
            return self._raw.get_input(name)
        except Exception:
            return False

    def command_move(self, length_mm: float, ang_sx: float = 0.0, ang_dx: float = 0.0,
                     profile: str = "", element: str = "") -> bool:
        return self._raw.command_move(length_mm, ang_sx, ang_dx, profile, element)

    def command_lock_brake(self) -> bool:
        return self._raw.command_lock_brake()

    def command_release_brake(self) -> bool:
        return self._raw.command_release_brake()

    def command_set_head_angles(self, sx: float, dx: float) -> bool:
        return self._raw.command_set_head_angles(sx, dx)

    def command_set_pressers(self, left_locked: bool, right_locked: bool) -> bool:
        return self._raw.command_set_pressers(left_locked, right_locked)

    def command_set_blade_inhibit(self, left: Optional[bool] = None, right: Optional[bool] = None) -> bool:
        return self._raw.command_set_blade_inhibit(left, right)

    def command_sim_cut_pulse(self) -> None:
        self._raw.command_sim_cut_pulse()

    def command_sim_start_pulse(self) -> None:
        self._raw.command_sim_start_pulse()

    def command_sim_dx_blade_out(self, on: bool) -> None:
        self._raw.command_sim_dx_blade_out(on)

    def do_homing(self, callback=None) -> None:
        if hasattr(self._raw, "do_homing"):
            self._raw.do_homing(callback=callback)

    def reset_machine(self) -> None:
        if hasattr(self._raw, "reset"):
            try:
                self._raw.reset()
            except Exception:
                pass

    def tick(self) -> None:
        try:
            self._raw.tick()
        except Exception:
            pass

    def get_state(self) -> Dict[str, Any]:
        try:
            return self._raw.get_state()
        except Exception:
            return {}

    def close(self) -> None:
        try:
            self._raw.close()
        except Exception:
            pass
