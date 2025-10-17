from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple
from collections import defaultdict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox
)

try:
    from ui_qt.widgets.header import Header
except Exception:
    Header = None

from ui_qt.services.typologies_store import TypologiesStore, default_db_path
from ui_qt.services.legacy_formula import eval_formula, sanitize_name

try:
    from ui_qt.services.profiles_store import ProfilesStore
except Exception:
    ProfilesStore = None

# Modali per aggiungere riga
from ui_qt.dialogs.order_row_typology_qt import OrderRowTypologyDialog
from ui_qt.dialogs.order_row_dims_qt import OrderRowDimsDialog
from ui_qt.dialogs.order_row_hw_qt import OrderRowHardwareDialog


class QuoteVaniPage(QFrame):
    """
    Commessa:
    - Pulsante 'Aggiungi riga' → 3 modali in sequenza: Tipologia → Dati (pezzi,H,L,vars) → Opzione ferramenta
    - Calcolo elenco taglio aggregato per profilo (discendente)
    - Invio ad 'automatico'
    """
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self._store = TypologiesStore(str(default_db_path()))
        self._profiles = None
        if ProfilesStore:
            try: self._profiles = ProfilesStore()
            except Exception: self._profiles = None

        self._rows: List[Dict[str, Any]] = []

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

        # Azioni commessa
        btn_add = QPushButton("Aggiungi riga…"); btn_add.clicked.connect(self._add_row_wizard)
        root.addWidget(btn_add, 0)

        # Tabella righe commessa
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

        # Calcolo/Invio
        act = QHBoxLayout()
        btn_calc = QPushButton("Calcola lista taglio"); btn_calc.clicked.connect(self._calc_and_aggregate)
        btn_send = QPushButton("Invia ad Automatico"); btn_send.clicked.connect(self._send_to_automatico)
        act.addWidget(btn_calc); act.addWidget(btn_send); act.addStretch(1)
        root.addLayout(act)

        # Elenco taglio
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

        hint = QLabel("Aggiungi righe tramite la finestra modale. La scelta ferramenta è per-riga ed usa le opzioni definite in Tipologie.")
        hint.setStyleSheet("color:#7f8c8d;")
        root.addWidget(hint, 0)

    def _add_row_wizard(self):
        # 1) Tipologia
        d1 = OrderRowTypologyDialog(self, self._store)
        if not d1.exec():
            return
        typ_id = int(d1.typology_id)

        # 2) Dati (qty,H,L,vars)
        d2 = OrderRowDimsDialog(self)
        if not d2.exec():
            return

        # 3) Opzione ferramenta (facolt.)
        d3 = OrderRowHardwareDialog(self, self._store, typ_id)
        d3.exec()  # anche se annullata, proseguiamo con None

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
                if opt: hw_txt = opt["name"]
            ri = self.tbl_rows.rowCount(); self.tbl_rows.insertRow(ri)
            self.tbl_rows.setItem(ri, 0, QTableWidgetItem(str(i)))
            self.tbl_rows.setItem(ri, 1, QTableWidgetItem(str(name)))
            self.tbl_rows.setItem(ri, 2, QTableWidgetItem(str(r["qty"])))
            self.tbl_rows.setItem(ri, 3, QTableWidgetItem(f"{r['H']:.1f}"))
            self.tbl_rows.setItem(ri, 4, QTableWidgetItem(f"{r['L']:.1f}"))
            self.tbl_rows.setItem(ri, 5, QTableWidgetItem(hw_txt))

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

            # Se è stata scelta una opzione ferramenta, prepara dati utili (handle_offset, arm_code)
            hw_opt_id = r.get("hw_option_id")
            handle_offset = None
            arm_code = None
            if hw_opt_id:
                opt = self._store.get_typology_hw_option(int(hw_opt_id))
                if opt:
                    if opt.get("handle_id"):
                        handle_offset = self._store.get_handle_offset(int(opt["handle_id"]))
                        if handle_offset is not None:
                            env_base["handle_offset"] = float(handle_offset)
                    # pick braccio per L
                    pick = self._store.pick_arm_for_width(int(opt["brand_id"]), int(opt["series_id"]), str(opt["subcat"]), L)
                    if pick:
                        arm_code = pick["arm_code"]
                        env_base["arm_code"] = str(arm_code)

            # Componenti – per ciascuno, se esiste un override formula per questa opzione, usalo
            comps = t.get("componenti") or []
            c_values: Dict[str, float] = {}
            for c in comps:
                prof = c.get("profilo_nome","") or ""
                qty = int(c.get("quantita",0) or 0) * qty_row
                angsx = float(c.get("ang_sx",0.0) or 0.0)
                angdx = float(c.get("ang_dx",0.0) or 0.0)
                expr = c.get("formula_lunghezza","") or "H"
                offs = float(c.get("offset_mm",0.0) or 0.0)
                env = dict(env_base); env.update(c_values)

                # override per opzione ferramenta su questo elemento
                if hw_opt_id:
                    f_override = self._store.get_comp_hw_formula(int(r["tid"]), str(c.get("id_riga","")), int(hw_opt_id))
                    if f_override and f_override.strip():
                        expr = f_override.strip()

                try:
                    length = float(eval_formula(expr, env)) + offs
                except Exception:
                    length = 0.0
                if prof and qty > 0:
                    aggregated[prof][(round(length, 2), angsx, angdx)] += qty
                rid = c.get("id_riga","")
                if rid:
                    c_values[f"C_{rid}"] = length

        # riempi tabella per profilo, lunghezza desc
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

    def _send_to_automatico(self):
        rows = []
        for r in range(self.tbl_cut.rowCount()):
            prof = self.tbl_cut.item(r, 0).text()
            length = float(self.tbl_cut.item(r, 1).text())
            ax = float(self.tbl_cut.item(r, 2).text())
            ad = float(self.tbl_cut.item(r, 3).text())
            qty = int(self.tbl_cut.item(r, 4).text())
            rows.append({
                "profile": prof,
                "length_mm": length,
                "ang_sx": ax,
                "ang_dx": ad,
                "qty": qty,
                "note": self.tbl_cut.item(r, 5).text() if self.tbl_cut.item(r, 5) else ""
            })
        if not rows:
            QMessageBox.information(self, "Automatico", "Nessun elemento da inviare."); return
        try:
            mq = getattr(self.appwin.machine, "work_queue", None)
            if isinstance(mq, list):
                mq.clear()
                mq.extend(rows)
                if hasattr(self.appwin.machine, "current_work_idx"):
                    self.appwin.machine.current_work_idx = 0
            if hasattr(self.appwin, "show_page"):
                self.appwin.show_page("automatico")
        except Exception:
            pass

    def on_show(self):
        # niente da ricaricare – si lavora via modali
        pass
