from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple
from collections import defaultdict
import json
from pathlib import Path
from datetime import datetime

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

try:
    from ui_qt.services.profiles_store import ProfilesStore
except Exception:
    ProfilesStore = None

class QuoteVaniPage(QFrame):
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

        actions_top.addWidget(btn_add)
        actions_top.addStretch(1)
        actions_top.addWidget(QLabel("Cliente:"))
        self.ed_customer = QLineEdit(); self.ed_customer.setPlaceholderText("Nome cliente"); self.ed_customer.setMaximumWidth(260)
        actions_top.addWidget(self.ed_customer)
        actions_top.addWidget(btn_new); actions_top.addWidget(btn_save); actions_top.addWidget(btn_open)
        actions_top.addWidget(btn_imp); actions_top.addWidget(btn_exp); actions_top.addWidget(btn_save_cutlist)
        root.addLayout(actions_top)

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

        row_actions = QHBoxLayout()
        btn_del = QPushButton("Rimuovi riga"); btn_del.clicked.connect(self._del_row)
        btn_clr = QPushButton("Svuota"); btn_clr.clicked.connect(self._clear_rows)
        row_actions.addWidget(btn_del); row_actions.addWidget(btn_clr); row_actions.addStretch(1)
        root.addLayout(row_actions)

        act = QHBoxLayout()
        btn_calc = QPushButton("Calcola lista taglio"); btn_calc.clicked.connect(self._calc_and_aggregate)
        act.addWidget(btn_calc); act.addStretch(1)
        root.addLayout(act)

        self.tbl_cut = QTableWidget(0, 6)
        self.tbl_cut.setHorizontalHeaderLabels(["Profilo", "Lunghezza (mm)", "Ang SX", "Ang DX", "Q.tà", "Note"])
        h2 = self.tbl_cut.horizontalHeader()
        h2.setSectionResizeMode(0, QHeaderView.Stretch)
        h2.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h2.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        h2.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        h2.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        h2.setSectionResizeMode(5, QHeaderView.Stretch)
        root.addWidget(self.tbl_cut, 1)

        hint = QLabel("Gruppi: braccio viene scelto automaticamente fra le regole (es. tipo0/1/2) in base a L; usa in formula solo 'braccio'.")
        hint.setStyleSheet("color:#7f8c8d;")
        root.addWidget(hint, 0)

    # ----- Orders DB -----
    def _new_order(self):
        self._current_order_id = None
        self._rows.clear()
        self.tbl_cut.setRowCount(0)
        self._refresh_rows_table()
        self.ed_customer.setText("")
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

    def _del_row(self):
        idx = self.tbl_rows.currentRow()
        if idx < 0: return
        if 0 <= idx < len(self._rows):
            del self._rows[idx]
            self._refresh_rows_table()

    def _clear_rows(self):
        self._rows.clear()
        self._refresh_rows_table()
        self.tbl_cut.setRowCount(0)

    # ----- Calcolo / aggregazione -----
    def _calc_and_aggregate(self):
        self.tbl_cut.setRowCount(0)
        if not self._rows:
            QMessageBox.information(self, "Commessa", "Aggiungi almeno una riga."); return

        prof_tokens: Dict[str, float] = {}
        if self._profiles:
            try:
                for pr in self._profiles.list_profiles():
                    n = str(pr.get("name") or ""); th = float(pr.get("thickness") or 0.0)
                    if n: prof_tokens[sanitize_name(n)] = th
            except Exception:
                pass

        aggregated: Dict[str, Dict[Tuple[float,float,float], int]] = defaultdict(lambda: defaultdict(int))

        for r in self._rows:
            t = self._store.get_typology_full(int(r["tid"]))
            if not t: continue
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
                        key = (item["label"] or "").strip().lower(); mf_map[key] = item
                    var_rules = self._store.list_multi_var_rules(int(r["tid"]), str(grp))
                except Exception:
                    mf_map = []; var_rules = []

            # Applica regole variabili: selezione migliore per var_name (range più stretto che matcha L)
            if var_rules:
                rules_by_var: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
                for vr in var_rules: rules_by_var[vr["var_name"]].append(vr)
                for var_name, rules in rules_by_var.items():
                    matches = [vr for vr in rules if float(vr["l_min"]) <= L <= float(vr["l_max"])]
                    if matches:
                        # scegli quella con intervallo più stretto
                        matches.sort(key=lambda x: (float(x["l_max"]) - float(x["l_min"])))
                        chosen = matches[0]
                        env_base[var_name] = float(chosen["value"])
                        variant = (chosen.get("variant") or "").strip()
                        if variant:
                            env_base[f"{var_name}_variant"] = variant

            comps = t.get("componenti") or []
            used_labels: set[str] = set()
            c_values: Dict[str, float] = {}
            for c in comps:
                prof = c.get("profilo_nome","") or ""
                qty = int(c.get("quantita",0) or 0) * qty_row
                angsx = float(c.get("ang_sx",0.0) or 0.0)
                angdx = float(c.get("ang_dx",0.0) or 0.0)
                expr = c.get("formula_lunghezza","") or "H"
                offs = float(c.get("offset_mm",0.0) or 0.0)
                env = dict(env_base); env.update(c_values)

                if grp:
                    cname = (c.get("nome") or "").strip().lower()
                    if cname in mf_map and (mf_map[cname].get("formula") or "").strip():
                        expr = mf_map[cname]["formula"]
                        used_labels.add(cname)

                try:
                    length = float(eval_formula(expr, env)) + offs
                except Exception:
                    length = 0.0
                if prof and qty > 0:
                    aggregated[prof][(round(length, 2), angsx, angdx)] += qty
                rid = c.get("id_riga","")
                if rid: c_values[f"C_{rid}"] = length

            # Elementi extra dal gruppo (non già usati)
            if grp and mf_map:
                for lbl, itm in mf_map.items():
                    if lbl in used_labels: continue
                    expr = (itm.get("formula") or "H").strip()
                    prof = (itm.get("profile_name") or "GENERIC") or "GENERIC"
                    q = int(itm.get("qty", 1) or 1) * qty_row
                    ax = float(itm.get("ang_sx", 0.0) or 0.0)
                    ad = float(itm.get("ang_dx", 0.0) or 0.0)
                    offs = float(itm.get("offset", 0.0) or 0.0)
                    env = dict(env_base)
                    try:
                        length = float(eval_formula(expr, env)) + offs
                    except Exception:
                        length = 0.0
                    if q > 0:
                        aggregated[prof][(round(length, 2), ax, ad)] += q

        # Tabella taglio
        self.tbl_cut.setRowCount(0)
        for prof in sorted(aggregated.keys()):
            lines = [(length, ax, ad, q) for (length, ax, ad), q in aggregated[prof].items()]
            lines.sort(key=lambda x: x[0], reverse=True)
            for length, ax, ad, q in lines:
                ri = self.tbl_cut.rowCount(); self.tbl_cut.insertRow(ri)
                self.tbl_cut.setItem(ri, 0, QTableWidgetItem(str(prof)))
                self.tbl_cut.setItem(ri, 1, QTableWidgetItem(f"{length:.2f}"))
                self.tbl_cut.setItem(ri, 2, QTableWidgetItem(f"{ax:.1f}"))
                self.tbl_cut.setItem(ri, 3, QTableWidgetItem(f"{ad:.1f}"))
                self.tbl_cut.setItem(ri, 4, QTableWidgetItem(str(q)))
                self.tbl_cut.setItem(ri, 5, QTableWidgetItem(""))

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
        cust = data.get("customer") or ""
        self.ed_customer.setText(str(cust))
        self._refresh_rows_table()

    # ----- Salva cutlist su DB -----
    def _save_cutlist_as_order(self):
        if self.tbl_cut.rowCount() == 0:
            QMessageBox.information(self, "Salva lista", "La lista di taglio è vuota."); return
        default_name = f"Cutlist {datetime.utcnow().isoformat()}"
        name, ok = QInputDialog.getText(self, "Salva lista di taglio", "Nome lista:", text=default_name)
        if not ok or not (name or "").strip(): return
        name = name.strip()
        customer = (self.ed_customer.text() or "").strip()
        cuts = []
        for r in range(self.tbl_cut.rowCount()):
            prof = self.tbl_cut.item(r, 0).text()
            length = float(self.tbl_cut.item(r, 1).text())
            ax = float(self.tbl_cut.item(r, 2).text())
            ad = float(self.tbl_cut.item(r, 3).text())
            qty = int(self.tbl_cut.item(r, 4).text())
            note = self.tbl_cut.item(r, 5).text() if self.tbl_cut.item(r, 5) else ""
            cuts.append({"profile": prof, "length_mm": length, "ang_sx": ax, "ang_dx": ad, "qty": qty, "note": note})
        data = {"type": "cutlist", "cuts": cuts, "saved_at": datetime.utcnow().isoformat() + "Z"}
        try:
            oid = self._orders.create_order(name, customer, data)
            QMessageBox.information(self, "Salva lista", f"Lista salvata come ordine id={oid}.")
        except Exception as e:
            QMessageBox.critical(self, "Errore salvataggio", str(e))
