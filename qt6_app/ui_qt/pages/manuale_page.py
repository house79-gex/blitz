from typing import Optional

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton, QSizePolicy
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QFontMetrics
from ui_qt.widgets.header import Header
from ui_qt.widgets.status_panel import StatusPanel

# Dimensioni base (verranno scalate dinamicamente)
BASE_HEIGHT = 900.0
QUOTA_FONT_PX_BASE = 155
BTN_FONT_PX_BASE = 52
PANEL_W = 420
PANEL_H = 220
FQ_H = 100

# Testi pulsanti
BTN_TESTA = "TESTA"
BTN_FRENO_ON = "Blocca Freno"
BTN_FRENO_OFF = "Sblocca Freno"  # etichetta più lunga -> riferimento larghezza fissa
BTN_FRIZ_ON = "Frizione ON"
BTN_FRIZ_OFF = "Frizione OFF"

# Colori
GREEN = "#2ecc71"
GREEN_DARK = "#27ae60"
ORANGE = "#f39c12"
ORANGE_DARK = "#e67e22"
QUOTA_COLOR = "#00e5ff"
LABEL_COLOR = "#2c3e50"

# Padding orizzontale totale (px): 36 per lato + 2px bordo per lato
BTN_PADDING_X_TOTAL = 36 * 2 + 2 * 2
# Extra larghezza per i due pulsanti centrali (margine visivo anti-salto)
BTN_EXTRA_W = 36


