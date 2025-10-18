from __future__ import annotations
from typing import Dict, Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit, QSpinBox, QPushButton, QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView
)

class OrderRowDimsDialog(QDialog):
    """
    Dati riga: pezzi, H, L e variabili riga.
    Le variabili vengono prese dalla tipologia (non si possono aggiungere nuove chiavi qui).
    Costruttore: OrderRowDimsDialog(parent, store=None, typology_id=None)
    - se store e typology_id forniti, carica le variabili dalla tipologia e le mostra per la modifica dei valori.
    """
    def __init__(self, parent, store=None, typology_id: Optional[int] = None):
        super().__init__(parent)
        self.setWindowTitle("Dati riga (pezzi, H, L, variabili)")
        self.setModal(True)
        self.resize(520, 360)
        self.qty = 1
        self.H = 0.0
        self.L = 0.0
        self.vars: Dict[str, float] = {}
        self._store = store
        self._typology_id = typology_id
        self._build()
        if self._store and self._typology_id:
            self._load_typology_vars()

    def _build(self):
        root = QVBoxLayout(self)
        root.addWidget(QLabel("Pezzi"))
        self.sp_qty = QSpinBox(); self.sp_qty.setRange(1, 999); root.addWidget(self.sp_qty)

        root.addWidget(QLabel("H (mm)"))
        self.ed_h = QLineEdit(); self.ed_h.setPlaceholderText("mm"); root.addWidget(self.ed_h)

        root.addWidget(QLabel("L (mm)"))
        self.ed_l = QLineEdit(); self.ed_l.setPlaceholderText("mm"); root.addWidget(self.ed_l)

        root.addWidget(QLabel("Variabili (preset dalla tipologia) — modifica solo i valori:"))
        self.tbl_vars = QTableWidget(0, 2)
        self.tbl_vars.setHorizontalHeaderLabels(["Nome", "Valore"])
        hdr = self.tbl_vars.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        root.addWidget(self.tbl_vars, 1)

        # bottoni OK/Annulla
        row = QHBoxLayout()
        btn_ok = QPushButton("OK"); btn_ok.clicked.connect(self._ok)
        btn_cancel = QPushButton("Annulla"); btn_cancel.clicked.connect(self.reject)
        row.addStretch(1); row.addWidget(btn_cancel); row.addWidget(btn_ok)
        root.addLayout(row)

    def _load_typology_vars(self):
        try:
            typ = self._store.get_typology_full(self._typology_id)
            vars_map = typ.get("variabili_locali") or {}
        except Exception:
            vars_map = {}
        self.tbl_vars.setRowCount(0)
        for k, v in sorted(vars_map.items()):
            r = self.tbl_vars.rowCount(); self.tbl_vars.insertRow(r)
            item_k = QTableWidgetItem(k)
            item_k.setFlags(item_k.flags() & ~Qt.ItemIsEditable)  # nome non editabile qui
            self.tbl_vars.setItem(r, 0, item_k)
            item_v = QTableWidgetItem(f"{float(v):.3f}")
            item_v.setFlags(item_v.flags() | Qt.ItemIsEditable)
            self.tbl_vars.setItem(r, 1, item_v)

    def _ok(self):
        try:
            self.qty = int(self.sp_qty.value())
            self.H = float((self.ed_h.text() or "0").replace(",", "."))
            self.L = float((self.ed_l.text() or "0").replace(",", "."))
        except Exception:
            self.qty, self.H, self.L = 1, 0.0, 0.0
        # raccogli valori variabili (senza permettere nuove chiavi)
        out: Dict[str, float] = {}
        for r in range(self.tbl_vars.rowCount()):
            k = self.tbl_vars.item(r, 0).text() if self.tbl_vars.item(r, 0) else ""
            v = self.tbl_vars.item(r, 1).text() if self.tbl_vars.item(r, 1) else "0"
            k = (k or "").strip()
            if not k:
                continue
            try:
                out[k] = float((v or "0").replace(",", "."))
            except Exception:
                out[k] = 0.0
        self.vars = out
        self.accept()
