from typing import Optional

from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QPushButton, QFrame, QLabel
from PySide6.QtCore import Qt, QTimer
from ui_qt.theme import THEME
from ui_qt.widgets.header import Header

BANNER_BG = "#fff3cd"   # giallo chiaro warning
BANNER_TX = "#856404"   # testo warning
BORDER = "#ffeeba"

class HomePage(QWidget):
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self._banner: Optional[QFrame] = None
        self._banner_lbl: Optional[QLabel] = None
        self._poll: Optional[QTimer] = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # Header in modalità 'home' con AZZERA (lampeggiante) e RESET
        root.addWidget(Header(self.appwin, "BLITZ 3 - Home", mode="home", on_azzera=self._azzera_home, on_reset=self._reset_home))

        # Banner “non azzerata”
        self._banner = QFrame()
        self._banner.setStyleSheet(f"QFrame{{background:{BANNER_BG}; border:1px solid {BORDER}; border-radius:8px;}}")
        bl = QVBoxLayout(self._banner)
        bl.setContentsMargins(10, 8, 10, 8)
        self._banner_lbl = QLabel("Attenzione: macchina non azzerata")
        self._banner_lbl.setStyleSheet(f"color:{BANNER_TX}; font-weight:800;")
        self._banner_lbl.setAlignment(Qt.AlignCenter)
        bl.addWidget(self._banner_lbl)
        root.addWidget(self._banner)
        self._banner.hide()  # nascosto finché non serve

        # Griglia tile principali
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        root.addLayout(grid, 1)

        def make_tile(text, key):
            btn = QPushButton(text)
            btn.setMinimumSize(220, 120)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {THEME.TILE_BG};
                    color: {THEME.TEXT};
                    border: 1px solid {THEME.OUTLINE};
                    border-radius: 10px;
                    font-weight: 700;
                    font-size: 16px;
                }}
                QPushButton:hover {{
                    border-color: {THEME.ACCENT};
                }}
                QPushButton:pressed {{
                    background: {THEME.PANEL_BG};
                }}
            """)
            btn.clicked.connect(lambda: self.appwin.show_page(key))
            return btn

        tiles = [
            ("Automatico", "automatico"),
            ("Semi-Automatico", "semi"),
            ("Manuale", "manuale"),
            ("Tipologie", "tipologie"),
            ("Quote Vani", "quotevani"),
            ("Utility", "utility"),
        ]

        r, c = 0, 0
        for text, key in tiles:
            grid.addWidget(make_tile(text, key), r, c)
            c += 1
            if c >= 3:
                c = 0
                r += 1

        spacer = QFrame()
        spacer.setMinimumHeight(20)
        root.addWidget(spacer)

    # ---- banner logic ----
    def _is_zeroed(self) -> bool:
        m = getattr(self.appwin, "machine", None)
        if not m:
            return True
        for name in ("is_homed", "homed", "is_zeroed", "zeroed", "azzerata", "home_done"):
            if hasattr(m, name):
                try:
                    return bool(getattr(m, name))
                except Exception:
                    pass
        return True

    def _update_banner(self):
        if self._is_zeroed():
            if self._banner:
                self._banner.hide()
        else:
            if self._banner:
                self._banner.show()

    # ---- header callbacks ----
    def _azzera_home(self):
        try:
            m = self.appwin.machine
            # Preferisci procedure di homing/azzeramento complete
            for attr in ("start_homing", "home", "do_zero", "homing_start"):
                if hasattr(m, attr) and callable(getattr(m, attr)):
                    getattr(m, attr)()
                    break
            else:
                # fallback su azzeramento quota
                for attr in ("set_zero", "zero_position", "zero", "set_zero_absolute"):
                    if hasattr(m, attr) and callable(getattr(m, attr)):
                        getattr(m, attr)()
                        break
            if hasattr(self.appwin, "toast"):
                self.appwin.toast.show("Azzeramento avviato", "ok", 2000)
        except Exception:
            pass

    def _reset_home(self):
        try:
            m = self.appwin.machine
            # Varianti comuni di reset EMG/allarmi
            for attr in ("clear_emergency", "reset_emergency", "clear_emg", "emg_reset", "reset_alarm", "reset"):
                if hasattr(m, attr) and callable(getattr(m, attr)):
                    getattr(m, attr)()
                    break
            if hasattr(self.appwin, "toast"):
                self.appwin.toast.show("Reset eseguito", "ok", 2000)
        except Exception:
            pass

    # ---- lifecycle ----
    def on_show(self):
        # avvia polling banner
        if self._poll is None:
            self._poll = QTimer(self)
            self._poll.timeout.connect(self._update_banner)
            self._poll.start(400)
        self._update_banner()

    def hideEvent(self, ev):
        if self._poll is not None:
            try:
                self._poll.stop()
            except Exception:
                pass
            self._poll = None
        super().hideEvent(ev)
