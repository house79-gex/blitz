from __future__ import annotations
from typing import Optional, List, Dict, Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QCheckBox
)

class ComponentHardwareFormulaPickerDialog(QDialog):
    """
    Selettore formula dalla Libreria per un componente:
    - Passi: scegli opzione ferramenta della tipologia -> vedi preset filtrati -> seleziona e:
      - Inserisci formula nell'elemento
      - (opzionale) Salva come override per questa opzione (comp_hw_formula)
    """
    def __init__(self, parent, store, typology_id: int, row_id: str):
        super().__init__(parent)
        self.setWindowTitle("Libreria formule → componente")
        self.resize(1000, 620)
        self.setModal(True)
        self.store = store
        self.typology_id = int(typology_id)
        self.row_id = str(row_id)
        self._opts: List[Dict[str, Any]] = []
        self._cur_opt: Optional[Dict[str, Any]] = None
        self._selected_formula: Optional[str] = None
        self._build()
        self._load_options()

    def _build(self):
        root = QVBoxLayout(self)
        info = QLabel("1) Seleziona l'opzione ferramenta della tipologia  2) scegli una formula dall'elenco  3) Applica")
        info.setStyleSheet("color:#7f8c8d;")
        root.addWidget(info)

        row = QHBoxLayout()
        row.addWidget(QLabel("Opzione ferramenta:"))
        self.cmb_opt = QComboBox(); self.cmb_opt.currentIndexChanged.connect(self._on_opt_changed)
        row.addWidget(self.cmb_opt, 1)
        btn_manage = QPushButton("Gestisci opzioni…"); btn_manage.clicked.connect(self._manage_options)
        row.addWidget(btn_manage)
        btn_lib = QPushButton("Apri libreria…"); btn_lib.clicked.connect(self._open_lib_manager)
        row.addWidget(btn_lib)
        root.addLayout(row)

        self.tbl = QTableWidget(0, 6)
        self.tbl.setHorizontalHeaderLabels(["ID","Nome","Sottocat.","Meccanismo","Scope/Target","Formula"])
        hdr = self.tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.Stretch)
        root.addWidget(self.tbl, 1)

        act = QHBoxLayout()
        self.chk_save_override = QCheckBox("Salva anche come override per questa opzione")
        act.addWidget(self.chk_save_override)
        act.addStretch(1)
        btn_apply = QPushButton("Applica alla formula dell'elemento"); btn_apply.clicked.connect(self._apply)
        btn_cancel = QPushButton("Chiudi"); btn_cancel.clicked.connect(self.reject)
        act.addWidget(btn_cancel); act.addWidget(btn_apply)
        root.addLayout(act)

    def _load_options(self):
        self._opts = self.store.list_typology_hw_options(self.typology_id)
        self.cmb_opt.clear()
        if not self._opts:
            self.cmb_opt.addItem("— Nessuna opzione definita —", None)
            self._cur_opt = None
            self._reload_presets()
            return
        for o in self._opts:
            self.cmb_opt.addItem(o["name"], int(o["id"]))
        self._on_opt_changed(0)

    def _on_opt_changed(self, _idx: int):
        opt_id = self.cmb_opt.currentData()
        self._cur_opt = next((o for o in self._opts if o["id"] == opt_id), None)
        self._reload_presets()

    def _reload_presets(self):
        self.tbl.setRowCount(0)
        if not self._cur_opt:
            return
        b = int(self._cur_opt["brand_id"]); s = int(self._cur_opt["series_id"])
        sub = str(self._cur_opt["subcat"]); mech = (self._cur_opt.get("mechanism_code") or None)
        presets = self.store.list_hw_formula_presets(brand_id=b, series_id=s, subcat=sub, mechanism_code=mech, scope="component")
        for p in presets:
            r = self.tbl.rowCount(); self.tbl.insertRow(r)
            self.tbl.setItem(r, 0, QTableWidgetItem(str(p["id"])))
            self.tbl.setItem(r, 1, QTableWidgetItem(p["name"]))
            self.tbl.setItem(r, 2, QTableWidgetItem(p.get("subcat") or ""))
            self.tbl.setItem(r, 3, QTableWidgetItem(p.get("mechanism_code") or ""))
            self.tbl.setItem(r, 4, QTableWidgetItem(f"{p.get('scope') or ''}/{p.get('target') or ''}"))
            self.tbl.setItem(r, 5, QTableWidgetItem(p.get("formula") or ""))

    def _selected_formula(self) -> Optional[str]:
        r = self.tbl.currentRow()
        if r < 0: return None
        item = self.tbl.item(r, 5)
        return item.text() if item else None

    def _apply(self):
        formula = self._selected_formula()
        if not formula:
            QMessageBox.information(self, "Applica", "Seleziona un preset dall'elenco.")
            return
        # applica all'elemento (ritorna la formula al chiamante via accept+property)
        self._selected = formula
        # salva override per opzione, se richiesto
        if self.chk_save_override.isChecked() and self._cur_opt:
            try:
                self.store.set_comp_hw_formula(self.typology_id, self.row_id, int(self._cur_opt["id"]), formula)
                QMessageBox.information(self, "Override", "Formula salvata come override per l'opzione.")
            except Exception as e:
                QMessageBox.critical(self, "Errore override", str(e))
                return
        self.accept()

    def selected_formula(self) -> Optional[str]:
        return getattr(self, "_selected", None)

    def _manage_options(self):
        try:
            from ui_qt.dialogs.typology_hw_options_qt import TypologyHardwareOptionsDialog
            dlg = TypologyHardwareOptionsDialog(self, self.store, self.typology_id)
            dlg.exec()
            self._load_options()
        except Exception:
            QMessageBox.information(self, "Opzioni", "Modulo opzioni non disponibile.")

    def _open_lib_manager(self):
        try:
            from ui_qt.dialogs.hw_formula_presets_qt import HardwareFormulaPresetsDialog
            HardwareFormulaPresetsDialog(self, self.store).exec()
            self._reload_presets()
        except Exception:
            QMessageBox.information(self, "Libreria", "Modulo libreria non disponibile.")
