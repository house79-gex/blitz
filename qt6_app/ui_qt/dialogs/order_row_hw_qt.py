from __future__ import annotations
from typing import Optional

from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QComboBox, QPushButton, QHBoxLayout

class OrderRowHardwareDialog(QDialog):
    """
    Seleziona una delle OPZIONI ferramenta definite nella tipologia (facoltativo).
    """
    def __init__(self, parent, store, typology_id: int):
        super().__init__(parent)
        self.setWindowTitle("Ferramenta – opzione")
        self.setModal(True)
        self.resize(420, 220)
        self.store = store
        self.typology_id = int(typology_id)
        self.hw_option_id: Optional[int] = None
        self._build()
        self._load()

    def _build(self):
        root = QVBoxLayout(self)
        root.addWidget(QLabel("Opzione (facoltativo)"))
        self.cmb = QComboBox()
        root.addWidget(self.cmb)
        row = QHBoxLayout()
        btn_skip = QPushButton("Nessuna"); btn_skip.clicked.connect(self._skip)
        btn_ok = QPushButton("OK"); btn_ok.clicked.connect(self._ok)
        btn_cancel = QPushButton("Annulla"); btn_cancel.clicked.connect(self.reject)
        row.addWidget(btn_skip); row.addStretch(1); row.addWidget(btn_cancel); row.addWidget(btn_ok)
        root.addLayout(row)

    def _load(self):
        self.cmb.clear()
        opts = self.store.list_typology_hw_options(self.typology_id)
        if not opts:
            self.cmb.addItem("— Nessuna opzione definita —", None)
        else:
            for o in opts:
                self.cmb.addItem(o["name"], int(o["id"]))

    def _skip(self):
        self.hw_option_id = None
        self.accept()

    def _ok(self):
        self.hw_option_id = self.cmb.currentData()
        self.accept()
