from __future__ import annotations
from typing import Dict, Any, List, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox
)

class TypologyMechanismFormulasDialog(QDialog):
    """
    Per una tipologia + opzione ferramenta mostra le parti del meccanismo
    e permette di specificare/salvare formule personalizzate per ogni parte.
    """
    def __init__(self, parent, store, typology_id: int, hw_option_id: int):
        super().__init__(parent)
        self.setWindowTitle("Formule meccanismo (opzione ferramenta)")
        self.resize(900, 520)
        self.setModal(True)
        self.store = store
        self.typology_id = int(typology_id)
        self.hw_option_id = int(hw_option_id)
        self.mechanism_code = None
        # load option to find mechanism_code
        opt = self.store.get_typology_hw_option(self.hw_option_id)
        if opt:
            self.mechanism_code = opt.get("mechanism_code") or None
        self._build()
        self._load()

    def _build(self):
        root = QVBoxLayout(self)
        self.lbl_info = QLabel("")
        root.addWidget(self.lbl_info)
        self.tbl = QTableWidget(0, 4)
        self.tbl.setHorizontalHeaderLabels(["Part key", "Nome parte", "Formula corrente", "Formula (override)"])
        hdr = self.tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)
        root.addWidget(self.tbl, 1)

        row = QHBoxLayout()
        btn_save = QPushButton("Salva"); btn_save.clicked.connect(self._save)
        btn_close = QPushButton("Chiudi"); btn_close.clicked.connect(self.accept)
        row.addStretch(1); row.addWidget(btn_save); row.addWidget(btn_close)
        root.addLayout(row)

    def _load(self):
        if not self.mechanism_code:
            QMessageBox.information(self, "Nessun meccanismo", "L'opzione non ha un meccanismo associato.")
            self.lbl_info.setText("Nessun meccanismo associato a questa opzione.")
            return
        self.lbl_info.setText(f"Meccanismo: {self.mechanism_code} — modifica formule override per questa opzione.")
        parts = self.store.list_mech_parts(self.mechanism_code)
        existing_list = self.store.list_typology_mech_part_formulas(self.typology_id, self.hw_option_id)
        existing = {p["part_key"]: p["formula"] for p in existing_list}
        self.tbl.setRowCount(0)
        for p in parts:
            r = self.tbl.rowCount(); self.tbl.insertRow(r)
            self.tbl.setItem(r, 0, QTableWidgetItem(p["part_key"]))
            self.tbl.setItem(r, 1, QTableWidgetItem(p["display_name"]))
            self.tbl.setItem(r, 2, QTableWidgetItem(p["formula"]))
            fm = existing.get(p["part_key"], "")
            self.tbl.setItem(r, 3, QTableWidgetItem(fm))

    def _save(self):
        for r in range(self.tbl.rowCount()):
            part_key = self.tbl.item(r, 0).text()
            override = self.tbl.item(r, 3).text() if self.tbl.item(r, 3) else ""
            if override and override.strip():
                try:
                    self.store.set_typology_mech_part_formula(self.typology_id, self.hw_option_id, part_key, override.strip())
                except Exception as e:
                    QMessageBox.critical(self, "Errore salvataggio", str(e))
                    return
            else:
                try:
                    self.store.delete_typology_mech_part_formula(self.typology_id, self.hw_option_id, part_key)
                except Exception:
                    pass
        QMessageBox.information(self, "Salvataggio", "Formule salvate.")
