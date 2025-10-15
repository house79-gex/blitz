from __future__ import annotations
from typing import Optional, Dict, Any, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox
)

# Header opzionale (se il tuo progetto lo include)
try:
    from ui_qt.widgets.header import Header
except Exception:
    Header = None  # fallback

# Store tipologie su SQLite (se presente)
def _try_load_typologies_store():
    try:
        from ui_qt.services.typologies_store import TypologiesStore, default_db_path
        return TypologiesStore(str(default_db_path()))
    except Exception:
        return None

class QuoteVaniPage(QFrame):
    """
    Scheletro 'Quote vani luce'
    - Pulsante Home
    - Campi H / L
    - Selettore tipologia (dal DB tipologie, se disponibile)
    - Tabella placeholder 'distinta'
    Nota: 'Genera distinta' è uno stub (da implementare nei prossimi step).
    """
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self._store = _try_load_typologies_store()
        self._build()

    def _build(self):
        self.setStyleSheet("QFrame { border: 1px solid #3b4b5a; border-radius: 6px; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # Header
        if Header:
            root.addWidget(Header(self.appwin, "QUOTE VANI LUCE"), 0)
        else:
            title = QLabel("QUOTE VANI LUCE")
            title.setStyleSheet("font-size:18px; font-weight:700;")
            root.addWidget(title, 0)

        # Barra comandi
        top = QHBoxLayout()
        btn_home = QPushButton("Home")
        btn_home.setToolTip("Torna alla Home")
        btn_home.clicked.connect(self._go_home)
        top.addWidget(btn_home)

        top.addSpacing(10)
        top.addWidget(QLabel("H (mm):"))
        self.ed_h = QLineEdit()
        self.ed_h.setPlaceholderText("Altezza")
        self.ed_h.setFixedWidth(110)
        top.addWidget(self.ed_h)

        top.addWidget(QLabel("L (mm):"))
        self.ed_l = QLineEdit()
        self.ed_l.setPlaceholderText("Larghezza")
        self.ed_l.setFixedWidth(110)
        top.addWidget(self.ed_l)

        top.addSpacing(10)
        top.addWidget(QLabel("Tipologia:"))
        self.cmb_typ = QComboBox()
        self.cmb_typ.setMinimumWidth(280)
        self._reload_typologies()
        top.addWidget(self.cmb_typ, 1)

        self.btn_gen = QPushButton("Genera distinta")
        self.btn_gen.setEnabled(False)  # stub
        self.btn_gen.setToolTip("Stub: calcolo distinta verrà implementato qui")
        self.btn_gen.clicked.connect(self._generate_stub)
        top.addWidget(self.btn_gen)

        root.addLayout(top)

        # Tabella placeholder
        self.tbl = QTableWidget(0, 6)
        self.tbl.setHorizontalHeaderLabels(["ID", "Ruolo/Nome", "Profilo", "Q.tà", "Lunghezza (mm)", "Angoli (°)"])
        hdr = self.tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.Stretch)
        root.addWidget(self.tbl, 1)

        note = QLabel("Nota: questa è una pagina segnaposto. La logica di 'Genera distinta' sarà implementata qui.")
        note.setStyleSheet("color:#7f8c8d;")
        root.addWidget(note, 0)

    def _reload_typologies(self):
        self.cmb_typ.clear()
        if not self._store:
            self.cmb_typ.addItem("— DB tipologie non disponibile —", None)
            return
        try:
            rows = self._store.list_typologies()  # type: ignore
            if not rows:
                self.cmb_typ.addItem("— Nessuna tipologia nel DB —", None)
            else:
                for r in rows:
                    self.cmb_typ.addItem(str(r.get("name") or f"ID {r.get('id')}"), int(r.get("id")))
        except Exception:
            self.cmb_typ.addItem("— Errore lettura DB tipologie —", None)

    def _generate_stub(self):
        QMessageBox.information(self, "Genera distinta", "Stub: la generazione della distinta sarà implementata qui.")

    def _go_home(self):
        try:
            if hasattr(self.appwin, "show_page"):
                self.appwin.show_page("home")
            elif hasattr(self.appwin, "go_home"):
                self.appwin.go_home()
        except Exception:
            pass

    def on_show(self):
        # refresh tipologie ogni volta che apri la pagina
        self._reload_typologies()
