from __future__ import annotations
from typing import Optional, Dict, Any
from ui_qt.machine.interfaces import MachineIO

class MachineAdapter:
    """
    Adatta l'oggetto 'raw_machine' (SimulationMachine o RealMachine)
    ad eventuali accessi legacy e fornisce comodo wrapper.
    Le pagine useranno SEMPRE l'istanza di MachineAdapter (mio) anziché il raw.
    """
    def __init__(self, raw_machine: MachineIO):
        self._raw = raw_machine

    # Accessi diretti unificati
    def get_position(self) -> Optional[float]:
        return self._raw.get_position()

    def is_positioning_active(self) -> bool:
        return self._raw.is_positioning_active()

    def get_input(self, name: str) -> bool:
        return self._raw.get_input(name)

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

    # Simulazioni
    def command_sim_cut_pulse(self) -> None:
        self._raw.command_sim_cut_pulse()

    def command_sim_start_pulse(self) -> None:
        self._raw.command_sim_start_pulse()

    def command_sim_dx_blade_out(self, on: bool) -> None:
        self._raw.command_sim_dx_blade_out(on)

    def tick(self) -> None:
        self._raw.tick()

    def get_state(self) -> Dict[str, Any]:
        return self._raw.get_state()

    def close(self) -> None:
        self._raw.close()
