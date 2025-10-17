from __future__ import annotations
from typing import Dict, Any, List, Optional, Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QComboBox,
    QPushButton, QTableWidget, QTableWidgetItem, QSpinBox, QDoubleSpinBox,
    QGroupBox, QMessageBox, QHeaderView, QCheckBox
)

from ui_qt.services.legacy_formula import scan_variables, eval_formula, sanitize_name

# DB profili (spessori)
try:
    from ui_qt.services.profiles_store import ProfilesStore
except Exception:
    ProfilesStore = None  # type: ignore

# DB tipologie (lamelle/opzioni + ferramenta)
try:
    from ui_qt.services.typologies_store import TypologiesStore, default_db_path
except Exception:
    TypologiesStore = None  # type: ignore
    default_db_path = lambda: Path.cwd() / "typologies.db"  # type: ignore

# Gestione catalogo ferramenta (CRUD)
try:
    from ui_qt.dialogs.hardware_manager_qt import HardwareManagerDialog
except Exception:
    HardwareManagerDialog = None  # type: ignore


def _profiles_map() -> Dict[str, float]:
    try:
        store = ProfilesStore()
        return {str(r.get("name") or ""): float(r.get("thickness") or 0.0) for r in store.list_profiles()}
    except Exception:
        return {}


def _abbrev_token(s: str, maxlen: int = 10) -> str:
    s = str(s or "")
    if len(s) <= maxlen:
        return s
    return s[:maxlen - 1] + "…"


