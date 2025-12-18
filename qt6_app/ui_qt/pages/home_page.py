from typing import Optional

from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QPushButton, QFrame, QLabel, QSizePolicy
from PySide6.QtCore import Qt, QTimer, QEvent, QSize
from PySide6.QtGui import QIcon
from ui_qt.theme import THEME
from ui_qt.widgets.header import Header
from ui_qt.logic.homing import start_homing  # simulazione homing

# Import “tollerante” del theme_store (icone tema + tema attivo)
try:
    from ui_qt.utils.theme_store import get_active_theme
except Exception:
    def get_active_theme(): return {}

# Applica stylesheet globale se possibile
try:
    from ui_qt.theme import set_palette_from_dict, apply_global_stylesheet
    from PySide6.QtWidgets import QApplication
except Exception:
    def set_palette_from_dict(_p: dict): pass
    def apply_global_stylesheet(_app): pass
    QApplication = None  # type: ignore

BANNER_BG = "#fff3cd"
BANNER_TX = "#856404"
BORDER = "#ffeeba"
BANNER_SLOT_H = 56

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
        # Applica tema attivo (palette + stylesheet globale)
        try:
            active = get_active_theme() or {}
            pal = active.get("palette") or {}
            set_palette_from_dict(pal)
            if QApplication:
                apply_global_stylesheet(QApplication.instance())
        except Exception:
            pass

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(14)

        # Header
        root.addWidget(Header(
            self.appwin,
            "BLITZ 3 - Home",
            mode="home",
            on_azzera=self._azzera_home,
            on_reset=self._reset_home,
            show_home=False
        ))

        # Slot fisso per banner (evita salti)
        self._banner_slot = QFrame()
        self._banner_slot.setFixedHeight(BANNER_SLOT_H)
        slot_l = QVBoxLayout(self._banner_slot); slot_l.setContentsMargins(0, 0, 0, 0); slot_l.setSpacing(0)
        self._banner = QFrame()
        self._banner.setStyleSheet(f"QFrame{{background:{BANNER_BG}; border:1px solid {BORDER}; border-radius:8px;}}")
        bl = QVBoxLayout(self._banner); bl.setContentsMargins(10, 8, 10, 8)
        self._banner_lbl = QLabel("Attenzione: macchina non azzerata")
        self._banner_lbl.setStyleSheet(f"color:{BANNER_TX}; font-weight:800;")
        self._banner_lbl.setAlignment(Qt.AlignCenter)
        bl.addWidget(self._banner_lbl)
        slot_l.addWidget(self._banner, 0, Qt.AlignVCenter)
        root.addWidget(self._banner_slot)
        self._banner.hide()

        # Griglia 2x3 sinistra/destra (ordine richiesto)
        grid = QGridLayout()
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(18)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        root.addLayout(grid, 1)

        # Icone tema attive (facoltative)
        try:
            from ui_qt.utils.theme_store import get_active_theme as _gat
            active = _gat()
            icons_map = (active.get("icons") if isinstance(active, dict) else {}) or {}
        except Exception:
            icons_map = {}

        def make_tile(text, key):
            btn = QPushButton(text)
            btn.setMinimumSize(240, 140)
            btn.setMaximumWidth(520)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {THEME.TILE_BG};
                    color: {THEME.TEXT};
                    border: 2px solid {THEME.ACCENT};
                    border-radius: 12px;
                    font-weight: 800;
                    font-size: 18px;
                    padding: 12px 16px;
                    text-align: center;
                }}
                QPushButton:hover {{ border-color: {THEME.ACCENT_2}; }}
                QPushButton:pressed {{ background: {THEME.PANEL_BG}; }}
            """)
            icon_path = str(icons_map.get(key, "")).strip()
            if icon_path:
                try:
                    btn.setIcon(QIcon(icon_path))
                    btn.setIconSize(QSize(32, 32))
                except Exception:
                    pass
            btn.clicked.connect(lambda: self.appwin.show_page(key))
            return btn

        # Colonna sinistra: Tipologie, Quote Vani Luce, Utility, Cutlist
        # Colonna destra: Automatico, Semi-Automatico, Manuale
        tiles = [
            ("Tipologie", "tipologie"),
            ("Automatico", "automatico"),
            ("Quote Vani Luce", "quotevani"),
            ("Semi-Automatico", "semi"),
            ("Utility", "utility"),
            ("Manuale", "manuale"),
            ("🏷️ Editor Etichette", "label_editor"),
        ]

        r, c = 0, 0
        for text, key in tiles:
            grid.addWidget(make_tile(text, key), r, c)
            c += 1
            if c >= 2:
                c = 0
                r += 1

        spacer = QFrame(); spacer.setMinimumHeight(10)
        root.addWidget(spacer)

        self._update_banner()

    # ---- logica banner ----
    def _is_zeroed(self) -> bool:
        m = getattr(self.appwin, "machine", None)
        if not m:
            return False
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
            if hasattr(m, "do_homing") and callable(getattr(m, "do_homing")):
                m.do_homing(callback=lambda **_: QTimer.singleShot(0, self._update_banner))
            else:
                start_homing(m, callback=lambda **_: QTimer.singleShot(0, self._update_banner))
            if hasattr(self.appwin, "toast"):
                self.appwin.toast.show("Azzeramento avviato", "ok", 2000)
        except Exception:
            pass

    def _reset_home(self):
        try:
            m = self.appwin.machine
            for attr in ("clear_emergency", "reset_emergency", "clear_emg", "emg_reset", "reset_alarm", "reset"):
                if hasattr(m, attr) and callable(getattr(m, attr)):
                    getattr(m, attr)(); break
            try: setattr(m, "machine_homed", False)
            except Exception: pass
            self._update_banner()
            if hasattr(self.appwin, "toast"):
                self.appwin.toast.show("Reset eseguito", "ok", 2000)
        except Exception:
            pass

    # ---- lifecycle ----
    def on_show(self):
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
            try: self._poll.stop()
            except Exception: pass
            self._poll = None
        super().hideEvent(ev)
