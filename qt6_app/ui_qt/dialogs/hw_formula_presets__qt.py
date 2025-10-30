from __future__ import annotations
from typing import Optional, List, Dict, Any

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QInputDialog, QMessageBox
)

class HardwareFormulaPresetsDialog(QDialog):
    """
    Gestione libreria formule ferramenta:
    - Filtra per Marca/Serie/Sottocategoria/Meccanismo/Scope/Target
    - CRUD preset con formula
    """
    def __init__(self, parent, store):
        super().__init__(parent)
        self.setWindowTitle("Libreria formule ferramenta")
        self.resize(1000, 640)
        self.setModal(True)
        self.store = store
        self._build()
        self._reload()

    def _build(self):
        root = QVBoxLayout(self)
        root.addWidget(QLabel("Presets di formula (riutilizzabili nei componenti)"))
        self.tbl = QTableWidget(0, 9)
        self.tbl.setHorizontalHeaderLabels(["ID","Nome","Marca","Serie","Sottocat.","Meccanismo","Scope","Target","Formula"])
        hdr = self.tbl.horizontalHeader()
        for i, mode in enumerate([QHeaderView.ResizeToContents, QHeaderView.Stretch, QHeaderView.ResizeToContents,
                                  QHeaderView.ResizeToContents, QHeaderView.ResizeToContents, QHeaderView.ResizeToContents,
                                  QHeaderView.ResizeToContents, QHeaderView.ResizeToContents, QHeaderView.Stretch]):
            hdr.setSectionResizeMode(i, mode)
        root.addWidget(self.tbl, 1)

        row = QHBoxLayout()
        b_add = QPushButton("Aggiungi"); b_add.clicked.connect(self._add)
        b_edit = QPushButton("Modifica"); b_edit.clicked.connect(self._edit)
        b_del = QPushButton("Elimina"); b_del.clicked.connect(self._del)
        b_close = QPushButton("Chiudi"); b_close.clicked.connect(self.accept)
        row.addWidget(b_add); row.addWidget(b_edit); row.addWidget(b_del); row.addStretch(1); row.addWidget(b_close)
        root.addLayout(row)

    def _reload(self):
        self.tbl.setRowCount(0)
        rows = self.store.list_hw_formula_presets()
        for p in rows:
            r = self.tbl.rowCount(); self.tbl.insertRow(r)
            self.tbl.setItem(r, 0, QTableWidgetItem(str(p["id"])))
            self.tbl.setItem(r, 1, QTableWidgetItem(p["name"]))
            self.tbl.setItem(r, 2, QTableWidgetItem(str(p.get("brand_id") or "")))
            self.tbl.setItem(r, 3, QTableWidgetItem(str(p.get("series_id") or "")))
            self.tbl.setItem(r, 4, QTableWidgetItem(p.get("subcat") or ""))
            self.tbl.setItem(r, 5, QTableWidgetItem(p.get("mechanism_code") or ""))
            self.tbl.setItem(r, 6, QTableWidgetItem(p.get("scope") or ""))
            self.tbl.setItem(r, 7, QTableWidgetItem(p.get("target") or ""))
            self.tbl.setItem(r, 8, QTableWidgetItem(p.get("formula") or ""))

    def _get_sel_id(self) -> Optional[int]:
        r = self.tbl.currentRow()
        if r < 0: return None
        try: return int(self.tbl.item(r, 0).text())
        except Exception: return None

    def _add(self):
        name, ok = QInputDialog.getText(self, "Preset", "Nome:")
        if not ok or not (name or "").strip(): return
        brand_id, ok_b = QInputDialog.getInt(self, "Preset", "Brand ID (0 = qualsiasi):", 0, 0, 999999, 1)
        if not ok_b: return
        series_id, ok_s = QInputDialog.getInt(self, "Preset", "Series ID (0 = qualsiasi):", 0, 0, 999999, 1)
        if not ok_s: return
        subcat, ok_sub = QInputDialog.getText(self, "Preset", "Sottocategoria (vuoto = qualsiasi):", text="")
        if not ok_sub: return
        mech, ok_m = QInputDialog.getText(self, "Preset", "Meccanismo (vuoto = qualsiasi):", text="")
        if not ok_m: return
        scope, ok_sc = QInputDialog.getText(self, "Preset", "Scope (es. component/part):", text="component")
        if not ok_sc: return
        target, ok_t = QInputDialog.getText(self, "Preset", "Target (es. montante_anta / AST_SUP_MONT):", text="")
        if not ok_t: return
        formula, ok_f = QInputDialog.getMultiLineText(self, "Preset", "Formula:", "H - 80")
        if not ok_f: return
        try:
            pid = self.store.create_hw_formula_preset(
                name.strip(), formula.strip(),
                (brand_id or None), (series_id or None),
                (subcat.strip() or None), (mech.strip() or None),
                (scope.strip() or None), (target.strip() or None), ""
            )
            self._reload()
            QMessageBox.information(self, "Preset", f"Creato (id={pid}).")
        except Exception as e:
            QMessageBox.critical(self, "Errore", str(e))

    def _edit(self):
        pid = self._get_sel_id()
        if not pid: return
        # Semplice: chiedi di nuovo tutti i campi (per brevità)
        name, ok = QInputDialog.getText(self, "Preset", "Nome:")
        if not ok or not (name or "").strip(): return
        brand_id, ok_b = QInputDialog.getInt(self, "Preset", "Brand ID (0 = qualsiasi):", 0, 0, 999999, 1)
        if not ok_b: return
        series_id, ok_s = QInputDialog.getInt(self, "Preset", "Series ID (0 = qualsiasi):", 0, 0, 999999, 1)
        if not ok_s: return
        subcat, ok_sub = QInputDialog.getText(self, "Preset", "Sottocategoria (vuoto = qualsiasi):", text="")
        if not ok_sub: return
        mech, ok_m = QInputDialog.getText(self, "Preset", "Meccanismo (vuoto = qualsiasi):", text="")
        if not ok_m: return
        scope, ok_sc = QInputDialog.getText(self, "Preset", "Scope (es. component/part):", text="component")
        if not ok_sc: return
        target, ok_t = QInputDialog.getText(self, "Preset", "Target (es. montante_anta / AST_SUP_MONT):", text="")
        if not ok_t: return
        formula, ok_f = QInputDialog.getMultiLineText(self, "Preset", "Formula:", "H - 80")
        if not ok_f: return
        try:
            self.store.update_hw_formula_preset(
                int(pid), name.strip(), formula.strip(),
                (brand_id or None), (series_id or None),
                (subcat.strip() or None), (mech.strip() or None),
                (scope.strip() or None), (target.strip() or None), ""
            )
            self._reload()
            QMessageBox.information(self, "Preset", "Aggiornato.")
        except Exception as e:
            QMessageBox.critical(self, "Errore", str(e))

    def _del(self):
        pid = self._get_sel_id()
        if not pid: return
        from PySide6.QtWidgets import QMessageBox as _MB
        if _MB.question(self, "Elimina", "Eliminare il preset selezionato?") != _MB.Yes:
            return
        try:
            self.store.delete_hw_formula_preset(int(pid))
            self._reload()
        except Exception as e:
            QMessageBox.critical(self, "Errore", str(e))
