from __future__ import annotations
from typing import Optional, Dict, Any, List

from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QComboBox, QPushButton, QHBoxLayout

class OrderRowTypologyDialog(QDialog):
    def __init__(self, parent, store):
        super().__init__(parent)
        self.setWindowTitle("Seleziona tipologia")
        self.setModal(True)
        self.resize(420, 200)
        self.store = store
        self.typology_id: Optional[int] = None
        self._build()
        self._load()

    def _build(self):
        root = QVBoxLayout(self)
        root.addWidget(QLabel("Tipologia"))
        self.cmb = QComboBox(); root.addWidget(self.cmb)
        row = QHBoxLayout()
        btn_ok = QPushButton("OK"); btn_ok.clicked.connect(self._ok)
        btn_cancel = QPushButton("Annulla"); btn_cancel.clicked.connect(self.reject)
        row.addStretch(1); row.addWidget(btn_cancel); row.addWidget(btn_ok)
        root.addLayout(row)

    def _load(self):
        self.cmb.clear()
        rows = self.store.list_typologies()
        for r in rows:
            self.cmb.addItem(str(r["name"]), int(r["id"]))

    def _ok(self):
        self.typology_id = self.cmb.currentData()
        self.accept()