class ManualePage(QWidget):
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self.machine = appwin.machine

        self.status: Optional[StatusPanel] = None
        self.lbl_quota_val: Optional[ QLabel ] = None
        self.btn_freno: Optional[ QPushButton ] = None
        self.btn_frizione: Optional[ QPushButton ] = None
        self.btn_testa: Optional[ QPushButton ] = None

        self._poll: Optional[QTimer] = None
        self._sim_mm: float = 0.0
        self._sim_dir: float = +1.0

        self._scale: float = 1.0
        self._btn_main_min_w: int = 0   # larghezza fissa FRENO/FRIZIONE (da “Sblocca Freno” + extra)
        self._btn_testa_min_w: int = 0  # larghezza pulsante TESTA (1/3)

        self._build()

    # ---------------- Helpers nav/reset ----------------
    def _nav_home(self) -> bool:
        if hasattr(self.appwin, "show_page") and callable(getattr(self.appwin, "show_page")):
            try:
                self.appwin.show_page("home"); return True
            except Exception: pass
        for attr in ("go_home", "show_home", "navigate_home", "home"):
            if hasattr(self.appwin, attr) and callable(getattr(self.appwin, attr)):
                try: getattr(self.appwin, attr)(); return True
                except Exception: pass
        if hasattr(self.appwin, "nav") and hasattr(self.appwin.nav, "go_home") and callable(self.appwin.nav.go_home):
            try: self.appwin.nav.go_home(); return True
            except Exception: pass
        return False

    def _reset_and_home(self):
        try:
            m = self.machine
            if hasattr(m, "reset") and callable(getattr(m, "reset")):
                m.reset()
            else:
                setattr(m, "machine_homed", False)
                setattr(m, "emergency_active", False)
                setattr(m, "brake_active", False)
                setattr(m, "clutch_active", True)
        except Exception:
            pass
        if self._poll is not None:
            try: self._poll.stop()
            except Exception: pass
            self._poll = None

    # ---------------- Lettura/Scrittura stati robusti ----------------
    def _get_flag(self, names: list[str], default=False) -> bool:
        for n in names:
            if hasattr(self.machine, n):
                try:
                    return bool(getattr(self.machine, n))
                except Exception:
                    pass
        return bool(default)

    def _sync_aliases(self, base_name: str, value: bool, aliases: list[str]):
        for a in aliases:
            if a == base_name:
                continue
            if hasattr(self.machine, a):
                try:
                    setattr(self.machine, a, bool(value))
                except Exception:
                    pass

    # ---------------- Style helpers ----------------
    @staticmethod
    def _hex_to_rgb(hex_color: str):
        h = hex_color.lstrip("#"); return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
    @staticmethod
    def _rgb_to_hex(rgb): return "#{:02x}{:02x}{:02x}".format(*rgb)
    def _shade(self, hex_color: str, delta: float) -> str:
        r, g, b = self._hex_to_rgb(hex_color)
        if delta >= 0:
            r = min(255, int(r + (255 - r) * delta)); g = min(255, int(g + (255 - g) * delta)); b = min(255, int(b + (255 - b) * delta))
        else:
            r = max(0, int(r * (1 + delta))); g = max(0, int(g * (1 + delta))); b = max(0, int(b * (1 + delta)))
        return self._rgb_to_hex((r, g, b))
    def _btn_style_3d(self, base: str, dark: str, font_px: int) -> str:
        base_hover = self._shade(base, 0.08); dark_hover = self._shade(dark, 0.06)
        base_pressed = self._shade(base, -0.06); dark_pressed = self._shade(dark, -0.08)
        return f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {base}, stop:1 {dark});
                color: white;
                border: 2px solid {dark};
                border-radius: 18px;
                padding: 18px 36px;
                font-weight: 800;
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
                padding-top: 22px; padding-bottom: 14px;
            }}
            QPushButton:disabled {{
                background: #95a5a6;
                border-color: #7f8c8d;
                color: #ecf0f1;
            }}
        """
    @staticmethod
    def _frame_style() -> str:
        return """
            QFrame {
                background: #ecf7ff;
                border: 2px solid #3498db;
                border-radius: 16px;
            }
        """

    # ---------------- Larghezze fisse e adattamento font ----------------
    def _text_width_for_px(self, text: str, pixel_size: int) -> int:
        f = QFont()
        f.setPixelSize(pixel_size)
        fm = QFontMetrics(f)
        return fm.horizontalAdvance(text)

    def _fit_font_px_for_text(self, text: str, base_px: int, avail_w: int) -> int:
        # Riduci il font finché il testo entra nella larghezza disponibile
        px = base_px
        while px > 10 and self._text_width_for_px(text, px) + BTN_PADDING_X_TOTAL > avail_w:
            px -= 1
        return px

    def _compute_button_widths(self):
        """
        Larghezza fissa dei 2 pulsanti centrali = larghezza di 'Sblocca Freno' (etichetta più lunga) + extra.
        TESTA = 1/3 dei principali, ma non meno della sua larghezza testo.
        """
        base_px = int(BTN_FONT_PX_BASE * self._scale)

        # Fisso su Sblocca Freno
        w_main_text = self._text_width_for_px(BTN_FRENO_OFF, base_px)
        w_main = w_main_text + BTN_PADDING_X_TOTAL + BTN_EXTRA_W
        self._btn_main_min_w = w_main

        # TESTA
        w_testa_text = self._text_width_for_px(BTN_TESTA, base_px) + BTN_PADDING_X_TOTAL
        self._btn_testa_min_w = max(w_main // 3, w_testa_text)

        # Applica larghezze fisse
        if self.btn_freno: self.btn_freno.setFixedWidth(self._btn_main_min_w)
        if self.btn_frizione: self.btn_frizione.setFixedWidth(self._btn_main_min_w)
        if self.btn_testa: self.btn_testa.setFixedWidth(self._btn_testa_min_w)

    # ---------------- Scaling dinamico ----------------
    def _apply_scaling(self):
        h = max(1, self.height())
        scale = min(1.0, max(0.75, h / BASE_HEIGHT))
        if abs(scale - self._scale) < 0.02:
            return
        self._scale = scale

        quota_px = int(QUOTA_FONT_PX_BASE * scale)
        label_px = max(12, int(QUOTA_FONT_PX_BASE * 0.35 * scale))

        if self.lbl_quota_val:
            self.lbl_quota_val.setStyleSheet(f"font-family:Consolas; font-weight:900; font-size:{quota_px}px; color:{QUOTA_COLOR};")

        # Aggiorna label “Quota” e “mm”
        try:
            quota_frame = self.lbl_quota_val.parentWidget().parentWidget()
            if quota_frame:
                lay = quota_frame.layout()
                if lay and lay.count() >= 3:
                    lbl_quota = lay.itemAt(0).widget()
                    lbl_mm = lay.itemAt(2).widget()
                    if isinstance(lbl_quota, QLabel):
                        lbl_quota.setStyleSheet(f"font-weight:900; font-size:{label_px}px; color:{LABEL_COLOR};")
                    if isinstance(lbl_mm, QLabel):
                        lbl_mm.setStyleSheet(f"font-weight:900; font-size:{label_px}px; color:{LABEL_COLOR};")
        except Exception:
            pass

        # Recalcola larghezze fisse e re-stila
        self._compute_button_widths()
        self._style_buttons_by_state()

    def _style_buttons_by_state(self):
        brake_on = self._get_flag(["brake_active", "brake_on", "freno_bloccato"], default=False)
        clutch_on = self._get_flag(["clutch_active", "clutch_on", "frizione_inserita"], default=True)
        base_btn_px = int(BTN_FONT_PX_BASE * self._scale)

        # FRENO (centrale sinistra)
        if self.btn_freno:
            txt = BTN_FRENO_OFF if brake_on else BTN_FRENO_ON
            px = self._fit_font_px_for_text(txt, base_btn_px, self._btn_main_min_w)
            self.btn_freno.setText(txt)
            self.btn_freno.setStyleSheet(self._btn_style_3d(GREEN if brake_on else ORANGE, GREEN_DARK if brake_on else ORANGE_DARK, px))

        # FRIZIONE (centrale destra)
        if self.btn_frizione:
            txt = BTN_FRIZ_ON if clutch_on else BTN_FRIZ_OFF
            px = self._fit_font_px_for_text(txt, base_btn_px, self._btn_main_min_w)
            self.btn_frizione.setText(txt)
            self.btn_frizione.setStyleSheet(self._btn_style_3d(GREEN if clutch_on else ORANGE, GREEN_DARK if clutch_on else ORANGE_DARK, px))

        # TESTA (in basso a destra, 1/3 larghezza)
        if self.btn_testa:
            txt = BTN_TESTA
            px = self._fit_font_px_for_text(txt, base_btn_px, self._btn_testa_min_w)
            self.btn_testa.setText(txt)
            self.btn_testa.setStyleSheet(self._btn_style_3d(GREEN if brake_on else ORANGE, GREEN_DARK if brake_on else ORANGE_DARK, px))

    # ---------------- Build UI ----------------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8); root.setSpacing(6)

        # Header
        root.addWidget(Header(self.appwin, "MANUALE", mode="default", on_home=self._nav_home, on_reset=self._reset_and_home))

        body = QHBoxLayout(); body.setSpacing(8); root.addLayout(body, 1)

        # Sinistra: QUOTA + pulsanti
        left = QFrame(); body.addWidget(left, 2)
        ll = QVBoxLayout(left); ll.setContentsMargins(6, 6, 6, 6); ll.setSpacing(16)

        # QUOTA
        quota_frame = QFrame(); quota_frame.setStyleSheet(self._frame_style())
        qh = QHBoxLayout(quota_frame); qh.setContentsMargins(18, 18, 18, 18); qh.setSpacing(20); qh.setAlignment(Qt.AlignCenter)

        lbl_quota = QLabel("Quota"); lbl_quota.setStyleSheet(f"font-weight:900; font-size:{int(QUOTA_FONT_PX_BASE*0.35)}px; color:{LABEL_COLOR};")
        qh.addWidget(lbl_quota, 0, Qt.AlignVCenter)

        self.lbl_quota_val = QLabel("—")
        self.lbl_quota_val.setStyleSheet(f"font-family:Consolas; font-weight:900; font-size:{QUOTA_FONT_PX_BASE}px; color:{QUOTA_COLOR};")
        self.lbl_quota_val.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding); self.lbl_quota_val.setAlignment(Qt.AlignCenter)
        qh.addWidget(self.lbl_quota_val, 0, Qt.AlignVCenter)

        lbl_mm = QLabel("mm"); lbl_mm.setStyleSheet(f"font-weight:900; font-size:{int(QUOTA_FONT_PX_BASE*0.35)}px; color:{LABEL_COLOR};")
        qh.addWidget(lbl_mm, 0, Qt.AlignVCenter)

        ll.addWidget(quota_frame, 3, alignment=Qt.AlignCenter)

        # Pulsanti centrali: FRENO + FRIZIONE (centrati, distanziati)
        center_btns = QFrame()
        cb_lay = QHBoxLayout(center_btns)
        cb_lay.setContentsMargins(12, 12, 12, 12)
        cb_lay.setSpacing(48)
        cb_lay.setAlignment(Qt.AlignCenter)

        self.btn_freno = QPushButton(BTN_FRENO_ON); self.btn_freno.clicked.connect(self._toggle_freno)
        self.btn_frizione = QPushButton(BTN_FRIZ_ON); self.btn_frizione.clicked.connect(self._toggle_frizione)
        cb_lay.addWidget(self.btn_freno, 0, Qt.AlignCenter)
        cb_lay.addWidget(self.btn_frizione, 0, Qt.AlignCenter)
        ll.addWidget(center_btns, 0, Qt.AlignCenter)

        # Spacer e TESTA in basso a destra (1/3 larghezza)
        ll.addStretch(1)
        bottom_bar = QFrame()
        bb_lay = QHBoxLayout(bottom_bar)
        bb_lay.setContentsMargins(12, 0, 0, 0)
        bb_lay.setSpacing(0)
        bb_lay.addStretch(1)  # spinge a destra

        self.btn_testa = QPushButton(BTN_TESTA); self.btn_testa.clicked.connect(self._press_testa)
        self.btn_testa.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        bb_lay.addWidget(self.btn_testa, 0, Qt.AlignRight | Qt.AlignBottom)
        ll.addWidget(bottom_bar, 0)

        # Destra: Status + placeholder FQ
        right = QFrame(); right.setFixedWidth(PANEL_W + 12); body.addWidget(right, 0)
        rl = QVBoxLayout(right); rl.setContentsMargins(6,6,6,6); rl.setSpacing(8)

        status_wrap = QFrame()
        status_wrap.setFixedWidth(PANEL_W)
        swl = QVBoxLayout(status_wrap); swl.setContentsMargins(0,0,0,0)
        self.status = StatusPanel(self.machine, "STATO", status_wrap); swl.addWidget(self.status)
        rl.addWidget(status_wrap, 0, alignment=Qt.AlignLeft | Qt.AlignTop)

        fq_placeholder = QFrame()
        fq_placeholder.setFixedWidth(PANEL_W)
        fq_placeholder.setFrameShape(QFrame.StyledPanel)
        fq_placeholder.setFixedHeight(FQ_H)
        rl.addWidget(fq_placeholder, 0, alignment=Qt.AlignLeft)
        rl.addStretch(1)

        # Stile iniziale
        self._apply_scaling()

    # ---------------- Button logic ----------------
    def _toggle_freno(self):
        want = not self._get_flag(["brake_active", "brake_on", "freno_bloccato"], default=False)
        m = self.machine
        ok = False
        if hasattr(m, "set_brake") and callable(getattr(m, "set_brake")):
            try: ok = bool(m.set_brake(want))
            except Exception: ok = False
        if not ok and hasattr(m, "toggle_brake") and callable(getattr(m, "toggle_brake")):
            try:
                cur = self._get_flag(["brake_active", "brake_on", "freno_bloccato"], default=False)
                if cur != want: ok = bool(m.toggle_brake())
            except Exception: ok = False
        if not ok:
            for a in ("brake_active", "brake_on", "freno_bloccato"):
                if hasattr(m, a):
                    try: setattr(m, a, bool(want))
                    except Exception: pass
            ok = True
        if ok:
            self._sync_aliases("brake_active", getattr(m, "brake_active", want), ["brake_on", "freno_bloccato"])
        # aggiornamento immediato
        self._compute_button_widths()
        self._style_buttons_by_state()
        if self.status: self.status.refresh()

    def _toggle_frizione(self):
        cur = self._get_flag(["clutch_active", "clutch_on", "frizione_inserita"], default=True)
        want = not cur
        m = self.machine
        ok = False
        if hasattr(m, "set_clutch") and callable(getattr(m, "set_clutch")):
            try: ok = bool(m.set_clutch(want))
            except Exception: ok = False
        if not ok and hasattr(m, "toggle_clutch") and callable(getattr(m, "toggle_clutch")):
            try:
                if cur != want:
                    ok = bool(m.toggle_clutch())
            except Exception: ok = False
        if not ok:
            for a in ("clutch_active", "clutch_on", "frizione_inserita"):
                if hasattr(m, a):
                    try: setattr(m, a, bool(want))
                    except Exception: pass
            ok = True

        new_val = getattr(m, "clutch_active", want)
        self._sync_aliases("clutch_active", new_val, ["clutch_on", "frizione_inserita"])

        # aggiornamento immediato
        self._compute_button_widths()
        self._style_buttons_by_state()
        if self.status: self.status.refresh()

    def _press_testa(self):
        handled = False
        if hasattr(self.machine, "external_head_button_press") and callable(getattr(self.machine, "external_head_button_press")):
            try:
                handled = bool(self.machine.external_head_button_press())
            except Exception:
                handled = False

        if not handled:
            brake_on = self._get_flag(["brake_active", "brake_on", "freno_bloccato"], default=False)
            target_locked = not brake_on
            try:
                setattr(self.machine, "brake_active", target_locked)
                setattr(self.machine, "clutch_active", target_locked)
                self._sync_aliases("brake_active", target_locked, ["brake_on", "freno_bloccato"])
                self._sync_aliases("clutch_active", target_locked, ["clutch_on", "frizione_inserita"])
            except Exception:
                pass

        # aggiornamento immediato
        self._compute_button_widths()
        self._style_buttons_by_state()
        if self.status: self.status.refresh()

    # ---------------- Encoder display ----------------
    @staticmethod
    def _fmt_mm(v) -> str:
        try: return f"{float(v):.2f}"
        except Exception: return "—"

    def _update_quota_label(self):
        for name in ("encoder_position", "position_current"):
            if hasattr(self.machine, name):
                try:
                    val = float(getattr(self.machine, name))
                    if self.lbl_quota_val:
                        self.lbl_quota_val.setText(self._fmt_mm(val))
                    return
                except Exception:
                    pass
        # Simulazione locale
        brake_on = self._get_flag(["brake_active", "brake_on", "freno_bloccato"], default=False)
        clutch_on = self._get_flag(["clutch_active", "clutch_on", "frizione_inserita"], default=True)
        manual_move_ok = (not brake_on) and (not clutch_on)
        if manual_move_ok:
            if not (0.0 <= self._sim_mm <= 4000.0):
                self._sim_mm = max(0.0, min(4000.0, self._sim_mm)); self._sim_dir = -self._sim_dir
            self._sim_mm += self._sim_dir * 1.5
            if self._sim_mm >= 4000.0: self._sim_mm = 4000.0; self._sim_dir = -1.0
            elif self._sim_mm <= 0.0: self._sim_mm = 0.0; self._sim_dir = +1.0
        if self.lbl_quota_val:
            self.lbl_quota_val.setText(self._fmt_mm(self._sim_mm))

    # ---------------- Lifecycle ----------------
    def on_show(self):
        try:
            if hasattr(self.machine, "set_head_button_input_enabled"): self.machine.set_head_button_input_enabled(True)
        except Exception: pass
        if self._poll is None:
            self._poll = QTimer(self); self._poll.timeout.connect(self._tick); self._poll.start(200)
        self._apply_scaling()
        self._update_quota_label()
        if self.status: self.status.refresh()

    def _tick(self):
        self._update_quota_label()
        if self.status: self.status.refresh()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._apply_scaling()

    def hideEvent(self, ev):
        try:
            if hasattr(self.machine, "set_head_button_input_enabled"): self.machine.set_head_button_input_enabled(False)
        except Exception: pass
        try:
            if hasattr(self.machine, "normalize_after_manual"): self.machine.normalize_after_manual()
            elif hasattr(self.machine, "clutch_active"): setattr(self.machine, "clutch_active", True)
        except Exception: pass
        if self._poll is not None:
            try: self._poll.stop()
            except Exception: pass
            self._poll = None
        super().hideEvent(ev)
