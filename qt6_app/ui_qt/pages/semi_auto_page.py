from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QSpinBox, QGridLayout, QDoubleSpinBox, QLineEdit
)
from PySide6.QtCore import Qt, QTimer
from ui_qt.widgets.header import Header
from ui_qt.widgets.status_panel import StatusPanel
from ui_qt.widgets.heads_view import HeadsView
import math

class SemiAutoPage(QWidget):
    """
    Semi-Automatico:
    - Vista teste: SX fissa e DX mobile su scala 250–4000 con pivot basso e inclinazione 0–45°
    - Comandi inclinazione teste raggruppati a destra (SX: 45° • 0° • input) (DX: input • 0° • 45°)
    - Misura esterna + spessore con calcolo quota interna e validazioni
    - Start posizionamento e toggle freno
    - Pannello stato compatto
    - Impostazioni sensori spostate in Utility > Configurazione
    """
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self.machine = appwin.machine
        self._poll = None
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
        l.addWidget(self.heads, 2)

        meas_box = QFrame(); l.addWidget(meas_box)
        meas = QGridLayout(meas_box); meas.setHorizontalSpacing(8); meas.setVerticalSpacing(6)
        meas.addWidget(QLabel("Misure (mm)"), 0, 0, 1, 4, alignment=Qt.AlignLeft)

        meas.addWidget(QLabel("Misura esterna:"), 1, 0)
        self.ext_len = QLineEdit(); self.ext_len.setPlaceholderText("Es. 1000.0")
        meas.addWidget(self.ext_len, 1, 1)

        meas.addWidget(QLabel("Spessore profilo:"), 1, 2)
        self.thickness = QLineEdit(); self.thickness.setPlaceholderText("Es. 50.0")
        meas.addWidget(self.thickness, 1, 3)

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

        # Destra: comandi angoli + stato compatto
        right = QFrame(); body.addWidget(right, 2)
        r = QVBoxLayout(right); r.setContentsMargins(6,6,6,6); r.setSpacing(10)

        # Comandi inclinazione teste (ordine richiesto)
        ang_box = QFrame(); r.addWidget(ang_box)
        ang = QGridLayout(ang_box); ang.setHorizontalSpacing(8); ang.setVerticalSpacing(6)
        title = QLabel("Inclinazione Teste (0–45°)")
        title.setStyleSheet("font-weight:600;")
        ang.addWidget(title, 0, 0, 1, 6, alignment=Qt.AlignLeft)

        # Testa SX: 45° • 0° • input
        lbl_sx = QLabel("Testa SX"); lbl_sx.setStyleSheet("color:#ccd6e3;")
        ang.addWidget(lbl_sx, 1, 0)
        btn_sx_45 = QPushButton("45°"); btn_sx_45.clicked.connect(lambda: self._set_angle_quick("sx", 45.0))
        btn_sx_0  = QPushButton("0°");  btn_sx_0.clicked.connect(lambda: self._set_angle_quick("sx", 0.0))
        self.spin_sx = QDoubleSpinBox(); self.spin_sx.setRange(0.0, 45.0); self.spin_sx.setDecimals(1)
        self.spin_sx.setValue(float(getattr(self.machine, "left_head_angle", 0.0)))
        self.spin_sx.valueChanged.connect(self._apply_angles)
        ang.addWidget(btn_sx_45, 1, 1); ang.addWidget(btn_sx_0, 1, 2); ang.addWidget(self.spin_sx, 1, 3)

        # Testa DX: input • 0° • 45°
        lbl_dx = QLabel("Testa DX"); lbl_dx.setStyleSheet("color:#ccd6e3;")
        ang.addWidget(lbl_dx, 2, 0)
        self.spin_dx = QDoubleSpinBox(); self.spin_dx.setRange(0.0, 45.0); self.spin_dx.setDecimals(1)
        self.spin_dx.setValue(float(getattr(self.machine, "right_head_angle", 0.0)))
        self.spin_dx.valueChanged.connect(self._apply_angles)
        btn_dx_0  = QPushButton("0°");  btn_dx_0.clicked.connect(lambda: self._set_angle_quick("dx", 0.0))
        btn_dx_45 = QPushButton("45°"); btn_dx_45.clicked.connect(lambda: self._set_angle_quick("dx", 45.0))
        ang.addWidget(self.spin_dx, 2, 1); ang.addWidget(btn_dx_0, 2, 2); ang.addWidget(btn_dx_45, 2, 3)

        # Pannello stato compatto
        self.status_panel = StatusPanel(self.machine, title="STATO")
        try:
            self.status_panel.setMaximumHeight(140)
        except Exception:
            pass
        r.addWidget(self.status_panel)

        r.addStretch(1)

        # Poll UI
        self._start_poll()

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
        # Aggiorna vista teste e calcoli
        self.heads.refresh()
        self._recalc_displays()

    def _recalc_displays(self):
        try:
            ext = float(self.ext_len.text().strip() or "0")
        except Exception:
            ext = 0.0
        try:
            th = float(self.thickness.text().strip() or "0")
        except Exception:
            th = 0.0

        sx = float(self.spin_sx.value())
        dx = float(self.spin_dx.value())
        det_sx = th * math.tan(math.radians(sx)) if sx > 0 else 0.0
        det_dx = th * math.tan(math.radians(dx)) if dx > 0 else 0.0
        internal = ext - (det_sx + det_dx) if ext > 0 and th > 0 else None

        self.lbl_det_sx.setText(f"Detrazione SX: {det_sx:.1f} mm")
        self.lbl_det_dx.setText(f"Detrazione DX: {det_dx:.1f} mm")
        if internal is None:
            self.lbl_internal.setText("Quota interna: — mm")
        else:
            self.lbl_internal.setText(f"Quota interna: {internal:.1f} mm")

        self._set_note("")

    def _set_note(self, msg: str, error: bool=False):
        self.lbl_note.setText(msg)
        self.lbl_note.setStyleSheet(f"color: {'#e74c3c' if error else '#95a5a6'};")

    def _start_positioning(self):
        if getattr(self.machine, "emergency_active", False):
            self._set_note("EMERGENZA ATTIVA: ESEGUI AZZERA", error=True); return
        if not getattr(self.machine, "machine_homed", False):
            self._set_note("ESEGUI AZZERA (HOMING)", error=True); return
        if getattr(self.machine, "brake_active", False):
            self._set_note("SBLOCCA FRENO", error=True); return
        if getattr(self.machine, "positioning_active", False):
            self._set_note("Movimento in corso", error=True); return

        try:
            ext = float(self.ext_len.text().strip() or "0")
        except Exception:
            ext = 0.0
        try:
            th = float(self.thickness.text().strip() or "0")
        except Exception:
            th = 50.0

        if ext <= 0:
            self._set_note("MISURA ESTERNA NON VALIDA", error=True); return
        if th <= 0:
            self._set_note("SPESSORE NON VALIDO", error=True); return

        sx = float(self.spin_sx.value())
        dx = float(self.spin_dx.value())
        det_sx = th * math.tan(math.radians(sx)) if sx > 0 else 0.0
        det_dx = th * math.tan(math.radians(dx)) if dx > 0 else 0.0
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