class ComponentEditorDialog(QDialog):
    """
    Editor componente:
    - Token rapidi H/L + variabili locali abbreviate (tooltip con nome completo e valore)
    - Token profilo con spessore in tooltip
    - Token componenti C_Rx con tooltip (nome componente)
    - Pulsanti 0°/45° + scorciatoie Alt+0 / Alt+5
    - Usa var_provider() per leggere le variabili correnti dall'editor padre
    """
    def __init__(self, parent, base: Dict[str, Any],
                 prev_components: List[Dict[str, Any]],
                 profiles: Dict[str, float],
                 var_provider: Optional[Callable[[], Dict[str, float]]] = None):
        super().__init__(parent)
        self.setWindowTitle("Componente")
        self.setModal(True)
        self.resize(940, 640)
        self.setMinimumSize(860, 560)

        self.base = dict(base)
        self.prev_components = prev_components
        self.profiles = profiles
        self.var_provider = var_provider
        self.created = False

        self._build()
        self._install_shortcuts()

    def _build(self):
        root = QVBoxLayout(self)

        g = QGridLayout(); g.setHorizontalSpacing(12); g.setVerticalSpacing(8)
        row = 0

        g.addWidget(QLabel("ID riga:"), row, 0)
        self.ed_id = QLineEdit(self.base.get("id_riga", "")); self.ed_id.setReadOnly(True)
        g.addWidget(self.ed_id, row, 1); row += 1

        g.addWidget(QLabel("Nome:"), row, 0)
        self.ed_name = QLineEdit(self.base.get("nome", "")); g.addWidget(self.ed_name, row, 1, 1, 3); row += 1

        g.addWidget(QLabel("Profilo:"), row, 0)
        self.cmb_prof = QComboBox()
        names = sorted(self.profiles.keys()); self.cmb_prof.addItem("")
        for n in names: self.cmb_prof.addItem(n)
        if self.base.get("profilo_nome"):
            idx = self.cmb_prof.findText(self.base["profilo_nome"]); 
            if idx >= 0: self.cmb_prof.setCurrentIndex(idx)
        g.addWidget(self.cmb_prof, row, 1)
        self.lbl_token = QLabel(""); self.lbl_token.setStyleSheet("color:#7f8c8d;")
        g.addWidget(self.lbl_token, row, 2, 1, 2); row += 1

        g.addWidget(QLabel("Quantità:"), row, 0)
        self.sp_qta = QSpinBox(); self.sp_qta.setRange(0, 999); self.sp_qta.setValue(int(self.base.get("quantita", 1) or 1))
        g.addWidget(self.sp_qta, row, 1); row += 1

        g.addWidget(QLabel("Angolo SX (°):"), row, 0)
        self.sp_ang_sx = QDoubleSpinBox(); self.sp_ang_sx.setRange(0.0, 90.0); self.sp_ang_sx.setDecimals(2); self.sp_ang_sx.setSingleStep(0.5)
        self.sp_ang_sx.setValue(float(self.base.get("ang_sx", 0.0) or 0.0)); g.addWidget(self.sp_ang_sx, row, 1)
        row_sx = QHBoxLayout(); b0sx = QPushButton("0°"); b45sx = QPushButton("45°")
        b0sx.setToolTip("Imposta 0°"); b45sx.setToolTip("Imposta 45°")
        b0sx.clicked.connect(lambda: self.sp_ang_sx.setValue(0.0)); b45sx.clicked.connect(lambda: self.sp_ang_sx.setValue(45.0))
        row_sx.addWidget(b0sx); row_sx.addWidget(b45sx); row_sx.addStretch(1)
        g.addLayout(row_sx, row, 2, 1, 2); row += 1

        g.addWidget(QLabel("Angolo DX (°):"), row, 0)
        self.sp_ang_dx = QDoubleSpinBox(); self.sp_ang_dx.setRange(0.0, 90.0); self.sp_ang_dx.setDecimals(2); self.sp_ang_dx.setSingleStep(0.5)
        self.sp_ang_dx.setValue(float(self.base.get("ang_dx", 0.0) or 0.0)); g.addWidget(self.sp_ang_dx, row, 1)
        row_dx = QHBoxLayout(); b0dx = QPushButton("0°"); b45dx = QPushButton("45°")
        b0dx.setToolTip("Imposta 0°"); b45dx.setToolTip("Imposta 45°")
        b0dx.clicked.connect(lambda: self.sp_ang_dx.setValue(0.0)); b45dx.clicked.connect(lambda: self.sp_ang_dx.setValue(45.0))
        row_dx.addWidget(b0dx); row_dx.addWidget(b45dx); row_dx.addStretch(1)
        g.addLayout(row_dx, row, 2, 1, 2); row += 1

        g.addWidget(QLabel("Offset (mm):"), row, 0)
        self.sp_off = QDoubleSpinBox(); self.sp_off.setRange(-1e6, 1e6); self.sp_off.setDecimals(3); self.sp_off.setSingleStep(0.1)
        self.sp_off.setValue(float(self.base.get("offset_mm", 0.0) or 0.0)); g.addWidget(self.sp_off, row, 1); row += 1

        g.addWidget(QLabel("Formula lunghezza:"), row, 0)
        self.ed_formula = QLineEdit(self.base.get("formula_lunghezza", "H")); g.addWidget(self.ed_formula, row, 1, 1, 3); row += 1

        # Token bar: H/L, var locali abbreviate, C_Rx
        token_bar = QHBoxLayout()
        lbl = QLabel("Token:"); lbl.setStyleSheet("color:#7f8c8d;"); token_bar.addWidget(lbl)
        # H/L
        for t, tip in (("H","Altezza finita"), ("L","Larghezza finita")):
            b = QPushButton(t); b.setToolTip(tip); b.clicked.connect(lambda _=None, v=t: self._ins_token(v)); token_bar.addWidget(b)
        # Variabili locali (abbreviate a schermo, tooltip completo)
        token_bar.addWidget(QLabel("Variabili:"))
        var_map = (self.var_provider() or {}) if self.var_provider else {}
        for k in sorted(var_map.keys()):
            label = _abbrev_token(k, 10)
            b = QPushButton(label)
            b.setToolTip(f"{k} = {var_map.get(k)}")
            b.clicked.connect(lambda _=None, v=k: self._ins_token(v))
            token_bar.addWidget(b)
        # Componenti precedenti
        token_bar.addWidget(QLabel("Componenti prec.:"))
        for c in self.prev_components:
            rid = c.get("id_riga",""); nm = c.get("nome","")
            if rid:
                t = f"C_{rid}"
                b = QPushButton(_abbrev_token(t, 10))
                b.setToolTip(f"{t} → {nm}")
                b.clicked.connect(lambda _=None, v=t: self._ins_token(v))
                token_bar.addWidget(b)

        token_bar.addStretch(1)

        root.addLayout(g); root.addLayout(token_bar)

        # Test formula
        test_box = QGroupBox("Test formula")
        tb = QVBoxLayout(test_box)
        tb.addWidget(QLabel("Valori test es: H=1500; L=900; TOKEN_PROFILO=60"))
        self.ed_test = QLineEdit(); tb.addWidget(self.ed_test)
        self.lbl_test = QLabel("Risultato: —"); tb.addWidget(self.lbl_test)
        rowt = QHBoxLayout()
        btn_an = QPushButton("Analizza"); btn_an.clicked.connect(self._analyze)
        btn_ts = QPushButton("Valuta"); btn_ts.clicked.connect(self._try_eval)
        rowt.addWidget(btn_an); rowt.addWidget(btn_ts); rowt.addStretch(1)
        tb.addLayout(rowt)
        root.addWidget(test_box)

        root.addWidget(QLabel("Note:"))
        self.ed_note = QLineEdit(self.base.get("note", "")); root.addWidget(self.ed_note)

        acts = QHBoxLayout()
        btn_cancel = QPushButton("Annulla"); btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("Salva"); btn_ok.clicked.connect(self._save)
        acts.addWidget(btn_cancel); acts.addWidget(btn_ok); acts.addStretch(1)
        root.addLayout(acts)

        self._update_prof_token()
        self.cmb_prof.currentIndexChanged.connect(self._update_prof_token)

    def _install_shortcuts(self):
        sc0 = QShortcut(QKeySequence("Alt+0"), self)
        sc0.activated.connect(lambda: (self.sp_ang_sx.setValue(0.0), self.sp_ang_dx.setValue(0.0)))
        sc45 = QShortcut(QKeySequence("Alt+5"), self)
        sc45.activated.connect(lambda: (self.sp_ang_sx.setValue(45.0), self.sp_ang_dx.setValue(45.0)))

    def _ins_token(self, tok: str):
        if not tok: return
        t = self.ed_formula.text() or ""
        sep = "" if (not t or t.endswith(("+","-","*","/","("," "))) else ""
        self.ed_formula.setText(t + sep + tok)

    def _update_prof_token(self):
        p = self.cmb_prof.currentText().strip()
        if p:
            th = self.profiles.get(p, None)
            tip = f"Token profilo: {sanitize_name(p)}"
            if th is not None: tip += f" (spessore={th} mm)"
            self.lbl_token.setText(tip)
        else:
            self.lbl_token.setText("")

    def _env_vars(self) -> Dict[str, float]:
        return dict(self.var_provider() or {})

    def _build_env(self) -> Dict[str, Any]:
        env: Dict[str, Any] = {"H": 1000.0, "L": 1000.0}
        env.update(self._env_vars())
        p = self.cmb_prof.currentText().strip()
        if p and p in self.profiles:
            env[sanitize_name(p)] = float(self.profiles[p])
        for c in self.prev_components:
            rid = c.get("id_riga","")
            if rid: env[f"C_{rid}"] = 1000.0
        raw = (self.ed_test.text() or "").strip()
        if raw:
            for pair in [x.strip() for x in raw.split(";") if x.strip()]:
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    try: env[k.strip()] = float(v.strip().replace(",", "."))
                    except Exception: pass
        return env

    def _analyze(self):
        try:
            names = scan_variables(self.ed_formula.text().strip())
            self.lbl_test.setText("Variabili: " + (", ".join(names) if names else "(nessuna)"))
        except Exception as e:
            self.lbl_test.setText(f"Errore parse: {e}")

    def _try_eval(self):
        try:
            val = eval_formula(self.ed_formula.text().strip(), self._build_env())
            self.lbl_test.setText(f"Risultato: {val:.3f}")
        except Exception as e:
            self.lbl_test.setText(f"Errore: {e}")

    def _save(self):
        name = (self.ed_name.text() or "").strip() or "Senza Nome"
        prof = (self.cmb_prof.currentText() or "").strip()
        qta = int(self.sp_qta.value())
        angsx = float(self.sp_ang_sx.value())
        angdx = float(self.sp_ang_dx.value())
        offs = float(self.sp_off.value())
        form = (self.ed_formula.text() or "H").strip()
        note = (self.ed_note.text() or "").strip()
        if not (0.0 <= angsx <= 90.0 and 0.0 <= angdx <= 90.0):
            QMessageBox.warning(self, "Angoli", "Angoli fuori range (0-90)."); return
        self.base.update({
            "nome": name, "profilo_nome": prof, "quantita": qta,
            "ang_sx": angsx, "ang_dx": angdx, "formula_lunghezza": form,
            "offset_mm": offs, "note": note
        })
        self.created = True
        self.accept()

    def result_component(self) -> Dict[str, Any]:
        return dict(self.base)


