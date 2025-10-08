from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton
from PySide6.QtCore import Qt, QTimer
from ui_qt.widgets.header import Header
from ui_qt.widgets.status_panel import StatusPanel


class ManualePage(QWidget):
    """
    Modalità MANUALE:
    - Visualizza quota letta dall'encoder (simulata se non disponibile).
    - Pulsanti: BLOCCA/SBLOCCA FRENO e INSERISCI/DISINSERISCI FRIZIONE.
    - Abilita la lettura del pulsante hardware TESTA solo qui (toggle freno/frizione a impulsi).
    - All'uscita dal menù manuale la frizione viene sempre inserita e il pulsante TESTA disabilitato.
    """
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self.machine = appwin.machine
        self.status: StatusPanel | None = None
        self._poll: QTimer | None = None

        # UI refs
        self.lbl_quota: QLabel | None = None
        self.btn_freno: QPushButton | None = None
        self.btn_frizione: QPushButton | None = None

        # simulazione encoder (se non presente in machine)
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

        # Sinistra: quota + pulsanti
        left = QFrame()
        body.addWidget(left, 1)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(6, 6, 6, 6)
        ll.setSpacing(10)

        # Quota encoder
        box_quota = QFrame()
        ql = QVBoxLayout(box_quota)
        title = QLabel("QUOTA INTERNA (mm)")
        title.setStyleSheet("font-weight:700;")
        ql.addWidget(title, 0, alignment=Qt.AlignLeft)
        self.lbl_quota = QLabel("—")
        self.lbl_quota.setStyleSheet("font-family: Consolas; font-weight: 800; font-size: 28px;")
        ql.addWidget(self.lbl_quota, 0, alignment=Qt.AlignLeft)
        ll.addWidget(box_quota)

        # Pulsanti freno/frizione
        box_btn = QFrame()
        bl = QHBoxLayout(box_btn)
        self.btn_freno = QPushButton("BLOCCA FRENO")
        self.btn_freno.clicked.connect(self._toggle_freno)
        self.btn_frizione = QPushButton("INSERISCI FRIZIONE")
        self.btn_frizione.clicked.connect(self._toggle_frizione)
        bl.addWidget(self.btn_freno)
        bl.addWidget(self.btn_frizione)
        bl.addStretch(1)
        ll.addWidget(box_btn)

        ll.addStretch(1)

        # Destra: StatusPanel
        right = QFrame()
        body.addWidget(right, 1)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(6, 6, 6, 6)
        self.status = StatusPanel(self.machine, "STATO", right)
        rl.addWidget(self.status, 1)

        # inizializza testo pulsanti in base allo stato corrente
        self._refresh_buttons()

    # --------- Helpers UI/state ----------
    def _refresh_buttons(self):
        try:
            brake_on = bool(getattr(self.machine, "brake_active", False))
            clutch_on = bool(getattr(self.machine, "clutch_active", True))
        except Exception:
            brake_on = False
            clutch_on = True

        # Freno
        if self.btn_freno:
            if brake_on:
                self.btn_freno.setText("SBLOCCA FRENO")
            else:
                self.btn_freno.setText("BLOCCA FRENO")

        # Frizione
        if self.btn_frizione:
            if clutch_on:
                self.btn_frizione.setText("DISINSERISCI FRIZIONE")
            else:
                self.btn_frizione.setText("INSERISCI FRIZIONE")

    def _set_brake(self, want_active: bool) -> bool:
        m = self.machine
        try:
            if hasattr(m, "set_brake"):
                m.set_brake(want_active)
                return True
            if hasattr(m, "toggle_brake"):
                cur = bool(getattr(m, "brake_active", False))
                if cur != want_active:
                    return bool(m.toggle_brake())
                return True
            # fallback su attributo
            if hasattr(m, "brake_active"):
                setattr(m, "brake_active", bool(want_active))
                return True
        except Exception:
            pass
        return False

    def _set_clutch(self, want_active: bool) -> bool:
        m = self.machine
        try:
            if hasattr(m, "set_clutch"):
                m.set_clutch(want_active)
                return True
            if hasattr(m, "toggle_clutch"):
                cur = bool(getattr(m, "clutch_active", True))
                if cur != want_active:
                    return bool(m.toggle_clutch())
                return True
            # fallback su attributo
            if hasattr(m, "clutch_active"):
                setattr(m, "clutch_active", bool(want_active))
                return True
        except Exception:
            pass
        return False

    def _toggle_freno(self):
        cur = bool(getattr(self.machine, "brake_active", False))
        self._set_brake(not cur)
        self._refresh_buttons()

    def _toggle_frizione(self):
        # Funziona solo qui: la pagina Manuale è l’unica a presentare il controllo
        cur = bool(getattr(self.machine, "clutch_active", True))
        self._set_clutch(not cur)
        self._refresh_buttons()

    # --------- Encoder display ----------
    @staticmethod
    def _fmt_mm(v) -> str:
        try:
            return f"{float(v):.2f}"
        except Exception:
            return "—"

    def _update_quota_label(self):
        # Usa valore reale se disponibile, altrimenti simula
        if hasattr(self.machine, "encoder_position"):
            try:
                val = float(getattr(self.machine, "encoder_position"))
                self.lbl_quota.setText(self._fmt_mm(val))
                return
            except Exception:
                pass

        # Simulazione: varia solo quando è consentito lo spostamento manuale
        # Regola: si può muovere quando freno è sbloccato e frizione disinserita
        brake_on = bool(getattr(self.machine, "brake_active", False))
        clutch_on = bool(getattr(self.machine, "clutch_active", True))
        manual_move_ok = (not brake_on) and (not clutch_on)

        if manual_move_ok:
            # saw fra 0 e 4000 mm
            if not (0.0 <= self._sim_mm <= 4000.0):
                self._sim_mm = max(0.0, min(4000.0, self._sim_mm))
                self._sim_dir = -self._sim_dir
            self._sim_mm += self._sim_dir * 0.5
            if self._sim_mm >= 4000.0:
                self._sim_mm = 4000.0; self._sim_dir = -1.0
            elif self._sim_mm <= 0.0:
                self._sim_mm = 0.0; self._sim_dir = +1.0
        # se non si può muovere, mostra ultimo valore simulato
        self.lbl_quota.setText(self._fmt_mm(self._sim_mm))

    # --------- Lifecycle ----------
    def on_show(self):
        # Abilita lettura pulsante TESTA SOLO in questo menu
        try:
            if hasattr(self.machine, "set_head_button_input_enabled"):
                self.machine.set_head_button_input_enabled(True)
        except Exception:
            pass

        # avvia polling per status e quota
        if self._poll is None:
            self._poll = QTimer(self)
            self._poll.timeout.connect(self._tick)
            self._poll.start(200)

        # sync iniziale UI con stato corrente
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
