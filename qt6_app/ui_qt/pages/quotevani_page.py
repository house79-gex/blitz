from __future__ import annotations
from typing import Optional, Dict, Any, List
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QGroupBox
)

# Header opzionale
try:
    from ui_qt.widgets.header import Header
except Exception:
    Header = None

# DB tipologie + HW
from ui_qt.services.typologies_store import TypologiesStore, default_db_path

# Formula evaluator legacy
from ui_qt.services.legacy_formula import eval_formula, sanitize_name

# Profili spessori
try:
    from ui_qt.services.profiles_store import ProfilesStore
except Exception:
    ProfilesStore = None

# Calcolatori
from ui_qt.services.calculators import compute_lamelle, compute_astina_for_hw


class QuoteVaniPage(QFrame):
    def __init__(self, appwin):
        super().__init__()
        self.appwin = appwin
        self._store = TypologiesStore(str(default_db_path()))
        self._profiles = None
        if ProfilesStore:
            try:
                self._profiles = ProfilesStore()
            except Exception:
                self._profiles = None
        self._build()

    def _build(self):
        self.setStyleSheet("QFrame { border: 1px solid #3b4b5a; border-radius: 6px; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # Header
        if Header:
            root.addWidget(Header(self.appwin, "QUOTE VANI LUCE"), 0)
        else:
            title = QLabel("QUOTE VANI LUCE")
            title.setStyleSheet("font-size:18px; font-weight:700;")
            root.addWidget(title, 0)

        # Riga comandi
        top = QHBoxLayout()
        btn_home = QPushButton("Home")
        btn_home.setToolTip("Torna alla Home")
        btn_home.clicked.connect(self._go_home)
        top.addWidget(btn_home)

        top.addSpacing(10)
        top.addWidget(QLabel("H (mm):"))
        self.ed_h = QLineEdit(); self.ed_h.setPlaceholderText("Altezza"); self.ed_h.setFixedWidth(110)
        top.addWidget(self.ed_h)

        top.addWidget(QLabel("L (mm):"))
        self.ed_l = QLineEdit(); self.ed_l.setPlaceholderText("Larghezza"); self.ed_l.setFixedWidth(110)
        top.addWidget(self.ed_l)

        top.addSpacing(10)
        top.addWidget(QLabel("Tipologia:"))
        self.cmb_typ = QComboBox(); self.cmb_typ.setMinimumWidth(280)
        top.addWidget(self.cmb_typ, 1)

        self.btn_gen = QPushButton("Genera distinta")
        self.btn_gen.clicked.connect(self._generate)
        top.addWidget(self.btn_gen)

        root.addLayout(top)

        # Gruppo ferramenta
        hw = QGroupBox("Ferramenta (anta-ribalta opzionale)")
        hw_l = QHBoxLayout(hw)

        hw_l.addWidget(QLabel("Marca:"))
        self.cmb_brand = QComboBox(); self.cmb_brand.currentIndexChanged.connect(self._on_brand_changed)
        hw_l.addWidget(self.cmb_brand)

        hw_l.addWidget(QLabel("Serie:"))
        self.cmb_series = QComboBox(); self.cmb_series.currentIndexChanged.connect(self._on_series_changed)
        hw_l.addWidget(self.cmb_series)

        hw_l.addWidget(QLabel("Sottocategoria:"))
        self.cmb_subcat = QComboBox(); self.cmb_subcat.setToolTip("Es. battente_standard, battente_pesante …")
        hw_l.addWidget(self.cmb_subcat)

        hw_l.addWidget(QLabel("Maniglia:"))
        self.cmb_handle = QComboBox()
        hw_l.addWidget(self.cmb_handle)

        self.lbl_arm = QLabel("Braccio: —")
        self.lbl_arm.setStyleSheet("color:#7f8c8d;")
        hw_l.addWidget(self.lbl_arm, 1)

        root.addWidget(hw)

        # Tabella distinta
        self.tbl = QTableWidget(0, 7)
        self.tbl.setHorizontalHeaderLabels(["Tipo", "ID", "Nome", "Profilo", "Q.tà", "Lunghezza (mm)", "Angoli (°)"])
        hdr = self.tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(6, QHeaderView.Stretch)
        root.addWidget(self.tbl, 1)

        # Nota
        note = QLabel("Suggerimento: seleziona tipologia e (opzionale) ferramenta. Il calcolo lamelle/astine è automatico se applicabile.")
        note.setStyleSheet("color:#7f8c8d;")
        root.addWidget(note, 0)

        self._reload_typologies()
        self._reload_brands()

        # aggiorna braccio quando cambiano dati
        self.ed_l.textChanged.connect(self._refresh_arm_pick)
        self.cmb_subcat.currentIndexChanged.connect(self._refresh_arm_pick)
        self.cmb_series.currentIndexChanged.connect(self._refresh_arm_pick)
        self.cmb_brand.currentIndexChanged.connect(self._refresh_arm_pick)

    def _go_home(self):
        try:
            if hasattr(self.appwin, "show_page"):
                self.appwin.show_page("home")
            elif hasattr(self.appwin, "go_home"):
                self.appwin.go_home()
        except Exception:
            pass

    # ---------- Loaders ----------
    def _reload_typologies(self):
        self.cmb_typ.clear()
        rows = self._store.list_typologies()
        if not rows:
            self.cmb_typ.addItem("— Nessuna tipologia —", None)
        else:
            for r in rows:
                self.cmb_typ.addItem(str(r["name"]), int(r["id"]))

    def _reload_brands(self):
        self.cmb_brand.clear(); self.cmb_series.clear(); self.cmb_handle.clear(); self.cmb_subcat.clear()
        try:
            brands = self._store.list_hw_brands()
        except Exception:
            brands = []
        if not brands:
            self.cmb_brand.addItem("— Nessuna marca —", None)
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
            self.cmb_series.addItem("— Nessuna serie —", None)
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
            self.cmb_handle.addItem("— Nessuna maniglia —", None)
        else:
            for h in handles:
                label = f"{h['name']} ({h['handle_offset_mm']:.0f} mm)"
                self.cmb_handle.addItem(label, (int(h["id"]), float(h["handle_offset_mm"])))
        subcats = self._store.list_hw_sash_subcats(int(bid), int(sid))
        if not subcats:
            self.cmb_subcat.addItem("— Nessuna sottocategoria —", "")
        else:
            for sc in subcats:
                self.cmb_subcat.addItem(sc, sc)
        self._refresh_arm_pick()

    def _refresh_arm_pick(self):
        bid = self.cmb_brand.currentData(); sid = self.cmb_series.currentData(); subcat = self.cmb_subcat.currentData()
        try:
            L = float((self.ed_l.text() or "0").replace(",", "."))
        except Exception:
            L = 0.0
        if not (bid and sid and subcat and L > 0):
            self.lbl_arm.setText("Braccio: —"); return
        pick = self._store.pick_arm_for_width(int(bid), int(sid), str(subcat), L)
        if not pick:
            self.lbl_arm.setText("Braccio: — (nessuna regola)"); return
        self.lbl_arm.setText(f"Braccio: {pick['arm_code']} — {pick.get('arm_name','') or ''}")

    # ---------- Calcolo distinta ----------
    def _generate(self):
        # Pulisci output
        self.tbl.setRowCount(0)

        # Dati base
        try:
            H = float((self.ed_h.text() or "0").replace(",", "."))
            L = float((self.ed_l.text() or "0").replace(",", "."))
        except Exception:
            QMessageBox.warning(self, "Dati", "Inserisci H e L validi."); return

        tid = self.cmb_typ.currentData()
        if not tid:
            QMessageBox.warning(self, "Tipologia", "Seleziona una tipologia."); return

        tdata = self._store.get_typology_full(int(tid))
        if not tdata:
            QMessageBox.warning(self, "Tipologia", "Tipologia non trovata."); return

        # Ambiente formule: H/L + variabili locali + token profilo (spessori)
        env: Dict[str, Any] = {"H": H, "L": L}
        env.update(tdata.get("variabili_locali") or {})

        # Token profili: nome->spessore
        prof_tokens: Dict[str, float] = {}
        if self._profiles:
            try:
                rows = self._profiles.list_profiles()
                for r in rows:
                    n = str(r.get("name") or ""); th = float(r.get("thickness") or 0.0)
                    if n:
                        prof_tokens[sanitize_name(n)] = th
            except Exception:
                pass
        env.update(prof_tokens)

        # Valori C_Rx (componenti precedenti): li calcoliamo in sequenza
        components = tdata.get("componenti") or []

        # Prima riga: lamelle (persiana) se presenti opzioni/lamelle
        category = (tdata.get("categoria") or "").strip().lower()
        opts = tdata.get("options") or {}
        if category == "persiana":
            ruleset = (opts.get("lamelle_ruleset") or "").strip()
            if ruleset:
                try:
                    rules = self._store.list_lamella_rules(ruleset, "persiana")
                except Exception:
                    rules = []
                res = compute_lamelle(H, rules) if rules else {"count": 0, "pitch": None}
                if res["count"] > 0:
                    self._add_row("lamella", "-", f"Set lamelle {ruleset}", "-", res["count"], "-", f"pitch:{res['pitch'] or '-'}")

        # Componenti legacy
        c_values: Dict[str, float] = {}  # C_Rx -> length
        for c in components:
            rid = c.get("id_riga","") or ""
            name = c.get("nome","") or ""
            prof = c.get("profilo_nome","") or ""
            qty = int(c.get("quantita",0) or 0)
            angsx = float(c.get("ang_sx",0.0) or 0.0)
            angdx = float(c.get("ang_dx",0.0) or 0.0)
            expr = c.get("formula_lunghezza","") or "H"
            offs = float(c.get("offset_mm",0.0) or 0.0)

            # arricchisci env con C_Rprev
            env_local = dict(env)
            env_local.update(c_values)

            try:
                length = float(eval_formula(expr, env_local)) + offs
            except Exception as e:
                length = 0.0

            self._add_row("comp", rid, name, prof, qty, f"{length:.2f}", f"{angsx:.1f}/{angdx:.1f}")

            if rid:
                c_values[f"C_{rid}"] = length

        # Astine anta-ribalta (se hardware selezionato e sottocategoria presente)
        bid = self.cmb_brand.currentData(); sid = self.cmb_series.currentData(); subcat = self.cmb_subcat.currentData()
        handle_data = self.cmb_handle.currentData()
        handle_offset = float(handle_data[1]) if (isinstance(handle_data, tuple) and len(handle_data) > 1) else None

        if bid and sid and subcat and handle_offset is not None:
            arm = self._store.pick_arm_for_width(int(bid), int(sid), str(subcat), L)
            arm_code = arm["arm_code"] if arm else None
            formula = self._store.get_astina_formula(int(bid), int(sid), str(subcat), arm_code)
            if formula:
                try:
                    ast_len = compute_astina_for_hw(H, L, handle_offset, formula)
                    self._add_row("astina", "-", f"Astina AR ({arm_code or '—'})", "-", 2, f"{ast_len:.2f}", "-")
                except Exception:
                    pass

    def _add_row(self, tipo: str, rid: str, nome: str, profilo: str, qta: Any, lung: Any, angoli: Any):
        r = self.tbl.rowCount(); self.tbl.insertRow(r)
        self.tbl.setItem(r, 0, QTableWidgetItem(str(tipo)))
        self.tbl.setItem(r, 1, QTableWidgetItem(str(rid)))
        self.tbl.setItem(r, 2, QTableWidgetItem(str(nome)))
        self.tbl.setItem(r, 3, QTableWidgetItem(str(profilo)))
        self.tbl.setItem(r, 4, QTableWidgetItem(str(qta)))
        self.tbl.setItem(r, 5, QTableWidgetItem(str(lung)))
        self.tbl.setItem(r, 6, QTableWidgetItem(str(angoli)))