class TipologiaEditorDialog(QDialog):
    """
    Editor tipologia (legacy):
    - Massimizzata all'apertura
    - Variabili locali CRUD (visibili nel componente con token abbreviati + tooltip)
    - Opzioni:
      - persiana: schema lamelle
      - astine/battente: selezione Ferramenta (Marca/Serie/Sottocategoria/Maniglia) + pulsante "Gestisci ferramenta…"
    """
    def __init__(self, parent, base: Optional[Dict[str, Any]] = None, is_new: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Nuova Tipologia" if is_new else "Modifica Tipologia")
        self.setModal(True)
        # finestra massimizzata: evita pulsanti fuori dallo schermo
        self.setWindowState(Qt.WindowMaximized)

        self.base = dict(base or {})
        self.is_new = is_new
        self.profiles = _profiles_map()

        # Store per lamelle/opzioni + ferramenta
        try:
            self._store = TypologiesStore(str(default_db_path()))
        except Exception:
            self._store = None

        self._build()
        self._load_base()

    def _build(self):
        root = QVBoxLayout(self)

        meta = QGridLayout(); meta.setHorizontalSpacing(12); meta.setVerticalSpacing(6); row = 0
        lbl_nome = QLabel("Nome tipologia:"); lbl_nome.setWordWrap(True); meta.addWidget(lbl_nome, row, 0)
        self.ed_name = QLineEdit(); meta.addWidget(self.ed_name, row, 1, 1, 3); row += 1

        meta.addWidget(QLabel("Categoria:"), row, 0)
        self.ed_cat = QLineEdit(); meta.addWidget(self.ed_cat, row, 1)
        meta.addWidget(QLabel("Materiale:"), row, 2)
        self.ed_mat = QLineLineEdit := QLineEdit(); meta.addWidget(self.ed_mat, row, 3); row += 1  # noqa

        meta.addWidget(QLabel("Riferimento quota:"), row, 0)
        self.cmb_rif = QComboBox(); self.cmb_rif.addItems(["esterna","interna"]); meta.addWidget(self.cmb_rif, row, 1)
        meta.addWidget(QLabel("Extra detrazione (mm):"), row, 2)
        self.sp_extra = QDoubleSpinBox(); self.sp_extra.setRange(-1e6, 1e6); self.sp_extra.setDecimals(3); meta.addWidget(self.sp_extra, row, 3); row += 1

        meta.addWidget(QLabel("Pezzi totali:"), row, 0)
        self.sp_pezzi = QSpinBox(); self.sp_pezzi.setRange(1, 999); meta.addWidget(self.sp_pezzi, row, 1)
        meta.addWidget(QLabel("Note:"), row, 2)
        self.ed_note = QLineEdit(); meta.addWidget(self.ed_note, row, 3); row += 1

        # Opzioni categoria-specifiche
        self.grp_opts = QGroupBox("Opzioni tipologia"); og = QGridLayout(self.grp_opts); og.setHorizontalSpacing(10); og.setVerticalSpacing(6)
        # Persiana: schema lamelle
        og.addWidget(QLabel("Schema lamelle (persiana):"), 0, 0)
        self.cmb_lamella = QComboBox(); self.cmb_lamella.setToolTip("Schema lamelle per persiane (range H → n. lamelle)")
        og.addWidget(self.cmb_lamella, 0, 1)
        # Ferramenta (astine/battente)
        rowo = 1
        og.addWidget(QLabel("Ferramenta (astine/battente):"), rowo, 0, 1, 2)
        rowo += 1
        og.addWidget(QLabel("Marca:"), rowo, 0); self.cmb_brand = QComboBox(); og.addWidget(self.cmb_brand, rowo, 1); rowo += 1
        og.addWidget(QLabel("Serie:"), rowo, 0); self.cmb_series = QComboBox(); og.addWidget(self.cmb_series, rowo, 1); rowo += 1
        og.addWidget(QLabel("Sottocategoria:"), rowo, 0); self.cmb_subcat = QComboBox(); og.addWidget(self.cmb_subcat, rowo, 1); rowo += 1
        og.addWidget(QLabel("Maniglia:"), rowo, 0); self.cmb_handle = QComboBox(); og.addWidget(self.cmb_handle, rowo, 1); rowo += 1
        self.btn_hw_manage = QPushButton("Gestisci ferramenta…"); og.addWidget(self.btn_hw_manage, rowo, 0, 1, 2); rowo += 1

        self.grp_opts.setVisible(False)

        root.addLayout(meta)
        root.addWidget(self.grp_opts)

        # Variabili locali
        root.addWidget(QLabel("Variabili locali (nome → valore):"))
        self.tbl_vars = QTableWidget(0, 2)
        self.tbl_vars.setHorizontalHeaderLabels(["Nome","Valore"])
        self.tbl_vars.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl_vars.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        root.addWidget(self.tbl_vars)

        rowv = QHBoxLayout()
        btn_add_v = QPushButton("Aggiungi variabile"); btn_add_v.clicked.connect(self._add_var)
        btn_del_v = QPushButton("Elimina"); btn_del_v.clicked.connect(self._del_var)
        rowv.addWidget(btn_add_v); rowv.addWidget(btn_del_v); rowv.addStretch(1)
        root.addLayout(rowv)

        # Componenti
        root.addWidget(QLabel("Componenti (doppio click per modificare):"))
        self.tbl_comp = QTableWidget(0, 9)
        self.tbl_comp.setHorizontalHeaderLabels(["ID","Nome","Profilo","Spess.","Q.tà","Ang SX","Ang DX","Formula","Offset"])
        hdr = self.tbl_comp.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(7, QHeaderView.Stretch)
        hdr.setSectionResizeMode(8, QHeaderView.ResizeToContents)
        self.tbl_comp.cellDoubleClicked.connect(self._edit_comp_row)
        root.addWidget(self.tbl_comp)

        rowc = QHBoxLayout()
        btn_add_c = QPushButton("Aggiungi"); btn_add_c.clicked.connect(self._add_comp)
        btn_edit_c = QPushButton("Modifica"); btn_edit_c.clicked.connect(self._edit_comp)
        btn_dup_c = QPushButton("Duplica"); btn_dup_c.clicked.connect(self._dup_comp)
        btn_del_c = QPushButton("Elimina"); btn_del_c.clicked.connect(self._del_comp)
        rowc.addWidget(btn_add_c); rowc.addWidget(btn_edit_c); rowc.addWidget(btn_dup_c); rowc.addWidget(btn_del_c); rowc.addStretch(1)
        root.addLayout(rowc)

        acts = QHBoxLayout()
        btn_cancel = QPushButton("Annulla"); btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Salva tipologia"); btn_save.clicked.connect(self._save)
        acts.addWidget(btn_cancel); acts.addWidget(btn_save); acts.addStretch(1)
        root.addLayout(acts)

        # Reazioni
        self.ed_cat.textChanged.connect(self._refresh_options_group)
        self.btn_hw_manage.clicked.connect(self._open_hw_manager)
        self.cmb_brand.currentIndexChanged.connect(self._on_brand_changed)
        self.cmb_series.currentIndexChanged.connect(self._on_series_changed)

    def _open_hw_manager(self):
        if HardwareManagerDialog is None or self._store is None:
            QMessageBox.information(self, "Ferramenta", "Modulo gestione ferramenta non disponibile.")
            return
        dlg = HardwareManagerDialog(self, self._store)
        dlg.exec()
        # dopo gestione, ricarica combo
        self._reload_hw_combos()

    def _refresh_options_group(self):
        cat = (self.ed_cat.text() or "").strip().lower()
        show = (cat in ("persiana", "astine", "battente"))
        self.grp_opts.setVisible(show)
        # lamelle se persiana
        if self._store:
            self.cmb_lamella.clear()
            if cat == "persiana":
                try:
                    names = self._store.list_lamella_rulesets("persiana")
                    if not names:
                        self.cmb_lamella.addItem("— Nessuno —", "")
                    else:
                        for n in names: self.cmb_lamella.addItem(n, n)
                except Exception:
                    self.cmb_lamella.addItem("— Errore DB —", "")
            else:
                self.cmb_lamella.addItem("— N/D —", "")
        # ferramenta se astine o battente
        self._reload_hw_combos()

    def _reload_hw_combos(self):
        if self._store is None:
            for cb in (self.cmb_brand, self.cmb_series, self.cmb_subcat, self.cmb_handle):
                cb.clear(); cb.addItem("— N/D —", None)
            return
        # Marca
        self.cmb_brand.clear()
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
        if self._store is None:
            return
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
        if self._store is None:
            return
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
                self.cmb_handle.addItem(label, int(h["id"]))
        subcats = self._store.list_hw_sash_subcats(int(bid), int(sid))
        if not subcats:
            self.cmb_subcat.addItem("— Nessuna sottocategoria —", "")
        else:
            for sc in subcats:
                self.cmb_subcat.addItem(sc, sc)

    def _load_base(self):
        b = self.base
        self.ed_name.setText(str(b.get("nome",""))); self.ed_cat.setText(str(b.get("categoria",""))); self.ed_mat.setText(str(b.get("materiale","")))
        rif = str(b.get("riferimento_quota","esterna")).lower(); idx = self.cmb_rif.findText(rif) if rif else 0
        self.cmb_rif.setCurrentIndex(idx if idx >= 0 else 0)
        self.sp_extra.setValue(float(b.get("extra_detrazione_mm",0.0) or 0.0))
        self.sp_pezzi.setValue(int(b.get("pezzi_totali",1) or 1))
        self.ed_note.setText(str(b.get("note","")))

        # Opzioni salvatate
        opts = b.get("options") or {}
        self._refresh_options_group()
        # lamelle
        lam = opts.get("lamelle_ruleset","")
        if lam:
            i = self.cmb_lamella.findData(lam)
            if i >= 0: self.cmb_lamella.setCurrentIndex(i)
        # ferramenta defaults
        bid = int(opts.get("hw_brand_id")) if opts.get("hw_brand_id") else None
        sid = int(opts.get("hw_series_id")) if opts.get("hw_series_id") else None
        subc = opts.get("hw_subcat","")
        hid = int(opts.get("hw_handle_id")) if opts.get("hw_handle_id") else None
        if bid:
            # set current brand
            for i in range(self.cmb_brand.count()):
                if self.cmb_brand.itemData(i) == bid:
                    self.cmb_brand.setCurrentIndex(i); break
        if sid:
            for i in range(self.cmb_series.count()):
                if self.cmb_series.itemData(i) == sid:
                    self.cmb_series.setCurrentIndex(i); break
        if subc:
            for i in range(self.cmb_subcat.count()):
                if self.cmb_subcat.itemData(i) == subc:
                    self.cmb_subcat.setCurrentIndex(i); break
        if hid:
            for i in range(self.cmb_handle.count()):
                if self.cmb_handle.itemData(i) == hid:
                    self.cmb_handle.setCurrentIndex(i); break

        # variabili
        for k, v in sorted((b.get("variabili_locali") or {}).items()):
            self._vars_insert_row(k, float(v))
        # componenti
        for c in (b.get("componenti") or []):
            self._comp_insert_row(c)

    def _vars_insert_row(self, k: str, v: float):
        r = self.tbl_vars.rowCount(); self.tbl_vars.insertRow(r)
        self.tbl_vars.setItem(r, 0, QTableWidgetItem(k))
        self.tbl_vars.setItem(r, 1, QTableWidgetItem(f"{float(v):.3f}"))

    def _collect_vars_map(self) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for r in range(self.tbl_vars.rowCount()):
            k = self.tbl_vars.item(r, 0).text() if self.tbl_vars.item(r, 0) else ""
            v = self.tbl_vars.item(r, 1).text() if self.tbl_vars.item(r, 1) else "0"
            k = (k or "").strip()
            if not k: continue
            try: out[k] = float((v or "0").replace(",", "."))
            except Exception: out[k] = 0.0
        return out

    def _add_var(self):
        r = self.tbl_vars.rowCount(); self.tbl_vars.insertRow(r)
        self.tbl_vars.setItem(r, 0, QTableWidgetItem(""))
        self.tbl_vars.setItem(r, 1, QTableWidgetItem("0"))

    def _del_var(self):
        r = self.tbl_vars.currentRow()
        if r >= 0: self.tbl_vars.removeRow(r)

    def _next_component_id(self) -> str:
        ids = set()
        for r in range(self.tbl_comp.rowCount()):
            ids.add(self.tbl_comp.item(r, 0).text() if self.tbl_comp.item(r, 0) else "")
        i = 1
        while True:
            rid = f"R{i}"
            if rid not in ids:
                return rid
            i += 1

    def _collect_components_list(self) -> List[Dict[str, Any]]:
        comps: List[Dict[str, Any]] = []
        for r in range(self.tbl_comp.rowCount()):
            def gi(c): return self.tbl_comp.item(r, c).text() if self.tbl_comp.item(r, c) else ""
            try:
                comps.append({
                    "id_riga": gi(0), "nome": gi(1), "profilo_nome": gi(2),
                    "quantita": int(float(gi(4) or "0")),
                    "ang_sx": float(gi(5) or "0"),
                    "ang_dx": float(gi(6) or "0"),
                    "formula_lunghezza": gi(7) or "H",
                    "offset_mm": float(gi(8) or "0"),
                    "note": ""
                })
            except Exception:
                continue
        return comps

    def _comp_insert_row(self, c: Dict[str, Any], row: Optional[int] = None):
        r = self.tbl_comp.rowCount() if row is None else row
        if row is None: self.tbl_comp.insertRow(r)
        sp = ""
        prof = c.get("profilo_nome","")
        if prof in self.profiles: sp = f"{float(self.profiles[prof]):.3f}"
        vals = [c.get("id_riga",""), c.get("nome",""), prof, sp,
                str(c.get("quantita",0)), f"{float(c.get('ang_sx',0.0)):.2f}",
                f"{float(c.get('ang_dx',0.0)):.2f}", c.get("formula_lunghezza",""),
                f"{float(c.get('offset_mm',0.0)):.3f}"]
        for i, v in enumerate(vals):
            self.tbl_comp.setItem(r, i, QTableWidgetItem(v))

    def _new_component_dialog(self, base_comp: Dict[str, Any], row_to_replace: Optional[int] = None):
        comps_before = self._collect_components_list() if row_to_replace is None else self._collect_components_list()[:row_to_replace]
        var_provider: Callable[[], Dict[str, float]] = lambda: self._collect_vars_map()
        from PySide6.QtWidgets import QDialog as _QDialog
        dlg = ComponentEditorDialog(self, base_comp, prev_components=comps_before, profiles=self.profiles, var_provider=var_provider)
        if dlg.exec() == _QDialog.DialogCode.Accepted and dlg.created:
            if row_to_replace is None:
                self._comp_insert_row(dlg.result_component())
            else:
                self._comp_insert_row(dlg.result_component(), row=row_to_replace)

    def _add_comp(self):
        rid = self._next_component_id()
        base_comp = {"id_riga": rid, "nome": "", "profilo_nome": "", "quantita": 1,
                     "ang_sx": 0.0, "ang_dx": 0.0, "formula_lunghezza": "H", "offset_mm": 0.0, "note": ""}
        self._new_component_dialog(base_comp, row_to_replace=None)

    def _edit_comp_row(self, row: int, _col: int):
        comps = self._collect_components_list()
        if not (0 <= row < len(comps)): return
        self._new_component_dialog(comps[row], row_to_replace=row)

    def _edit_comp(self):
        row = self.tbl_comp.currentRow()
        if row >= 0: self._edit_comp_row(row, 0)

    def _dup_comp(self):
        row = self.tbl_comp.currentRow()
        if row < 0: return
        comp = dict(self._collect_components_list()[row])
        comp["id_riga"] = self._next_component_id()
        comp["nome"] = (comp.get("nome") or "") + " (copia)"
        self._comp_insert_row(comp)

    def _del_comp(self):
        row = self.tbl_comp.currentRow()
        if row >= 0: self.tbl_comp.removeRow(row)

    def _save(self):
        name = (self.ed_name.text() or "").strip()
        if not name:
            QMessageBox.warning(self, "Dati", "Inserisci un nome tipologia."); return
        vars_map = self._collect_vars_map()
        comps = self._collect_components_list()
        if len(comps) == 0:
            from PySide6.QtWidgets import QMessageBox as _MB
            if _MB.question(self, "Conferma", "Nessun componente. Salvare comunque?") != _MB.Yes:
                return

        # Opzioni da salvare
        opts: Dict[str, str] = {}
        cat = (self.ed_cat.text() or "").strip().lower()
        # lamelle
        lam = self.cmb_lamella.currentData()
        if cat == "persiana" and lam:
            opts["lamelle_ruleset"] = str(lam)
        # ferramenta default
        if cat in ("astine", "battente"):
            bid = self.cmb_brand.currentData() or ""
            sid = self.cmb_series.currentData() or ""
            subc = self.cmb_subcat.currentData() or ""
            hid = self.cmb_handle.currentData() or ""
            if bid: opts["hw_brand_id"] = str(bid)
            if sid: opts["hw_series_id"] = str(sid)
            if subc: opts["hw_subcat"] = str(subc)
            if hid: opts["hw_handle_id"] = str(hid)

        self.base = {
            "nome": name,
            "categoria": (self.ed_cat.text() or "").strip(),
            "materiale": (self.ed_mat.text() or "").strip(),
            "riferimento_quota": (self.cmb_rif.currentText() or "esterna").strip(),
            "extra_detrazione_mm": float(self.sp_extra.value()),
            "pezzi_totali": int(self.sp_pezzi.value()),
            "note": (self.ed_note.text() or "").strip(),
            "variabili_locali": vars_map,
            "options": opts,
            "componenti": comps
        }
        self.accept()

    def result_tipologia(self) -> Dict[str, Any]:
        return dict(self.base)
