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
from ui_qt.services.orders_store import OrdersStore
from ui_qt.services.legacy_formula import eval_formula, sanitize_name

try:
    from ui_qt.services.profiles_store import ProfilesStore
except Exception:
    ProfilesStore = None

from ui_qt.dialogs.order_row_typology_qt import OrderRowTypologyDialog
from ui_qt.dialogs.order_row_dims_qt import OrderRowDimsDialog
from ui_qt.dialogs.order_row_hw_qt import OrderRowHardwareDialog
from ui_qt.dialogs.orders_manager_qt import OrdersManagerDialog


class QuoteVaniPage(QFrame):
    """
    Commessa editor:
    - Nuova/Apri/Salva commessa (DB OrdersStore)
    - Aggiungi riga: tipologia -> dims (carica variabili dalla tipologia) -> opzione ferramenta
    - Calcola lista taglio (componenti tipologia + parti meccanismo con override)
    - Salva lista di taglio (salva su OrdersStore come 'cutlist')
    """
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self._store = TypologiesStore(str(default_db_path()))
        self._orders = OrdersStore(str(default_db_path()))
        self._profiles = None
        if ProfilesStore:
            try:
                self._profiles = ProfilesStore()
            except Exception:
                self._profiles = None

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

        # tabella righe commessa
        self.tbl_rows = QTableWidget(0, 6)
        self.tbl_rows.setHorizontalHeaderLabels(["#", "Tipologia", "Pezzi", "H", "L", "Ferramenta"])
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

        # elenco taglio
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

        hint = QLabel("Aggiungi righe tramite la finestra modale. Le variabili riga sono prese dalla tipologia (modifica solo i valori).")
        hint.setStyleSheet("color:#7f8c8d;")
        root.addWidget(hint, 0)

    # ---------- Orders CRUD ----------
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
        if not ok or not (name or "").strip():
            return
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
                QMessageBox.critical(self, "Apri", "Comessa non trovata.")
                return
            data = ord_item.get("data") or {}
            rows = data.get("rows") or []
            self._rows = rows
            self._current_order_id = oid
            self.ed_customer.setText(str(ord_item.get("customer") or ""))
            self._refresh_rows_table()
            QMessageBox.information(self, "Apri", f"Comessa aperta: {ord_item.get('name')} (id={oid}).")

    # salva la lista di taglio corrente come order di tipo 'cutlist' (rows=lista taglio)
    def _save_cutlist_as_order(self):
        if self.tbl_cut.rowCount() == 0:
            QMessageBox.information(self, "Salva lista", "La lista di taglio è vuota."); return
        default_name = f"Cutlist {datetime.utcnow().isoformat()}"
        name, ok = QInputDialog.getText(self, "Salva lista di taglio", "Nome lista:", text=default_name)
        if not ok or not (name or "").strip():
            return
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
            QMessageBox.information(self, "Salva lista", f"Lista salvata come order id={oid}.")
        except Exception as e:
            QMessageBox.critical(self, "Errore salvataggio", str(e))

    # ---------- Add row wizard ----------
    def _add_row_wizard(self):
        # 1) seleziona tipologia
        d1 = OrderRowTypologyDialog(self, self._store)
        if not d1.exec():
            return
        typ_id = int(d1.typology_id)

        # 2) dimensions + variables (passo typology_id e store così OrderRowDimsDialog carica le variabili)
        d2 = OrderRowDimsDialog(self, store=self._store, typology_id=typ_id)
        if not d2.exec():
            return

        # 3) scelta opzione ferramenta (facoltativa)
        d3 = OrderRowHardwareDialog(self, self._store, typ_id)
        d3.exec()

        row = {
            "tid": typ_id,
            "qty": int(d2.qty),
            "H": float(d2.H),
            "L": float(d2.L),
            "vars": dict(d2.vars),
            "hw_option_id": (int(d3.hw_option_id) if d3.hw_option_id else None)
        }
        self._rows.append(row)
        self._refresh_rows_table()

    def _refresh_rows_table(self):
        self.tbl_rows.setRowCount(0)
        for i, r in enumerate(self._rows, start=1):
            tdata = self._store.get_typology_full(int(r["tid"]))
            name = tdata["nome"] if tdata else str(r["tid"])
            hw_txt = "-"
            if r.get("hw_option_id"):
                opt = self._store.get_typology_hw_option(int(r["hw_option_id"]))
                if opt:
                    hw_txt = f"{opt['name']} [{opt.get('mechanism_code') or '-'}]"
            ri = self.tbl_rows.rowCount(); self.tbl_rows.insertRow(ri)
            self.tbl_rows.setItem(ri, 0, QTableWidgetItem(str(i)))
            self.tbl_rows.setItem(ri, 1, QTableWidgetItem(str(name)))
            self.tbl_rows.setItem(ri, 2, QTableWidgetItem(str(r["qty"])))
            self.tbl_rows.setItem(ri, 3, QTableWidgetItem(f"{r['H']:.1f}"))
            self.tbl_rows.setItem(ri, 4, QTableWidgetItem(f"{r['L']:.1f}"))
            self.tbl_rows.setItem(ri, 5, QTableWidgetItem(hw_txt))

    def _del_row(self):
        idx = self.tbl_rows.currentRow()
        if idx < 0:
            return
        if 0 <= idx < len(self._rows):
            del self._rows[idx]
            self._refresh_rows_table()

    def _clear_rows(self):
        self._rows.clear()
        self._refresh_rows_table()
        self.tbl_cut.setRowCount(0)

    # ---------- Calcolo e aggregazione (componenti tipologia + parti meccanismo con override) ----------
    def _calc_and_aggregate(self):
        self.tbl_cut.setRowCount(0)
        if not self._rows:
            QMessageBox.information(self, "Commessa", "Aggiungi almeno una riga."); return

        # token profili (spessori)
        prof_tokens: Dict[str, float] = {}
        if self._profiles:
            try:
                for r in self._profiles.list_profiles():
                    n = str(r.get("name") or ""); th = float(r.get("thickness") or 0.0)
                    if n:
                        prof_tokens[sanitize_name(n)] = th
            except Exception:
                pass

        aggregated: Dict[str, Dict[Tuple[float, float, float], int]] = defaultdict(lambda: defaultdict(int))

        for r in self._rows:
            t = self._store.get_typology_full(int(r["tid"]))
            if not t:
                continue
            H = float(r["H"]); L = float(r["L"]); qty_row = int(r["qty"])
            env_base: Dict[str, Any] = {"H": H, "L": L}
            env_base.update(t.get("variabili_locali") or {})
            env_base.update(r.get("vars") or {})
            env_base.update(prof_tokens)

            # opzione ferramenta
            hw_opt_id = r.get("hw_option_id")
            opt = self._store.get_typology_hw_option(int(hw_opt_id)) if hw_opt_id else None
            if opt:
                if opt.get("handle_id"):
                    handle_offset = self._store.get_handle_offset(int(opt["handle_id"]))
                    if handle_offset is not None:
                        env_base["handle_offset"] = float(handle_offset)
                pick = self._store.pick_arm_for_width(int(opt["brand_id"]), int(opt["series_id"]), str(opt["subcat"]), L)
                if pick:
                    if pick.get("arm_code"): env_base["arm_code"] = str(pick["arm_code"])
                    if pick.get("arm_class"): env_base["arm_class"] = str(pick["arm_class"])
                    if pick.get("arm_len") is not None: env_base["arm_len"] = float(pick["arm_len"])

            # componenti tipologia
            comps = t.get("componenti") or []
            c_values: Dict[str, float] = {}
            for c in comps:
                prof = c.get("profilo_nome", "") or ""
                qty = int(c.get("quantita", 0) or 0) * qty_row
                angsx = float(c.get("ang_sx", 0.0) or 0.0)
                angdx = float(c.get("ang_dx", 0.0) or 0.0)
                expr = c.get("formula_lunghezza", "") or "H"
                offs = float(c.get("offset_mm", 0.0) or 0.0)
                env = dict(env_base); env.update(c_values)

                # override per opzione ferramenta su questo elemento
                if opt:
                    try:
                        f_override = self._store.get_comp_hw_formula(int(r["tid"]), str(c.get("id_riga", "")), int(opt["id"]))
                        if f_override and f_override.strip():
                            expr = f_override.strip()
                    except Exception:
                        pass

                try:
                    length = float(eval_formula(expr, env)) + offs
                except Exception:
                    length = 0.0
                if prof and qty > 0:
                    aggregated[prof][(round(length, 2), angsx, angdx)] += qty
                rid = c.get("id_riga", "")
                if rid:
                    c_values[f"C_{rid}"] = length

            # parti meccanismo (astine)
            if opt:
                mechanism = opt.get("mechanism_code") or None
                if mechanism:
                    parts = self._store.list_mech_parts(str(mechanism))
                    for p in parts:
                        env = dict(env_base)
                        # override per tipologia+opzione+part
                        try:
                            override = self._store.get_typology_mech_part_formula(int(r["tid"]), int(opt["id"]), p["part_key"])
                            formula = override.strip() if (override and override.strip()) else p["formula"]
                        except Exception:
                            formula = p["formula"]
                        try:
                            length = float(eval_formula(formula, env))
                        except Exception:
                            length = 0.0
                        prof = p["profile_name"] or "ASTINA"
                        q = int(p["qty"] or 1) * qty_row
                        aggregated[prof][(round(length, 2), float(p["ang_sx"] or 0.0), float(p["ang_dx"] or 0.0))] += q

        # popola tabella con aggregazione per profilo e lunghezza (decrescente)
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

    # ---------- Export/Import JSON (unchanged) ----------
    def _export_order(self):
        if not self._rows:
            QMessageBox.information(self, "Esporta", "La commessa è vuota."); return
        path, _ = QFileDialog.getSaveFileName(self, "Esporta commessa", "", "Commessa JSON (*.order.json)")
        if not path: return
        data = {"type": "blitz-order", "version": 1, "created_at": datetime.utcnow().isoformat() + "Z", "customer": (self.ed_customer.text() or ""), "rows": self._rows}
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
                self._rows.append({"tid": int(r["tid"]), "qty": int(r["qty"]), "H": float(r["H"]), "L": float(r["L"]), "vars": dict(r.get("vars") or {}), "hw_option_id": (int(r["hw_option_id"]) if r.get("hw_option_id") is not None else None)})
            except Exception:
                continue
        cust = data.get("customer") or ""
        self.ed_customer.setText(str(cust))
        self._refresh_rows_table()
