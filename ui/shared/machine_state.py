import time
import threading
from typing import List, Dict, Any, Optional, Tuple

class MachineState:
    """
    Stato macchina e logica.
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

        # Pulsante testa abilitato (Manuale)
        self._head_button_input_enabled = False

        # Contapezzi (omessi qui per brevità: invariati rispetto alla tua versione)

        # Output comando taglio
        self.cut_enable_output = False

        # Avvia worker encoder
        self._start_encoder_sim()

    def set_active_mode(self, mode: str):
        self.active_mode = mode if mode in ("manual", "semi", "automatic", "other") else "other"
        self._update_cut_enable_output()

    # ---------------- Encoder simulation (fix) ----------------
    def _start_encoder_sim(self):
        def loop():
            while True:
                # Aggiorna SEMPRE l'encoder dalla posizione attuale, anche durante i movimenti
                self.encoder_position = self.position_current
                time.sleep(0.05)
        threading.Thread(target=loop, daemon=True).start()

    # ---------------- Emergenza (omesso: invariato) ----------------
    # ... mantieni le tue funzioni set_emergency_input, clear_emergency, ecc.

    # ---------------- Pulsante TESTA (omesso: invariato) ----------------

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

        # contatori / work queue (omessi: invariati)
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
            self.encoder_position = self.min_distance
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

    # ---------------- Manuale: freno/frizione (omesso: invariato) ----------------

    # ---------------- Movimento (fix encoder live) ----------------
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
        self._update_cut_enable_output()  # durante movimento: disabilita cut

        def motion():
            start = self.position_current
            target = self.position_target
            steps = 80
            dt = 0.02
            for i in range(steps + 1):
                if self.emergency_active or not self.positioning_active:
                    break
                f = i / steps
                self.position_current = start + (target - start) * f
                # Aggiorna encoder in tempo reale
                self.encoder_position = self.position_current
                time.sleep(dt)
            # Fine movimento
            if not self.emergency_active:
                self.position_current = target
                self.encoder_position = target
            self.positioning_active = False
            # Blocca freno e aggiorna cut_enable
            self.brake_active = True
            self._update_cut_enable_output()
            if done_cb:
                if self.emergency_active:
                    done_cb(False, "INTERR. EMERGENZA")
                else:
                    done_cb(True, "POSIZIONATO")
        threading.Thread(target=motion, daemon=True).start()

    # ---------------- Restante logica (conta, queue, cut_enable) invariata ----------------
    def _compute_cut_enable(self) -> bool:
        if self.emergency_active or not self.machine_homed:
            return False
        if self.positioning_active:
            return False
        if not self.brake_active:
            return False
        if self.active_mode == "semi":
            return (getattr(self, "semi_auto_target_pieces", 0) - getattr(self, "semi_auto_count_done", 0)) > 0
        if self.active_mode == "automatic":
            it = self.get_current_work()
            return bool(it and it["remaining"] > 0)
        return False

    def _update_cut_enable_output(self):
        self.cut_enable_output = self._compute_cut_enable()

    # Placeholder per metodi referenziati dal pannello (se mancano altrove)
    def get_current_work(self):  # evita errori se non usi automatico
        return None
