from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple
from collections import defaultdict
import json
from pathlib import Path
from datetime import datetime
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QHBoxLayout, QFileDialog, QLineEdit, QInputDialog
)

try:
    from ui_qt.widgets.header import Header
except Exception:
    Header = None

from ui_qt.services.typologies_store import TypologiesStore, default_db_path
from ui_qt.services.legacy_formula import eval_formula, sanitize_name
from ui_qt.services.orders_store import OrdersStore
from ui_qt.dialogs.order_row_typology_qt import OrderRowTypologyDialog
from ui_qt.dialogs.order_row_dims_qt import OrderRowDimsDialog
from ui_qt.dialogs.order_row_group_qt import OrderRowFormulasGroupDialog
from ui_qt.dialogs.orders_manager_qt import OrdersManagerDialog
from ui_qt.dialogs.cutlist_viewer_qt import CutlistViewerDialog

try:
    from ui_qt.services.profiles_store import ProfilesStore
except Exception:
    ProfilesStore = None


def _norm_label(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[\s_]+", "", s)
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def _is_base_formula_valid(expr: Optional[str]) -> bool:
    if not expr:
        return False
    t = expr.strip().lower()
    if not t:
        return False
    return t not in ("no", "-", "n")


class QuoteVaniPage(QFrame):
    """
    Commesse su DB + Formule multiple (gruppi) con regole variabili (es. braccio).
    Visualizzazione: finestra massimizzata della lista di taglio (Profilo + Elemento), già ordinata per profilo e lunghezza desc.
    """
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self._store = TypologiesStore(str(default_db_path()))
        self._orders = OrdersStore(str(default_db_path()))
        self._profiles = None
        if ProfilesStore:
            try: self._profiles = ProfilesStore()
            except Exception: self._profiles = None

        self._rows: List[Dict[str, Any]] = []
        self._current_order_id: Optional[int] = None

        # ultima lista calcolata per viewer/salvataggio
        self._last_cuts: List[Dict[str, Any]] = []
        self._build()

    def _build(self):
        self.setStyleSheet("QFrame { border: 1px solid #3b4b5a; border-radius: 6px; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        if Header:
            root.addWidget(Header(self.appwin, "COMMESSA - QUOTE VANI"), 0)
        else:
            title = QLabel("COMMESSA - QUOTE VANI")
            title.setStyleSheet("font-size:18px; font-weight:700;")
            root.addWidget(title, 0)

        actions_top = QHBoxLayout()
        btn_add = QPushButton("Aggiungi riga…"); btn_add.clicked.connect(self._add_row_wizard)
        btn_new = QPushButton("Nuova commessa"); btn_new.clicked.connect(self._new_order)
        btn_save = QPushButton("Salva commessa"); btn_save.clicked.connect(self._save_order_to_db)
        btn_open = QPushButton("Apri commessa…"); btn_open.clicked.connect(self._open_order_from_db)
        btn_imp = QPushButton("Importa…"); btn_imp.clicked.connect(self._import_order)
        btn_exp = QPushButton("Esporta…"); btn_exp.clicked.connect(self._export_order)
        btn_save_cutlist = QPushButton("Salva lista di taglio"); btn_save_cutlist.clicked.connect(self._save_cutlist_as_order)
        self.btn_view = QPushButton("Visualizza lista…")
        self.btn_view.setEnabled(False)
        self.btn_view.clicked.connect(self._open_viewer)

        actions_top.addWidget(btn_add)
        actions_top.addStretch(1)
        actions_top.addWidget(QLabel("Cliente:"))
        self.ed_customer = QLineEdit(); self.ed_customer.setPlaceholderText("Nome cliente"); self.ed_customer.setMaximumWidth(260)
        actions_top.addWidget(self.ed_customer)
        actions_top.addWidget(btn_new); actions_top.addWidget(btn_save); actions_top.addWidget(btn_open)
        actions_top.addWidget(btn_imp); actions_top.addWidget(btn_exp); actions_top.addWidget(btn_save_cutlist)
        actions_top.addWidget(self.btn_view)
        root.addLayout(actions_top)

        # Tabella righe
        self.tbl_rows = QTableWidget(0, 6)
        self.tbl_rows.setHorizontalHeaderLabels(["#", "Tipologia", "Pezzi", "H", "L", "Gruppo formule"])
        hdr = self.tbl_rows.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.Stretch)
        root.addWidget(self.tbl_rows)

        hint = QLabel("Se selezioni un Gruppo: applico le formule associate e aggiungo eventuali elementi extra; se non selezioni un Gruppo: uso solo le formule base valide. 'no' o vuoto = escluso.")
        hint.setStyleSheet("color:#7f8c8d;")
        root.addWidget(hint, 0)

        act = QHBoxLayout()
        btn_calc = QPushButton("Calcola lista taglio"); btn_calc.clicked.connect(self._calc_and_store)
        act.addWidget(btn_calc); act.addStretch(1)
        root.addLayout(act)

    # ----- Viewer -----
    def _open_viewer(self):
        if not self._last_cuts:
            QMessageBox.information(self, "Lista", "Calcola prima la lista di taglio."); return
        CutlistViewerDialog(self, self._last_cuts).exec()

    # ----- Orders DB -----
    def _new_order(self):
        self._current_order_id = None
        self._rows.clear()
        self._last_cuts = []
        self._refresh_rows_table()
        self.ed_customer.setText("")
        self.btn_view.setEnabled(False)
        QMessageBox.information(self, "Commessa", "Nuova commessa creata (non salvata).")

    def _save_order_to_db(self):
        if not self._rows:
            QMessageBox.information(self, "Salva", "La commessa è vuota."); return
        default_name = f"Commessa {datetime.utcnow().isoformat()}" if not self._current_order_id else ""
        name, ok = QInputDialog.getText(self, "Salva commessa", "Nome commessa:", text=default_name)
        if not ok or not (name or "").strip(): return
        name = name.strip()
        customer = (self.ed_customer.text() or "").strip()
        data = {"rows": self._rows, "saved_at": datetime.utcnow().isoformat() + "Z", "customer": customer}
        try:
            if self._current_order_id:
                self._orders.update_order(self._current_order_id, name, customer, data)
                QMessageBox.information(self, "Salva", "Commessa aggiornata nel DB.")
            else:
                oid = self._orders.create_order(name, customer, data)
                self._current_order_id = oid
                QMessageBox.information(self, "Salva", f"Commessa salvata (id={oid}).")
        except Exception as e:
            QMessageBox.critical(self, "Errore salvataggio", str(e))

    def _open_order_from_db(self):
        dlg = OrdersManagerDialog(self, self._orders)
        if dlg.exec() and getattr(dlg, "selected_order_id", None):
            oid = dlg.selected_order_id
            ord_item = self._orders.get_order(oid)
            if not ord_item:
                QMessageBox.critical(self, "Apri", "Commessa non trovata."); return
            data = ord_item.get("data") or {}
            rows = data.get("rows") or []
            self._rows = rows
            self._current_order_id = oid
            self._last_cuts = []
            self.btn_view.setEnabled(False)
            self.ed_customer.setText(str(ord_item.get("customer") or ""))
            self._refresh_rows_table()
            QMessageBox.information(self, "Apri", f"Commessa aperta: {ord_item.get('name')} (id={oid}).")

    # ----- Wizard add row -----
    def _add_row_wizard(self):
        d1 = OrderRowTypologyDialog(self, self._store)
        if not d1.exec(): return
        typ_id = int(d1.typology_id)

        d2 = OrderRowDimsDialog(self, store=self._store, typology_id=typ_id)
        if not d2.exec(): return

        groups = self._store.list_multi_formula_groups(typ_id)
        selected_group = None
        if groups:
            dg = OrderRowFormulasGroupDialog(self, groups); dg.exec()
            selected_group = dg.selected_group

        row = {
            "tid": typ_id,
            "qty": int(d2.qty),
            "H": float(d2.H),
            "L": float(d2.L),
            "vars": dict(d2.vars),
            "formula_group": selected_group
        }
        self._rows.append(row)
        self._refresh_rows_table()

    def _refresh_rows_table(self):
        self.tbl_rows.setRowCount(0)
        for i, r in enumerate(self._rows, start=1):
            tdata = self._store.get_typology_full(int(r["tid"]))
            name = tdata["nome"] if tdata else str(r["tid"])
            gtxt = r.get("formula_group") or "-"
            ri = self.tbl_rows.rowCount(); self.tbl_rows.insertRow(ri)
            self.tbl_rows.setItem(ri, 0, QTableWidgetItem(str(i)))
            self.tbl_rows.setItem(ri, 1, QTableWidgetItem(str(name)))
            self.tbl_rows.setItem(ri, 2, QTableWidgetItem(str(r["qty"])))
            self.tbl_rows.setItem(ri, 3, QTableWidgetItem(f"{r['H']:.1f}"))
            self.tbl_rows.setItem(ri, 4, QTableWidgetItem(f"{r['L']:.1f}"))
            self.tbl_rows.setItem(ri, 5, QTableWidgetItem(gtxt))

    # ----- Calcolo / store lista -----
    def _calc_and_store(self):
        cuts = self._calc_cutlist()
        if cuts is None:
            return
        self._last_cuts = cuts
        self.btn_view.setEnabled(bool(self._last_cuts))
        if self._last_cuts:
            QMessageBox.information(self, "Lista", f"Lista di taglio calcolata: {len(self._last_cuts)} righe. Clicca 'Visualizza lista…'")

    def _calc_cutlist(self) -> Optional[List[Dict[str, Any]]]:
        if not self._rows:
            QMessageBox.information(self, "Commessa", "Aggiungi almeno una riga."); return None

        # Token profili (spessori sanitizzati)
        prof_tokens: Dict[str, float] = {}
        if self._profiles:
            try:
                for pr in self._profiles.list_profiles():
                    n = str(pr.get("name") or ""); th = float(pr.get("thickness") or 0.0)
                    if n: prof_tokens[sanitize_name(n)] = th
            except Exception:
                pass

        # aggregated[profile][(element, length, ax, ad, note)] = qty
        aggregated: Dict[str, Dict[Tuple[str, float, float, float, str], int]] = defaultdict(lambda: defaultdict(int))
        profile_order: List[str] = []  # ordine di apparizione per gruppi profilo
        cuts_out: List[Dict[str, Any]] = []  # per eventuale bisogno

        for r in self._rows:
            t = self._store.get_typology_full(int(r["tid"]))
            if not t:
                continue
            H = float(r["H"]); L = float(r["L"]); qty_row = int(r["qty"])

            env_base: Dict[str, Any] = {"H": H, "L": L}
            env_base.update(t.get("variabili_locali") or {})
            env_base.update(r.get("vars") or {})
            env_base.update(prof_tokens)

            grp = r.get("formula_group")
            mf_map: Dict[str, Dict[str, Any]] = {}
            var_rules: List[Dict[str, Any]] = []
            if grp:
                try:
                    for item in self._store.list_multi_formulas(int(r["tid"]), str(grp)):
                        key = _norm_label(item.get("label") or "")
                        mf_map[key] = item
                    var_rules = self._store.list_multi_var_rules(int(r["tid"]), str(grp))
                except Exception:
                    mf_map = {}
                    var_rules = []

            # Varianti (es. braccio) selezionate
            variants_used: Dict[str, str] = {}
            if var_rules:
                by_var: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
                for vr in var_rules: by_var[vr["var_name"]].append(vr)
                for var_name, rules in by_var.items():
                    matches = [vr for vr in rules if float(vr["l_min"]) <= L <= float(vr["l_max"])]
                    if matches:
                        matches.sort(key=lambda x: (float(x["l_max"]) - float(x["l_min"])))
                        chosen = matches[0]
                        env_base[var_name] = float(chosen["value"])
                        variant = (chosen.get("variant") or "").strip()
                        if variant:
                            env_base[f"{var_name}_variant"] = variant
                            variants_used[var_name] = variant

            comps = t.get("componenti") or []
            used_labels: set[str] = set()
            c_values: Dict[str, float] = {}

            # Componenti tipologia (base o gruppo)
            for c in comps:
                elemento = (c.get("nome") or "").strip() or "-"
                elemento_key = _norm_label(elemento)
                prof = (c.get("profilo_nome", "") or "").strip() or "—"
                qty = int(c.get("quantita", 0) or 0) * qty_row
                angsx = float(c.get("ang_sx", 0.0) or 0.0)
                angdx = float(c.get("ang_dx", 0.0) or 0.0)
                base_expr_raw = c.get("formula_lunghezza", None)
                offs = float(c.get("offset_mm", 0.0) or 0.0)

                env = dict(env_base); env.update(c_values)

                expr_to_use: Optional[str] = None
                note_str_parts: List[str] = []

                if grp and elemento_key in mf_map:
                    fm = (mf_map[elemento_key].get("formula") or "").strip()
                    if fm:
                        expr_to_use = fm
                        used_labels.add(elemento_key)
                        # note dalla riga gruppo (se presente)
                        rnote = (mf_map[elemento_key].get("note") or "").strip()
                        if rnote: note_str_parts.append(rnote)
                        # variant (es. braccio=tipoX)
                        if "braccio" in variants_used:
                            note_str_parts.append(f"braccio={variants_used['braccio']}")
                else:
                    if _is_base_formula_valid(base_expr_raw):
                        expr_to_use = (base_expr_raw or "").strip()

                if expr_to_use and qty > 0:
                    try:
                        length = float(eval_formula(expr_to_use, env)) + offs
                    except Exception:
                        length = 0.0
                    note_str = " | ".join(note_str_parts) if note_str_parts else ""
                    key = (elemento, round(length, 2), angsx, angdx, note_str)
                    aggregated[prof][key] += qty
                    if prof not in profile_order:
                        profile_order.append(prof)
                    rid = c.get("id_riga", "")
                    if rid:
                        c_values[f"C_{rid}"] = length

            # Elementi extra del gruppo
            if grp and mf_map:
                for lbl_key, itm in mf_map.items():
                    if lbl_key in used_labels:
                        continue
                    elemento = (itm.get("label") or "").strip() or "-"
                    expr = (itm.get("formula") or "").strip()
                    if not _is_base_formula_valid(expr):
                        continue
                    prof = (itm.get("profile_name") or "ASTINA") or "ASTINA"
                    q = int(itm.get("qty", 1) or 1) * qty_row
                    ax = float(itm.get("ang_sx", 0.0) or 0.0)
                    ad = float(itm.get("ang_dx", 0.0) or 0.0)
                    offs = float(itm.get("offset", 0.0) or 0.0)
                    env = dict(env_base); env.update(c_values)
                    try:
                        length = float(eval_formula(expr, env)) + offs
                    except Exception:
                        length = 0.0
                    note_parts = []
                    rnote = (itm.get("note") or "").strip()
                    if rnote: note_parts.append(rnote)
                    if "braccio" in variants_used:
                        note_parts.append(f"braccio={variants_used['braccio']}")
                    note_str = " | ".join(note_parts) if note_parts else ""
                    key = (elemento, round(length, 2), ax, ad, note_str)
                    if q > 0:
                        aggregated[prof][key] += q
                        if prof not in profile_order:
                            profile_order.append(prof)

        # Costruisci lista finale seguendo l'ordine profili apparizione e lunghezze desc
        cuts_final: List[Dict[str, Any]] = []
        for prof in profile_order:
            if prof not in aggregated:
                continue
            items = [(elt, Ls, ax, ad, note, q) for (elt, Ls, ax, ad, note), q in aggregated[prof].items()]
            items.sort(key=lambda x: x[1], reverse=True)
            for elt, Ls, ax, ad, note, q in items:
                cuts_final.append({
                    "profile": prof,
                    "element": elt,
                    "length_mm": float(Ls),
                    "ang_sx": float(ax),
                    "ang_dx": float(ad),
                    "qty": int(q),
                    "note": note
                })
        return cuts_final

    # ----- Export/Import JSON -----
    def _export_order(self):
        if not self._rows:
            QMessageBox.information(self, "Esporta", "La commessa è vuota."); return
        path, _ = QFileDialog.getSaveFileName(self, "Esporta commessa", "", "Commessa JSON (*.order.json)")
        if not path: return
        data = {"type": "blitz-order", "version": 1, "created_at": datetime.utcnow().isoformat() + "Z",
                "customer": (self.ed_customer.text() or ""), "rows": self._rows}
        try:
            Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            QMessageBox.information(self, "Esporta", "Commessa esportata.")
        except Exception as e:
            QMessageBox.critical(self, "Errore export", str(e))

    def _import_order(self):
        path, _ = QFileDialog.getOpenFileName(self, "Importa commessa", "", "Commessa JSON (*.order.json)")
        if not path: return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as e:
            QMessageBox.critical(self, "Errore import", f"File non valido:\n{e}"); return
        if not isinstance(data, dict) or data.get("type") != "blitz-order" or "rows" not in data:
            QMessageBox.critical(self, "Errore import", "Formato commessa non riconosciuto."); return
        rows = data.get("rows") or []
        if not isinstance(rows, list):
            QMessageBox.critical(self, "Errore import", "Formato righe non valido."); return
        self._rows = []
        for r in rows:
            try:
                self._rows.append({
                    "tid": int(r["tid"]),
                    "qty": int(r["qty"]),
                    "H": float(r["H"]),
                    "L": float(r["L"]),
                    "vars": dict(r.get("vars") or {}),
                    "formula_group": (r.get("formula_group") or None)
                })
            except Exception:
                continue
        self._last_cuts = []
        self.btn_view.setEnabled(False)
        cust = data.get("customer") or ""
        self.ed_customer.setText(str(cust))
        self._refresh_rows_table()

    def _save_cutlist_as_order(self):
        if not self._last_cuts:
            QMessageBox.information(self, "Salva lista", "Calcola prima la lista di taglio (pulsante Calcola)."); return
        default_name = f"Cutlist {datetime.utcnow().isoformat()}"
        name, ok = QInputDialog.getText(self, "Salva lista di taglio", "Nome lista:", text=default_name)
        if not ok or not (name or "").strip(): return
        name = name.strip()
        customer = (self.ed_customer.text() or "").strip()
        data = {"type": "cutlist", "cuts": self._last_cuts, "saved_at": datetime.utcnow().isoformat() + "Z"}
        try:
            oid = self._orders.create_order(name, customer, data)
            QMessageBox.information(self, "Salva lista", f"Lista salvata come ordine id={oid}.")
        except Exception as e:
            QMessageBox.critical(self, "Errore salvataggio", str(e))
