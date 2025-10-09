from typing import Optional

from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QPushButton, QFrame, QLabel
from PySide6.QtCore import Qt, QTimer, QEvent, QSize
from PySide6.QtGui import QIcon
from ui_qt.theme import THEME
from ui_qt.widgets.header import Header
from ui_qt.logic.homing import start_homing  # simulazione homing
from ui_qt.utils.theme_store import get_active_theme  # icone/palette attive

BANNER_BG = "#fff3cd"   # giallo chiaro warning
BANNER_TX = "#856404"   # testo warning
BORDER = "#ffeeba"
BANNER_SLOT_H = 56      # altezza fissa slot banner (evita salti layout)

class HomePage(QWidget):
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self._banner_slot: Optional[QFrame] = None
        self._banner: Optional[QFrame] = None
        self._banner_lbl: Optional[QLabel] = None
        self._poll: Optional[QTimer] = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # Header 'home' senza pulsante Home: Azzera a sinistra, Reset a destra
        root.addWidget(Header(
            self.appwin,
            "BLITZ 3 - Home",
            mode="home",
            on_azzera=self._azzera_home,
            on_reset=self._reset_home,
            show_home=False
        ))

        # Slot fisso per il banner (evita che i pulsanti saltino)
        self._banner_slot = QFrame()
        self._banner_slot.setFixedHeight(BANNER_SLOT_H)
        slot_l = QVBoxLayout(self._banner_slot)
        slot_l.setContentsMargins(0, 0, 0, 0)
        slot_l.setSpacing(0)

        # Banner “macchina non azzerata” (inserito nello slot fisso)
        self._banner = QFrame()
        self._banner.setStyleSheet(f"QFrame{{background:{BANNER_BG}; border:1px solid {BORDER}; border-radius:8px;}}")
        bl = QVBoxLayout(self._banner)
        bl.setContentsMargins(10, 8, 10, 8)
        self._banner_lbl = QLabel("Attenzione: macchina non azzerata")
        self._banner_lbl.setStyleSheet(f"color:{BANNER_TX}; font-weight:800;")
        self._banner_lbl.setAlignment(Qt.AlignCenter)
        bl.addWidget(self._banner_lbl)
        slot_l.addWidget(self._banner, 0, Qt.AlignVCenter)
        root.addWidget(self._banner_slot)
        self._banner.hide()  # parte nascosto, ma lo slot resta

        # Griglia di tile principali: 2 colonne x 3 righe
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        root.addLayout(grid, 1)

        # Carica icone attive dai temi
        active = get_active_theme()
        icons_map = (active.get("icons") if isinstance(active, dict) else {}) or {}

        def make_tile(text, key):
            btn = QPushButton(text)
            # Dimensioni maggiorate
            btn.setMinimumSize(280, 160)
            # Bordo colorato e hover
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {THEME.TILE_BG};
                    color: {THEME.TEXT};
                    border: 2px solid {THEME.ACCENT};
                    border-radius: 12px;
                    font-weight: 800;
                    font-size: 20px;
                    padding: 12px 18px;
                    text-align: center;
                }}
                QPushButton:hover {{
                    border-color: {THEME.ACCENT_2};
                }}
                QPushButton:pressed {{
                    background: {THEME.PANEL_BG};
                }}
            """)
            # Icona, se configurata
            icon_path = str(icons_map.get(key, "")).strip()
            if icon_path:
                try:
                    btn.setIcon(QIcon(icon_path))
                    btn.setIconSize(QSize(36, 36))
                except Exception:
                    pass
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
            if c >= 2:  # 2 colonne
                c = 0
                r += 1  # 3 righe totali (6 elementi)

        spacer = QFrame()
        spacer.setMinimumHeight(20)
        root.addWidget(spacer)

        # Aggiorna subito il banner alla costruzione
        self._update_banner()

    # ---- logica banner ----
    def _is_zeroed(self) -> bool:
        m = getattr(self.appwin, "machine", None)
        if not m:
            return False  # trattiamo come NON azzerata
        for name in ("machine_homed", "is_homed", "homed", "is_zeroed", "zeroed", "azzerata", "home_done", "calibrated", "is_calibrated"):
            if hasattr(m, name):
                try:
                    return bool(getattr(m, name))
                except Exception:
                    pass
        return False

    def _update_banner(self):
        if self._is_zeroed():
            if self._banner and self._banner.isVisible():
                self._banner.hide()
        else:
            if self._banner and not self._banner.isVisible():
                self._banner.show()

    # ---- callback header ----
    def _azzera_home(self):
        try:
            m = self.appwin.machine
            # 1) Preferisci API reale
            if hasattr(m, "do_homing") and callable(getattr(m, "do_homing")):
                m.do_homing(callback=lambda **_: QTimer.singleShot(0, self._update_banner))
            else:
                # 2) Simulazione Qt-side se non disponibile
                start_homing(m, callback=lambda **_: QTimer.singleShot(0, self._update_banner))
            if hasattr(self.appwin, "toast"):
                self.appwin.toast.show("Azzeramento avviato", "ok", 2000)
        except Exception:
            pass

    def _reset_home(self):
        try:
            m = self.appwin.machine
            # Alias comuni per reset EMG/allarmi
            for attr in ("clear_emergency", "reset_emergency", "clear_emg", "emg_reset", "reset_alarm", "reset"):
                if hasattr(m, attr) and callable(getattr(m, attr)):
                    getattr(m, attr)()
                    break
            # Dopo il reset, forza banner visibile (non azzerata)
            try:
                setattr(m, "machine_homed", False)
            except Exception:
                pass
            self._update_banner()
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

    def showEvent(self, ev: QEvent):
        if self._poll is None:
            self._poll = QTimer(self)
            self._poll.timeout.connect(self._update_banner)
            self._poll.start(400)
        self._update_banner()
        super().showEvent(ev)

    def hideEvent(self, ev):
        if self._poll is not None:
            try:
                self._poll.stop()
            except Exception:
                pass
            self._poll = None
        super().hideEvent(ev)
