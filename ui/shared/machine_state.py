from __future__ import annotations

class MachineState:
    """
    Porting MachineState con stub I/O.
    Mantiene i nomi/metodi usati dall'interfaccia Tk/Qt:
    - Attributi: emergency_active, machine_homed, brake_active, positioning_active, clutch_active, encoder_position
    - Metodi: set_head_button_input_enabled, normalize_after_manual, simulate_head_button, toggle_emergency,
              clear_emergency, simulate_cut_pulse, decrement_current_remaining, start_jog/jog/stop_jog,
              open_clamp/close_clamp, home_machine/home, move_to_position/move_head_to, move_by/nudge,
              set_zero/zero_position, rebuild_work_queue
    """
    def __init__(self):
        # Stato macchina
        self.emergency_active = False
        self.machine_homed = False
        self.brake_active = True
        self.positioning_active = False
        self.clutch_active = False
        self.encoder_position = 0.0

        # Sensori contapezzi / utility
        self.count_active_on_closed = True
        self.invert_left_switch = False
        self.invert_right_switch = False
        self.cut_pulse_debounce_ms = 50
        self.cut_pulse_group_ms = 300

        # Sensori
        self.left_switch_active = False
        self.right_switch_active = False

        # Coda lavoro (se usata)
        self.work_queue = []

        # Internal
        self._head_button_enabled = False

    # Utility / globali
    def set_head_button_input_enabled(self, enabled: bool):
        self._head_button_enabled = bool(enabled)

    def normalize_after_manual(self):
        # Ripristina eventuali stati (stub)
        self.positioning_active = False

    # EMERGENZA
    def toggle_emergency(self):
        self.emergency_active = not self.emergency_active
        if self.emergency_active:
            # Blocco base in emergenza
            self.positioning_active = False
            self.clutch_active = False
        return self.emergency_active

    def clear_emergency(self):
        self.emergency_active = False

    # Pulsanti testata / taglio
    def simulate_head_button(self):
        # Stub: abilita input e genera un impulso taglio
        self._head_button_enabled = True
        self.simulate_cut_pulse()

    def simulate_cut_pulse(self):
        # Stub: decrementa un ipotetico contatore corrente
        self.decrement_current_remaining()

    def decrement_current_remaining(self):
        # Stub: no-op; in reale agirebbe sul job corrente
        pass

    # Jog / movimento
    def start_jog(self, direction: str, speed: int):
        if self.emergency_active:
            return
        self.positioning_active = True
        step = max(0.1, float(speed) * 0.1)
        if direction.lower().startswith("l"):
            self.encoder_position -= step
        else:
            self.encoder_position += step

    def jog(self, direction: str, speed: int):
        self.start_jog(direction, speed)

    def stop_jog(self):
        self.positioning_active = False

    # Pinza / freno / frizione
    def open_clamp(self):
        self.clutch_active = False

    def close_clamp(self):
        self.clutch_active = True

    # Homing
    def home_machine(self):
        return self.home()

    def home(self):
        if self.emergency_active:
            return False
        self.encoder_position = 0.0
        self.machine_homed = True
        return True

    # Movimento posizionale
    def move_to_position(self, pos: float):
        return self.move_head_to(pos)

    def move_head_to(self, pos: float):
        if self.emergency_active:
            return False
        self.positioning_active = True
        try:
            self.encoder_position = float(pos)
            return True
        finally:
            self.positioning_active = False

    def move_by(self, delta: float):
        return self.nudge(delta)

    def nudge(self, delta: float):
        if self.emergency_active:
            return False
        self.positioning_active = True
        try:
            self.encoder_position += float(delta)
            return True
        finally:
            self.positioning_active = False

    # Zero
    def set_zero(self):
        return self.zero_position()

    def zero_position(self):
        self.encoder_position = 0.0
        return True

    # Work queue
    def rebuild_work_queue(self):
        # Stub: ricostruisce da lista interna, in futuro può leggere da DB
        return list(self.work_queue)
