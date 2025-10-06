from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QPushButton, QLabel, QFrame
from PySide6.QtCore import Qt
from ui_qt.theme import THEME

class HomePage(QWidget):
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        title = QLabel("BLITZ 3 - Home")
        title.setAlignment(Qt.AlignHCenter)
        title.setStyleSheet("font-size: 22px; font-weight: 800;")
        root.addWidget(title)

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

        # Spazio inferiore
        spacer = QFrame()
        spacer.setMinimumHeight(20)
        root.addWidget(spacer)

    def on_show(self):
        pass
