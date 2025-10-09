from typing import Optional

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton, QSizePolicy
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontMetrics
from ui_qt.widgets.header import Header
from ui_qt.widgets.status_panel import StatusPanel

# Dimensioni base (verranno scalate dinamicamente)
BASE_HEIGHT = 900.0
QUOTA_FONT_PX_BASE = 168
BTN_FONT_PX_BASE = 56
PANEL_W = 420
PANEL_H = 220
FQ_H = 100

# Testi pulsanti (uniformati e stabili)
BTN_TESTA = "TESTA"
BTN_FRENO_ON = "BLOCCA FRENO"
BTN_FRENO_OFF = "SBLOCCA FRENO"
BTN_FRIZ_ON = "Frizione ON (inserita)"
BTN_FRIZ_OFF = "Frizione OFF (disinserita)"

# Colori
GREEN = "#2ecc71"
GREEN_DARK = "#27ae60"
ORANGE = "#f39c12"
ORANGE_DARK = "#e67e22"
QUOTA_COLOR = "#00e5ff"
LABEL_COLOR = "#2c3e50"

class ManualePage(QWidget):
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self.machine = appwin.machine

        self.status: Optional[StatusPanel] = None
        self.lbl_quota_val: Optional[QLabel] = None
        self.btn_freno: Optional[QPushButton] = None
        self.btn_frizione: Optional[QPushButton] = None
        self.btn_testa: Optional[QPushButton] = None

        self._poll: Optional[QTimer] = None
        self._sim_mm: float = 0.0
        self._sim_dir: float = +1.0

        self._scale: float = 1.0  # scala UI dinamica

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
        """
        Ritorna il primo attributo disponibile in ordine di priorità.
        Evita OR fra alias che generano stati incoerenti.
        """
        for n in names:
            if hasattr(self.machine, n):
                try:
                    return bool(getattr(self.machine, n))
                except Exception:
                    pass
        return bool(default)

    def _sync_aliases(self, base_name: str, value: bool, aliases: list[str]):
        """
        Sincronizza eventuali alias sullo stesso stato, se presenti.
        """
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

    # ---------------- Larghezza pulsanti stabile ----------------
    def _compute_text_width(self, btn: QPushButton, text: str) -> int:
        fm = QFontMetrics(btn.font())
        return fm.horizontalAdvance(text)

    def _sync_button_widths(self):
        """
        Imposta la stessa larghezza minima per FRENO, FRIZIONE e TESTA, basata
        sul testo più lungo (considerando entrambi gli stati).
        Evita 'salti' quando cambia il testo.
        """
        if not (self.btn_freno and self.btn_frizione and self.btn_testa):
            return

        # Testi possibili per ogni pulsante
        texts = [
            BTN_FRENO_ON, BTN_FRENO_OFF,
            BTN_FRIZ_ON, BTN_FRIZ_OFF,
            BTN_TESTA
        ]

        # Misura tutte le alternative con l'attuale font (già scalato via stylesheet)
        widths = []
        for t in texts:
            # usa il font del pulsante frizione (stesso stile) come riferimento
            ref_btn = self.btn_frizione
            widths.append(self._compute_text_width(ref_btn, t))

        # Aggiungi padding orizzontale del nostro stile: 36px per lato + bordi (2px per lato)
        padding_x = 36 * 2 + 2 * 2
        base_w = max(widths) + padding_x

        # Imposta la minima uguale per tutti (stessa dimensione visiva, niente salti)
        for b in (self.btn_freno, self.btn_frizione, self.btn_testa):
            b.setMinimumWidth(base_w)

    # ---------------- Scaling dinamico ----------------
    def _apply_scaling(self):
        """
        Riduce/ingrandisce dinamicamente i font per stare nello schermo,
        senza introdurre scroll bar.
        """
        h = max(1, self.height())
        scale = min(1.0, max(0.75, h / BASE_HEIGHT))
        if abs(scale - self._scale) < 0.02:
            return
        self._scale = scale

        quota_px = int(QUOTA_FONT_PX_BASE * scale)
        btn_px = int(BTN_FONT_PX_BASE * scale)
        label_px = max(12, int(QUOTA_FONT_PX_BASE * 0.35 * scale))

        if self.lbl_quota_val:
            self.lbl_quota_val.setStyleSheet(f"font-family:Consolas; font-weight:900; font-size:{quota_px}px; color:{QUOTA_COLOR};")

        # Aggiorna stili pulsanti (colore in base allo stato)
        brake_on = self._get_flag(["brake_active", "brake_on", "freno_bloccato"], default=False)
        clutch_on = self._get_flag(["clutch_active", "clutch_on", "frizione_inserita"], default=True)
        if self.btn_freno:
            self.btn_freno.setStyleSheet(self._btn_style_3d(GREEN if brake_on else ORANGE, GREEN_DARK if brake_on else ORANGE_DARK, btn_px))
        if self.btn_frizione:
            self.btn_frizione.setStyleSheet(self._btn_style_3d(GREEN if clutch_on else ORANGE, GREEN_DARK if clutch_on else ORANGE_DARK, btn_px))
        if self.btn_testa:
            self.btn_testa.setStyleSheet(self._btn_style_3d(GREEN if brake_on else ORANGE, GREEN_DARK if brake_on else ORANGE_DARK, btn_px))

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

        # Reimposta larghezze minime coerenti dopo lo scaling
        self._sync_button_widths()
        self._style_buttons_by_state()

    def _style_buttons_by_state(self):
        brake_on = self._get_flag(["brake_active", "brake_on", "freno_bloccato"], default=False)
        clutch_on = self._get_flag(["clutch_active", "clutch_on", "frizione_inserita"], default=True)
        btn_px = int(BTN_FONT_PX_BASE * self._scale)

        if self.btn_freno:
            if brake_on:
                self.btn_freno.setText(BTN_FRENO_OFF)
                self.btn_freno.setStyleSheet(self._btn_style_3d(GREEN, GREEN_DARK, btn_px))
            else:
                self.btn_freno.setText(BTN_FRENO_ON)
                self.btn_freno.setStyleSheet(self._btn_style_3d(ORANGE, ORANGE_DARK, btn_px))
        if self.btn_frizione:
            if clutch_on:
                self.btn_frizione.setText(BTN_FRIZ_ON)
                self.btn_frizione.setStyleSheet(self._btn_style_3d(GREEN, GREEN_DARK, btn_px))
            else:
                self.btn_frizione.setText(BTN_FRIZ_OFF)
                self.btn_frizione.setStyleSheet(self._btn_style_3d(ORANGE, ORANGE_DARK, btn_px))
        if self.btn_testa:
            self.btn_testa.setText(BTN_TESTA)
            self.btn_testa.setStyleSheet(self._btn_style_3d(GREEN if brake_on else ORANGE, GREEN_DARK if brake_on else ORANGE_DARK, btn_px))

        # Garantisce larghezze stabili anche dopo cambi testo/stato
        self._sync_button_widths()

    # ---------------- Build UI ----------------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8); root.setSpacing(6)

        # Header con callback: Reset -> normalize; Home -> nav Home
        root.addWidget(Header(self.appwin, "MANUALE", mode="default", on_home=self._nav_home, on_reset=self._reset_and_home))

        body = QHBoxLayout(); body.setSpacing(8); root.addLayout(body, 1)

        # Sinistra: QUOTA + pulsanti
        left = QFrame(); body.addWidget(left, 2)
        ll = QVBoxLayout(left); ll.setContentsMargins(6, 6, 6, 6); ll.setSpacing(16)

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

        # Pulsanti: FRENO / FRIZIONE / TESTA (nessuna min-height rigida)
        btn_box = QFrame(); bl = QHBoxLayout(btn_box); bl.setContentsMargins(12,12,12,12); bl.setSpacing(24); bl.setAlignment(Qt.AlignCenter)
        self.btn_freno = QPushButton(BTN_FRENO_ON); self.btn_freno.clicked.connect(self._toggle_freno)
        self.btn_frizione = QPushButton(BTN_FRIZ_ON); self.btn_frizione.clicked.connect(self._toggle_frizione)
        self.btn_testa = QPushButton(BTN_TESTA); self.btn_testa.clicked.connect(self._press_testa)
        bl.addWidget(self.btn_freno, 0, Qt.AlignCenter)
        bl.addWidget(self.btn_frizione, 0, Qt.AlignCenter)
        bl.addWidget(self.btn_testa, 0, Qt.AlignCenter)
        ll.addWidget(btn_box, 2, alignment=Qt.AlignCenter)

        # Destra: Status + placeholder FQ
        right = QFrame(); right.setFixedWidth(PANEL_W + 12); body.addWidget(right, 0)
        rl = QVBoxLayout(right); rl.setContentsMargins(6,6,6,6); rl.setSpacing(8)

        status_wrap = QFrame()
        status_wrap.setFixedWidth(PANEL_W)   # solo larghezza fissa, niente altezza fissa
        swl = QVBoxLayout(status_wrap); swl.setContentsMargins(0,0,0,0)
        self.status = StatusPanel(self.machine, "STATO", status_wrap); swl.addWidget(self.status)
        rl.addWidget(status_wrap, 0, alignment=Qt.AlignLeft | Qt.AlignTop)

        fq_placeholder = QFrame()
        fq_placeholder.setFixedWidth(PANEL_W)
        fq_placeholder.setFrameShape(QFrame.StyledPanel)
        fq_placeholder.setFixedHeight(FQ_H)
        rl.addWidget(fq_placeholder, 0, alignment=Qt.AlignLeft)
        rl.addStretch(1)

        # Stile iniziale, larghezze stabili
        self._style_buttons_by_state()
        self._sync_button_widths()

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
        self._style_buttons_by_state(); self._update_quota_label()
        if self.status: self.status.refresh()

    def _tick(self):
        self._update_quota_label()
        if self.status: self.status.refresh()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._apply_scaling()
        self._style_buttons_by_state()

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
