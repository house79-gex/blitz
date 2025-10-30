from __future__ import annotations
from typing import Dict, Any, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QLineEdit, QMessageBox, QListWidget, QListWidgetItem, QComboBox
)

from ui_qt.services.typologies_store import TypologiesStore
from ui_qt.services.legacy_formula import sanitize_name

class MultiFormulasEditorDialog(QDialog):
    """
    Editor 'Formule multiple' per tipologia:
    - Tab 1: Formule (Gruppo, Etichetta, Formula, Profilo, Q.tà, Ang SX, Ang DX, Offset)
      • Token con tooltip a sinistra; click inserisce nel campo formula alla posizione del cursore
      • Pulsante 'Usa etichetta elemento corrente' per riempire la colonna Etichetta sulla riga selezionata
    - Tab 2: Regole variabili (var_name, L_min, L_max, valore), per gruppo selezionato
    """
    def __init__(self, parent, store: TypologiesStore, typology_id: int, vars_map: Dict[str, float],
                 components: List[Dict[str, Any]], profiles_map: Optional[Dict[str, float]] = None,
                 current_label: Optional[str] = None):
        super().__init__(parent)
        self.setWindowTitle("Formule multiple - Tipologia")
        self.resize(1180, 680)
        self.setModal(True)
        self.store = store
        self.typology_id = int(typology_id)
        self.vars_map = dict(vars_map or {})
        self.components = components or []
        self.profiles_map = profiles_map or {}
        self.current_label = (current_label or "").strip()
        self._build()
        self._load_existing()

    def _build(self):
        root = QHBoxLayout(self)

        # Colonna Token
        left = QVBoxLayout()
        left.addWidget(QLabel("Token (clic per inserire)"))
        self.lst_tokens = QListWidget()
        self.lst_tokens.itemClicked.connect(self._insert_token_into_editor)
        left.addWidget(self.lst_tokens, 1)
        # Etichetta corrente
        if self.current_label:
            ml = QLabel(f"Etichetta elemento corrente: {self.current_label}")
            ml.setStyleSheet("color:#7f8c8d;")
            left.addWidget(ml)
        root.addLayout(left, 1)
        self._fill_tokens()

        # Colonna destra: Formule + Regole variabili
        right = QVBoxLayout()

        # Selettore gruppo per regole variabili
        grp_row = QHBoxLayout()
        grp_row.addWidget(QLabel("Gruppo regole variabili:"))
        self.cmb_group = QComboBox()
        self.cmb_group.currentIndexChanged.connect(self._load_rules_for_group)
        grp_row.addWidget(self.cmb_group, 1)
        btn_use_label = QPushButton("Usa etichetta elemento corrente")
        btn_use_label.clicked.connect(self._apply_current_label_to_row)
        grp_row.addWidget(btn_use_label)
        right.addLayout(grp_row)

        # Tabella Formule
        right.addWidget(QLabel("Formule (Gruppo, Etichetta, Formula, Profilo, Q.tà, Ang SX, Ang DX, Offset)"))
        self.tbl = QTableWidget(0, 8)
        self.tbl.setHorizontalHeaderLabels(["Gruppo", "Etichetta", "Formula", "Profilo", "Q.tà", "Ang SX", "Ang DX", "Offset"])
        hdr = self.tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(7, QHeaderView.ResizeToContents)
        right.addWidget(self.tbl, 4)

        # Editor formula singola (per inserimento a caret)
        right.addWidget(QLabel("Modifica formula (riga selezionata):"))
        self.ed_formula = QLineEdit()
        right.addWidget(self.ed_formula)

        # Bottoni formule
        fbtns = QHBoxLayout()
        btn_add = QPushButton("Aggiungi riga"); btn_add.clicked.connect(self._add_row)
        btn_del = QPushButton("Elimina riga"); btn_del.clicked.connect(self._del_row)
        btn_apply = QPushButton("Applica formula alla riga"); btn_apply.clicked.connect(self._apply_to_row)
        btn_save = QPushButton("Salva formule"); btn_save.clicked.connect(self._save_all_formulas)
        fbtns.addWidget(btn_add); fbtns.addWidget(btn_del); fbtns.addStretch(1); fbtns.addWidget(btn_apply); fbtns.addWidget(btn_save)
        right.addLayout(fbtns)

        # Regole variabili
        right.addWidget(QLabel("Regole variabili per gruppo (var_name, L_min, L_max, valore)"))
        self.tbl_rules = QTableWidget(0, 4)
        self.tbl_rules.setHorizontalHeaderLabels(["Var", "L_min", "L_max", "Valore"])
        hr = self.tbl_rules.horizontalHeader()
        hr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        right.addWidget(self.tbl_rules, 2)

        rbtns = QHBoxLayout()
        btn_r_add = QPushButton("Aggiungi regola"); btn_r_add.clicked.connect(self._rules_add)
        btn_r_del = QPushButton("Elimina regola"); btn_r_del.clicked.connect(self._rules_del)
        btn_r_save = QPushButton("Salva regole"); btn_r_save.clicked.connect(self._rules_save)
        btn_close = QPushButton("Chiudi"); btn_close.clicked.connect(self.accept)
        rbtns.addWidget(btn_r_add); rbtns.addWidget(btn_r_del); rbtns.addStretch(1); rbtns.addWidget(btn_r_save); rbtns.addWidget(btn_close)
        right.addLayout(rbtns)

        root.addLayout(right, 3)

        # sync selezione tabella -> editor
        self.tbl.itemSelectionChanged.connect(self._sync_editor_from_row)

    def _fill_tokens(self):
        def add_tok(text: str, tip: str):
            it = QListWidgetItem(text)
            it.setToolTip(tip)
            self.lst_tokens.addItem(it)
        add_tok("H", "Altezza finita del vano")
        add_tok("L", "Larghezza finita del vano")
        for k in sorted(self.vars_map.keys()):
            add_tok(k, f"Variabile tipologia: {k} = {self.vars_map[k]}")
        for name, th in sorted((self.profiles_map or {}).items()):
            tok = sanitize_name(name)
            add_tok(tok, f"Spessore profilo '{name}' (token {tok}) = {th} mm")
        for c in self.components:
            rid = (c.get("id_riga") or "").strip()
            nm = (c.get("nome") or "").strip()
            if rid:
                add_tok(f"C_{rid}", f"Lunghezza calcolata del componente {rid} ({nm})")

    def _insert_token_into_editor(self, item: QListWidgetItem):
        tok = item.text()
        t = self.ed_formula.text() or ""
        pos = self.ed_formula.cursorPosition()
        sep = "" if (pos == 0 or t[:pos].endswith(("+","-","*","/","("," "))) else ""
        new_text = t[:pos] + sep + tok + t[pos:]
        self.ed_formula.setText(new_text)
        self.ed_formula.setCursorPosition(pos + len(sep) + len(tok))

    def _apply_current_label_to_row(self):
        if not self.current_label:
            QMessageBox.information(self, "Etichetta", "Nessuna etichetta elemento corrente disponibile.")
            return
        r = self.tbl.currentRow()
        if r < 0:
            QMessageBox.information(self, "Etichetta", "Seleziona una riga nella tabella Formule.")
            return
        self.tbl.setItem(r, 1, QTableWidgetItem(self.current_label))

    def _load_existing(self):
        # gruppi a combo per regole
        groups = self.store.list_multi_formula_groups(self.typology_id)
        self.cmb_group.clear()
        for g in groups:
            self.cmb_group.addItem(g)
        # formule
        self.tbl.setRowCount(0)
        for g in groups:
            rows = self.store.list_multi_formulas(self.typology_id, g)
            for row in rows:
                r = self.tbl.rowCount(); self.tbl.insertRow(r)
                self.tbl.setItem(r, 0, QTableWidgetItem(g))
                self.tbl.setItem(r, 1, QTableWidgetItem(row["label"]))
                self.tbl.setItem(r, 2, QTableWidgetItem(row["formula"]))
                self.tbl.setItem(r, 3, QTableWidgetItem(row.get("profile_name") or ""))
                self.tbl.setItem(r, 4, QTableWidgetItem(str(int(row.get("qty",1)))))
                self.tbl.setItem(r, 5, QTableWidgetItem(f"{float(row.get('ang_sx',0.0)):.1f}"))
                self.tbl.setItem(r, 6, QTableWidgetItem(f"{float(row.get('ang_dx',0.0)):.1f}"))
                self.tbl.setItem(r, 7, QTableWidgetItem(f"{float(row.get('offset',0.0)):.1f}"))
        # carica regole del primo gruppo (se presente)
        if groups:
            self._load_rules_for_group(0)

    def _load_rules_for_group(self, _idx: int):
        grp = self.cmb_group.currentText()
        self.tbl_rules.setRowCount(0)
        if not grp:
            return
        rows = self.store.list_multi_var_rules(self.typology_id, grp)
        for r in rows:
            i = self.tbl_rules.rowCount(); self.tbl_rules.insertRow(i)
            self.tbl_rules.setItem(i, 0, QTableWidgetItem(r["var_name"]))
            self.tbl_rules.setItem(i, 1, QTableWidgetItem(f"{float(r['l_min']):.1f}"))
            self.tbl_rules.setItem(i, 2, QTableWidgetItem(f"{float(r['l_max']):.1f}"))
            self.tbl_rules.setItem(i, 3, QTableWidgetItem(f"{float(r['value']):.3f}"))

    def _sync_editor_from_row(self):
        r = self.tbl.currentRow()
        self.ed_formula.setText(self.tbl.item(r, 2).text() if r >= 0 and self.tbl.item(r, 2) else "")

    def _apply_to_row(self):
        r = self.tbl.currentRow()
        if r < 0:
            QMessageBox.information(self, "Applica", "Seleziona una riga.")
            return
        self.tbl.setItem(r, 2, QTableWidgetItem(self.ed_formula.text() or ""))

    def _add_row(self):
        r = self.tbl.rowCount(); self.tbl.insertRow(r)
        # default: primo gruppo esistente oppure GRUPPO-1
        grp = self.cmb_group.currentText() or "GRUPPO-1"
        self.tbl.setItem(r, 0, QTableWidgetItem(grp))
        # suggerisci etichetta dal nome componenti
        suggested = ""
        if self.components:
            names = [c.get("nome","") for c in self.components if c.get("nome")]
            if names:
                suggested = names[min(r, len(names)-1)]
        self.tbl.setItem(r, 1, QTableWidgetItem(suggested))
        self.tbl.setItem(r, 2, QTableWidgetItem("H"))
        self.tbl.setItem(r, 3, QTableWidgetItem(""))
        self.tbl.setItem(r, 4, QTableWidgetItem("1"))
        self.tbl.setItem(r, 5, QTableWidgetItem("0.0"))
        self.tbl.setItem(r, 6, QTableWidgetItem("0.0"))
        self.tbl.setItem(r, 7, QTableWidgetItem("0.0"))

    def _del_row(self):
        r = self.tbl.currentRow()
        if r >= 0:
            self.tbl.removeRow(r)

    def _save_all_formulas(self):
        n = self.tbl.rowCount()
        for r in range(n):
            grp = (self.tbl.item(r, 0).text() if self.tbl.item(r, 0) else "").strip()
            lab = (self.tbl.item(r, 1).text() if self.tbl.item(r, 1) else "").strip()
            frm = (self.tbl.item(r, 2).text() if self.tbl.item(r, 2) else "").strip()
            prof = (self.tbl.item(r, 3).text() if self.tbl.item(r, 3) else "").strip() or None
            try:
                qty = int((self.tbl.item(r, 4).text() if self.tbl.item(r, 4) else "1").strip())
                ax = float((self.tbl.item(r, 5).text() if self.tbl.item(r, 5) else "0").strip().replace(",", "."))
                ad = float((self.tbl.item(r, 6).text() if self.tbl.item(r, 6) else "0").strip().replace(",", "."))
                offs = float((self.tbl.item(r, 7).text() if self.tbl.item(r, 7) else "0").strip().replace(",", "."))
            except Exception:
                QMessageBox.critical(self, "Errore", f"Valori non validi alla riga {r+1}.")
                return
            if not grp or not lab or not frm:
                continue
            try:
                self.store.upsert_multi_formula(self.typology_id, grp, lab, frm, prof, qty, ax, ad, offs)
            except Exception as e:
                QMessageBox.critical(self, "Errore salvataggio", str(e))
                return
        QMessageBox.information(self, "Salva", "Formule multiple salvate.")

    # Regole variabili
    def _rules_add(self):
        r = self.tbl_rules.rowCount(); self.tbl_rules.insertRow(r)
        self.tbl_rules.setItem(r, 0, QTableWidgetItem("braccio"))
        self.tbl_rules.setItem(r, 1, QTableWidgetItem("0"))
        self.tbl_rules.setItem(r, 2, QTableWidgetItem("9999"))
        self.tbl_rules.setItem(r, 3, QTableWidgetItem("150"))

    def _rules_del(self):
        r = self.tbl_rules.currentRow()
        if r >= 0:
            self.tbl_rules.removeRow(r)

    def _rules_save(self):
        grp = self.cmb_group.currentText().strip()
        if not grp:
            QMessageBox.information(self, "Regole", "Seleziona un gruppo nella combo in alto.")
            return
        rules: List[Dict[str, Any]] = []
        for r in range(self.tbl_rules.rowCount()):
            var = (self.tbl_rules.item(r, 0).text() if self.tbl_rules.item(r, 0) else "").strip()
            lmin = (self.tbl_rules.item(r, 1).text() if self.tbl_rules.item(r, 1) else "0").strip()
            lmax = (self.tbl_rules.item(r, 2).text() if self.tbl_rules.item(r, 2) else "0").strip()
            val  = (self.tbl_rules.item(r, 3).text() if self.tbl_rules.item(r, 3) else "0").strip()
            if not var:
                continue
            try:
                rules.append({"var_name": var, "l_min": float(lmin.replace(",", ".")), "l_max": float(lmax.replace(",", ".")), "value": float(val.replace(",", "."))})
            except Exception:
                QMessageBox.critical(self, "Regole", f"Valori non validi nella riga {r+1}.")
                return
        try:
            self.store.replace_multi_var_rules(self.typology_id, grp, rules)
            QMessageBox.information(self, "Regole", "Regole variabili salvate.")
        except Exception as e:
            QMessageBox.critical(self, "Regole", str(e))
