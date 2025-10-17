from __future__ import annotations
from typing import Dict, Any, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox
)

class ComponentHardwareMapDialog(QDialog):
    """
    Mappa le formule dell'ELEMENTO corrente (row_id) sulle opzioni ferramenta della TIP0LOGIA.
    - Colonna Opzione (nome)
    - Colonna Formula override (se vuota → usa formula base dell'elemento)
    """
    def __init__(self, parent, store, typology_id: int, row_id: str):
        super().__init__(parent)
        self.setWindowTitle(f"Ferramenta – mapping formule per {row_id}")
        self.resize(820, 520)
        self.setModal(True)
        self.store = store
        self.typology_id = int(typology_id)
        self.row_id = str(row_id)
        self._opts: List[Dict[str, Any]] = []
        self._formulas: Dict[int, str] = {}  # hw_option_id -> formula
        self._build()
        self._load()

    def _build(self):
        root = QVBoxLayout(self)

        info = QLabel("Per ogni opzione definita nella tipologia, puoi impostare una formula specifica per questo elemento.\n"
                      "Se lasci vuoto, l'elemento userà la sua formula base.")
        info.setStyleSheet("color:#7f8c8d;")
        root.addWidget(info)

        self.tbl = QTableWidget(0, 2)
        self.tbl.setHorizontalHeaderLabels(["Opzione", "Formula override"])
        hdr = self.tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        root.addWidget(self.tbl, 1)

        row = QHBoxLayout()
        self.btn_manage = QPushButton("Gestisci opzioni…")
        self.btn_manage.clicked.connect(self._manage_options)
        btn_close = QPushButton("Chiudi"); btn_close.clicked.connect(self.accept)
        row.addWidget(self.btn_manage); row.addStretch(1); row.addWidget(btn_close)
        root.addLayout(row)

    def _load(self):
        try:
            self._opts = self.store.list_typology_hw_options(self.typology_id)
        except Exception:
            self._opts = []
        # formule esistenti
        fm_rows = self.store.list_comp_hw_formulas_for_row(self.typology_id, self.row_id)
        self._formulas = {int(r["hw_option_id"]): str(r["formula"]) for r in fm_rows}

        self.tbl.setRowCount(0)
        for opt in self._opts:
            r = self.tbl.rowCount(); self.tbl.insertRow(r)
            self.tbl.setItem(r, 0, QTableWidgetItem(opt["name"]))
            self.tbl.setItem(r, 1, QTableWidgetItem(self._formulas.get(opt["id"], "")))

    def _manage_options(self):
        # apre gestore opzioni per questa tipologia
        try:
            from ui_qt.dialogs.typology_hw_options_qt import TypologyHardwareOptionsDialog
        except Exception:
            QMessageBox.information(self, "Opzioni", "Modulo non disponibile")
            return
        dlg = TypologyHardwareOptionsDialog(self, self.store, self.typology_id)
        if dlg.exec():
            # salva eventuali modifiche correnti prima di ricaricare
            self._save_current_table()
            self._load()

    def _save_current_table(self):
        for r in range(self.tbl.rowCount()):
            name = self.tbl.item(r, 0).text()
            formula = self.tbl.item(r, 1).text() if self.tbl.item(r, 1) else ""
            # trova opt_id da nome
            opt = next((o for o in self._opts if o["name"] == name), None)
            if not opt: continue
            opt_id = int(opt["id"])
            if (formula or "").strip():
                self.store.set_comp_hw_formula(self.typology_id, self.row_id, opt_id, formula.strip())
            else:
                # se svuotata, rimuovi override
                self.store.delete_comp_hw_formula(self.typology_id, self.row_id, opt_id)

    def accept(self):
        self._save_current_table()
        super().accept()
