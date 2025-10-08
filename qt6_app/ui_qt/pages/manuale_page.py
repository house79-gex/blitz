from typing import Optional

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

        self.status: Optional[StatusPanel] = None
        self.lbl_quota_val: Optional[QLabel] = None
        self.btn_freno: Optional[QPushButton] = None
        self.btn_frizione: Optional[QPushButton] = None
        self.btn_testa: Optional[QPushButton] = None  # NUOVO: pulsante TESTA

        self._poll: Optional[QTimer] = None
        self._sim_mm: float = 0.0
        self._sim_dir: float = +1.0

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
        brake_on = bool(getattr(self.machine, "brake_active", False) or getattr(self.machine, "brake_on", False) or getattr(self.machine, "freno_bloccato", False))
        clutch_on = bool(getattr(self.machine, "clutch_active", True) or getattr(self.machine, "clutch_on", False) or getattr(self.machine, "frizione_inserita", True))
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
        if self.btn_testa:
            # Il testo resta fisso; colore in base al freno (bloccato=verde, sbloccato=arancio)
            self.btn_testa.setStyleSheet(self._btn_style_3d(GREEN if brake_on else ORANGE, GREEN_DARK if brake_on else ORANGE_DARK))
            self.btn_testa.setMinimumHeight(BTN_MIN_H)

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

        lbl_quota = QLabel("Quota"); lbl_quota.setStyleSheet(f"font-weight:900; font-size:{int(QUOTA_FONT_PX*0.35)}px; color:{LABEL_COLOR};")
        qh.addWidget(lbl_quota, 0, Qt.AlignVCenter)

        self.lbl_quota_val = QLabel("—")
        self.lbl_quota_val.setStyleSheet(f"font-family:Consolas; font-weight:900; font-size:{QUOTA_FONT_PX}px; color:{QUOTA_COLOR};")
        self.lbl_quota_val.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding); self.lbl_quota_val.setAlignment(Qt.AlignCenter)
        qh.addWidget(self.lbl_quota_val, 0, Qt.AlignVCenter)

        lbl_mm = QLabel("mm"); lbl_mm.setStyleSheet(f"font-weight:900; font-size:{int(QUOTA_FONT_PX*0.35)}px; color:{LABEL_COLOR};")
        qh.addWidget(lbl_mm, 0, Qt.AlignVCenter)

        ll.addWidget(quota_frame, 3, alignment=Qt.AlignCenter)

        # Pulsanti: FRENO / FRIZIONE / TESTA
        btn_box = QFrame(); bl = QHBoxLayout(btn_box); bl.setContentsMargins(12,12,12,12); bl.setSpacing(24); bl.setAlignment(Qt.AlignCenter)
        self.btn_freno = QPushButton("BLOCCA FRENO"); self.btn_freno.clicked.connect(self._toggle_freno)
        self.btn_frizione = QPushButton("INSERISCI FRIZIONE"); self.btn_frizione.clicked.connect(self._toggle_frizione)
        self.btn_testa = QPushButton("TESTA"); self.btn_testa.clicked.connect(self._press_testa)
        bl.addWidget(self.btn_freno, 0, Qt.AlignCenter)
        bl.addWidget(self.btn_frizione, 0, Qt.AlignCenter)
        bl.addWidget(self.btn_testa, 0, Qt.AlignCenter)
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
        # Forza stato desiderato provando API robuste
        want = not bool(getattr(self.machine, "brake_active", False) or getattr(self.machine, "brake_on", False) or getattr(self.machine, "freno_bloccato", False))
        if hasattr(self.machine, "set_brake") and callable(getattr(self.machine, "set_brake")):
            try: self.machine.set_brake(want)
            except Exception: pass
        else:
            cur = bool(getattr(self.machine, "brake_active", False))
            if hasattr(self.machine, "toggle_brake") and callable(getattr(self.machine, "toggle_brake")):
                try:
                    if cur != want: self.machine.toggle_brake()
                except Exception: pass
            else:
                # fallback su attributi
                for attr in ("brake_active", "brake_on", "freno_bloccato"):
                    if hasattr(self.machine, attr):
                        try: setattr(self.machine, attr, bool(want)); break
                        except Exception: pass
        self._style_buttons_by_state()
        if self.status: self.status.refresh()

    def _toggle_frizione(self):
        want = not bool(getattr(self.machine, "clutch_active", True) or getattr(self.machine, "clutch_on", False) or getattr(self.machine, "frizione_inserita", True))
        # In Manuale devi poterla inserire/disinserire sempre (salvo emergenza/posizionamento)
        if hasattr(self.machine, "set_clutch") and callable(getattr(self.machine, "set_clutch")):
            try: self.machine.set_clutch(want)
            except Exception: pass
        else:
            cur = bool(getattr(self.machine, "clutch_active", True))
            if hasattr(self.machine, "toggle_clutch") and callable(getattr(self.machine, "toggle_clutch")):
                try:
                    if cur != want: self.machine.toggle_clutch()
                except Exception: pass
            else:
                for attr in ("clutch_active", "clutch_on", "frizione_inserita"):
                    if hasattr(self.machine, attr):
                        try: setattr(self.machine, attr, bool(want)); break
                        except Exception: pass
        self._style_buttons_by_state()
        if self.status: self.status.refresh()

    def _press_testa(self):
        """
        Simula il pulsante hardware TESTA: blocco/sblocco simultaneo freno+frizione.
        Usa external_head_button_press() se disponibile, altrimenti applica una logica equivalente.
        """
        handled = False
        if hasattr(self.machine, "external_head_button_press") and callable(getattr(self.machine, "external_head_button_press")):
            try:
                handled = bool(self.machine.external_head_button_press())
            except Exception:
                handled = False

        if not handled:
            # fallback: alterna insieme freno e frizione
            brake_on = bool(getattr(self.machine, "brake_active", False))
            target_locked = not brake_on
            try:
                setattr(self.machine, "brake_active", target_locked)
                setattr(self.machine, "clutch_active", target_locked)
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
        # Preferisci encoder_position, poi position_current, altrimenti sim locale
        for name in ("encoder_position", "position_current"):
            if hasattr(self.machine, name):
                try:
                    val = float(getattr(self.machine, name))
                    if self.lbl_quota_val:
                        self.lbl_quota_val.setText(self._fmt_mm(val))
                    return
                except Exception:
                    pass

        # Simulazione locale: solo con freno sbloccato e frizione disinserita
        brake_on = bool(getattr(self.machine, "brake_active", False))
        clutch_on = bool(getattr(self.machine, "clutch_active", True))
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
        # Abilita simulazione pulsante TESTA solo in Manuale
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
        # Disabilita simulazione TESTA e reinserisce frizione in uscita
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
