import time, math, random
from typing import Dict, Any, Optional

class SimulationMachine:
    """
    Simulazione macchina per fase di progettazione.
    Riproduce encoder, stato posizionamento, freno, pressori, impulsi.
    """
    def __init__(self):
        # Stato basico
        self.encoder_position: float = 0.0
        self.position_target: Optional[float] = None
        self.positioning_active: bool = False
        self.brake_active: bool = False
        self.left_presser_locked: bool = False
        self.right_presser_locked: bool = False

        # Inputs logici
        self._inputs: Dict[str, bool] = {
            "blade_pulse": False,
            "start_pressed": False,
        }

        # Parametri dinamica (ms)
        self.speed_mm_s: float = 2500.0   # velocità fittizia
        self.last_tick: float = time.time()

        # Sim profile / angles
        self.current_profile: str = ""
        self.current_element: str = ""
        self.ang_sx: float = 0.0
        self.ang_dx: float = 0.0

    # Letture
    def get_position(self) -> Optional[float]:
        return self.encoder_position

    def is_positioning_active(self) -> bool:
        return self.positioning_active

    def get_input(self, name: str) -> bool:
        return bool(self._inputs.get(name, False))

    def get_state(self) -> Dict[str, Any]:
        return {
            "encoder_position": self.encoder_position,
            "positioning_active": self.positioning_active,
            "brake_active": self.brake_active,
            "left_presser_locked": self.left_presser_locked,
            "right_presser_locked": self.right_presser_locked,
            "blade_pulse": self._inputs.get("blade_pulse", False),
            "start_pressed": self._inputs.get("start_pressed", False),
            "current_profile": self.current_profile,
            "current_element": self.current_element,
            "ang_sx": self.ang_sx,
            "ang_dx": self.ang_dx
        }

    # Comandi
    def move_to(self, length_mm: float, ang_sx: float = 0.0, ang_dx: float = 0.0,
                profile: str = "", element: str = "") -> None:
        self.position_target = max(0.0, float(length_mm))
        self.positioning_active = True
        self.current_profile = profile
        self.current_element = element
        self.ang_sx = float(ang_sx)
        self.ang_dx = float(ang_dx)

    def lock_brake(self) -> None:
        self.brake_active = True

    def release_brake(self) -> None:
        self.brake_active = False

    def set_presser(self, side: str, locked: bool) -> None:
        if side.lower().startswith("l"):
            self.left_presser_locked = bool(locked)
        elif side.lower().startswith("r"):
            self.right_presser_locked = bool(locked)

    def simulate_cut_pulse(self) -> None:
        self._inputs["blade_pulse"] = True

    def simulate_start_press(self) -> None:
        self._inputs["start_pressed"] = True

    # Aggiornamento temporale
    def tick(self) -> None:
        now = time.time()
        dt = max(1e-4, now - self.last_tick)
        self.last_tick = now

        # Avanzamento posizione
        if self.positioning_active and self.position_target is not None:
            diff = self.position_target - self.encoder_position
            direction = 1.0 if diff > 0 else -1.0
            step = self.speed_mm_s * dt
            if abs(diff) <= step:
                self.encoder_position = self.position_target
                self.positioning_active = False
            else:
                self.encoder_position += direction * step

        # Resetta impulsi monofronto
        if self._inputs.get("blade_pulse"):
            # dura un tick
            self._inputs["blade_pulse"] = False
        if self._inputs.get("start_pressed"):
            self._inputs["start_pressed"] = False
