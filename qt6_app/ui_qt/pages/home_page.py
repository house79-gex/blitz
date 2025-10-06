from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QPushButton, QLabel, QFrame, QHBoxLayout
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

        root.addWidget(Header(self.appwin, "BLITZ 3 - Home"))

        # Barra comandi rapidi: Azzera + Reset
        quick = QHBoxLayout()
        btn_zero = QPushButton("AZZERA")
        btn_zero.setMinimumHeight(36)
        btn_zero.clicked.connect(self._zero)
        quick.addWidget(btn_zero)

        btn_reset = QPushButton("RESET")
        btn_reset.setMinimumHeight(36)
        btn_reset.clicked.connect(self._reset)
        quick.addWidget(btn_reset)

        quick.addStretch(1)
        root.addLayout(quick)

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

        # Disposizione pulsanti principali
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

    def _zero(self):
        try:
            m = self.appwin.machine
            if hasattr(m, "set_zero"):
                m.set_zero()
            elif hasattr(m, "zero_position"):
                m.zero_position()
            if hasattr(self.appwin, "toast"):
                self.appwin.toast.show("Quota azzerata", "ok", 2000)
        except Exception:
            pass

    def _reset(self):
        try:
            m = self.appwin.machine
            if hasattr(m, "clear_emergency"):
                m.clear_emergency()
            if hasattr(self.appwin, "toast"):
                self.appwin.toast.show("Reset (EMG clear) eseguito", "ok", 2000)
        except Exception:
            pass

    def on_show(self):
        pass
