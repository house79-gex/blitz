from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QPushButton, QFrame
from PySide6.QtCore import Qt
from ui_qt.theme import THEME
from ui_qt.widgets.header import Header

class HomePage(QWidget):
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # Header in modalità 'home' con AZZERA (lampeggiante) e RESET
        root.addWidget(Header(self.appwin, "BLITZ 3 - Home", mode="home", on_azzera=self._azzera_home, on_reset=self._reset_home))

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

    def _azzera_home(self):
        try:
            m = self.appwin.machine
            # Preferisci procedure di homing/azzeramento complete
            for attr in ("start_homing", "home", "do_zero"):
                if hasattr(m, attr) and callable(getattr(m, attr)):
                    getattr(m, attr)()
                    break
            else:
                # fallback su azzeramento quota
                if hasattr(m, "set_zero"):
                    m.set_zero()
                elif hasattr(m, "zero_position"):
                    m.zero_position()
            if hasattr(self.appwin, "toast"):
                self.appwin.toast.show("Azzeramento avviato", "ok", 2000)
        except Exception:
            pass

    def _reset_home(self):
        try:
            m = self.appwin.machine
            if hasattr(m, "clear_emergency") and callable(m.clear_emergency):
                m.clear_emergency()
            elif hasattr(m, "reset") and callable(m.reset):
                m.reset()
            if hasattr(self.appwin, "toast"):
                self.appwin.toast.show("Reset eseguito", "ok", 2000)
        except Exception:
            pass

    def on_show(self):
        pass
