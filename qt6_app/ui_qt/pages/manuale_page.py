from PySide6.QtWidgets import QWidget, QVBoxLayout, QFrame
from PySide6.QtCore import QTimer
from ui_qt.widgets.header import Header
from ui_qt.widgets.status_panel import StatusPanel


class ManualePage(QWidget):
    """
    Modalità MANUALE minimal:
    - Solo StatusPanel (mostra quota encoder e stati macchina).
    - Abilita la lettura del pulsante hardware TESTA solo qui (toggle freno/frizione a impulsi).
    - All'uscita dal menù manuale la frizione viene sempre inserita.
    """
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self.machine = appwin.machine
        self.status: StatusPanel | None = None
        self._poll: QTimer | None = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)
        root.addWidget(Header(self.appwin, "MANUALE"))

        body = QFrame()
        root.addWidget(body, 1)
        r = QVBoxLayout(body)
        r.setContentsMargins(6, 6, 6, 6)

        # Solo StatusPanel (feedback visivo: quota encoder, EMG, freno, frizione, homing, etc.)
        self.status = StatusPanel(self.machine, "STATO", body)
        r.addWidget(self.status, 1)

    def on_show(self):
        # Abilita lettura pulsante TESTA SOLO in questo menu
        try:
            if hasattr(self.machine, "set_head_button_input_enabled"):
                self.machine.set_head_button_input_enabled(True)
        except Exception:
            pass

        # Avvia polling pannello stato
        if self._poll is None:
            self._poll = QTimer(self)
            self._poll.timeout.connect(self._tick)
            self._poll.start(200)

    def _tick(self):
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
                # Deve impostare clutch_active = True (inserita)
                self.machine.normalize_after_manual()
            else:
                # Fallback: se esposto, forza direttamente lo stato frizione inserita
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
