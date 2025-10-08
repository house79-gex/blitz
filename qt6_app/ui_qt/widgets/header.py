from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QFrame


class Header(QWidget):
    """
    Header generico:
    - Home a sinistra (azzurro chiaro)
    - Titolo centrato e più grande
    - Lato destro:
        * mode='default' (pagine): solo Reset (rosso). Al click: chiama on_reset (se fornito) e poi torna alla Home.
        * mode='home' (Home): Azzera (lampeggiante se non azzerata) + Reset (rosso).
    Segnali: home_clicked, reset_clicked.
    """
    home_clicked = Signal()
    reset_clicked = Signal()

    def __init__(
        self,
        appwin,
        title: str,
        mode: str = "default",
        on_home: Optional[Callable[[], None]] = None,
        on_reset: Optional[Callable[[], None]] = None,
        on_azzera: Optional[Callable[[], None]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.appwin = appwin
        self.mode = mode
        self._on_home_cb = on_home
        self._on_reset_cb = on_reset
        self._on_azzera_cb = on_azzera

        self.btn_home: Optional[QPushButton] = None
        self.btn_reset: Optional[QPushButton] = None
        self.btn_azzera: Optional[QPushButton] = None
        self.lbl_title: Optional[QLabel] = None

        self._blink_timer: Optional[QTimer] = None
        self._blink_on: bool = False

        self._build(title)

    # ---- colori utils ----
    @staticmethod
    def _hex_to_rgb(hex_color: str):
        h = hex_color.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    @staticmethod
    def _rgb_to_hex(rgb):
        return "#{:02x}{:02x}{:02x}".format(*rgb)

    def _shade(self, hex_color: str, delta: float) -> str:
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
        right_bar_l.setSpacing(8)

        lay.addWidget(left_bar, 0)
        lay.addWidget(center, 1)
        lay.addWidget(right_bar, 0)

        # Home (azzurro) a sinistra
        self.btn_home = QPushButton("Home", left_bar)
        self.btn_home.setCursor(Qt.PointingHandCursor)
        self.btn_home.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_home.clicked.connect(self._on_home_clicked)
        HOME_BASE = "#5dade2"
        HOME_DARK = "#3498db"
        self.btn_home.setStyleSheet(self._btn_style_3d(HOME_BASE, HOME_DARK, font_px=16))
        left_bar_l.addWidget(self.btn_home)

        # Titolo centrato
        self.lbl_title = QLabel(title, center)
        self.lbl_title.setAlignment(Qt.AlignCenter)
        self.lbl_title.setStyleSheet("font-size: 26px; font-weight: 800;")
        self.lbl_title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        center_l.addWidget(self.lbl_title, 1, Qt.AlignCenter)

        RESET_BASE = "#e74c3c"
        RESET_DARK = "#c0392b"

        if self.mode == "home":
            # Azzera
            self.btn_azzera = QPushButton("Azzera", right_bar)
            self.btn_azzera.setCursor(Qt.PointingHandCursor)
            self.btn_azzera.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            self.btn_azzera.clicked.connect(self._on_azzera_clicked)
            AZZ_BASE = "#f1c40f"
            AZZ_DARK = "#d4ac0d"
            self._azzera_style_base = self._btn_style_3d(AZZ_BASE, AZZ_DARK, font_px=16)
            AZZ_BASE_L = self._shade(AZZ_BASE, 0.18)
            AZZ_DARK_L = self._shade(AZZ_DARK, 0.12)
            self._azzera_style_blink = self._btn_style_3d(AZZ_BASE_L, AZZ_DARK_L, font_px=16)
            self.btn_azzera.setStyleSheet(self._azzera_style_base)
            right_bar_l.addWidget(self.btn_azzera)

            # Reset
            self.btn_reset = QPushButton("Reset", right_bar)
            self.btn_reset.setCursor(Qt.PointingHandCursor)
            self.btn_reset.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            self.btn_reset.clicked.connect(self._on_reset_clicked_home)
            self.btn_reset.setStyleSheet(self._btn_style_3d(RESET_BASE, RESET_DARK, font_px=16))
            right_bar_l.addWidget(self.btn_reset)

            # Timer lampeggio per “Azzera”
            self._blink_timer = QTimer(self)
            self._blink_timer.timeout.connect(self._blink_tick)
            self._blink_timer.start(600)
        else:
            # Solo Reset nelle pagine
            self.btn_reset = QPushButton("Reset", right_bar)
            self.btn_reset.setCursor(Qt.PointingHandCursor)
            self.btn_reset.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            self.btn_reset.clicked.connect(self._on_reset_clicked_page)
            self.btn_reset.setStyleSheet(self._btn_style_3d(RESET_BASE, RESET_DARK, font_px=16))
            right_bar_l.addWidget(self.btn_reset)

        self._sync_buttons_width()

    def _sync_buttons_width(self):
        if self.btn_reset and self.btn_home:
            w = max(self.btn_home.sizeHint().width(), self.btn_reset.sizeHint().width())
            self.btn_home.setMinimumWidth(w)
            self.btn_reset.setMinimumWidth(w)
        if self.mode == "home" and self.btn_azzera and self.btn_reset:
            w = max(self.btn_azzera.sizeHint().width(), self.btn_reset.sizeHint().width())
            self.btn_azzera.setMinimumWidth(w)
            self.btn_reset.setMinimumWidth(w)

    def setTitle(self, title: str):
        self.lbl_title.setText(title)

    # ---- event handlers ----
    def _navigate_home_fallback(self):
        # Callback esplicita
        if callable(self._on_home_cb):
            try:
                self._on_home_cb()
                return True
            except Exception:
                pass
        # Fallback esplicito su show_page('home')
        if hasattr(self.appwin, "show_page") and callable(getattr(self.appwin, "show_page")):
            try:
                self.appwin.show_page("home")
                return True
            except Exception:
                pass
        # Altri nomi possibili
        for attr in ("go_home", "show_home", "navigate_home", "home"):
            if hasattr(self.appwin, attr) and callable(getattr(self.appwin, attr)):
                try:
                    getattr(self.appwin, attr)()
                    return True
                except Exception:
                    pass
        # nav helper
        if hasattr(self.appwin, "nav") and hasattr(self.appwin.nav, "go_home") and callable(self.appwin.nav.go_home):
            try:
                self.appwin.nav.go_home()
                return True
            except Exception:
                pass
        return False

    def _on_home_clicked(self):
        if not self._navigate_home_fallback():
            self.home_clicked.emit()

    def _on_reset_clicked_page(self):
        # Reset nelle pagine, poi vai Home
        self.reset_clicked.emit()
        if callable(self._on_reset_cb):
            try:
                self._on_reset_cb()
            except Exception:
                pass
        self._navigate_home_fallback()

    def _on_reset_clicked_home(self):
        # Reset in Home: resta in Home
        self.reset_clicked.emit()
        if callable(self._on_reset_cb):
            try:
                self._on_reset_cb()
                return
            except Exception:
                pass
        # fallback reset appwin o machine
        for attr in ("reset_current_page", "reset_all", "reset"):
            if hasattr(self.appwin, attr) and callable(getattr(self.appwin, attr)):
                try:
                    getattr(self.appwin, attr)()
                    return
                except Exception:
                    pass
        if hasattr(self.appwin, "machine"):
            m = self.appwin.machine
            for attr in ("clear_emergency", "reset"):
                if hasattr(m, attr) and callable(getattr(m, attr)):
                    try:
                        getattr(m, attr)()
                        return
                    except Exception:
                        pass

    def _on_azzera_clicked(self):
        if callable(self._on_azzera_cb):
            try:
                self._on_azzera_cb()
                return
            except Exception:
                pass
        # fallback
        for attr in ("start_homing", "do_zero", "homing"):
            if hasattr(self.appwin, attr) and callable(getattr(self.appwin, attr)):
                try:
                    getattr(self.appwin, attr)()
                    return
                except Exception:
                    pass
        if hasattr(self.appwin, "machine"):
            m = self.appwin.machine
            for attr in ("start_homing", "home", "do_zero", "azzera", "set_zero", "zero_position"):
                if hasattr(m, attr) and callable(getattr(m, attr)):
                    try:
                        getattr(m, attr)()
                        return
                    except Exception:
                        pass

    # ---- blink “Azzera” in Home ----
    def _is_machine_zeroed(self) -> bool:
        m = getattr(self.appwin, "machine", None)
        if not m:
            return True
        for name in ("is_homed", "homed", "is_zeroed", "zeroed", "azzerata"):
            if hasattr(m, name):
                try:
                    return bool(getattr(m, name))
                except Exception:
                    pass
        return True

    def _blink_tick(self):
        if self.mode != "home" or not self.btn_azzera:
            return
        if self._is_machine_zeroed():
            self.btn_azzera.setStyleSheet(self._azzera_style_base)
            self._blink_on = False
            return
        self._blink_on = not self._blink_on
        self.btn_azzera.setStyleSheet(self._azzera_style_blink if self._blink_on else self._azzera_style_base)
