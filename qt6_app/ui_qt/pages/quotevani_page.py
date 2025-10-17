from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple
from collections import defaultdict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QGroupBox, QWidget
)

try:
    from ui_qt.widgets.header import Header
except Exception:
    Header = None

from ui_qt.services.typologies_store import TypologiesStore, default_db_path
from ui_qt.services.legacy_formula import eval_formula, sanitize_name
from ui_qt.dialogs.vars_editor_qt import VarsEditorDialog

try:
    from ui_qt.services.profiles_store import ProfilesStore
except Exception:
    ProfilesStore = None


class QuoteVaniPage(QFrame):
    """
    Commessa:
    - Aggiungi più righe (tipologia, pezzi, H, L, variabili riga, ferramenta riga opzionale)
    - Calcola elenco taglio aggregato per profilo, ordinato per lunghezza decrescente
    - Invia ad 'automatico'
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
        self._reload_typologies()
        self._reload_brands()

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

        # Helper per input con label sopra
        def vfield(label: str, widget: QWidget, minw: int = 100) -> QWidget:
            w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(0,0,0,0); l.setSpacing(4)
            lab = QLabel(label); lab.setStyleSheet("color:#7f8c8d; font-size:11px;")
            l.addWidget(lab, 0); widget.setMinimumWidth(minw); l.addWidget(widget, 0)
            return w

        # Aggiungi riga commessa (label sopra agli input, testi brevi)
        gb = QGroupBox("Aggiungi riga")
        gl = QHBoxLayout(gb); gl.setSpacing(12)

        self.cmb_typ = QComboBox(); self.cmb_typ.setMinimumWidth(200)
        gl.addWidget(vfield("Tipologia", self.cmb_typ, 200))

        self.sp_qty = QSpinBox(); self.sp_qty.setRange(1, 999); self.sp_qty.setValue(1)
        gl.addWidget(vfield("Pezzi", self.sp_qty, 80))

        self.ed_h = QLineEdit(); self.ed_h.setPlaceholderText("mm")
        gl.addWidget(vfield("H (mm)", self.ed_h, 100))

        self.ed_l = QLineEdit(); self.ed_l.setPlaceholderText("mm")
        gl.addWidget(vfield("L (mm)", self.ed_l, 100))

        self.btn_vars = QPushButton("Apri")
        self.btn_vars.setToolTip("Variabili riga")
        self.btn_vars.clicked.connect(self._edit_row_vars)
        gl.addWidget(vfield("Variabili", self.btn_vars, 80))

        # Ferramenta riga opzionale
        self.cmb_brand = QComboBox()
        self.cmb_brand.currentIndexChanged.connect(self._on_brand_changed)
        gl.addWidget(vfield("Marca", self.cmb_brand, 150))

        self.cmb_series = QComboBox()
        self.cmb_series.currentIndexChanged.connect(self._on_series_changed)
        gl.addWidget(vfield("Serie", self.cmb_series, 150))

        self.cmb_subcat = QComboBox()
        gl.addWidget(vfield("Sottocat.", self.cmb_subcat, 150))

        self.cmb_handle = QComboBox()
        gl.addWidget(vfield("Maniglia", self.cmb_handle, 180))

        self.btn_add = QPushButton("Aggiungi")
        self.btn_add.clicked.connect(self._add_row)
        gl.addWidget(vfield(" ", self.btn_add, 110))

        root.addWidget(gb)

        # Tabella righe
        self.tbl_rows = QTableWidget(0, 7)
        self.tbl_rows.setHorizontalHeaderLabels(["#", "Tipologia", "Pezzi", "H", "L", "Ferramenta", "Variabili"])
        hdr = self.tbl_rows.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.Stretch)
        hdr.setSectionResizeMode(6, QHeaderView.Stretch)
        root.addWidget(self.tbl_rows)

        # Azioni righe
        rr = QHBoxLayout()
        btn_del = QPushButton("Rimuovi riga"); btn_del.clicked.connect(self._del_row)
        btn_clr = QPushButton("Svuota"); btn_clr.clicked.connect(self._clear_rows)
        rr.addWidget(btn_del); rr.addWidget(btn_clr); rr.addStretch(1)
        root.addLayout(rr)

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

        hint = QLabel("Aggiungi righe con dati essenziali (Tipologia, Pezzi, H, L). Ferramenta/Variabili sono opzionali.")
        hint.setStyleSheet("color:#7f8c8d;")
        root.addWidget(hint, 0)

        self._cur_row_vars: Dict[str, float] = {}

    def _reload_typologies(self):
        self.cmb_typ.clear()
        rows = self._store.list_typologies()
        if not rows:
            self.cmb_typ.addItem("— Nessuna —", None)
            return
        for r in rows:
            self.cmb_typ.addItem(str(r["name"]), int(r["id"]))

    def _reload_brands(self):
        self.cmb_brand.clear(); self.cmb_series.clear(); self.cmb_handle.clear(); self.cmb_subcat.clear()
        try:
            brands = self._store.list_hw_brands()
        except Exception:
            brands = []
        if not brands:
            self.cmb_brand.addItem("—", None)
        else:
            for b in brands:
                self.cmb_brand.addItem(b["name"], int(b["id"]))
        self._on_brand_changed()

    def _on_brand_changed(self):
        self.cmb_series.clear(); self.cmb_handle.clear(); self.cmb_subcat.clear()
        bid = self.cmb_brand.currentData()
        if not bid:
            self.cmb_series.addItem("—", None); self.cmb_handle.addItem("—", None); self.cmb_subcat.addItem("—", None); return
        series = self._store.list_hw_series(int(bid))
        if not series:
            self.cmb_series.addItem("—", None)
        else:
            for s in series:
                self.cmb_series.addItem(s["name"], int(s["id"]))
        self._on_series_changed()

    def _on_series_changed(self):
        self.cmb_handle.clear(); self.cmb_subcat.clear()
        bid = self.cmb_brand.currentData(); sid = self.cmb_series.currentData()
        if not (bid and sid): 
            self.cmb_handle.addItem("—", None); self.cmb_subcat.addItem("—", None); return
        handles = self._store.list_hw_handle_types(int(bid), int(sid))
        if not handles:
            self.cmb_handle.addItem("—", None)
        else:
            for h in handles:
                label = f"{h['name']} ({h['handle_offset_mm']:.0f} mm)"
                self.cmb_handle.addItem(label, int(h["id"]))
        subcats = self._store.list_hw_sash_subcats(int(bid), int(sid))
        if not subcats:
            self.cmb_subcat.addItem("—", "")
        else:
            for sc in subcats:
                self.cmb_subcat.addItem(sc, sc)

    def _edit_row_vars(self):
        dlg = VarsEditorDialog(self, base=self._cur_row_vars)
        if dlg.exec():
            self._cur_row_vars = dlg.result_vars()

    def _add_row(self):
        tid = self.cmb_typ.currentData()
        if not tid:
            QMessageBox.warning(self, "Tipologia", "Seleziona una tipologia."); return
        try:
            H = float((self.ed_h.text() or "0").replace(",", "."))
            L = float((self.ed_l.text() or "0").replace(",", "."))
        except Exception:
            QMessageBox.warning(self, "Dati", "Inserisci H e L validi."); return
        qty = int(self.sp_qty.value())

        r_bid = self.cmb_brand.currentData(); r_sid = self.cmb_series.currentData()
        r_subc = self.cmb_subcat.currentData(); r_hid = self.cmb_handle.currentData()

        row = {
            "tid": int(tid),
            "qty": qty,
            "H": H,
            "L": L,
            "vars": dict(self._cur_row_vars),
            "hw": {
                "brand_id": int(r_bid) if r_bid else None,
                "series_id": int(r_sid) if r_sid else None,
                "subcat": str(r_subc) if r_subc else "",
                "handle_id": int(r_hid) if r_hid else None
            }
        }
        self._rows.append(row)
        self._cur_row_vars = {}
        self._refresh_rows_table()

    def _refresh_rows_table(self):
        self.tbl_rows.setRowCount(0)
        for i, r in enumerate(self._rows, start=1):
            hw_txt = "-"
            if r["hw"]["brand_id"]:
                hw_txt = f"B{r['hw']['brand_id']}/S{r['hw']['series_id']}/{r['hw']['subcat'] or '-'} H:{r['hw']['handle_id'] or '-'}"
            vars_txt = "; ".join(f"{k}={v}" for k, v in sorted((r.get("vars") or {}).items()))
            ri = self.tbl_rows.rowCount(); self.tbl_rows.insertRow(ri)
            self.tbl_rows.setItem(ri, 0, QTableWidgetItem(str(i)))
            tdata = self._store.get_typology_full(int(r["tid"]))
            self.tbl_rows.setItem(ri, 1, QTableWidgetItem(str(tdata["nome"] if tdata else r["tid"])))
            self.tbl_rows.setItem(ri, 2, QTableWidgetItem(str(r["qty"])))
            self.tbl_rows.setItem(ri, 3, QTableWidgetItem(f"{r['H']:.1f}"))
            self.tbl_rows.setItem(ri, 4, QTableWidgetItem(f"{r['L']:.1f}"))
            self.tbl_rows.setItem(ri, 5, QTableWidgetItem(hw_txt))
            self.tbl_rows.setItem(ri, 6, QTableWidgetItem(vars_txt))

    def _del_row(self):
        idx = self.tbl_rows.currentRow()
        if idx < 0: return
        if 0 <= idx < len(self._rows):
            del self._rows[idx]
            self._refresh_rows_table()

    def _clear_rows(self):
        self._rows.clear(); self._refresh_rows_table()
        self.tbl_cut.setRowCount(0)

    def _calc_and_aggregate(self):
        self.tbl_cut.setRowCount(0)
        if not self._rows:
            QMessageBox.information(self, "Commessa", "Aggiungi almeno una riga."); return

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

            # Componenti tipologia
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
        self._reload_typologies()
        self._reload_brands()
