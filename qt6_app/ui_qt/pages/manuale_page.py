from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton, QDoubleSpinBox, QGridLayout
from PySide6.QtCore import Qt, QTimer
from ui_qt.widgets.header import Header
from ui_qt.widgets.status_panel import StatusPanel

class ManualePage(QWidget):
    """
    Controlli manuali: posizionamento diretto, step +/- e servizi base.
    Aggiunto Homing e mantenute chiamate MachineState.
    """
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self.machine = appwin.machine
        self._poll = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(8,8,8,8); root.setSpacing(6)
        root.addWidget(Header(self.appwin, "MANUALE"))

        body = QHBoxLayout(); body.setSpacing(8)
        root.addLayout(body, 1)

        left = QFrame(); body.addWidget(left, 2)
        l = QVBoxLayout(left); l.setContentsMargins(6,6,6,6); l.setSpacing(10)

        # Move absolute / relative
        mv_box = QFrame(); l.addWidget(mv_box)
        mv = QGridLayout(mv_box); mv.setHorizontalSpacing(8); mv.setVerticalSpacing(6)
        mv.addWidget(QLabel("POSIZIONAMENTO"), 0, 0, 1, 4, alignment=Qt.AlignLeft)

        mv.addWidget(QLabel("Assoluta (mm):"), 1, 0)
        self.spin_abs = QDoubleSpinBox(); self.spin_abs.setDecimals(2); self.spin_abs.setRange(-1e6, 1e6); self.spin_abs.setValue(0.0)
        mv.addWidget(self.spin_abs, 1, 1)
        btn_go = QPushButton("VAI"); btn_go.clicked.connect(self._move_abs)
        mv.addWidget(btn_go, 1, 2)

        mv.addWidget(QLabel("Step (mm):"), 2, 0)
        self.spin_step = QDoubleSpinBox(); self.spin_step.setDecimals(2); self.spin_step.setRange(0.01, 1000.0); self.spin_step.setValue(1.0)
        mv.addWidget(self.spin_step, 2, 1)
        btn_minus = QPushButton("− STEP"); btn_minus.clicked.connect(lambda: self._step(-1))
        btn_plus = QPushButton("+ STEP"); btn_plus.clicked.connect(lambda: self._step(+1))
        mv.addWidget(btn_minus, 2, 2); mv.addWidget(btn_plus, 2, 3)

        # Service
        svc_box = QFrame(); l.addWidget(svc_box)
        svc = QHBoxLayout(svc_box)
        btn_zero = QPushButton("AZZERA QUOTA"); btn_zero.clicked.connect(self._zero)
        btn_cut = QPushButton("IMPULSO TAGLIO"); btn_cut.clicked.connect(self._cut_pulse)
        btn_home = QPushButton("HOMING"); btn_home.clicked.connect(self._home)
        svc.addWidget(btn_zero); svc.addWidget(btn_cut); svc.addWidget(btn_home); svc.addStretch(1)

        l.addStretch(1)

        # Right status
        right = QFrame(); body.addWidget(right, 1)
        r = QVBoxLayout(right); r.setContentsMargins(6,6,6,6)
        self.status = StatusPanel(self.machine, "STATO", right)
        r.addWidget(self.status, 1)

    def _toast(self, msg, level="info"):
        if hasattr(self.appwin, "toast"):
            self.appwin.toast.show(msg, level, 2500)

    def _move_abs(self):
        pos = float(self.spin_abs.value())
        try:
            if hasattr(self.machine, "move_to_position"):
                self.machine.move_to_position(pos)
            elif hasattr(self.machine, "move_head_to"):
                self.machine.move_head_to(pos)
            else:
                self._toast("API move_to_position non disponibile", "warn")
        except Exception as e:
            self._toast(f"Errore move_to_position: {e}", "error")

    def _step(self, sign):
        step = float(self.spin_step.value()) * float(sign)
        try:
            if hasattr(self.machine, "move_by"):
                self.machine.move_by(step)
            elif hasattr(self.machine, "nudge"):
                self.machine.nudge(step)
            else:
                self._toast("API step non disponibile", "warn")
        except Exception as e:
            self._toast(f"Errore step: {e}", "error")

    def _zero(self):
        try:
            if hasattr(self.machine, "set_zero"):
                self.machine.set_zero()
            elif hasattr(self.machine, "zero_position"):
                self.machine.zero_position()
            else:
                self._toast("API azzera non disponibile", "warn")
        except Exception as e:
            self._toast(f"Errore azzera: {e}", "error")

    def _cut_pulse(self):
        try:
            if hasattr(self.machine, "simulate_cut_pulse"):
                self.machine.simulate_cut_pulse()
            elif hasattr(self.machine, "decrement_current_remaining"):
                self.machine.decrement_current_remaining()
            else:
                self._toast("API impulso taglio non disponibile", "warn")
        except Exception as e:
            self._toast(f"Errore impulso taglio: {e}", "error")

    def _home(self):
        try:
            if hasattr(self.machine, "home_machine"):
                self.machine.home_machine()
            elif hasattr(self.machine, "home"):
                self.machine.home()
            else:
                self._toast("API homing non disponibile", "warn")
        except Exception as e:
            self._toast(f"Errore homing: {e}", "error")

    def on_show(self):
        self.status.refresh()
        if self._poll is None:
            self._poll = QTimer(self); self._poll.timeout.connect(self._tick); self._poll.start(200)

    def _tick(self):
        self.status.refresh()

    def hideEvent(self, ev):
        if self._poll:
            self._poll.stop(); self._poll = None
        super().hideEvent(ev)
