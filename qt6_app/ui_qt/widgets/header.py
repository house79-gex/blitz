from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame
from PySide6.QtCore import Qt, QTimer
from ui_qt.theme import THEME

class Header(QFrame):
    """
    Header con titolo + azioni comuni:
    - Home: ritorna alla pagina Home
    - AZZERA: clear emergency (se attiva) + homing
    - Se non azzerata: banner e lampeggio AZZERA
    Compatibile con chiamata Header(appwin, title).
    """
    def __init__(self, appwin, title: str, show_home: bool = True, show_reset: bool = True):
        super().__init__(appwin)
        self.appwin = appwin
        self.setObjectName("Header")
        self.setStyleSheet(f"""
            QFrame#Header {{
                background: {THEME.PANEL_BG};
                border-bottom: 1px solid {THEME.OUTLINE};
            }}
            QLabel#HeaderTitle {{
                font-size: 18px;
                font-weight: 800;
            }}
            QPushButton#HdrBtn {{
                padding: 6px 10px;
                border: 1px solid {THEME.OUTLINE};
                border-radius: 6px;
                background: {THEME.TILE_BG};
            }}
            QPushButton#HdrBtn:hover {{
                border-color: {THEME.ACCENT};
            }}
        """)

        self._blink_timer = None
        self._blink_on = False

        vlay = QVBoxLayout(self)
        vlay.setContentsMargins(8, 8, 8, 0)
        vlay.setSpacing(0)

        # Riga superiore: titolo + azioni
        h = QHBoxLayout()
        h.setContentsMargins(0, 0, 0, 8)
        h.setSpacing(8)
        vlay.addLayout(h)

        self.lbl = QLabel(title)
        self.lbl.setObjectName("HeaderTitle")
        h.addWidget(self.lbl, 0, alignment=Qt.AlignVCenter | Qt.AlignLeft)
        h.addStretch(1)

        if show_home:
            btn_home = QPushButton("Home")
            btn_home.setObjectName("HdrBtn")
            btn_home.clicked.connect(lambda: self.appwin.show_page("home"))
            h.addWidget(btn_home)

        if show_reset:
            self.btn_reset = QPushButton("AZZERA")
            self.btn_reset.setObjectName("HdrBtn")
            self.btn_reset.clicked.connect(self._do_reset)
            h.addWidget(self.btn_reset)

        # Banner “non azzerata”
        self.warn_banner = QLabel("Macchina non azzerata: premi AZZERA")
        self.warn_banner.setVisible(False)
        self.warn_banner.setStyleSheet(f"""
            QLabel {{
                background: {THEME.WARN}22;
                color: {THEME.WARN};
                border-top: 1px solid {THEME.OUTLINE_SOFT};
                border-bottom: 1px solid {THEME.OUTLINE_SOFT};
                padding: 6px 10px;
            }}
        """)
        vlay.addWidget(self.warn_banner, 0, alignment=Qt.AlignLeft)

        # Timer di monitor per banner + lampeggio
        self._start_monitor()

    def _start_monitor(self):
        self._mon = QTimer(self)
        self._mon.setInterval(250)
        self._mon.timeout.connect(self._tick_monitor)
        self._mon.start()

    def _tick_monitor(self):
        try:
            m = self.appwin.machine
            not_homed = not bool(getattr(m, "machine_homed", False))
            emg = bool(getattr(m, "emergency_active", False))
        except Exception:
            not_homed = True
            emg = False

        # Banner visibile se non azzerata o EMG
        self.warn_banner.setVisible(not_homed or emg)

        # Lampeggio AZZERA se non azzerata
        if hasattr(self, "btn_reset"):
            if not_homed or emg:
                if self._blink_timer is None:
                    self._blink_timer = QTimer(self)
                    self._blink_timer.setInterval(500)
                    self._blink_timer.timeout.connect(self._blink_tick)
                    self._blink_timer.start()
            else:
                # stop blink
                if self._blink_timer:
                    self._blink_timer.stop()
                    self._blink_timer = None
                self._blink_on = False
                self.btn_reset.setStyleSheet("")  # reset stile
                self.btn_reset.repaint()

    def _blink_tick(self):
        if not hasattr(self, "btn_reset"):
            return
        self._blink_on = not self._blink_on
        if self._blink_on:
            self.btn_reset.setStyleSheet("background:#d35400; color:white;")  # arancio
        else:
            self.btn_reset.setStyleSheet("")

    def _do_reset(self):
        try:
            m = self.appwin.machine

            # Se emergenza attiva, prova a cancellarla
            if getattr(m, "emergency_active", False) and hasattr(m, "clear_emergency"):
                m.clear_emergency()

            # Avvia homing
            if hasattr(m, "do_homing"):
                try:
                    self.btn_reset.setEnabled(False)
                except Exception:
                    pass

                def cb(success: bool, msg: str):
                    # feedback utente (se c'è un toast)
                    try:
                        if hasattr(self.appwin, "toast") and self.appwin.toast:
                            self.appwin.toast.show(f"AZZERA: {msg}", "ok" if success else "warn", 2500)
                    except Exception:
                        pass
                    try:
                        self.btn_reset.setEnabled(True)
                    except Exception:
                        pass

                m.do_homing(callback=cb)
            else:
                # Fallback: stato base per consentire test
                setattr(m, "machine_homed", True)
                setattr(m, "brake_active", False)
                setattr(m, "clutch_active", True)
        except Exception:
            try:
                self.btn_reset.setEnabled(True)
            except Exception:
                pass
