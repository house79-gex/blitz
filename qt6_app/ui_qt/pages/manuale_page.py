from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton, QSizePolicy
from PySide6.QtCore import Qt, QTimer
from ui_qt.widgets.header import Header
from ui_qt.widgets.status_panel import StatusPanel

# Dimensioni identiche a Semi-Automatico/Automatico per lo StatusPanel
PANEL_W = 420      # larghezza StatusPanel
PANEL_H = 220      # altezza StatusPanel
FQ_H = 100         # altezza riquadro “Fuori Quota” (placeholder in Manuale)

# Dimensioni raddoppiate per quota/pulsanti
QUOTA_FONT_PX = 168
BTN_MIN_H = 192
BTN_FONT_PX = 56

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

        self.status: StatusPanel | None = None
        self.lbl_quota_val: QLabel | None = None
        self.btn_freno: QPushButton | None = None
        self.btn_frizione: QPushButton | None = None

        self._poll: QTimer | None = None
        self._sim_mm: float = 0.0
        self._sim_dir: float = +1.0

        self._build()

    # ---------------- Helpers nav/reset ----------------
    def _nav_home(self):
        # Navigazione home robusta
        for attr in ("go_home", "show_home", "navigate_home", "home"):
            if hasattr(self.appwin, attr) and callable(getattr(self.appwin, attr)):
                try:
                    getattr(self.appwin, attr)(); return
                except Exception:
                    pass
        if hasattr(self.appwin, "nav") and hasattr(self.appwin.nav, "go_home") and callable(self.appwin.nav.go_home):
            try: self.appwin.nav.go_home(); return
            except Exception: pass

    def _reset_and_home(self):
        # Reset pagina Manuale: reinserisci frizione, arresta polling
        try:
            if hasattr(self.machine, "normalize_after_manual"):
                self.machine.normalize_after_manual()
            elif hasattr(self.machine, "clutch_active"):
                setattr(self.machine, "clutch_active", True)
        except Exception:
            pass
        if self._poll is not None:
            try: self._poll.stop()
            except Exception: pass
            self._poll = None

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
    def _btn_style_3d(self, base: str, dark: str) -> str:
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
                font-size: {BTN_FONT_PX}px;
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

    def _style_buttons_by_state(self):
        brake_on = bool(getattr(self.machine, "brake_active", False))
        clutch_on = bool(getattr(self.machine, "clutch_active", True))
        if self.btn_freno:
            if brake_on:
                self.btn_freno.setText("SBLOCCA FRENO")
                self.btn_freno.setStyleSheet(self._btn_style_3d(GREEN, GREEN_DARK))
            else:
                self.btn_freno.setText("BLOCCA FRENO")
                self.btn_freno.setStyleSheet(self._btn_style_3d(ORANGE, ORANGE_DARK))
            self.btn_freno.setMinimumHeight(BTN_MIN_H)
        if self.btn_frizione:
            if clutch_on:
                self.btn_frizione.setText("DISINSERISCI FRIZIONE")
                self.btn_frizione.setStyleSheet(self._btn_style_3d(GREEN, GREEN_DARK))
            else:
                self.btn_frizione.setText("INSERISCI FRIZIONE")
                self.btn_frizione.setStyleSheet(self._btn_style_3d(ORANGE, ORANGE_DARK))
            self.btn_frizione.setMinimumHeight(BTN_MIN_H)

    # ---------------- Build UI ----------------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8); root.setSpacing(6)

        # Header con callback: Reset -> normalize + Home; Home -> nav Home
        root.addWidget(Header(self.appwin, "MANUALE", mode="default", on_home=self._nav_home, on_reset=self._reset_and_home))

        body = QHBoxLayout(); body.setSpacing(8); root.addLayout(body, 1)

        # Sinistra: QUOTA + pulsanti
        left = QFrame(); body.addWidget(left, 2)
        ll = QVBoxLayout(left); ll.setContentsMargins(6, 6, 6, 6); ll.setSpacing(16)

        quota_frame = QFrame(); quota_frame.setStyleSheet(self._frame_style())
        qh = QHBoxLayout(quota_frame); qh.setContentsMargins(18, 18, 18, 18); qh.setSpacing(20); qh.setAlignment(Qt.AlignCenter)

        lbl_quota = QLabel("Quota"); lbl_quota.setStyleSheet(f"font-weight:900; font-size:{int(QUOTA_FONT_PX*0.35)}px; color:{LABEL_COLOR};")
        qh.addWidget(lbl_quota, 0, Qt.AlignVCenter)

        self.lbl_quota_val = QLabel("—")
        self.lbl_quota_val.setStyleSheet(f"font-family:Consolas; font-weight:900; font-size:{QUOTA_FONT_PX}px; color:{QUOTA_COLOR};")
        self.lbl_quota_val.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding); self.lbl_quota_val.setAlignment(Qt.AlignCenter)
        qh.addWidget(self.lbl_quota_val, 0, Qt.AlignVCenter)

        lbl_mm = QLabel("mm"); lbl_mm.setStyleSheet(f"font-weight:900; font-size:{int(QUOTA_FONT_PX*0.35)}px; color:{LABEL_COLOR};")
        qh.addWidget(lbl_mm, 0, Qt.AlignVCenter)

        ll.addWidget(quota_frame, 3, alignment=Qt.AlignCenter)

        btn_box = QFrame(); bl = QHBoxLayout(btn_box); bl.setContentsMargins(12,12,12,12); bl.setSpacing(24); bl.setAlignment(Qt.AlignCenter)
        self.btn_freno = QPushButton("BLOCCA FRENO"); self.btn_freno.clicked.connect(self._toggle_freno)
        self.btn_frizione = QPushButton("INSERISCI FRIZIONE"); self.btn_frizione.clicked.connect(self._toggle_frizione)
        bl.addWidget(self.btn_freno, 0, Qt.AlignCenter); bl.addWidget(self.btn_frizione, 0, Qt.AlignCenter)
        ll.addWidget(btn_box, 2, alignment=Qt.AlignCenter)

        # Destra: Status + placeholder FQ
        right = QFrame(); right.setFixedWidth(PANEL_W + 12); body.addWidget(right, 0)
        rl = QVBoxLayout(right); rl.setContentsMargins(6,6,6,6); rl.setSpacing(8)

        status_wrap = QFrame(); status_wrap.setFixedSize(PANEL_W, PANEL_H)
        swl = QVBoxLayout(status_wrap); swl.setContentsMargins(0,0,0,0)
        self.status = StatusPanel(self.machine, "STATO", status_wrap); swl.addWidget(self.status)
        rl.addWidget(status_wrap, 0, alignment=Qt.AlignLeft | Qt.AlignTop)

        fq_placeholder = QFrame(); fq_placeholder.setFixedSize(PANEL_W, FQ_H); fq_placeholder.setFrameShape(QFrame.StyledPanel)
        rl.addWidget(fq_placeholder, 0, alignment=Qt.AlignLeft)
        rl.addStretch(1)

        self._style_buttons_by_state()

    # ---------------- Button logic ----------------
    def _toggle_freno(self):
        cur = bool(getattr(self.machine, "brake_active", False))
        self._set_brake(not cur); self._style_buttons_by_state()
    def _toggle_frizione(self):
        cur = bool(getattr(self.machine, "clutch_active", True))
        self._set_clutch(not cur); self._style_buttons_by_state()
    def _set_brake(self, want_active: bool) -> bool:
        m = self.machine
        try:
            if hasattr(m, "set_brake"): m.set_brake(want_active); return True
            if hasattr(m, "toggle_brake"):
                cur = bool(getattr(m, "brake_active", False))
                if cur != want_active: return bool(m.toggle_brake())
                return True
            if hasattr(m, "brake_active"): setattr(m, "brake_active", bool(want_active)); return True
        except Exception: pass
        return False
    def _set_clutch(self, want_active: bool) -> bool:
        m = self.machine
        try:
            if hasattr(m, "set_clutch"): m.set_clutch(want_active); return True
            if hasattr(m, "toggle_clutch"):
                cur = bool(getattr(m, "clutch_active", True))
                if cur != want_active: return bool(m.toggle_clutch())
                return True
            if hasattr(m, "clutch_active"): setattr(m, "clutch_active", bool(want_active)); return True
        except Exception: pass
        return False

    # ---------------- Encoder display ----------------
    @staticmethod
    def _fmt_mm(v) -> str:
        try: return f"{float(v):.2f}"
        except Exception: return "—"
    def _update_quota_label(self):
        if hasattr(self.machine, "encoder_position"):
            try:
                val = float(getattr(self.machine, "encoder_position"))
                if self.lbl_quota_val: self.lbl_quota_val.setText(self._fmt_mm(val)); return
            except Exception: pass
        brake_on = bool(getattr(self.machine, "brake_active", False))
        clutch_on = bool(getattr(self.machine, "clutch_active", True))
        manual_move_ok = (not brake_on) and (not clutch_on)
        if manual_move_ok:
            if not (0.0 <= self._sim_mm <= 4000.0):
                self._sim_mm = max(0.0, min(4000.0, self._sim_mm)); self._sim_dir = -self._sim_dir
            self._sim_mm += self._sim_dir * 1.5
            if self._sim_mm >= 4000.0: self._sim_mm = 4000.0; self._sim_dir = -1.0
            elif self._sim_mm <= 0.0: self._sim_mm = 0.0; self._sim_dir = +1.0
        if self.lbl_quota_val: self.lbl_quota_val.setText(self._fmt_mm(self._sim_mm))

    # ---------------- Lifecycle ----------------
    def on_show(self):
        try:
            if hasattr(self.machine, "set_head_button_input_enabled"): self.machine.set_head_button_input_enabled(True)
        except Exception: pass
        if self._poll is None:
            self._poll = QTimer(self); self._poll.timeout.connect(self._tick); self._poll.start(200)
        self._style_buttons_by_state(); self._update_quota_label()
        if self.status: self.status.refresh()

    def _tick(self):
        self._update_quota_label(); self._style_buttons_by_state()
        if self.status: self.status.refresh()

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
