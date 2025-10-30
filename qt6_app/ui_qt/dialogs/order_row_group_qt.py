from __future__ import annotations
from typing import Optional, List

from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QComboBox, QPushButton, QHBoxLayout

class OrderRowFormulasGroupDialog(QDialog):
    """
    Selezione gruppo di formule multiple per la tipologia (facoltativo).
    """
    def __init__(self, parent, groups: List[str]):
        super().__init__(parent)
        self.setWindowTitle("Gruppo formule multiple")
        self.setModal(True)
        self.resize(420, 180)
        self.groups = groups
        self.selected_group: Optional[str] = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.addWidget(QLabel("Seleziona un gruppo di formule multiple (opzionale):"))
        self.cmb = QComboBox()
        self.cmb.addItem("— Nessuno —", None)
        for g in self.groups:
            self.cmb.addItem(g, g)
        root.addWidget(self.cmb)
        row = QHBoxLayout()
        btn_ok = QPushButton("OK"); btn_ok.clicked.connect(self._ok)
        btn_cancel = QPushButton("Annulla"); btn_cancel.clicked.connect(self.reject)
        row.addStretch(1); row.addWidget(btn_cancel); row.addWidget(btn_ok)
        root.addLayout(row)

    def _ok(self):
        self.selected_group = self.cmb.currentData()
        self.accept()
