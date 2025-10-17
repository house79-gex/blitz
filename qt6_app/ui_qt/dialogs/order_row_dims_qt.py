from __future__ import annotations
from typing import Dict, Any

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit, QSpinBox, QPushButton, QHBoxLayout
)

from ui_qt.dialogs.vars_editor_qt import VarsEditorDialog

class OrderRowDimsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Dati riga (pezzi, H, L, variabili)")
        self.setModal(True)
        self.resize(420, 260)
        self.qty = 1
        self.H = 0.0
        self.L = 0.0
        self.vars: Dict[str, float] = {}
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.addWidget(QLabel("Pezzi"))
        self.sp_qty = QSpinBox(); self.sp_qty.setRange(1, 999); root.addWidget(self.sp_qty)

        root.addWidget(QLabel("H (mm)"))
        self.ed_h = QLineEdit(); self.ed_h.setPlaceholderText("mm"); root.addWidget(self.ed_h)

        root.addWidget(QLabel("L (mm)"))
        self.ed_l = QLineEdit(); self.ed_l.setPlaceholderText("mm"); root.addWidget(self.ed_l)

        btn_vars = QPushButton("Variabili…"); btn_vars.clicked.connect(self._edit_vars)
        root.addWidget(btn_vars)

        row = QHBoxLayout()
        btn_ok = QPushButton("OK"); btn_ok.clicked.connect(self._ok)
        btn_cancel = QPushButton("Annulla"); btn_cancel.clicked.connect(self.reject)
        row.addStretch(1); row.addWidget(btn_cancel); row.addWidget(btn_ok)
        root.addLayout(row)

    def _edit_vars(self):
        dlg = VarsEditorDialog(self, base=self.vars)
        if dlg.exec():
            self.vars = dlg.result_vars()

    def _ok(self):
        try:
            self.qty = int(self.sp_qty.value())
            self.H = float((self.ed_h.text() or "0").replace(",", "."))
            self.L = float((self.ed_l.text() or "0").replace(",", "."))
        except Exception:
            self.qty, self.H, self.L = 1, 0.0, 0.0
        self.accept()
