from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QSpinBox, QGridLayout, QDoubleSpinBox, QLineEdit, QComboBox
)
from PySide6.QtCore import Qt, QTimer
from ui_qt.widgets.header import Header
from ui_qt.widgets.status_panel import StatusPanel
from ui_qt.widgets.heads_view import HeadsView
import math

class SemiAutoPage(QWidget):
    """
    Semi-Automatico:
    - Vista teste: SX fissa e DX mobile su scala 250–4000, pivot alla base (pallino), inclinazione 0–45°
    - In alto a destra: riquadro contapezzi (target/contati/rimanenti, reset) sopra lo StatusPanel (più alto)
    - Sotto la grafica (a destra della colonna sinistra): comandi inclinazione su un'unica riga SX/DX
    - Misura esterna + profilo (nome) + spessore (default 0) con calcolo quota interna e validazioni
    """
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self.machine = appwin.machine
        self._poll = None
        # Profili demo (nome -> spessore mm); sostituibile con DB se disponibile
        self._profiles = {
            "Nessuno": 0.0,
            "Alluminio 50": 50.0,
            "PVC 60": 60.0,
            "Legno 40": 40.0,
        }
        self._build()

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(8,8,8,8); root.setSpacing(6)
        root.addWidget(Header(self.appwin, "SEMI-AUTOMATICO"))

        body = QHBoxLayout(); body.setSpacing(8)
        root.addLayout(body, 1)

        # Sinistra: Heads + misure + azioni
        left = QFrame(); body.addWidget(left, 3)
        l = QVBoxLayout(left); l.setContentsMargins(6,6,6,6); l.setSpacing(10)

        self.heads = HeadsView(self.machine, left)
        l.addWidget(self.heads, 3)

        # Riga comandi inclinazione sotto la grafica, allineata a destra
        ang_row = QHBoxLayout()
        ang_row.setSpacing(8)
        ang_lbl = QLabel("Inclinazione Teste (0–45°)")
        ang_lbl.setStyleSheet("font-weight:600;")
        ang_row.addWidget(ang_lbl)
        ang_row.addStretch(1)

        # SX: 45° (accent), 0° (secondario), input
        self.btn_sx_45 = QPushButton("45°")
        self.btn_sx_45.setStyleSheet("background:#8e44ad; color:white;")  # viola
        self.btn_sx_45.clicked.connect(lambda: self._set_angle_quick("sx", 45.0))

        self.btn_sx_0 = QPushButton("0°")
        self.btn_sx_0.setStyleSheet("background:#2c3e50; color:#ecf0f1;")  # scuro
        self.btn_sx_0.clicked.connect(lambda: self._set_angle_quick("sx", 0.0))

        self.spin_sx = QDoubleSpinBox(); self.spin_sx.setRange(0.0, 45.0); self.spin_sx.setDecimals(1)
        self.spin_sx.setValue(float(getattr(self.machine, "left_head_angle", 0.0)))
        self.spin_sx.valueChanged.connect(self._apply_angles)

        # DX: input, 0°, 45°
        self.spin_dx = QDoubleSpinBox(); self.spin_dx.setRange(0.0, 45.0); self.spin_dx.setDecimals(1)
        self.spin_dx.setValue(float(getattr(self.machine, "right_head_angle", 0.0)))
        self.spin_dx.valueChanged.connect(self._apply_angles)

        self.btn_dx_0  = QPushButton("0°")
        self.btn_dx_0.setStyleSheet("background:#2c3e50; color:#ecf0f1;")
        self.btn_dx_0.clicked.connect(lambda: self._set_angle_quick("dx", 0.0))

        self.btn_dx_45 = QPushButton("45°")
        self.btn_dx_45.setStyleSheet("background:#8e44ad; color:white;")
        self.btn_dx_45.clicked.connect(lambda: self._set_angle_quick("dx", 45.0))

        # Unica riga SX e DX
        ang_row.addWidget(QLabel("SX"))
        ang_row.addWidget(self.btn_sx_45)
        ang_row.addWidget(self.btn_sx_0)
        ang_row.addWidget(self.spin_sx)
        ang_row.addSpacing(16)
        ang_row.addWidget(QLabel("DX"))
        ang_row.addWidget(self.spin_dx)
        ang_row.addWidget(self.btn_dx_0)
        ang_row.addWidget(self.btn_dx_45)

        l.addLayout(ang_row)

        # Misure + profili (spessore consentito 0)
        meas_box = QFrame(); l.addWidget(meas_box)
        meas = QGridLayout(meas_box); meas.setHorizontalSpacing(8); meas.setVerticalSpacing(6)
        meas.addWidget(QLabel("Misure e profilo"), 0, 0, 1, 6, alignment=Qt.AlignLeft)

        meas.addWidget(QLabel("Profilo:"), 1, 0)
        self.cb_profilo = QComboBox(); self.cb_profilo.setEditable(True)
        for name in self._profiles.keys():
            self.cb_profilo.addItem(name)
        self.cb_profilo.setCurrentText("Nessuno")
        self.cb_profilo.currentTextChanged.connect(self._on_profile_changed)
        meas.addWidget(self.cb_profilo, 1, 1)

        meas.addWidget(QLabel("Spessore profilo (mm):"), 1, 2)
        self.thickness = QLineEdit(); self.thickness.setPlaceholderText("0.0"); self.thickness.setText("0")
        self.thickness.textChanged.connect(lambda _: self._recalc_displays())
        meas.addWidget(self.thickness, 1, 3)

        meas.addWidget(QLabel("Misura esterna (mm):"), 2, 0)
        self.ext_len = QLineEdit(); self.ext_len.setPlaceholderText("Es. 1000.0")
        self.ext_len.textChanged.connect(lambda _: self._recalc_displays())
        meas.addWidget(self.ext_len, 2, 1)

        disp = QGridLayout(); l.addLayout(disp)
        self.lbl_det_sx = QLabel("Detrazione SX: — mm"); disp.addWidget(self.lbl_det_sx, 0, 0)
        self.lbl_det_dx = QLabel("Detrazione DX: — mm"); disp.addWidget(self.lbl_det_dx, 0, 1)
        self.lbl_internal = QLabel("Quota interna: — mm"); disp.addWidget(self.lbl_internal, 1, 0)
        self.lbl_note = QLabel(""); disp.addWidget(self.lbl_note, 1, 1)

        actions = QHBoxLayout(); l.addLayout(actions)
        self.btn_start = QPushButton("START POSIZIONAMENTO")
        self.btn_brake = QPushButton("SBLOCCA FRENO")
        self.btn_start.clicked.connect(self._start_positioning)
        self.btn_brake.clicked.connect(self._toggle_brake)
        actions.addWidget(self.btn_start); actions.addWidget(self.btn_brake)
        actions.addStretch(1)

        # Destra: contapezzi in alto + stato sotto (stato più alto)
        right = QFrame(); body.addWidget(right, 2)
        r = QVBoxLayout(right); r.setContentsMargins(6,6,6,6); r.setSpacing(10)

        # Riquadro contapezzi
        cnt_box = QFrame(); r.addWidget(cnt_box)
        cnt_box.setStyleSheet("QFrame { border: 1px solid #3b4b5a; border-radius:6px; }")
        cnt = QGridLayout(cnt_box); cnt.setHorizontalSpacing(8); cnt.setVerticalSpacing(6)
        title_cnt = QLabel("CONTAPEZZI (Semi-auto)")
        title_cnt.setStyleSheet("font-weight:600;")
        cnt.addWidget(title_cnt, 0, 0, 1, 4, alignment=Qt.AlignLeft)
        cnt.addWidget(QLabel("Target:"), 1, 0)
        self.spin_target = QSpinBox(); self.spin_target.setRange(0, 999999)
        self.spin_target.setValue(int(getattr(self.machine, "semi_auto_target_pieces", 0)))
        self.spin_target.valueChanged.connect(self._update_target_pieces)
        cnt.addWidget(self.spin_target, 1, 1)
        self.lbl_counted = QLabel("Contati: 0"); cnt.addWidget(self.lbl_counted, 2, 0)
        self.lbl_remaining = QLabel("Rimanenti: 0"); cnt.addWidget(self.lbl_remaining, 2, 1)
        self.btn_cnt_reset = QPushButton("Reset conteggio")
        self.btn_cnt_reset.clicked.connect(self._reset_counter)
        cnt.addWidget(self.btn_cnt_reset, 1, 3)

        # Stato
        self.status_panel = StatusPanel(self.machine, title="STATO")
        try:
            self.status_panel.setMinimumHeight(260)
        except Exception:
            pass
        r.addWidget(self.status_panel, 1)

        r.addStretch(1)

        # Poll UI
        self._start_poll()

    # ---- Profili ----
    def _on_profile_changed(self, name: str):
        name = name.strip()
        if name in self._profiles:
            th = self._profiles.get(name, 0.0)
            self.thickness.setText(f"{th:.0f}" if th.is_integer() else f"{th}")
        # sempre ricalcola
        self._recalc_displays()

    # ---- Helpers ----
    def _set_angle_quick(self, side: str, val: float):
        if side == "sx":
            self.spin_sx.setValue(float(val))
        else:
            self.spin_dx.setValue(float(val))
        self._apply_angles()

    def _apply_angles(self):
        sx = max(0.0, min(45.0, float(self.spin_sx.value())))
        dx = max(0.0, min(45.0, float(self.spin_dx.value())))
        if hasattr(self.machine, "set_head_angles"):
            ok = self.machine.set_head_angles(sx, dx)
            if not ok:
                self._set_note("Angoli non applicati (EMG?)", error=True)
        else:
            setattr(self.machine, "left_head_angle", sx)
            setattr(self.machine, "right_head_angle", dx)
        self.heads.refresh()
        self._recalc_displays()

    def _parse_float(self, s: str, default: float = 0.0) -> float:
        try:
            v = float((s or "").replace(",", ".").strip())
            return v
        except Exception:
            return default

    def _recalc_displays(self):
        ext = self._parse_float(self.ext_len.text(), 0.0)
        th = self._parse_float(self.thickness.text(), 0.0)  # consentito 0

        sx = float(self.spin_sx.value())
        dx = float(self.spin_dx.value())
        det_sx = th * math.tan(math.radians(sx)) if sx > 0 and th > 0 else 0.0
        det_dx = th * math.tan(math.radians(dx)) if dx > 0 and th > 0 else 0.0
        internal = ext - (det_sx + det_dx) if ext > 0 else None

        self.lbl_det_sx.setText(f"Detrazione SX: {det_sx:.1f} mm")
        self.lbl_det_dx.setText(f"Detrazione DX: {det_dx:.1f} mm")
        self.lbl_internal.setText("Quota interna: — mm" if internal is None else f"Quota interna: {internal:.1f} mm")
        self._set_note("")

    def _set_note(self, msg: str, error: bool=False):
        self.lbl_note.setText(msg)
        self.lbl_note.setStyleSheet(f"color: {'#e74c3c' if error else '#95a5a6'};")

    # ---- Contapezzi ----
    def _update_target_pieces(self, v: int):
        setattr(self.machine, "semi_auto_target_pieces", int(v))

    def _reset_counter(self):
        setattr(self.machine, "semi_auto_count_done", 0)

    # ---- Azioni ----
    def _start_positioning(self):
        if getattr(self.machine, "emergency_active", False):
            self._set_note("EMERGENZA ATTIVA: ESEGUI AZZERA", error=True); return
        if not getattr(self.machine, "machine_homed", False):
            self._set_note("ESEGUI AZZERA (HOMING)", error=True); return
        if getattr(self.machine, "brake_active", False):
            self._set_note("SBLOCCA FRENO", error=True); return
        if getattr(self.machine, "positioning_active", False):
            self._set_note("Movimento in corso", error=True); return

        ext = self._parse_float(self.ext_len.text(), 0.0)
        th = self._parse_float(self.thickness.text(), 0.0)  # consentito 0

        if ext <= 0:
            self._set_note("MISURA ESTERNA NON VALIDA", error=True); return

        sx = float(self.spin_sx.value())
        dx = float(self.spin_dx.value())
        det_sx = th * math.tan(math.radians(sx)) if sx > 0 and th > 0 else 0.0
        det_dx = th * math.tan(math.radians(dx)) if dx > 0 and th > 0 else 0.0
        internal = ext - (det_sx + det_dx)

        min_q = float(getattr(self.machine, "min_distance", 0.0))
        max_q = float(getattr(self.machine, "max_cut_length", 1e9))
        if internal < min_q:
            self._set_note(f"QUOTA MIN {int(min_q)}MM", error=True); return
        if internal > max_q:
            self._set_note(f"QUOTA MAX {int(max_q)}MM", error=True); return

        if hasattr(self.machine, "move_to_length_and_angles"):
            self.machine.move_to_length_and_angles(
                length_mm=internal, ang_sx=sx, ang_dx=dx,
                done_cb=lambda ok, msg: self._after_move(ok, msg)
            )
        self._update_buttons()

    def _after_move(self, ok: bool, msg: str):
        self._set_note("POSIZIONAMENTO OK" if ok else (msg or "Interrotto"), error=not ok)
        self._update_buttons()

    def _toggle_brake(self):
        if hasattr(self.machine, "toggle_brake"):
            ok = self.machine.toggle_brake()
            if not ok:
                self._set_note("Operazione non consentita", error=True)
        self._update_buttons()

    # ---- Poll / Stato ----
    def _start_poll(self):
        self._poll = QTimer(self)
        self._poll.setInterval(200)
        self._poll.timeout.connect(self._tick)
        self._poll.start()
        self._recalc_displays()
        self._update_buttons()

    def _tick(self):
        try:
            self.status_panel.update_status()
        except Exception:
            pass
        try:
            self.heads.refresh()
        except Exception:
            pass
        # contapezzi
        tgt = int(getattr(self.machine, "semi_auto_target_pieces", 0))
        done = int(getattr(self.machine, "semi_auto_count_done", 0))
        rem = max(0, tgt - done)
        self.lbl_remaining.setText(f"Rimanenti: {rem}")
        self.lbl_counted.setText(f"Contati: {done}")
        self._update_buttons()

    def _update_buttons(self):
        homed = bool(getattr(self.machine, "machine_homed", False))
        emg = bool(getattr(self.machine, "emergency_active", False))
        brk = bool(getattr(self.machine, "brake_active", False))
        mov = bool(getattr(self.machine, "positioning_active", False))
        enable_start = (homed and not emg and not brk and not mov)
        self.btn_start.setEnabled(enable_start)
        enable_brake = (homed and not mov and not emg)
        self.btn_brake.setEnabled(enable_brake)
        self.btn_brake.setText("SBLOCCA FRENO" if brk else "BLOCCA FRENO")

    def on_show(self):
        self._recalc_displays()
        self._update_buttons()
