from __future__ import annotations
from typing import Dict, Any, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QComboBox, QTextEdit
)

from ui_qt.services.legacy_formula import sanitize_name


class TypologyMechanismFormulasDialog(QDialog):
    """
    Per una tipologia + opzione ferramenta mostra le parti del meccanismo
    e permette di specificare/salvare formule personalizzate per ogni parte.
    Fornisce strumenti per inserire token e importare variabili tipologia.
    """
    def __init__(self, parent, store, typology_id: int, hw_option_id: int):
        super().__init__(parent)
        self.setWindowTitle("Formule meccanismo (opzione ferramenta)")
        self.resize(1000, 560)
        self.setModal(True)
        self.store = store
        self.typology_id = int(typology_id)
        self.hw_option_id = int(hw_option_id)
        self.mechanism_code = None
        opt = self.store.get_typology_hw_option(self.hw_option_id)
        if opt:
            self.mechanism_code = opt.get("mechanism_code") or None
        self._parts: List[Dict[str, Any]] = []
        self._build()
        self._load()

    def _build(self):
        root = QVBoxLayout(self)
        self.lbl_info = QLabel("")
        root.addWidget(self.lbl_info)

        # token / utilità
        tools = QHBoxLayout()
        tools.addWidget(QLabel("Token:"))
        self.cmb_tokens = QComboBox()
        self.cmb_tokens.setEditable(False)
        tools.addWidget(self.cmb_tokens)
        btn_ins = QPushButton("Inserisci nel campo selezionato")
        btn_ins.clicked.connect(self._insert_token_into_selected)
        tools.addWidget(btn_ins)
        btn_import_vars = QPushButton("Importa variabili tipologia")
        btn_import_vars.clicked.connect(self._import_typology_vars)
        tools.addWidget(btn_import_vars)
        tools.addStretch(1)
        root.addLayout(tools)

        # table: part_key, display_name, formula_base, formula_override (editable)
        self.tbl = QTableWidget(0, 4)
        self.tbl.setHorizontalHeaderLabels(["Part key", "Nome parte", "Formula base", "Formula (override)"])
        hdr = self.tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)
        root.addWidget(self.tbl, 1)

        # preview/edit text area for selected override cell (better UX)
        bottom = QHBoxLayout()
        self.txt_preview = QTextEdit()
        self.txt_preview.setPlaceholderText("Seleziona una riga e modifica l'override qui; poi clicca 'Applica a cella selezionata'")
        bottom.addWidget(self.txt_preview, 3)
        col_actions = QVBoxLayout()
        btn_apply = QPushButton("Applica a cella selezionata")
        btn_apply.clicked.connect(self._apply_preview_to_cell)
        col_actions.addWidget(btn_apply)
        btn_save = QPushButton("Salva tutte")
        btn_save.clicked.connect(self._save)
        col_actions.addWidget(btn_save)
        btn_close = QPushButton("Chiudi")
        btn_close.clicked.connect(self.accept)
        col_actions.addWidget(btn_close)
        col_actions.addStretch(1)
        bottom.addLayout(col_actions, 1)
        root.addLayout(bottom)

    def _load(self):
        if not self.mechanism_code:
            QMessageBox.information(self, "Nessun meccanismo", "L'opzione non ha un meccanismo associato.")
            self.lbl_info.setText("Nessun meccanismo associato a questa opzione.")
            return
        self.lbl_info.setText(f"Meccanismo: {self.mechanism_code} — modifica formule override per questa opzione.")
        # populate tokens combo: base (H,L), variabili tipologia, profili, componenti della tipologia
        tokens = ["H", "L"]
        typ = self.store.get_typology_full(self.typology_id)
        if typ:
            # variabili locali
            for k in sorted((typ.get("variabili_locali") or {}).keys()):
                tokens.append(k)
            # profili (sanitized)
            try:
                from ui_qt.services.profiles_store import ProfilesStore
                ps = ProfilesStore()
                for p in ps.list_profiles():
                    name = str(p.get("name") or "")
                    if name:
                        tokens.append(sanitize_name(name))
            except Exception:
                pass
            # componenti ids
            for c in (typ.get("componenti") or []):
                rid = c.get("id_riga", "")
                if rid:
                    tokens.append(f"C_{rid}")
        # set tokens
        self.cmb_tokens.clear()
        for t in tokens:
            self.cmb_tokens.addItem(t)

        # load parts
        parts = self.store.list_mech_parts(self.mechanism_code)
        self._parts = parts
        existing_list = self.store.list_typology_mech_part_formulas(self.typology_id, self.hw_option_id)
        existing = {p["part_key"]: p["formula"] for p in existing_list}
        self.tbl.setRowCount(0)
        for p in parts:
            r = self.tbl.rowCount(); self.tbl.insertRow(r)
            self.tbl.setItem(r, 0, QTableWidgetItem(p["part_key"]))
            self.tbl.setItem(r, 1, QTableWidgetItem(p["display_name"]))
            self.tbl.setItem(r, 2, QTableWidgetItem(p["formula"]))
            fm = existing.get(p["part_key"], "")
            item = QTableWidgetItem(fm)
            # ensure editable using Qt flag (correct enum operations)
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            self.tbl.setItem(r, 3, item)

    def _insert_token_into_selected(self):
        tok = self.cmb_tokens.currentText()
        if not tok:
            return
        r = self.tbl.currentRow()
        if r < 0:
            QMessageBox.information(self, "Token", "Seleziona prima una riga nella tabella e poi clicca Inserisci.")
            return
        # preferiamo inserire nel campo override (colonna 3)
        cell_item = self.tbl.item(r, 3)
        if cell_item is None:
            cell_item = QTableWidgetItem("")
            self.tbl.setItem(r, 3, cell_item)
        txt = cell_item.text() or ""
        sep = "" if (not txt or txt.endswith(("+", "-", "*", "/", "(", " "))) else ""
        cell_item.setText(txt + sep + tok)

    def _apply_preview_to_cell(self):
        txt = self.txt_preview.toPlainText() or ""
        r = self.tbl.currentRow()
        if r < 0:
            QMessageBox.information(self, "Applica", "Seleziona prima una riga.")
            return
        item = QTableWidgetItem(txt)
        item.setFlags(item.flags() | Qt.ItemIsEditable)
        self.tbl.setItem(r, 3, item)
        QMessageBox.information(self, "Applica", "Valore applicato alla cella override selezionata.")

    def _import_typology_vars(self):
        typ = self.store.get_typology_full(self.typology_id)
        if not typ:
            QMessageBox.information(self, "Importa", "Tipologia non trovata.")
            return
        vars_map = typ.get("variabili_locali") or {}
        if not vars_map:
            QMessageBox.information(self, "Importa", "Nessuna variabile locale definita nella tipologia.")
            return
        lines = [f"{k} = {v}" for k, v in sorted(vars_map.items())]
        self.txt_preview.append("\n# Variabili tipologia importate:")
        for L in lines:
            self.txt_preview.append(f"# {L}")
        QMessageBox.information(self, "Importa", "Variabili tipologia aggiunte nell'area di editing (commenti).")

    def _save(self):
        for r in range(self.tbl.rowCount()):
            part_key = self.tbl.item(r, 0).text() if self.tbl.item(r, 0) else ""
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
