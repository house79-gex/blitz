import time
import threading
from typing import List, Dict, Any, Optional, Tuple

class MachineState:
    """
    Stato macchina e logica:
    - Frizione normalmente inserita (True), freno sbloccato di default (False)
    - Accoppiamento freno+frizione SOLO via pulsante testa (abilitato in Manuale)
    - Emergenza: richiede nuovo homing, blocca movimenti e angoli
    - Tipologie: registro id<->nome per selezioni per NOME in UI
    - Contapezzi:
        * Semi-Automatico: target libero con decremento su impulso teste
        * Automatico: per-Elemento (work queue) con rimanenti; finito il lotto disabilita comando taglio
    - cut_enable_output: stato logico per abilitare il comando hardware di taglio
        Abilitato se: in semi/automatico, no emergenza, homed, freno bloccato, e ci sono pezzi rimanenti
    """
    def __init__(self):
        # Stato base
        self.machine_homed = False
        self.emergency_active = False
        self.brake_active = False
        self.clutch_active = True
        self.positioning_active = False

        # Modalità attiva: 'manual' | 'semi' | 'automatic' | 'other'
        self.active_mode = "other"

        # Touch mode
        self.touch_mode = False

        # Corsa
        self.min_distance = 250.0
        self.max_cut_length = 4000.0
        self.position_current = self.min_distance
        self.position_target = self.min_distance

        # Parametri
        self.external_piece_length = 1000.0
        self.profile_thickness = 50.0

        # Angoli
        self.left_head_angle = 0.0
        self.right_head_angle = 0.0

        # Encoder (simulazione)
        self.encoder_position = self.min_distance

        # Produzione (sorgente)
        self.production_components: List[Dict[str, Any]] = []

        # Tipologie (registro id<->nome)
        self.tipologie_by_id: Dict[Any, str] = {}
        self.tipologie_by_name: Dict[str, Any] = {}
        self.active_tipologia_id: Optional[Any] = None

        # HW emergenza
        self._emergency_contact_open = False

        # Pulsante testa abilitato (solo Manuale)
        self._head_button_input_enabled = False

        # ------------- Contapezzi: ingressi teste -------------
        # Config ingressi
        self.count_active_on_closed = True
        self.invert_left_switch = False
        self.invert_right_switch = False
        self.cut_pulse_debounce_ms = 120
        self.cut_pulse_group_ms = 500
        # Stato per fronti
        self._left_sw_prev_active = False
        self._right_sw_prev_active = False
        self._last_pulse_t = 0.0
        self._last_group_t = 0.0

        # Semi-Auto counters
        self.semi_auto_target_pieces = 0
        self.semi_auto_count_done = 0

        # Automatico: coda per-elemento
        self.work_queue: List[Dict[str, Any]] = []
        self.current_work_idx: Optional[int] = None
        self.sort_ascending = True
        self.group_by_profile = True

        # Output comando taglio
        self.cut_enable_output = False

        # Worker encoder
        self._start_encoder_sim()

    # ---------------- Modalità attiva ----------------
    def set_active_mode(self, mode: str):
        self.active_mode = mode if mode in ("manual", "semi", "automatic", "other") else "other"
        self._update_cut_enable_output()

    # ---------------- Tipologie: registro id<->nome ----------------
    def set_tipologie_registry(self, items: List[Dict[str, Any]]):
        self.tipologie_by_id.clear()
        self.tipologie_by_name.clear()
        for it in items:
            tid = it.get("id")
            nome = it.get("nome") or str(tid)
            self.tipologie_by_id[tid] = nome
            self.tipologie_by_name[nome] = tid

    def get_tipologia_name(self, tid) -> str:
        return self.tipologie_by_id.get(tid, str(tid))

    def get_tipologia_id_by_name(self, nome: str):
        return self.tipologie_by_name.get(nome)

    def set_active_tipologia_by_name(self, nome: str) -> bool:
        tid = self.get_tipologia_id_by_name(nome)
        if tid is None:
            return False
        self.active_tipologia_id = tid
        return True

    # ---------------- Touch ----------------
    def toggle_touch_mode(self):
        self.touch_mode = not self.touch_mode
        return self.touch_mode

    # ---------------- Encoder simulation ----------------
    def _start_encoder_sim(self):
        def loop():
            while True:
                if not self.positioning_active:
                    self.encoder_position = self.position_current
                time.sleep(0.20)
        threading.Thread(target=loop, daemon=True).start()

    # ---------------- Emergenza (hardware) ----------------
    def set_emergency_input(self, contact_open: bool):
        self._emergency_contact_open = contact_open
        if contact_open:
            self.emergency_active = True
            self.positioning_active = False
            self.machine_homed = False
            self.brake_active = False
            self.clutch_active = True
        else:
            self.emergency_active = False
            self.brake_active = False
            self.clutch_active = True
        self._update_cut_enable_output()

    def is_emergency_contact_open(self):
        return self._emergency_contact_open

    # ---------------- Pulsante fisico TESTA ----------------
    def set_head_button_input_enabled(self, enabled: bool):
        self._head_button_input_enabled = bool(enabled)

    def external_head_button_press(self) -> bool:
        if self.emergency_active or self.positioning_active or not self._head_button_input_enabled:
            return False
        target_locked = not self.brake_active
        if target_locked and not self.machine_homed:
            return False
        self.brake_active = target_locked
        self.clutch_active = target_locked
        self._update_cut_enable_output()
        return True

    # ---------------- Reset / Homing ----------------
    def reset(self):
        self.machine_homed = False
        self.emergency_active = False
               self.brake_active = False
        self.clutch_active = True
        self.positioning_active = False
        self.position_current = self.min_distance
        self.position_target = self.min_distance
        self.external_piece_length = 1000.0
        self.profile_thickness = 50.0
        self.left_head_angle = 0.0
        self.right_head_angle = 0.0
        self.encoder_position = self.min_distance
        self._emergency_contact_open = False
        self._head_button_input_enabled = False

        # counters
        self.semi_auto_target_pieces = 0
        self.semi_auto_count_done = 0

        # work queue
        self.work_queue.clear()
        self.current_work_idx = None
        self.cut_enable_output = False

    def do_homing(self, callback=None):
        if self.emergency_active:
            if callback: callback(success=False, msg="EMERGENZA ATTIVA")
            return
        if self.machine_homed:
            if callback: callback(success=True, msg="GIÀ AZZERATA")
            return
        def seq():
            time.sleep(2)
            self.machine_homed = True
            self.position_current = self.min_distance
            self.position_target = self.min_distance
            self.brake_active = False
            self.clutch_active = True
            self.left_head_angle = 0.0
            self.right_head_angle = 0.0
            self._update_cut_enable_output()
            if callback: callback(success=True, msg="HOMING COMPLETATO")
        threading.Thread(target=seq, daemon=True).start()

    # ---------------- Angoli ----------------
    def set_head_angles(self, ang_sx: float, ang_dx: float) -> bool:
        if self.emergency_active:
            return False
        self.left_head_angle = float(ang_sx)
        self.right_head_angle = float(ang_dx)
        return True

    # ---------------- Manuale: freno/frizione ----------------
    def toggle_brake(self) -> bool:
        if self.emergency_active or self.positioning_active:
            return False
        if not self.machine_homed and not self.brake_active:
            return False
        self.brake_active = not self.brake_active
        self._update_cut_enable_output()
        return True

    def toggle_clutch(self) -> bool:
        if self.emergency_active or self.positioning_active:
            return False
        self.clutch_active = not self.clutch_active
        return True

    def normalize_after_manual(self):
        self.clutch_active = True
        self._head_button_input_enabled = False

    # ---------------- Movimento ----------------
    def move_to_length_and_angles(self, length_mm: float, ang_sx: float, ang_dx: float, done_cb=None):
        if self.emergency_active:
            if done_cb: done_cb(False, "EMERGENZA"); return
        if not self.machine_homed:
            if done_cb: done_cb(False, "NO HOMING"); return

        # Sblocco per muovere
        self.brake_active = False
        if not self.clutch_active:
            self.clutch_active = True

        if not self.set_head_angles(ang_sx, ang_dx):
            if done_cb: done_cb(False, "EMERGENZA"); return

        self.position_target = max(self.min_distance, min(length_mm, self.max_cut_length))
        self.positioning_active = True
        self._update_cut_enable_output()  # durante movimento: disable cut

        def motion():
            start = self.position_current
            target = self.position_target
            steps = 60
            for i in range(steps + 1):
                if self.emergency_active or not self.positioning_active:
                    break
                f = i / steps
                self.position_current = start + (target - start) * f
                time.sleep(0.03)
            if not self.emergency_active:
                self.position_current = target
            self.positioning_active = False

            if self.emergency_active:
                self._update_cut_enable_output()
                if done_cb: done_cb(False, "INTERR. EMERGENZA")
            else:
                # Fine posizionamento: blocca freno, poi aggiorna cut_enable
                self.brake_active = True
                self._update_cut_enable_output()
                if done_cb: done_cb(True, "POSIZIONATO")
        threading.Thread(target=motion, daemon=True).start()

    # ---------------- Ordinamento coda (Automatico) ----------------
    def set_sorting(self, ascending: bool = True, group_by_profile: bool = True):
        self.sort_ascending = bool(ascending)
        self.group_by_profile = bool(group_by_profile)

    def rebuild_work_queue(self):
        prev_remaining: Dict[Tuple, int] = {}
        for it in self.work_queue:
            prev_remaining[it["key"]] = it.get("remaining", it.get("quantita", 0))

        items = []
        for comp in self.production_components:
            try:
                q = int(comp.get("quantita", 1))
            except:
                q = 1
            key = (comp.get("id"), float(comp.get("lunghezza_mm", 0.0)),
                   comp.get("profilo"), comp.get("nome"))
            item = {
                "key": key,
                "id": comp.get("id"),
                "nome": comp.get("nome"),
                "profilo": comp.get("profilo"),
                "lunghezza_mm": float(comp.get("lunghezza_mm", 0.0)),
                "ang_sx": float(comp.get("ang_sx", 0.0)),
                "ang_dx": float(comp.get("ang_dx", 0.0)),
                "quantita": max(0, q),
                "remaining": max(0, prev_remaining.get(key, q)),
                "status": "done" if prev_remaining.get(key, q) == 0 else "pending",
            }
            items.append(item)

        if self.group_by_profile:
            items.sort(key=lambda x: (str(x["profilo"] or ""), x["lunghezza_mm"]),
                       reverse=not self.sort_ascending)
        else:
            items.sort(key=lambda x: x["lunghezza_mm"], reverse=not self.sort_ascending)

        self.work_queue = items

        if self.current_work_idx is not None:
            if not (0 <= self.current_work_idx < len(self.work_queue)):
                self.current_work_idx = None

        self._update_cut_enable_output()

    def set_current_work_index(self, idx: Optional[int]) -> bool:
        if idx is None:
            self.current_work_idx = None
            self._update_cut_enable_output()
            return True
        if 0 <= idx < len(self.work_queue):
            self.current_work_idx = idx
            it = self.work_queue[idx]
            if it["remaining"] > 0:
                it["status"] = "in_progress"
            self._update_cut_enable_output()
            return True
        return False

    def get_current_work(self) -> Optional[Dict[str, Any]]:
        if self.current_work_idx is None:
            return None
        if 0 <= self.current_work_idx < len(self.work_queue):
            return self.work_queue[self.current_work_idx]
        return None

    def finish_current_if_done(self):
        it = self.get_current_work()
        if not it:
            return
        if it["remaining"] <= 0:
            it["status"] = "done"
            self.cut_enable_output = False
            # Sblocca freno a fine lotto (richiesta)
            self.brake_active = False

    # ---------------- Contapezzi: ingressi teste ----------------
    def set_head_switch_raw(self, left_raw_closed: bool, right_raw_closed: bool):
        left = (not left_raw_closed) if self.invert_left_switch else left_raw_closed
        right = (not right_raw_closed) if self.invert_right_switch else right_raw_closed
        left_active = left if self.count_active_on_closed else (not left)
        right_active = right if self.count_active_on_closed else (not right)

        left_rise = (not self._left_sw_prev_active) and left_active
        right_rise = (not self._right_sw_prev_active) and right_active

        self._left_sw_prev_active = left_active
        self._right_sw_prev_active = right_active

        if left_rise or right_rise:
            self._handle_cut_pulse_event()

    def simulate_cut_pulse(self):
        self._handle_cut_pulse_event()

    def _handle_cut_pulse_event(self):
        now = time.monotonic()
        if (now - self._last_pulse_t) * 1000 < self.cut_pulse_debounce_ms:
            return
        self._last_pulse_t = now
        if (now - self._last_group_t) * 1000 < self.cut_pulse_group_ms:
            return
        self._last_group_t = now

        if self.emergency_active:
            return

        if self.active_mode == "semi":
            if self.semi_auto_target_pieces > self.semi_auto_count_done:
                self.semi_auto_count_done += 1
                # Fine target => sblocca freno
                if self.semi_auto_count_done >= self.semi_auto_target_pieces:
                    self.brake_active = False
        elif self.active_mode == "automatic":
            it = self.get_current_work()
            if it and it["remaining"] > 0:
                it["remaining"] -= 1
                if it["remaining"] <= 0:
                    it["remaining"] = 0
                    it["status"] = "done"
                    # Fine lotto => sblocca freno
                    self.brake_active = False
        else:
            return

        self._update_cut_enable_output()

    # ---------------- Semi-auto API ----------------
    def semi_auto_set_target_pieces(self, n: int):
        self.semi_auto_target_pieces = max(0, int(n))
        self.semi_auto_count_done = 0
        self._update_cut_enable_output()

    # ---------------- Cut enable output ----------------
    def _compute_cut_enable(self) -> bool:
        if self.emergency_active or not self.machine_homed:
            return False
        if self.positioning_active:
            return False
        if not self.brake_active:
            return False
        if self.active_mode == "semi":
            return (self.semi_auto_target_pieces - self.semi_auto_count_done) > 0
        if self.active_mode == "automatic":
            it = self.get_current_work()
            return bool(it and it["remaining"] > 0)
        return False

    def _update_cut_enable_output(self):
        self.cut_enable_output = self._compute_cut_enable()
