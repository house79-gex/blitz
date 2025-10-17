from __future__ import annotations
from typing import Dict, Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView
)

class VarsEditorDialog(QDialog):
    """
    Editor semplice di variabili riga (key/value float).
    """
    def __init__(self, parent, base: Dict[str, float] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Variabili riga")
        self.resize(520, 360)
        self.setModal(True)
        self._vars = dict(base or {})
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        self.tbl = QTableWidget(0, 2)
        self.tbl.setHorizontalHeaderLabels(["Nome", "Valore"])
        hdr = self.tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        root.addWidget(self.tbl)

        for k, v in sorted(self._vars.items()):
            r = self.tbl.rowCount(); self.tbl.insertRow(r)
            self.tbl.setItem(r, 0, QTableWidgetItem(k))
            self.tbl.setItem(r, 1, QTableWidgetItem(f"{float(v):.3f}"))

        row = QHBoxLayout()
        btn_add = QPushButton("Aggiungi"); btn_add.clicked.connect(self._add)
        btn_del = QPushButton("Elimina"); btn_del.clicked.connect(self._del)
        btn_ok  = QPushButton("OK"); btn_ok.clicked.connect(self.accept)
        row.addWidget(btn_add); row.addWidget(btn_del); row.addStretch(1); row.addWidget(btn_ok)
        root.addLayout(row)

    def _add(self):
        r = self.tbl.rowCount(); self.tbl.insertRow(r)
        self.tbl.setItem(r, 0, QTableWidgetItem(""))
        self.tbl.setItem(r, 1, QTableWidgetItem("0"))

    def _del(self):
        r = self.tbl.currentRow()
        if r >= 0: self.tbl.removeRow(r)

    def result_vars(self) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for r in range(self.tbl.rowCount()):
            k = self.tbl.item(r, 0).text() if self.tbl.item(r, 0) else ""
            v = self.tbl.item(r, 1).text() if self.tbl.item(r, 1) else "0"
            k = (k or "").strip()
            if not k: continue
            try:
                out[k] = float((v or "0").replace(",", "."))
            except Exception:
                out[k] = 0.0
        return out
