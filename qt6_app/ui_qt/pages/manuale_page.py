from PySide6.QtWidgets import QWidget, QVBoxLayout, QFrame
from PySide6.QtCore import QTimer
from ui_qt.widgets.header import Header
from ui_qt.widgets.status_panel import StatusPanel


class ManualePage(QWidget):
    """
    Modalità MANUALE minimal:
    - Solo StatusPanel (feedback visivo: include quota encoder, stato freno/frizione, EMG, homing, ecc.).
    - Abilita la lettura del pulsante hardware TESTA solo qui.
      Il pulsante alterna:
        * pressione/impulso 1: blocca freno + inserisce frizione
        * pressione/impulso 2: sblocca freno + disinserisce frizione
      per permettere lo spostamento manuale della testa.
    """
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self.machine = appwin.machine
        self.status: StatusPanel | None = None
        self._poll: QTimer | None = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(8, 8, 8, 8); root.setSpacing(6)
        root.addWidget(Header(self.appwin, "MANUALE"))

        body = QFrame(); root.addWidget(body, 1)
        r = QVBoxLayout(body); r.setContentsMargins(6, 6, 6, 6)

        # Solo StatusPanel
        self.status = StatusPanel(self.machine, "STATO", body)
        r.addWidget(self.status, 1)

    def on_show(self):
        # Abilita la lettura del pulsante TESTA SOLO in questo menu
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
        # Il MainWindow disabilita già il pulsante TESTA quando si cambia pagina.
        if self._poll is not None:
            try: self._poll.stop()
            except Exception: pass
            self._poll = None
        super().hideEvent(ev)
