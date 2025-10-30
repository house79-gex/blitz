from __future__ import annotations
from typing import Dict, Any, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QLineEdit, QMessageBox, QListWidget, QListWidgetItem
)

from ui_qt.services.typologies_store import TypologiesStore
from ui_qt.services.legacy_formula import sanitize_name

class MultiFormulasEditorDialog(QDialog):
    """
    Editor 'Formule multiple' per tipologia:
    - Colonne: Gruppo, Etichetta, Formula
    - A sinistra elenco token (con tooltip); click inserisce alla posizione del cursore nell'editor formula
    - Toolbar: Aggiungi / Elimina / Salva
    """
    def __init__(self, parent, store: TypologiesStore, typology_id: int, vars_map: Dict[str, float], components: List[Dict[str, Any]], profiles_map: Optional[Dict[str, float]] = None):
        super().__init__(parent)
        self.setWindowTitle("Formule multiple - Tipologia")
        self.resize(1000, 620)
        self.setModal(True)
        self.store = store
        self.typology_id = int(typology_id)
        self.vars_map = dict(vars_map or {})
        self.components = components or []
        self.profiles_map = profiles_map or {}
        self._build()
        self._load_existing()

    def _build(self):
        root = QHBoxLayout(self)

        # Elenco token con tooltip
        left = QVBoxLayout()
        left.addWidget(QLabel("Token (clic per inserire)"))
        self.lst_tokens = QListWidget()
        self.lst_tokens.itemClicked.connect(self._insert_token_into_editor)
        left.addWidget(self.lst_tokens, 1)
        root.addLayout(left, 1)

        # Popola token con descrizioni
        self._fill_tokens()

        # Tabella formule
        right = QVBoxLayout()
        self.tbl = QTableWidget(0, 3)
        self.tbl.setHorizontalHeaderLabels(["Gruppo", "Etichetta", "Formula"])
        hdr = self.tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        right.addWidget(self.tbl, 5)

        # Editor formula con inserimento a caret
        right.addWidget(QLabel("Modifica formula (riga selezionata):"))
        self.ed_formula = QLineEdit()
        right.addWidget(self.ed_formula)

        # bottoni
        btns = QHBoxLayout()
        btn_add = QPushButton("Aggiungi riga"); btn_add.clicked.connect(self._add_row)
        btn_del = QPushButton("Elimina riga"); btn_del.clicked.connect(self._del_row)
        btn_apply = QPushButton("Applica formula alla riga"); btn_apply.clicked.connect(self._apply_to_row)
        btn_save = QPushButton("Salva tutto"); btn_save.clicked.connect(self._save_all)
        btn_close = QPushButton("Chiudi"); btn_close.clicked.connect(self.accept)
        btns.addWidget(btn_add); btns.addWidget(btn_del); btns.addStretch(1); btns.addWidget(btn_apply); btns.addWidget(btn_save); btns.addWidget(btn_close)
        right.addLayout(btns)

        root.addLayout(right, 3)

        # sync selezione tabella -> editor
        self.tbl.itemSelectionChanged.connect(self._sync_editor_from_row)

    def _fill_tokens(self):
        def add_tok(text: str, tip: str):
            it = QListWidgetItem(text)
            it.setToolTip(tip)
            self.lst_tokens.addItem(it)
        # Base
        add_tok("H", "Altezza finita del vano")
        add_tok("L", "Larghezza finita del vano")
        # Variabili tipologia
        for k in sorted(self.vars_map.keys()):
            add_tok(k, f"Variabile tipologia: {k} = {self.vars_map[k]}")
        # Profili (token = nome sanitizzato → spessore)
        for name, th in sorted((self.profiles_map or {}).items()):
            tok = sanitize_name(name)
            add_tok(tok, f"Spessore profilo '{name}' (token {tok}) = {th} mm")
        # Componenti (C_<id>)
        for c in self.components:
            rid = (c.get("id_riga") or "").strip()
            nm = (c.get("nome") or "").strip()
            if rid:
                add_tok(f"C_{rid}", f"Lunghezza calcolata del componente {rid} ({nm})")

    def _insert_token_into_editor(self, item: QListWidgetItem):
        tok = item.text()
        # inserisci nel QLineEdit alla posizione attuale del cursore
        t = self.ed_formula.text() or ""
        pos = self.ed_formula.cursorPosition()
        sep = "" if (pos == 0 or t[:pos].endswith(("+", "-", "*", "/", "(", " "))) else ""
        new_text = t[:pos] + sep + tok + t[pos:]
        self.ed_formula.setText(new_text)
        self.ed_formula.setCursorPosition(pos + len(sep) + len(tok))

    def _load_existing(self):
        self.tbl.setRowCount(0)
        for grp in self.store.list_multi_formula_groups(self.typology_id):
            for row in self.store.list_multi_formulas(self.typology_id, grp):
                r = self.tbl.rowCount(); self.tbl.insertRow(r)
                self.tbl.setItem(r, 0, QTableWidgetItem(grp))
                self.tbl.setItem(r, 1, QTableWidgetItem(row["label"]))
                self.tbl.setItem(r, 2, QTableWidgetItem(row["formula"]))

    def _sync_editor_from_row(self):
        r = self.tbl.currentRow()
        if r < 0:
            self.ed_formula.setText("")
            return
        item = self.tbl.item(r, 2)
        self.ed_formula.setText(item.text() if item else "")

    def _apply_to_row(self):
        r = self.tbl.currentRow()
        if r < 0:
            QMessageBox.information(self, "Applica", "Seleziona una riga.")
            return
        self.tbl.setItem(r, 2, QTableWidgetItem(self.ed_formula.text() or ""))

    def _add_row(self):
        r = self.tbl.rowCount(); self.tbl.insertRow(r)
        self.tbl.setItem(r, 0, QTableWidgetItem("GRUPPO-1"))
        # suggerisci etichette dai componenti (nome)
        suggested = ""
        if self.components:
            names = [c.get("nome","") for c in self.components if c.get("nome")]
            if names:
                suggested = names[min(r, len(names)-1)]
        self.tbl.setItem(r, 1, QTableWidgetItem(suggested))
        self.tbl.setItem(r, 2, QTableWidgetItem("H"))

    def _del_row(self):
        r = self.tbl.currentRow()
        if r >= 0:
            self.tbl.removeRow(r)

    def _save_all(self):
        # salva tutte le righe in DB (upsert)
        for r in range(self.tbl.rowCount()):
            grp = (self.tbl.item(r, 0).text() if self.tbl.item(r, 0) else "").strip()
            lab = (self.tbl.item(r, 1).text() if self.tbl.item(r, 1) else "").strip()
            frm = (self.tbl.item(r, 2).text() if self.tbl.item(r, 2) else "").strip()
            if not grp or not lab or not frm:
                continue
            try:
                self.store.upsert_multi_formula(self.typology_id, grp, lab, frm)
            except Exception as e:
                QMessageBox.critical(self, "Errore salvataggio", str(e))
                return
        QMessageBox.information(self, "Salva", "Formule multiple salvate.")
