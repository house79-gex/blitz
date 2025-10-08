from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton, QSizePolicy
from PySide6.QtCore import Qt, QTimer
from ui_qt.widgets.header import Header
from ui_qt.widgets.status_panel import StatusPanel

# Uniforma l'impronta del pannello stato a quella di Semi-Auto/Automatico
STATUS_PANEL_HEIGHT = 220


class ManualePage(QWidget):
    """
    Modalità MANUALE:
    - Visualizza quota letta dall'encoder (simulata se non disponibile), in grande.
    - Pulsanti grandi: BLOCCA/SBLOCCA FRENO e INSERISCI/DISINSERISCI FRIZIONE.
    - StatusPanel a destra con dimensione uniformata a Semi-Auto.
    - Abilita la lettura del pulsante hardware TESTA solo qui (toggle freno/frizione a impulsi).
    - All'uscita dal menù manuale la frizione viene sempre inserita e il pulsante TESTA disabilitato.
    """
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self.machine = appwin.machine

        # UI refs
        self.status: StatusPanel | None = None
        self.lbl_quota: QLabel | None = None
        self.btn_freno: QPushButton | None = None
        self.btn_frizione: QPushButton | None = None

        # Polling timer
        self._poll: QTimer | None = None

        # Sim encoder (se non disponibile dall'API)
        self._sim_mm: float = 0.0
        self._sim_dir: float = +1.0

        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        root.addWidget(Header(self.appwin, "MANUALE"))

        body = QHBoxLayout()
        body.setSpacing(8)
        root.addLayout(body, 1)

        # ---------------- Sinistra: QUOTA + PULSANTI (area ampia) ----------------
        left = QFrame()
        body.addWidget(left, 2)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(6, 6, 6, 6)
        ll.setSpacing(12)

        # Quota encoder: titolo + valore molto grande che cresce nello spazio
        quota_box = QFrame()
        ql = QVBoxLayout(quota_box)
        ql.setContentsMargins(4, 4, 4, 4)
        title = QLabel("QUOTA INTERNA (mm)")
        title.setStyleSheet("font-weight:700; font-size: 20px;")
        ql.addWidget(title, 0, alignment=Qt.AlignLeft)

        self.lbl_quota = QLabel("—")
        # Triplica/ingrandisce: font molto grande e usa lo spazio disponibile
        self.lbl_quota.setStyleSheet(
            "font-family: Consolas; font-weight: 800; font-size: 84px; color: #16a085;"
        )
        self.lbl_quota.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.lbl_quota.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        ql.addWidget(self.lbl_quota, 1)
        ll.addWidget(quota_box, 3)  # dà più peso al riquadro quota

        # Pulsanti Freno/Frizione: molto grandi
        btn_box = QFrame()
        bl = QHBoxLayout(btn_box)
        bl.setContentsMargins(4, 4, 4, 4)
        bl.setSpacing(12)

        self.btn_freno = QPushButton("BLOCCA FRENO")
        self.btn_freno.clicked.connect(self._toggle_freno)
        self.btn_freno.setMinimumHeight(96)
        self.btn_freno.setStyleSheet(
            "font-size: 28px; font-weight: 700; padding: 14px 24px;"
        )

        self.btn_frizione = QPushButton("INSERISCI FRIZIONE")
        self.btn_frizione.clicked.connect(self._toggle_frizione)
        self.btn_frizione.setMinimumHeight(96)
        self.btn_frizione.setStyleSheet(
            "font-size: 28px; font-weight: 700; padding: 14px 24px;"
        )

        bl.addWidget(self.btn_freno, 1)
        bl.addWidget(self.btn_frizione, 1)
        ll.addWidget(btn_box, 1)

        # ---------------- Destra: STATUS PANEL (dimensioni uniformate) ----------------
        right = QFrame()
        body.addWidget(right, 1)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(6, 6, 6, 6)
        rl.setSpacing(8)

        self.status = StatusPanel(self.machine, "STATO", right)
        self.status.setMinimumHeight(STATUS_PANEL_HEIGHT)
        self.status.setMaximumHeight(STATUS_PANEL_HEIGHT)
        rl.addWidget(self.status, 0)

        rl.addStretch(1)

        # Imposta testi iniziali dei pulsanti
        self._refresh_buttons()

    # ---------------- Helpers stato/pulsanti ----------------
    def _refresh_buttons(self):
        try:
            brake_on = bool(getattr(self.machine, "brake_active", False))
            clutch_on = bool(getattr(self.machine, "clutch_active", True))
        except Exception:
            brake_on = False
            clutch_on = True

        if self.btn_freno:
            self.btn_freno.setText("SBLOCCA FRENO" if brake_on else "BLOCCA FRENO")
        if self.btn_frizione:
            self.btn_frizione.setText("DISINSERISCI FRIZIONE" if clutch_on else "INSERISCI FRIZIONE")

    def _set_brake(self, want_active: bool) -> bool:
        m = self.machine
        try:
            if hasattr(m, "set_brake"):
                m.set_brake(want_active); return True
            if hasattr(m, "toggle_brake"):
                cur = bool(getattr(m, "brake_active", False))
                if cur != want_active:
                    return bool(m.toggle_brake())
                return True
            if hasattr(m, "brake_active"):
                setattr(m, "brake_active", bool(want_active)); return True
        except Exception:
            pass
        return False

    def _set_clutch(self, want_active: bool) -> bool:
        m = self.machine
        try:
            if hasattr(m, "set_clutch"):
                m.set_clutch(want_active); return True
            if hasattr(m, "toggle_clutch"):
                cur = bool(getattr(m, "clutch_active", True))
                if cur != want_active:
                    return bool(m.toggle_clutch())
                return True
            if hasattr(m, "clutch_active"):
                setattr(m, "clutch_active", bool(want_active)); return True
        except Exception:
            pass
        return False

    def _toggle_freno(self):
        cur = bool(getattr(self.machine, "brake_active", False))
        self._set_brake(not cur)
        self._refresh_buttons()

    def _toggle_frizione(self):
        # La frizione si controlla solo qui (Manuale)
        cur = bool(getattr(self.machine, "clutch_active", True))
        self._set_clutch(not cur)
        self._refresh_buttons()

    # ---------------- Encoder display ----------------
    @staticmethod
    def _fmt_mm(v) -> str:
        try:
            return f"{float(v):.2f}"
        except Exception:
            return "—"

    def _update_quota_label(self):
        # Preferisci il valore reale se disponibile
        if hasattr(self.machine, "encoder_position"):
            try:
                val = float(getattr(self.machine, "encoder_position"))
                if self.lbl_quota:
                    self.lbl_quota.setText(self._fmt_mm(val))
                return
            except Exception:
                pass

        # Simulazione se non disponibile:
        # Si muove solo quando il freno è sbloccato e la frizione disinserita (spostamento manuale)
        brake_on = bool(getattr(self.machine, "brake_active", False))
        clutch_on = bool(getattr(self.machine, "clutch_active", True))
        manual_move_ok = (not brake_on) and (not clutch_on)

        if manual_move_ok:
            if not (0.0 <= self._sim_mm <= 4000.0):
                self._sim_mm = max(0.0, min(4000.0, self._sim_mm))
                self._sim_dir = -self._sim_dir
            self._sim_mm += self._sim_dir * 1.5  # passo più grande per visibilità su font grande
            if self._sim_mm >= 4000.0:
                self._sim_mm = 4000.0; self._sim_dir = -1.0
            elif self._sim_mm <= 0.0:
                self._sim_mm = 0.0; self._sim_dir = +1.0

        if self.lbl_quota:
            self.lbl_quota.setText(self._fmt_mm(self._sim_mm))

    # ---------------- Lifecycle ----------------
    def on_show(self):
        # Abilita lettura pulsante TESTA SOLO in Manuale
        try:
            if hasattr(self.machine, "set_head_button_input_enabled"):
                self.machine.set_head_button_input_enabled(True)
        except Exception:
            pass

        # Avvia polling (quota + status + pulsanti)
        if self._poll is None:
            self._poll = QTimer(self)
            self._poll.timeout.connect(self._tick)
            self._poll.start(200)

        # Sync iniziale UI
        self._refresh_buttons()
        self._update_quota_label()
        if self.status:
            self.status.refresh()

    def _tick(self):
        self._update_quota_label()
        self._refresh_buttons()
        if self.status:
            self.status.refresh()

    def hideEvent(self, ev):
        # Disabilita pulsante TESTA all'uscita
        try:
            if hasattr(self.machine, "set_head_button_input_enabled"):
                self.machine.set_head_button_input_enabled(False)
        except Exception:
            pass

        # Reinserisce sempre la frizione all'uscita dal menù manuale
        try:
            if hasattr(self.machine, "normalize_after_manual"):
                self.machine.normalize_after_manual()
            else:
                if hasattr(self.machine, "clutch_active"):
                    setattr(self.machine, "clutch_active", True)
        except Exception:
            pass

        # Ferma polling
        if self._poll is not None:
            try:
                self._poll.stop()
            except Exception:
                pass
            self._poll = None

        super().hideEvent(ev)
