# ... (altri import e codice)
class DummyMachineState:
    def __init__(self):
        self.machine_homed = False
        self.emergency_active = False
        self.brake_active = False
        self.clutch_active = True
        self.positioning_active = False
        self.min_distance = 250.0
        self.max_cut_length = 4000.0
        self.position_current = self.min_distance
        self.left_head_angle = 0.0
        self.right_head_angle = 0.0
        self.count_active_on_closed = True
        self.invert_left_switch = False
        self.invert_right_switch = False
        self.cut_pulse_debounce_ms = 120
        self.cut_pulse_group_ms = 500
        self.semi_auto_target_pieces = 0
        self.semi_auto_count_done = 0
        self.work_queue = []
        self.current_work_idx = None

    def set_active_mode(self, mode: str): pass
    def normalize_after_manual(self): self.clutch_active = True
    def set_head_button_input_enabled(self, enabled: bool): pass

    # Simulazione homing: porta a minima, imposta homed=True, freno OFF, frizione ON
    def do_homing(self, callback=None):
        import time, threading
        def seq():
            if self.emergency_active:
                if callback: callback(success=False, msg="EMERGENZA")
                return
            if self.machine_homed:
                if callback: callback(success=True, msg="GIÀ HOMED")
                return
            # “avvicinamento” temporizzato
            time.sleep(1.0)
            self.position_current = self.min_distance
            self.brake_active = False
            self.clutch_active = True
            self.machine_homed = True
            if callback: callback(success=True, msg="HOMING OK")
        threading.Thread(target=seq, daemon=True).start()

    def move_to_length_and_angles(self, length_mm: float, ang_sx: float, ang_dx: float, done_cb=None):
        self.brake_active = False
        self.positioning_active = True
        self.left_head_angle = float(ang_sx)
        self.right_head_angle = float(ang_dx)
        from threading import Thread
        import time
        def run():
            time.sleep(0.8)
            self.positioning_active = False
            self.brake_active = True
            if done_cb: done_cb(True, "OK")
        Thread(target=run, daemon=True).start()
# ... resto file invariato
