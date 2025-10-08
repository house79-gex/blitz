from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QFrame

class Header(QWidget):
    """
    Header generico per le pagine:
    - Home a sinistra (azzurro chiaro)
    - Titolo centrato e più grande
    - Pulsante destro contestuale:
        * mode='default' (pagine): Reset rosso -> chiama on_reset (se fornito) e poi Home
        * mode='home' (solo Home): Azzera -> chiama on_azzera (se fornito) e NON cambia pagina
          (lampeggia se la macchina non è azzerata)
    - Segnali: home_clicked, reset_clicked
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
        self.btn_right: Optional[QPushButton] = None  # Reset o Azzera
        self.lbl_title: Optional[QLabel] = None

        # Lampeggio per Azzera in Home
        self._blink_timer: Optional[QTimer] = None
        self._blink_on: bool = False

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
        self.btn_home.setCursor(Qt.PointingHandCursor)
        self.btn_home.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_home.clicked.connect(self._on_home_clicked)
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

        # Pulsante destro: Reset (default) o Azzera (home)
        if self.mode == "home":
            self.btn_right = QPushButton("Azzera", right_bar)
            self.btn_right.setCursor(Qt.PointingHandCursor)
            self.btn_right.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            self.btn_right.clicked.connect(self._on_azzera_clicked)
            # Giallo/ambra per attenzione
            AZZ_BASE = "#f1c40f"
            AZZ_DARK = "#d4ac0d"
            self._azzera_style_base = self._btn_style_3d(AZZ_BASE, AZZ_DARK, font_px=16)
            # Variante più chiara per lampeggio
            AZZ_BASE_L = self._shade(AZZ_BASE, 0.18)
            AZZ_DARK_L = self._shade(AZZ_DARK, 0.12)
            self._azzera_style_blink = self._btn_style_3d(AZZ_BASE_L, AZZ_DARK_L, font_px=16)
            self.btn_right.setStyleSheet(self._azzera_style_base)
            right_bar_l.addWidget(self.btn_right)

            # Timer per lampeggio
            self._blink_timer = QTimer(self)
            self._blink_timer.timeout.connect(self._blink_tick)
            self._blink_timer.start(600)
        else:
            self.btn_right = QPushButton("Reset", right_bar)
            self.btn_right.setCursor(Qt.PointingHandCursor)
            self.btn_right.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            self.btn_right.clicked.connect(self._on_reset_clicked)
            RESET_BASE = "#e74c3c"  # rosso
            RESET_DARK = "#c0392b"
            self.btn_right.setStyleSheet(self._btn_style_3d(RESET_BASE, RESET_DARK, font_px=16))
            right_bar_l.addWidget(self.btn_right)

        # Simmetria Home/Right per centraggio perfetto del titolo
        self._sync_buttons_width()

    def _sync_buttons_width(self):
        if not (self.btn_home and self.btn_right):
            return
        w = max(self.btn_home.sizeHint().width(), self.btn_right.sizeHint().width())
        self.btn_home.setMinimumWidth(w)
        self.btn_right.setMinimumWidth(w)

    def setTitle(self, title: str):
        self.lbl_title.setText(title)

    # ---------------- Event handlers ----------------
    def _on_home_clicked(self):
        # Callback esplicita se fornita, altrimenti segnala
        if callable(self._on_home_cb):
            try:
                self._on_home_cb()
                return
            except Exception:
                pass
        # fallback: prova metodi comuni sull'app
        for attr in ("go_home", "show_home", "navigate_home", "home"):
            if hasattr(self.appwin, attr) and callable(getattr(self.appwin, attr)):
                try:
                    getattr(self.appwin, attr)()
                    return
                except Exception:
                    pass
        if hasattr(self.appwin, "nav") and hasattr(self.appwin.nav, "go_home") and callable(self.appwin.nav.go_home):
            try:
                self.appwin.nav.go_home()
                return
            except Exception:
                pass
        # Se nessun handler ha funzionato, emette segnale
        self.home_clicked.emit()

    def _on_reset_clicked(self):
        self.reset_clicked.emit()
        if callable(self._on_reset_cb):
            try:
                self._on_reset_cb()
            except Exception:
                pass
        # Dopo reset, torna alla Home
        self._on_home_clicked()

    def _on_azzera_clicked(self):
        if callable(self._on_azzera_cb):
            try:
                self._on_azzera_cb()
                return
            except Exception:
                pass
        # fallback su metodi noti di appwin o machine
        for attr in ("start_homing", "do_zero", "azzeramento", "homing"):
            if hasattr(self.appwin, attr) and callable(getattr(self.appwin, attr)):
                try:
                    getattr(self.appwin, attr)()
                    return
                except Exception:
                    pass
        if hasattr(self.appwin, "machine"):
            m = self.appwin.machine
            for attr in ("start_homing", "home", "do_zero", "azzera"):
                if hasattr(m, attr) and callable(getattr(m, attr)):
                    try:
                        getattr(m, attr)()
                        return
                    except Exception:
                        pass
        # Se non c'è handler, non cambia pagina (rimane in Home)

    # ---------------- Blink (solo per Azzera in Home) ----------------
    def _is_machine_zeroed(self) -> bool:
        # Prova attributi comuni
        m = getattr(self.appwin, "machine", None)
        if not m:
            return True
        for name in ("is_zeroed", "zeroed", "is_homed", "homed", "is_azzerata", "azzerata"):
            if hasattr(m, name):
                try:
                    return bool(getattr(m, name))
                except Exception:
                    pass
        # di default consideriamo azzerata per evitare lampeggi spurii
        return True

    def _blink_tick(self):
        if self.mode != "home" or not self.btn_right:
            return
        zeroed = self._is_machine_zeroed()
        if zeroed:
            # Stile fisso quando azzerata
            if hasattr(self, "_azzera_style_base"):
                self.btn_right.setStyleSheet(self._azzera_style_base)
            self._blink_on = False
            return
        # Non azzerata: lampeggia
        self._blink_on = not self._blink_on
        style = self._azzera_style_blink if self._blink_on else self._azzera_style_base
        self.btn_right.setStyleSheet(style)
