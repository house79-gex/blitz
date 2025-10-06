from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QSpinBox, QGridLayout, QDoubleSpinBox, QLineEdit, QComboBox, QMessageBox
)
from PySide6.QtCore import Qt, QTimer, QSize
from ui_qt.widgets.header import Header
from ui_qt.widgets.status_panel import StatusPanel
from ui_qt.widgets.heads_view import HeadsView
import math

class SemiAutoPage(QWidget):
    """
    Semi-Automatico:
    - Riga alta: [Contapezzi 200x200] [Grafica teste centrata/compatta] [Status laterale 200px + Fuori quota sotto]
    - Riga sotto grafica: [Profilo] [Inclinazione lame] sulla stessa riga
    - Riga bassa: Misura esterna e Quota di posizionamento (grandi) sopra i pulsanti Posizionamento/Sblocca
    - Teste: SX fissa 0mm, DX 250–4000; carter “mezzo esagono” con lato interno = segmento; inclinazione verso l'esterno
    - Fuori quota: min consentita = min_distance − offset; se internal < (min−offset) => avviso modale.
      Altrimenti posiziona a max(min_distance, internal + offset). Detrazioni considerate.
    """
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self.machine = appwin.machine
        self._poll = None
        self._profiles = {"Nessuno": 0.0, "Alluminio 50": 50.0, "PVC 60": 60.0, "Legno 40": 40.0}
        self._build()

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(8,8,8,8); root.setSpacing(6)
        root.addWidget(Header(self.appwin, "SEMI-AUTOMATICO"))

        # ----- Riga alta: contapezzi | grafica | status+fuori quota -----
        top = QHBoxLayout(); top.setSpacing(8)
        root.addLayout(top, 1)

        # Contapezzi 200x200 (alto-sinistra)
        cnt_container = QFrame()
        cnt_container.setFixedSize(QSize(200, 200))
        cnt_container.setStyleSheet("QFrame { border:1px solid #3b4b5a; border-radius:6px; }")
        cnt = QGridLayout(cnt_container); cnt.setHorizontalSpacing(6); cnt.setVerticalSpacing(4)
        title_cnt = QLabel("CONTAPEZZI"); title_cnt.setStyleSheet("font-weight:600;")
        cnt.addWidget(title_cnt, 0, 0, 1, 2, alignment=Qt.AlignLeft)
        cnt.addWidget(QLabel("Target:"), 1, 0)
        self.spin_target = QSpinBox(); self.spin_target.setRange(0, 999999)
        self.spin_target.setValue(int(getattr(self.machine, "semi_auto_target_pieces", 0)))
        self.spin_target.valueChanged.connect(self._update_target_pieces)
        cnt.addWidget(self.spin_target, 1, 1)
        self.lbl_counted = QLabel("Contati: 0"); cnt.addWidget(self.lbl_counted, 2, 0, 1, 2)
        self.lbl_remaining = QLabel("Rimanenti: 0"); cnt.addWidget(self.lbl_remaining, 3, 0, 1, 2)
        self.btn_cnt_reset = QPushButton("Reset"); self.btn_cnt_reset.clicked.connect(self._reset_counter)
        cnt.addWidget(self.btn_cnt_reset, 4, 0, 1, 2)
        top.addWidget(cnt_container, 0, alignment=Qt.AlignTop | Qt.AlignLeft)

        # Grafica teste (centro)
        self.heads = HeadsView(self.machine, self)
        top.addWidget(self.heads, 1)

        # Status laterale (200 px) + Fuori quota sotto
        right_side = QVBoxLayout(); right_side.setSpacing(6)
        self.status_panel = StatusPanel(self.machine, title="STATO")
        try:
            self.status_panel.setFixedWidth(200)
        except Exception:
            pass
        right_side.addWidget(self.status_panel, 1)

        # Fuori quota sotto status
        fq_box = QFrame()
        fq_box.setStyleSheet("QFrame { border: 1px solid #3b4b5a; border-radius:6px; }")
        fq = QGridLayout(fq_box); fq.setHorizontalSpacing(6); fq.setVerticalSpacing(4)
        from PySide6.QtWidgets import QCheckBox
        self.chk_fuori_quota = QCheckBox("Fuori quota (battuta sup.)")
        fq.addWidget(self.chk_fuori_quota, 0, 0, 1, 2)
        fq.addWidget(QLabel("Offset:"), 1, 0)
        self.spin_offset = QDoubleSpinBox(); self.spin_offset.setRange(0.0, 1000.0); self.spin_offset.setDecimals(0); self.spin_offset.setValue(120.0)
        self.spin_offset.setSuffix(" mm")
        fq.addWidget(self.spin_offset, 1, 1)
        right_side.addWidget(fq_box, 0)

        right_container = QFrame()
        rc_lay = QVBoxLayout(right_container); rc_lay.setContentsMargins(0,0,0,0); rc_lay.addLayout(right_side)
        top.addWidget(right_container, 0, alignment=Qt.AlignTop)

        # ----- Riga intermedia: profilo | inclinazione -----
        mid = QHBoxLayout(); mid.setSpacing(8)
        root.addLayout(mid, 0)

        # Profilo (sinistra)
        prof_box = QFrame()
        prof = QGridLayout(prof_box); prof.setHorizontalSpacing(8); prof.setVerticalSpacing(6)
        prof.addWidget(QLabel("Profilo"), 0, 0, 1, 4, alignment=Qt.AlignLeft)
        prof.addWidget(QLabel("Nome:"), 1, 0)
        self.cb_profilo = QComboBox(); self.cb_profilo.setEditable(True)
        for name in self._profiles.keys(): self.cb_profilo.addItem(name)
        self.cb_profilo.setCurrentText("Nessuno")
        self.cb_profilo.currentTextChanged.connect(self._on_profile_changed)
        prof.addWidget(self.cb_profilo, 1, 1, 1, 3)

        prof.addWidget(QLabel("Spessore (mm):"), 2, 0)
        self.thickness = QLineEdit(); self.thickness.setPlaceholderText("0.0"); self.thickness.setText("0")
        self.thickness.textChanged.connect(lambda _: self._recalc_displays())
        prof.addWidget(self.thickness, 2, 1)
        mid.addWidget(prof_box, 1)

        # Inclinazione (destra) - stessa riga
        ang_box = QFrame()
        ang = QGridLayout(ang_box); ang.setHorizontalSpacing(8); ang.setVerticalSpacing(6)
        lbl_sx = QLabel("Testa SX (0–45°)"); lbl_sx.setStyleSheet("font-weight:600;")
        lbl_dx = QLabel("Testa DX (0–45°)"); lbl_dx.setStyleSheet("font-weight:600;")
        ang.addWidget(lbl_sx, 0, 0, alignment=Qt.AlignLeft)
        ang.addWidget(lbl_dx, 0, 3, alignment=Qt.AlignLeft)

        # SX
        self.btn_sx_45 = QPushButton("45°"); self.btn_sx_45.setStyleSheet("background:#8e44ad; color:white;")
        self.btn_sx_45.clicked.connect(lambda: self._set_angle_quick("sx", 45.0))
        self.btn_sx_0  = QPushButton("0°");  self.btn_sx_0.setStyleSheet("background:#2c3e50; color:#ecf0f1;")
        self.btn_sx_0.clicked.connect(lambda: self._set_angle_quick("sx", 0.0))
        self.spin_sx = QDoubleSpinBox(); self.spin_sx.setRange(0.0, 45.0); self.spin_sx.setDecimals(1)
        self.spin_sx.setValue(float(getattr(self.machine, "left_head_angle", 0.0)))
        self.spin_sx.valueChanged.connect(self._apply_angles)
        ang.addWidget(self.btn_sx_45, 1, 0); ang.addWidget(self.btn_sx_0, 1, 1); ang.addWidget(self.spin_sx, 1, 2)

        # DX
        self.spin_dx = QDoubleSpinBox(); self.spin_dx.setRange(0.0, 45.0); self.spin_dx.setDecimals(1)
        self.spin_dx.setValue(float(getattr(self.machine, "right_head_angle", 0.0)))
        self.spin_dx.valueChanged.connect(self._apply_angles)
        self.btn_dx_0  = QPushButton("0°");  self.btn_dx_0.setStyleSheet("background:#2c3e50; color:#ecf0f1;")
        self.btn_dx_0.clicked.connect(lambda: self._set_angle_quick("dx", 0.0))
        self.btn_dx_45 = QPushButton("45°"); self.btn_dx_45.setStyleSheet("background:#8e44ad; color:white;")
        self.btn_dx_45.clicked.connect(lambda: self._set_angle_quick("dx", 45.0))
        ang.addWidget(self.spin_dx, 1, 3); ang.addWidget(self.btn_dx_0, 1, 4); ang.addWidget(self.btn_dx_45, 1, 5)
        mid.addWidget(ang_box, 1)

        # ----- Riga bassa: misure grandi + azioni -----
        bottom = QVBoxLayout(); bottom.setSpacing(6)
        root.addLayout(bottom, 0)

        # Quadro quote (grande)
        quotes = QGridLayout(); bottom.addLayout(quotes)
        self.lbl_internal = QLabel("Quota interna: — mm")
        self.lbl_det_sx = QLabel("Detrazione SX: — mm")
        self.lbl_det_dx = QLabel("Detrazione DX: — mm")
        self.lbl_internal.setStyleSheet("font-size: 20px; font-weight: 800;")
        for w in (self.lbl_det_sx, self.lbl_det_dx):
            w.setStyleSheet("font-size: 16px; font-weight: 700;")
        quotes.addWidget(self.lbl_internal, 0, 0, 1, 2)
        quotes.addWidget(self.lbl_det_sx, 1, 0)
        quotes.addWidget(self.lbl_det_dx, 1, 1)
        self.lbl_note = QLabel("")
        self.lbl_note.setStyleSheet("color:#95a5a6;")
        quotes.addWidget(self.lbl_note, 2, 0, 1, 2)

        # Azioni
        actions = QHBoxLayout(); bottom.addLayout(actions)
        self.btn_start = QPushButton("START POSIZIONAMENTO")
        self.btn_brake = QPushButton("SBLOCCA FRENO")
        self.btn_start.clicked.connect(self._start_positioning)
        self.btn_brake.clicked.connect(self._toggle_brake)
        actions.addWidget(self.btn_start); actions.addWidget(self.btn_brake)
        actions.addStretch(1)

        self._start_poll()

    # ---- Profili ----
    def _on_profile_changed(self, name: str):
        name = name.strip()
        if name in self._profiles:
            th = self._profiles.get(name, 0.0)
            self.thickness.setText(f"{th:.0f}" if float(th).is_integer() else f"{th}")
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
            return float((s or "").replace(",", ".").strip())
        except Exception:
            return default

    def _recalc_displays(self):
        ext = self._parse_float(self.ext_len.text(), 0.0) if hasattr(self, "ext_len") else 0.0
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

        # Misure
        # Nota: Misura esterna è sotto Profilo nella riga intermedia
        try:
            ext = float(self.ext_len.text().replace(",", ".").strip())
        except Exception:
            ext = 0.0
        th = self._parse_float(self.thickness.text(), 0.0)  # consentito 0
        if ext <= 0:
            self._set_note("MISURA ESTERNA NON VALIDA", error=True); return

        # Calcoli con detrazioni
        sx = float(self.spin_sx.value()); dx = float(self.spin_dx.value())
        det_sx = th * math.tan(math.radians(sx)) if sx > 0 and th > 0 else 0.0
        det_dx = th * math.tan(math.radians(dx)) if dx > 0 and th > 0 else 0.0
        internal = ext - (det_sx + det_dx)

        min_q = float(getattr(self.machine, "min_distance", 0.0))
        max_q = float(getattr(self.machine, "max_cut_length", 1e9))
        offset = float(self.spin_offset.value())
        min_with_offset = max(0.0, min_q - offset)  # minima teorica con battuta

        # Impossibilità anche con fuori quota
        if internal < min_with_offset:
            QMessageBox.warning(
                self, "Fuori quota non possibile",
                f"La quota interna {internal:.1f} mm è inferiore alla minima consentita {min_with_offset:.1f} mm "
                f"(min {min_q:.0f} − offset {offset:.0f}). Regola misura o offset."
            )
            self._set_note("Fuori quota impossibile con impostazioni attuali.", error=True)
            return

        # Target posizionamento
        if internal < min_q and self.chk_fuori_quota.isChecked():
            adjusted = max(min_q, internal + offset)  # almeno la minima reale
            self._set_note(f"Fuori quota: posiziono a {adjusted:.1f} mm (target {internal:.1f} + offset {offset:.0f}).", error=False)
            target_for_move = adjusted
        else:
            target_for_move = internal

        if target_for_move > max_q:
            self._set_note(f"QUOTA MAX {int(max_q)}MM", error=True); return

        if hasattr(self.machine, "move_to_length_and_angles"):
            self.machine.move_to_length_and_angles(
                length_mm=target_for_move, ang_sx=sx, ang_dx=dx,
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
            self.status_panel.refresh()
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
