from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QSpinBox, QGridLayout, QDoubleSpinBox, QLineEdit, QComboBox,
    QMessageBox, QSizePolicy, QCheckBox
)
from PySide6.QtCore import Qt, QTimer, QSize
from ui_qt.widgets.header import Header
from ui_qt.widgets.status_panel import StatusPanel
from ui_qt.widgets.heads_view import HeadsView
import math

SX_COLOR = "#2980b9"
DX_COLOR = "#9b59b6"

class SemiAutoPage(QWidget):
    """
    Layout 2 colonne:
    - Sinistra (expanding): top [Contapezzi 190x190 | Grafica (massimizzata tra contapezzi e status)], poi [Profilo/Spessore | Inclinazione], poi [Misura (input grande) | Quota live | Azioni]
    - Destra (fissa 180px): Status che riempie in altezza, sotto Fuori Quota 180x160
    """
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self.machine = appwin.machine
        self._poll = None
        self._profiles = {"Nessuno": 0.0, "Alluminio 50": 50.0, "PVC 60": 60.0, "Legno 40": 40.0}
        self._build()

    def _build(self):
        root = QHBoxLayout(self); root.setContentsMargins(16,16,16,16); root.setSpacing(8)

        # Colonna sinistra
        left_container = QFrame(); left_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        left_col = QVBoxLayout(left_container); left_col.setContentsMargins(0,0,0,0); left_col.setSpacing(8)

        header = Header(self.appwin, "SEMI-AUTOMATICO")
        left_col.addWidget(header, 0)

        # Riga alta: contapezzi + grafica
        top_left = QHBoxLayout(); top_left.setSpacing(8); top_left.setContentsMargins(0,0,0,0)

        cnt_container = QFrame()
        cnt_container.setFixedSize(QSize(190, 190))
        cnt_container.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
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
        top_left.addWidget(cnt_container, 0, alignment=Qt.AlignTop | Qt.AlignLeft)

        graph_frame = QFrame()
        graph_frame.setObjectName("GraphFrame")
        graph_frame.setStyleSheet("QFrame#GraphFrame { border: 1px solid #3b4b5a; border-radius: 8px; }")
        graph_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        graph_layout = QVBoxLayout(graph_frame); graph_layout.setContentsMargins(0,0,0,0); graph_layout.setSpacing(0)

        self.heads = HeadsView(self.machine, graph_frame)
        self.heads.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        graph_layout.addWidget(self.heads)  # niente alignment per riempire
        top_left.addWidget(graph_frame, 1)

        # Stretch esplicito: 0 per contapezzi, 1 per grafica
        top_left.setStretch(0, 0)
        top_left.setStretch(1, 1)

        left_col.addLayout(top_left, 1)

        # Riga intermedia: Profilo/Spessore | Inclinazione
        mid = QHBoxLayout(); mid.setSpacing(8)

        prof_box = QFrame()
        prof_box.setStyleSheet("QFrame { border:1px solid #3b4b5a; border-radius:6px; }")
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

        ang_container = QFrame()
        ang_container.setStyleSheet("QFrame { border:1px solid #3b4b5a; border-radius:6px; }")
        ang = QGridLayout(ang_container); ang.setHorizontalSpacing(8); ang.setVerticalSpacing(6)

        sx_block = QFrame(); sx_block.setStyleSheet(f"QFrame {{ border:2px solid {SX_COLOR}; border-radius:6px; }}")
        sx_lay = QVBoxLayout(sx_block); sx_lay.setContentsMargins(8,8,8,8)
        sx_lay.addWidget(QLabel("Testa SX (0–45°)"))
        sx_row = QHBoxLayout()
        self.btn_sx_45 = QPushButton("45°"); self.btn_sx_45.setStyleSheet("background:#8e44ad; color:white;")
        self.btn_sx_45.clicked.connect(lambda: self._set_angle_quick('sx', 45.0))
        self.btn_sx_0  = QPushButton("0°");  self.btn_sx_0.setStyleSheet("background:#2c3e50; color:#ecf0f1;")
        self.btn_sx_0.clicked.connect(lambda: self._set_angle_quick('sx', 0.0))
        self.spin_sx = QDoubleSpinBox(); self.spin_sx.setRange(0.0, 45.0); self.spin_sx.setDecimals(1)
        self.spin_sx.setValue(float(getattr(self.machine, "left_head_angle", 0.0)))
        self.spin_sx.valueChanged.connect(self._apply_angles)
        sx_row.addWidget(self.btn_sx_45); sx_row.addWidget(self.btn_sx_0); sx_row.addWidget(self.spin_sx)
        sx_lay.addLayout(sx_row)

        dx_block = QFrame(); dx_block.setStyleSheet(f"QFrame {{ border:2px solid {DX_COLOR}; border-radius:6px; }}")
        dx_lay = QVBoxLayout(dx_block); dx_lay.setContentsMargins(8,8,8,8)
        dx_lay.addWidget(QLabel("Testa DX (0–45°)"))
        dx_row = QHBoxLayout()
        self.spin_dx = QDoubleSpinBox(); self.spin_dx.setRange(0.0, 45.0); self.spin_dx.setDecimals(1)
        self.spin_dx.setValue(float(getattr(self.machine, "right_head_angle", 0.0)))
        self.spin_dx.valueChanged.connect(self._apply_angles)
        self.btn_dx_0  = QPushButton("0°");  self.btn_dx_0.setStyleSheet("background:#2c3e50; color:#ecf0f1;")
        self.btn_dx_0.clicked.connect(lambda: self._set_angle_quick('dx', 0.0))
        self.btn_dx_45 = QPushButton("45°"); self.btn_dx_45.setStyleSheet("background:#8e44ad; color:white;")
        self.btn_dx_45.clicked.connect(lambda: self._set_angle_quick('dx', 45.0))
        dx_row.addWidget(self.spin_dx); dx_row.addWidget(self.btn_dx_0); dx_row.addWidget(self.btn_dx_45)
        dx_lay.addLayout(dx_row)

        ang.addWidget(sx_block, 0, 0)
        ang.addWidget(dx_block, 0, 1)
        mid.addWidget(ang_container, 1)

        left_col.addLayout(mid, 0)

        # Riga bassa: misura / quota live / azioni
        bottom = QVBoxLayout(); bottom.setSpacing(8)
        big = QGridLayout(); bottom.addLayout(big)
        big.addWidget(QLabel("Misura esterna (mm):"), 0, 0, alignment=Qt.AlignLeft)
        self.ext_len = QLineEdit(); self.ext_len.setPlaceholderText("Es. 1000.0")
        self.ext_len.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.ext_len.textChanged.connect(lambda _: self._recalc_displays())
        big.addWidget(self.ext_len, 0, 1)

        self.lbl_target_big = QLabel("Quota posizionamento: — mm")
        self.lbl_target_big.setStyleSheet("font-size: 22px; font-weight: 800;")
        big.addWidget(self.lbl_target_big, 1, 0, 1, 2)

        quotes = QGridLayout(); bottom.addLayout(quotes)
        self.lbl_internal = QLabel("Quota interna: — mm")
        self.lbl_det_sx = QLabel("Detrazione SX: — mm")
        self.lbl_det_dx = QLabel("Detrazione DX: — mm")
        quotes.addWidget(self.lbl_internal, 0, 0, 1, 2)
        quotes.addWidget(self.lbl_det_sx, 1, 0)
        quotes.addWidget(self.lbl_det_dx, 1, 1)
        self.lbl_note = QLabel(""); self.lbl_note.setStyleSheet("color:#95a5a6;")
        quotes.addWidget(self.lbl_note, 2, 0, 1, 2)

        actions = QHBoxLayout(); bottom.addLayout(actions)
        self.btn_start = QPushButton("START POSIZIONAMENTO")
        self.btn_brake = QPushButton("SBLOCCA FRENO")
        self.btn_start.clicked.connect(self._start_positioning)
        self.btn_brake.clicked.connect(self._toggle_brake)
        actions.addWidget(self.btn_start); actions.addWidget(self.btn_brake)
        actions.addStretch(1)

        left_col.addLayout(bottom, 0)

        # Sidebar destra
        right_container = QFrame(); right_container.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding); right_container.setFixedWidth(180)
        right_col = QVBoxLayout(right_container); right_col.setContentsMargins(0,0,0,0); right_col.setSpacing(6)
        self.status_panel = StatusPanel(self.machine, title="STATO")
        self.status_panel.setFixedWidth(180)
        self.status_panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        right_col.addWidget(self.status_panel, 1)
        fq_box = QFrame(); fq_box.setFixedSize(QSize(180, 160)); fq_box.setStyleSheet("QFrame { border: 1px solid #3b4b5a; border-radius:6px; }")
        fq = QGridLayout(fq_box); fq.setHorizontalSpacing(6); fq.setVerticalSpacing(4)
        self.chk_fuori_quota = QCheckBox("Fuori quota"); fq.addWidget(self.chk_fuori_quota, 0, 0, 1, 2)
        fq.addWidget(QLabel("Offset:"), 1, 0)
        self.spin_offset = QDoubleSpinBox(); self.spin_offset.setRange(0.0, 1000.0); self.spin_offset.setDecimals(0); self.spin_offset.setValue(120.0); self.spin_offset.setSuffix(" mm")
        fq.addWidget(self.spin_offset, 1, 1)
        right_col.addWidget(fq_box, 0, alignment=Qt.AlignTop)

        # Monta
        root.addWidget(left_container, 1)
        root.addWidget(right_container, 0)

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
        if side == "sx": self.spin_sx.setValue(float(val))
        else:            self.spin_dx.setValue(float(val))
        self._apply_angles()

    def _apply_angles(self):
        sx = max(0.0, min(45.0, float(self.spin_sx.value())))
        dx = max(0.0, min(45.0, float(self.spin_dx.value())))
        if hasattr(self.machine, "set_head_angles"):
            ok = self.machine.set_head_angles(sx, dx)
            if not ok: self._set_note("Angoli non applicati (EMG?)", error=True)
        else:
            setattr(self.machine, "left_head_angle", sx); setattr(self.machine, "right_head_angle", dx)
        self.heads.refresh(); self._recalc_displays()

    def _parse_float(self, s: str, default: float = 0.0) -> float:
        try: return float((s or "").replace(",", ".").strip())
        except Exception: return default

    def _recalc_displays(self):
        ext = self._parse_float(self.ext_len.text(), 0.0)
        th  = self._parse_float(self.thickness.text(), 0.0)
        sx  = float(self.spin_sx.value()); dx = float(self.spin_dx.value())
        det_sx = th * math.tan(math.radians(sx)) if sx > 0 and th > 0 else 0.0
        det_dx = th * math.tan(math.radians(dx)) if dx > 0 and th > 0 else 0.0
        internal = ext - (det_sx + det_dx) if ext > 0 else None
        self.lbl_internal.setText("Quota interna: — mm" if internal is None else f"Quota interna: {internal:.1f} mm")
        self.lbl_det_sx.setText(f"Detrazione SX: {det_sx:.1f} mm")
        self.lbl_det_dx.setText(f"Detrazione DX: {det_dx:.1f} mm")
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
        if getattr(self.machine, "emergency_active", False): self._set_note("EMERGENZA ATTIVA: ESEGUI AZZERA", True); return
        if not getattr(self.machine, "machine_homed", False): self._set_note("ESEGUI AZZERA (HOMING)", True); return
        if getattr(self.machine, "brake_active", False): self._set_note("SBLOCCA FRENO", True); return
        if getattr(self.machine, "positioning_active", False): self._set_note("Movimento in corso", True); return

        ext = self._parse_float(self.ext_len.text(), 0.0); th = self._parse_float(self.thickness.text(), 0.0)
        if ext <= 0: self._set_note("MISURA ESTERNA NON VALIDA", True); return

        sx = float(self.spin_sx.value()); dx = float(self.spin_dx.value())
        det_sx = th * math.tan(math.radians(sx)) if sx > 0 and th > 0 else 0.0
        det_dx = th * math.tan(math.radians(dx)) if dx > 0 and th > 0 else 0.0
        internal = ext - (det_sx + det_dx)

        min_q = float(getattr(self.machine, "min_distance", 250.0))
        max_q = float(getattr(self.machine, "max_cut_length", 4000.0))
        offset = self._parse_float(self.spin_offset.value(), 120.0)
        min_with_offset = max(0.0, min_q - offset)

        if internal < min_with_offset:
            QMessageBox.warning(self, "Fuori quota non possibile", f"Quota interna {internal:.1f} < minima {min_with_offset:.1f} (min {min_q:.0f} − offset {offset:.0f}).")
            self._set_note("Fuori quota impossibile con impostazioni attuali.", True); return

        if internal < min_q and self.chk_fuori_quota.isChecked():
            target_for_move = max(min_q, internal + offset); self._set_note(f"Fuori quota: posiziono a {target_for_move:.1f} mm.", False)
        else:
            target_for_move = internal

        if target_for_move > max_q: self._set_note(f"QUOTA MAX {int(max_q)}MM", True); return

        if hasattr(self.machine, "move_to_length_and_angles"):
            self.machine.move_to_length_and_angles(length_mm=target_for_move, ang_sx=sx, ang_dx=dx, done_cb=lambda ok, msg: self._after_move(ok, msg))
        self._update_buttons()

    def _after_move(self, ok: bool, msg: str):
        self._set_note("POSIZIONAMENTO OK" if ok else (msg or "Interrotto"), not ok)
        self._update_buttons()

    def _toggle_brake(self):
        if hasattr(self.machine, "toggle_brake"):
            ok = self.machine.toggle_brake()
            if not ok: self._set_note("Operazione non consentita", True)
        self._update_buttons()

    # ---- Poll / Stato / Quota live ----
    def _start_poll(self):
        self._poll = QTimer(self); self._poll.setInterval(200); self._poll.timeout.connect(self._tick); self._poll.start()
        self._recalc_displays(); self._update_buttons()

    def _tick(self):
        try: self.status_panel.refresh()
        except Exception: pass
        try: self.heads.refresh()
        except Exception: pass

        # Quota posizionamento live: encoder -> fallback a position_current
        pos = getattr(self.machine, "encoder_position", None)
        if pos is None:
            pos = getattr(self.machine, "position_current", None)
        try:
            self.lbl_target_big.setText(f"Quota posizionamento: {float(pos):.1f} mm" if pos is not None else "Quota posizionamento: — mm")
        except Exception:
            self.lbl_target_big.setText("Quota posizionamento: — mm")

        # Contapezzi
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
        self.btn_start.setEnabled(homed and not emg and not brk and not mov)
        self.btn_brake.setEnabled(homed and not mov and not emg)
        self.btn_brake.setText("SBLOCCA FRENO" if brk else "BLOCCA FRENO")

    def on_show(self):
        self._recalc_displays(); self._update_buttons()
