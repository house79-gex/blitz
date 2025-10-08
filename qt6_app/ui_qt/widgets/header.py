from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QFrame

class Header(QWidget):
    """
    Header generico per le pagine:
    - Home a sinistra (azzurro chiaro)
    - Titolo centrato e più grande
    - Reset a destra (rosso); alla pressione effettua il reset (se definito) e torna alla Home
    - Segnali: home_clicked, reset_clicked
    """
    home_clicked = Signal()
    reset_clicked = Signal()

    def __init__(self, appwin, title: str, on_reset: Optional[Callable[[], None]] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.appwin = appwin
        self._on_reset_cb = on_reset
        self._build(title)

    # ---------------- Color helpers ----------------
    @staticmethod
    def _hex_to_rgb(hex_color: str):
        h = hex_color.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    @staticmethod
    def _rgb_to_hex(rgb):
        return "#{:02x}{:02x}{:02x}".format(*rgb)

    def _shade(self, hex_color: str, delta: float) -> str:
        # delta > 0 schiarisce (0..1), delta < 0 scurisce (-1..0)
        r, g, b = self._hex_to_rgb(hex_color)
        if delta >= 0:
            r = min(255, int(r + (255 - r) * delta))
            g = min(255, int(g + (255 - g) * delta))
            b = min(255, int(b + (255 - b) * delta))
        else:
            r = max(0, int(r * (1 + delta)))
            g = max(0, int(g * (1 + delta)))
            b = max(0, int(b * (1 + delta)))
        return self._rgb_to_hex((r, g, b))

    def _btn_style_3d(self, base: str, dark: str, text_color: str = "white", radius: int = 12, pad_v: int = 8, pad_h: int = 16, font_px: int = 18) -> str:
        base_hover = self._shade(base, 0.08)
        dark_hover = self._shade(dark, 0.06)
        base_pressed = self._shade(base, -0.06)
        dark_pressed = self._shade(dark, -0.08)
        return f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {base}, stop:1 {dark});
                color: {text_color};
                border: 2px solid {dark};
                border-radius: {radius}px;
                padding: {pad_v}px {pad_h}px;
                font-weight: 700;
                font-size: {font_px}px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {base_hover}, stop:1 {dark_hover});
                border-color: {dark_hover};
            }}
            QPushButton:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {dark_pressed}, stop:1 {base_pressed});
                border-color: {dark_pressed};
                padding-top: {pad_v + 2}px; padding-bottom: {max(0, pad_v - 2)}px;
            }}
            QPushButton:disabled {{
                background: #95a5a6;
                border-color: #7f8c8d;
                color: #ecf0f1;
            }}
        """

    def _build(self, title: str):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        # Barre laterali per centraggio del titolo
        left_bar = QFrame(self)
        left_bar_l = QHBoxLayout(left_bar)
        left_bar_l.setContentsMargins(0, 0, 0, 0)
        left_bar_l.setSpacing(0)

        center = QFrame(self)
        center_l = QHBoxLayout(center)
        center_l.setContentsMargins(0, 0, 0, 0)
        center_l.setSpacing(0)

        right_bar = QFrame(self)
        right_bar_l = QHBoxLayout(right_bar)
        right_bar_l.setContentsMargins(0, 0, 0, 0)
        right_bar_l.setSpacing(0)

        lay.addWidget(left_bar, 0)
        lay.addWidget(center, 1)  # il centro prende lo stretch
        lay.addWidget(right_bar, 0)

        # Pulsante Home (azzurro chiaro) a sinistra
        self.btn_home = QPushButton("Home", left_bar)
        self.btn_home.setObjectName("btn_home")
        self.btn_home.setCursor(Qt.PointingHandCursor)
        self.btn_home.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_home.clicked.connect(self._go_home)
        # Colori Home
        HOME_BASE = "#5dade2"   # azzurro chiaro
        HOME_DARK = "#3498db"
        self.btn_home.setStyleSheet(self._btn_style_3d(HOME_BASE, HOME_DARK, font_px=16))
        left_bar_l.addWidget(self.btn_home)

        # Titolo centrato e più grande
        self.lbl_title = QLabel(title, center)
        self.lbl_title.setAlignment(Qt.AlignCenter)
        self.lbl_title.setStyleSheet("font-size: 26px; font-weight: 800;")
        self.lbl_title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        center_l.addWidget(self.lbl_title, 1, Qt.AlignCenter)

        # Pulsante Reset (rosso) a destra
        self.btn_reset = QPushButton("Reset", right_bar)
        self.btn_reset.setObjectName("btn_reset")
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_reset.clicked.connect(self._do_reset_and_home)
        # Colori Reset
        RESET_BASE = "#e74c3c"  # rosso
        RESET_DARK = "#c0392b"
        self.btn_reset.setStyleSheet(self._btn_style_3d(RESET_BASE, RESET_DARK, font_px=16))
        right_bar_l.addWidget(self.btn_reset)

        # Rendi Home/Reset simmetrici in larghezza per mantenere il titolo centrato
        self._sync_buttons_width()

    def _sync_buttons_width(self):
        w = max(self.btn_home.sizeHint().width(), self.btn_reset.sizeHint().width())
        self.btn_home.setMinimumWidth(w)
        self.btn_reset.setMinimumWidth(w)

    def setTitle(self, title: str):
        self.lbl_title.setText(title)

    # Navigazione Home robusta
    def _go_home(self):
        handled = False
        # Tenta metodi comuni nel MainWindow/app
        for attr in ("go_home", "show_home", "navigate_home", "home"):
            if hasattr(self.appwin, attr) and callable(getattr(self.appwin, attr)):
                try:
                    getattr(self.appwin, attr)()
                    handled = True
                    break
                except Exception:
                    pass
        # Tenta un oggetto nav con go_home
        if not handled and hasattr(self.appwin, "nav"):
            nav = getattr(self.appwin, "nav")
            if hasattr(nav, "go_home") and callable(nav.go_home):
                try:
                    nav.go_home()
                    handled = True
                except Exception:
                    pass
        # Se nessun handler, emetti segnale (il chiamante può gestirlo)
        if not handled:
            self.home_clicked.emit()

    def _do_reset_and_home(self):
        # Emetti segnale per listener esterni
        self.reset_clicked.emit()

        # Invoca callback reset (se fornita)
        try:
            if callable(self._on_reset_cb):
                self._on_reset_cb()
        except Exception:
            pass

        # In assenza di callback, prova metodi noti sull'app
        if self._on_reset_cb is None:
            for attr in ("reset_current_page", "reset_page", "reset_all", "reset"):
                if hasattr(self.appwin, attr) and callable(getattr(self.appwin, attr)):
                    try:
                        getattr(self.appwin, attr)()
                        break
                    except Exception:
                        pass

        # Dopo il reset, vai sempre alla Home
        self._go_home()
