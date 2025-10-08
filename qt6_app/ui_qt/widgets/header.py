from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QFrame


class Header(QWidget):
    """
    Header generico per le pagine:
    - Home a sinistra
    - Titolo centrato e più grande
    - Reset a destra (sostituisce 'Azzera'); alla pressione effettua il reset (se definito)
      e torna automaticamente alla Home.
    - Segnali: home_clicked, reset_clicked
    """
    home_clicked = Signal()
    reset_clicked = Signal()

    def __init__(self, appwin, title: str, on_reset: Optional[Callable[[], None]] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.appwin = appwin
        self._on_reset_cb = on_reset

        self._build(title)

    def _build(self, title: str):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        # Contenitori laterali per aiutare il centraggio del titolo
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

        # Pulsante Home (sinistra)
        self.btn_home = QPushButton("Home", left_bar)
        self.btn_home.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_home.clicked.connect(self._go_home)
        left_bar_l.addWidget(self.btn_home)

        # Titolo centrato e più grande
        self.lbl_title = QLabel(title, center)
        self.lbl_title.setAlignment(Qt.AlignCenter)
        # "un po' più grande": aumentiamo il font con peso
        self.lbl_title.setStyleSheet("font-size: 26px; font-weight: 800;")
        self.lbl_title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        center_l.addWidget(self.lbl_title, 1, Qt.AlignCenter)

        # Pulsante Reset (destra) — sostituisce "Azzera"
        self.btn_reset = QPushButton("Reset", right_bar)
        self.btn_reset.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_reset.clicked.connect(self._do_reset_and_home)
        right_bar_l.addWidget(self.btn_reset)

        # Per mantenere il titolo perfettamente centrato, rendiamo i due bottoni simmetrici
        # forzando la stessa larghezza minima (basata sulla più ampia tra le due etichette)
        self._sync_buttons_width()

    def _sync_buttons_width(self):
        # Determina la larghezza suggerita e imposta una larghezza minima comune
        w = max(self.btn_home.sizeHint().width(), self.btn_reset.sizeHint().width())
        self.btn_home.setMinimumWidth(w)
        self.btn_reset.setMinimumWidth(w)

    def setTitle(self, title: str):
        self.lbl_title.setText(title)

    # Navigazione Home robusta
    def _go_home(self):
        handled = False
        # Tenta metodi comuni nel MainWindow/app
        for attr in ("go_home", "show_home", "navigate_home", "home"):
            if hasattr(self.appwin, attr) and callable(getattr(self.appwin, attr)):
                try:
                    getattr(self.appwin, attr)()
                    handled = True
                    break
                except Exception:
                    pass
        # Tenta un oggetto nav con go_home
        if not handled and hasattr(self.appwin, "nav"):
            nav = getattr(self.appwin, "nav")
            if hasattr(nav, "go_home") and callable(nav.go_home):
                try:
                    nav.go_home()
                    handled = True
                except Exception:
                    pass
        # Se nessun handler, emetti segnale
        if not handled:
            self.home_clicked.emit()

    def _do_reset_and_home(self):
        # Emette comunque il segnale (utile per page-specific listeners)
        self.reset_clicked.emit()

        # Invoca callback reset (se fornita)
        try:
            if callable(self._on_reset_cb):
                self._on_reset_cb()
        except Exception:
            pass

        # In assenza di callback, prova metodi noti sull'app
        if self._on_reset_cb is None:
            for attr in ("reset_current_page", "reset_page", "reset_all", "reset"):
                if hasattr(self.appwin, attr) and callable(getattr(self.appwin, attr)):
                    try:
                        getattr(self.appwin, attr)()
                        break
                    except Exception:
                        pass

        # Dopo il reset, vai sempre alla Home
        self._go_home()
