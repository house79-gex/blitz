from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton, QSpinBox, QGridLayout, QCheckBox
from PySide6.QtCore import Qt, QTimer
from ui_qt.widgets.header import Header
from ui_qt.widgets.status_panel import StatusPanel

class SemiAutoPage(QWidget):
    """
    Modalità Semi-Automatica con:
    - Jog continuo (press-and-hold) sinistra/destra + STOP
    - Velocità jog
    - Attuatori base (Freno/Frizione, Pinza apri/chiudi)
    - Homing, Clear EMG
    - Impulso Taglio
    - Toggle input pulsante testa
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

        left = QFrame(); body.addWidget(left, 2)
        l = QVBoxLayout(left); l.setContentsMargins(6,6,6,6); l.setSpacing(10)

        # Jog controls
        jog_box = QFrame(); l.addWidget(jog_box)
        jog = QGridLayout(jog_box); jog.setHorizontalSpacing(8); jog.setVerticalSpacing(6)
        jog.addWidget(QLabel("JOG TESTA"), 0, 0, 1, 4, alignment=Qt.AlignLeft)

        jog.addWidget(QLabel("Velocità (mm/s):"), 1, 0)
        self.spin_speed = QSpinBox(); self.spin_speed.setRange(1, 500); self.spin_speed.setValue(50)
        jog.addWidget(self.spin_speed, 1, 1)

        self.btn_left = QPushButton("← Sinistra")
        self.btn_stop = QPushButton("STOP")
        self.btn_right = QPushButton("Destra →")

        # Press-and-hold
        self.btn_left.pressed.connect(lambda: self._jog("left"))
        self.btn_left.released.connect(self._jog_stop)
        self.btn_right.pressed.connect(lambda: self._jog("right"))
        self.btn_right.released.connect(self._jog_stop)

        # Fallback click
        self.btn_stop.clicked.connect(self._jog_stop)

        jog.addWidget(self.btn_left, 2, 0)
        jog.addWidget(self.btn_stop, 2, 1)
        jog.addWidget(self.btn_right, 2, 2)

        # IO basic
        io_box = QFrame(); l.addWidget(io_box)
        io = QGridLayout(io_box); io.setHorizontalSpacing(8); io.setVerticalSpacing(6)
        io.addWidget(QLabel("ATTUATORI"), 0, 0, 1, 3, alignment=Qt.AlignLeft)

        btn_brake_on = QPushButton("Freno ON"); btn_brake_on.clicked.connect(lambda: self._set_attr("brake_active", True))
        btn_brake_off = QPushButton("Freno OFF"); btn_brake_off.clicked.connect(lambda: self._set_attr("brake_active", False))
        io.addWidget(btn_brake_on, 1, 0); io.addWidget(btn_brake_off, 1, 1)

        btn_clutch_on = QPushButton("Frizione ON"); btn_clutch_on.clicked.connect(lambda: self._set_attr("clutch_active", True))
        btn_clutch_off = QPushButton("Frizione OFF"); btn_clutch_off.clicked.connect(lambda: self._set_attr("clutch_active", False))
        io.addWidget(btn_clutch_on, 2, 0); io.addWidget(btn_clutch_off, 2, 1)

        btn_open = QPushButton("Apri Pinza"); btn_open.clicked.connect(self._open_clamp)
        btn_close = QPushButton("Chiudi Pinza"); btn_close.clicked.connect(self._close_clamp)
        io.addWidget(btn_open, 3, 0); io.addWidget(btn_close, 3, 1)

        # Service / utilities
        svc_box = QFrame(); l.addWidget(svc_box)
        svc = QHBoxLayout(svc_box)
        btn_home = QPushButton("HOMING"); btn_home.clicked.connect(self._home)
        btn_clear_emg = QPushButton("CLEAR EMG"); btn_clear_emg.clicked.connect(self._clear_emg)
        btn_pulse = QPushButton("IMPULSO TAGLIO"); btn_pulse.clicked.connect(self._cut_pulse)
        self.chk_head_input = QCheckBox("Input testa abilitato")
        self.chk_head_input.stateChanged.connect(lambda _: self._toggle_head_input())
        svc.addWidget(btn_home); svc.addWidget(btn_clear_emg); svc.addWidget(btn_pulse); svc.addWidget(self.chk_head_input); svc.addStretch(1)

        l.addStretch(1)

        # Right status
        right = QFrame(); body.addWidget(right, 1)
        r = QVBoxLayout(right); r.setContentsMargins(6,6,6,6)
        self.status = StatusPanel(self.machine, "STATO", right)
        r.addWidget(self.status, 1)

    def _toast(self, msg, level="info"):
        if hasattr(self.appwin, "toast"):
            self.appwin.toast.show(msg, level, 2500)

    def _jog(self, direction: str):
        speed = int(self.spin_speed.value())
        try:
            if hasattr(self.machine, "start_jog"):
                self.machine.start_jog(direction=direction, speed=speed)
            elif hasattr(self.machine, "jog"):
                self.machine.jog(direction, speed)
            else:
                self._toast("API jog non disponibile", "warn")
        except Exception as e:
            self._toast(f"Errore jog: {e}", "error")

    def _jog_stop(self):
        try:
            if hasattr(self.machine, "stop_jog"):
                self.machine.stop_jog()
            elif hasattr(self.machine, "jog_stop"):
                self.machine.jog_stop()
            else:
                self._toast("API stop jog non disponibile", "warn")
        except Exception as e:
            self._toast(f"Errore stop jog: {e}", "error")

    def _set_attr(self, name, value):
        try:
            if hasattr(self.machine, name):
                setattr(self.machine, name, value)
            elif hasattr(self.machine, f"set_{name}"):
                getattr(self.machine, f"set_{name}\")(value)
            else:
                self._toast(f"API {name} non disponibile", "warn")
        except Exception as e:
            self._toast(f"Errore {name}: {e}", "error")

    def _open_clamp(self):
        try:
            if hasattr(self.machine, "open_clamp"):
                self.machine.open_clamp()
            else:
                self._toast("API apri pinza non disponibile", "warn")
        except Exception as e:
            self._toast(f"Errore apri pinza: {e}", "error")

    def _close_clamp(self):
        try:
            if hasattr(self.machine, "close_clamp"):
                self.machine.close_clamp()
            else:
                self._toast("API chiudi pinza non disponibile", "warn")
        except Exception as e:
            self._toast(f"Errore chiudi pinza: {e}", "error")

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

    def _clear_emg(self):
        try:
            if hasattr(self.machine, "clear_emergency"):
                self.machine.clear_emergency()
            else:
                self._toast("API clear EMG non disponibile", "warn")
        except Exception as e:
            self._toast(f"Errore clear EMG: {e}", "error")

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

    def _toggle_head_input(self):
        try:
            if hasattr(self.machine, "set_head_button_input_enabled"):
                self.machine.set_head_button_input_enabled(bool(self.chk_head_input.isChecked()))
        except Exception:
            pass

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
