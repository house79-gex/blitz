from __future__ import annotations
from typing import Dict, Any, List, Optional, Callable
import traceback

from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QComboBox,
    QPushButton, QTableWidget, QTableWidgetItem, QSpinBox, QDoubleSpinBox,
    QGroupBox, QMessageBox, QHeaderView, QToolButton, QMenu
)

from ui_qt.services.legacy_formula import scan_variables, eval_formula, sanitize_name
from ui_qt.services.typologies_store import TypologiesStore, default_db_path

try:
    from ui_qt.services.profiles_store import ProfilesStore
except Exception:
    ProfilesStore = None  # type: ignore

def _profiles_map() -> Dict[str, float]:
    try:
        store = ProfilesStore()
        return {str(r.get("name") or ""): float(r.get("thickness") or 0.0) for r in store.list_profiles()}
    except Exception:
        return {}

def _abbrev(s: str, maxlen: int = 12) -> str:
    s = str(s or ""); return s if len(s) <= maxlen else (s[:maxlen-1] + "…")


class ComponentEditorDialog(QDialog):
    """
    Editor componente:
    - Token menu (tooltip attivi)
    - Pulsante 'Ferramenta…' per mappare formule per-opzione (override)
    - NUOVO: 'Libreria formule ferramenta…' per scegliere un preset (filtrato per opzione) e inserirlo
    """
    def __init__(self, parent, base: Dict[str, Any], prev_components: List[Dict[str, Any]],
                 profiles: Dict[str, float], var_provider: Optional[Callable[[], Dict[str, float]]] = None,
                 store: Optional[TypologiesStore] = None, typology_id: Optional[int] = None):
        super().__init__(parent)
        self.setWindowTitle("Componente")
        self.setModal(True)
        self.resize(960, 680)
        self.setMinimumSize(860, 560)
        self.base = dict(base)
        self.prev_components = prev_components
        self.profiles = profiles
        self.var_provider = var_provider
        self.store = store
        self.typology_id = typology_id
        self.created = False
        self._build()
        self._install_shortcuts()

    def _build(self):
        root = QVBoxLayout(self)
        g = QGridLayout(); g.setHorizontalSpacing(12); g.setVerticalSpacing(8); row = 0

        g.addWidget(QLabel("ID riga:"), row, 0)
        self.ed_id = QLineEdit(self.base.get("id_riga", "")); self.ed_id.setReadOnly(True)
        g.addWidget(self.ed_id, row, 1)
        self.btn_hw_map = QPushButton("Ferramenta (override)…")
        self.btn_hw_map.setToolTip("Mappa formule dell'elemento per le opzioni di ferramenta della tipologia")
        self.btn_hw_map.clicked.connect(self._open_hw_map)
        if not (self.store and self.typology_id):
            self.btn_hw_map.setEnabled(False)
        g.addWidget(self.btn_hw_map, row, 2)
        self.btn_lib = QPushButton("Libreria formule ferramenta…")
        self.btn_lib.setToolTip("Scegli un preset dalla libreria (filtra per opzione) e inseriscilo")
        self.btn_lib.clicked.connect(self._open_hw_library_picker)
        if not (self.store and self.typology_id):
            self.btn_lib.setEnabled(False)
        g.addWidget(self.btn_lib, row, 3)
        row += 1

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
        self.sp_ang_sx.setValue(float(self.base.get("ang_sx", 0.0) or 0.0)); g.addWidget(self.sp_ang_sx, row, 1); row += 1

        g.addWidget(QLabel("Angolo DX (°):"), row, 0)
        self.sp_ang_dx = QDoubleSpinBox(); self.sp_ang_dx.setRange(0.0, 90.0); self.sp_ang_dx.setDecimals(2); self.sp_ang_dx.setSingleStep(0.5)
        self.sp_ang_dx.setValue(float(self.base.get("ang_dx", 0.0) or 0.0)); g.addWidget(self.sp_ang_dx, row, 1); row += 1

        g.addWidget(QLabel("Offset (mm):"), row, 0)
        self.sp_off = QDoubleSpinBox(); self.sp_off.setRange(-1e6, 1e6); self.sp_off.setDecimals(3); self.sp_off.setSingleStep(0.1)
        self.sp_off.setValue(float(self.base.get("offset_mm", 0.0) or 0.0)); g.addWidget(self.sp_off, row, 1); row += 1

        g.addWidget(QLabel("Formula (base):"), row, 0)
        self.ed_formula = QLineEdit(self.base.get("formula_lunghezza", "H")); g.addWidget(self.ed_formula, row, 1, 1, 3); row += 1

        # Token menu
        token_row = QHBoxLayout()
        token_row.addWidget(QLabel("Token…"))
        self.btn_token = QToolButton(); self.btn_token.setText("Apri"); self.btn_token.setPopupMode(QToolButton.InstantPopup)
        self._rebuild_token_menu()
        token_row.addWidget(self.btn_token); token_row.addStretch(1)

        root.addLayout(g); root.addLayout(token_row)

        # Test formula
        test_box = QGroupBox("Test formula")
        tb = QVBoxLayout(test_box)
        tb.addWidget(QLabel("Valori test es: H=1500; L=900; TOKEN_PROFILO=60"))
        self.ed_test = QLineEdit(); tb.addWidget(self.ed_test)
        self.lbl_test = QLabel("Risultato: —"); tb.addWidget(self.lbl_test)
        rowt = QHBoxLayout()
        btn_an = QPushButton("Analizza"); btn_an.clicked.connect(self._analyze)
        btn_ts = QPushButton("Valuta"); btn_ts.clicked.connect(self._try_eval)
        rowt.addWidget(btn_an); rowt.addWidget(btn_ts); rowt.addStretch(1); tb.addLayout(rowt)
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

    def _rebuild_token_menu(self):
        m = QMenu(self)
        try: m.setToolTipsVisible(True)
        except Exception: pass
        # Base
        m_base = m.addMenu("Base")
        for t, tip in (("H","Altezza finita"), ("L","Larghezza finita")):
            act = m_base.addAction(t); act.setToolTip(tip); act.triggered.connect(lambda _, v=t: self._ins_token(v))
        # Variabili
        m_vars = m.addMenu("Variabili")
        var_map = (self.var_provider() or {}) if self.var_provider else {}
        if not var_map:
            a = m_vars.addAction("— Nessuna —"); a.setEnabled(False)
        else:
            for k in sorted(var_map.keys()):
                act = m_vars.addAction(_abbrev(k)); act.setToolTip(f"{k} = {var_map.get(k)}")
                act.triggered.connect(lambda _, v=k: self._ins_token(v))
        # Componenti
        m_comp = m.addMenu("Componenti prec.")
        had = False
        for c in self.prev_components:
            rid = c.get("id_riga",""); nm = c.get("nome","")
            if rid:
                t = f"C_{rid}"; act = m_comp.addAction(_abbrev(t)); act.setToolTip(f"{t} → {nm}")
                act.triggered.connect(lambda _, v=t: self._ins_token(v)); had = True
        if not had:
            a = m_comp.addAction("— Nessuno —"); a.setEnabled(False)
        # Profili
        m_prof = m.addMenu("Profili")
        hadp = False
        for name, th in sorted(self.profiles.items()):
            tok = sanitize_name(name)
            act = m_prof.addAction(_abbrev(tok)); act.setToolTip(f"{name} → {tok} (sp={th} mm)")
            act.triggered.connect(lambda _, v=tok: self._ins_token(v)); hadp = True
        if not hadp:
            a = m_prof.addAction("— Nessuno —"); a.setEnabled(False)
        self.btn_token.setMenu(m)

    def _install_shortcuts(self):
        QShortcut(QKeySequence("Alt+0"), self).activated.connect(lambda: (self.sp_ang_sx.setValue(0.0), self.sp_ang_dx.setValue(0.0)))
        QShortcut(QKeySequence("Alt+5"), self).activated.connect(lambda: (self.sp_ang_sx.setValue(45.0), self.sp_ang_dx.setValue(45.0)))

    def _ins_token(self, tok: str):
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
        self._rebuild_token_menu()

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

    def _build_env(self) -> Dict[str, Any]:
        env: Dict[str, Any] = {"H": 1000.0, "L": 1000.0}
        env.update((self.var_provider() or {}))
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

    def _open_hw_map(self):
        if not (self.store and self.typology_id):
            QMessageBox.information(self, "Ferramenta", "Salva la tipologia prima di mappare le formule.")
            return
        try:
            from ui_qt.dialogs.component_hardware_map_qt import ComponentHardwareMapDialog
        except Exception:
            QMessageBox.information(self, "Ferramenta", "Modulo mapping non disponibile.")
            return
        ComponentHardwareMapDialog(self, self.store, int(self.typology_id), self.ed_id.text().strip()).exec()

    def _open_hw_library_picker(self):
        if not (self.store and self.typology_id):
            QMessageBox.information(self, "Libreria", "Salva la tipologia prima di usare la libreria.")
            return
        try:
            from ui_qt.dialogs.component_hw_formula_picker_qt import ComponentHardwareFormulaPickerDialog
        except Exception:
            QMessageBox.information(self, "Libreria", "Modulo non disponibile.")
            return
        dlg = ComponentHardwareFormulaPickerDialog(self, self.store, int(self.typology_id), self.ed_id.text().strip())
        if dlg.exec():
            formula = dlg.selected_formula()
            if formula:
                self.ed_formula.setText(formula)

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
        self.base.update({"nome": name, "profilo_nome": prof, "quantita": qta,
                          "ang_sx": angsx, "ang_dx": angdx, "formula_lunghezza": form,
                          "offset_mm": offs, "note": note})
        self.created = True
        self.accept()

    def result_component(self) -> Dict[str, Any]:
        return dict(self.base)


class TipologiaEditorDialog(QDialog):
    """
    Editor tipologia – include accesso a:
    - Opzioni ferramenta
    - Gestione meccanismi
    - NUOVO: Libreria formule ferramenta (CRUD)
    """
    def __init__(self, parent, base: Optional[Dict[str, Any]] = None, is_new: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Nuova Tipologia" if is_new else "Modifica Tipologia")
        self.setModal(True)
        self.setWindowState(Qt.WindowMaximized)
        self.base = dict(base or {})
        self.is_new = is_new
        self.profiles = _profiles_map()
        self.store = TypologiesStore(str(default_db_path()))
        self._build()
        self._load_base()

    def _build(self):
        root = QVBoxLayout(self)
        meta = QGridLayout(); meta.setHorizontalSpacing(12); meta.setVerticalSpacing(6); row = 0

        meta.addWidget(QLabel("Nome tipologia:"), row, 0)
        self.ed_name = QLineEdit(); meta.addWidget(self.ed_name, row, 1, 1, 3); row += 1
        meta.addWidget(QLabel("Categoria:"), row, 0)
        self.ed_cat = QLineEdit(); meta.addWidget(self.ed_cat, row, 1)
        meta.addWidget(QLabel("Materiale:"), row, 2)
        self.ed_mat = QLineEdit(); meta.addWidget(self.ed_mat, row, 3); row += 1
        meta.addWidget(QLabel("Riferimento quota:"), row, 0)
        self.cmb_rif = QComboBox(); self.cmb_rif.addItems(["esterna","interna"]); meta.addWidget(self.cmb_rif, row, 1)
        meta.addWidget(QLabel("Extra detrazione (mm):"), row, 2)
        self.sp_extra = QDoubleSpinBox(); self.sp_extra.setRange(-1e6, 1e6); self.sp_extra.setDecimals(3); meta.addWidget(self.sp_extra, row, 3); row += 1
        meta.addWidget(QLabel("Pezzi totali:"), row, 0)
        self.sp_pezzi = QSpinBox(); self.sp_pezzi.setRange(1, 999); meta.addWidget(self.sp_pezzi, row, 1)
        meta.addWidget(QLabel("Note:"), row, 2)
        self.ed_note = QLineEdit(); meta.addWidget(self.ed_note, row, 3); row += 1
        root.addLayout(meta)

        bar = QHBoxLayout()
        btn_hw_opts = QPushButton("Opzioni ferramenta…"); btn_hw_opts.clicked.connect(self._open_hw_options)
        btn_mech_mgr = QPushButton("Gestisci meccanismi…"); btn_mech_mgr.clicked.connect(self._open_mech_mgr)
        btn_hw_lib = QPushButton("Libreria formule ferramenta…"); btn_hw_lib.clicked.connect(self._open_hw_lib)
        bar.addWidget(btn_hw_opts); bar.addWidget(btn_mech_mgr); bar.addWidget(btn_hw_lib); bar.addStretch(1)
        root.addLayout(bar)

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

        root.addWidget(QLabel("Componenti (doppio click per modificare)"))
        self.tbl_comp = QTableWidget(0, 9)
        self.tbl_comp.setHorizontalHeaderLabels(["ID","Nome","Profilo","Spess.","Q.tà","Ang SX","Ang DX","Formula","Offset"])
        hdr = self.tbl_comp.horizontalHeader()
        for i, mode in enumerate([QHeaderView.ResizeToContents, QHeaderView.Stretch, QHeaderView.Stretch,
                                  QHeaderView.ResizeToContents, QHeaderView.ResizeToContents, QHeaderView.ResizeToContents,
                                  QHeaderView.ResizeToContents, QHeaderView.Stretch, QHeaderView.ResizeToContents]):
            hdr.setSectionResizeMode(i, mode)
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

    def _open_hw_options(self):
        typ_id = self.base.get("id")
        if not isinstance(typ_id, int):
            QMessageBox.information(self, "Ferramenta", "Salva la tipologia per abilitare le opzioni."); return
        try:
            from ui_qt.dialogs.typology_hw_options_qt import TypologyHardwareOptionsDialog
            TypologyHardwareOptionsDialog(self, self.store, int(typ_id)).exec()
        except Exception:
            QMessageBox.information(self, "Ferramenta", "Modulo opzioni non disponibile.")

    def _open_mech_mgr(self):
        try:
            from ui_qt.dialogs.hw_mechanism_manager_qt import HardwareMechanismManagerDialog
            HardwareMechanismManagerDialog(self, self.store).exec()
        except Exception:
            QMessageBox.information(self, "Meccanismi", "Modulo non disponibile.")

    def _open_hw_lib(self):
        try:
            from ui_qt.dialogs.hw_formula_presets_qt import HardwareFormulaPresetsDialog
            HardwareFormulaPresetsDialog(self, self.store).exec()
        except Exception:
            QMessageBox.information(self, "Libreria", "Modulo non disponibile.")

    def _load_base(self):
        b = self.base or {}
        self.ed_name.setText(str(b.get("nome",""))); self.ed_cat.setText(str(b.get("categoria",""))); self.ed_mat.setText(str(b.get("materiale","")))
        rif = str(b.get("riferimento_quota","esterna")).lower(); idx = self.cmb_rif.findText(rif) if rif else 0
        self.cmb_rif.setCurrentIndex(idx if idx >= 0 else 0)
        self.sp_extra.setValue(float(b.get("extra_detrazione_mm",0.0) or 0.0))
        self.sp_pezzi.setValue(int(b.get("pezzi_totali",1) or 1))
        self.ed_note.setText(str(b.get("note","")))
        for k, v in sorted((b.get("variabili_locali") or {}).items()):
            self._vars_insert_row(k, float(v))
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
        ids = set(self.tbl_comp.item(r, 0).text() if self.tbl_comp.item(r, 0) else "" for r in range(self.tbl_comp.rowCount()))
        i = 1
        while f"R{i}" in ids: i += 1
        return f"R{i}"

    def _collect_components_list(self) -> List[Dict[str, Any]]:
        comps: List[Dict[str, Any]] = []
        for r in range(self.tbl_comp.rowCount()):
            def gi(c): return self.tbl_comp.item(r, c).text() if self.tbl_comp.item(r, c) else ""
            try:
                comps.append({
                    "id_riga": gi(0), "nome": gi(1), "profilo_nome": gi(2),
                    "quantita": int(float(gi(4) or "0")), "ang_sx": float(gi(5) or "0"),
                    "ang_dx": float(gi(6) or "0"), "formula_lunghezza": gi(7) or "H",
                    "offset_mm": float(gi(8) or "0"), "note": ""
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
        for i, v in enumerate(vals): self.tbl_comp.setItem(r, i, QTableWidgetItem(v))

    def _new_component_dialog(self, base_comp: Dict[str, Any], row_to_replace: Optional[int] = None):
        comps_before = self._collect_components_list() if row_to_replace is None else self._collect_components_list()[:row_to_replace]
        var_provider: Callable[[], Dict[str, float]] = lambda: self._collect_vars_map()
        from PySide6.QtWidgets import QDialog as _QDialog
        typ_id = self.base.get("id") if isinstance(self.base.get("id"), int) else None
        dlg = ComponentEditorDialog(self, base_comp, prev_components=comps_before, profiles=self.profiles,
                                    var_provider=var_provider, store=self.store, typology_id=typ_id)
        if dlg.exec() == _QDialog.DialogCode.Accepted and getattr(dlg, "created", False):
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
        self.base = {
            "id": self.base.get("id"),
            "nome": name,
            "categoria": (self.ed_cat.text() or "").strip(),
            "materiale": (self.ed_mat.text() or "").strip(),
            "riferimento_quota": (self.cmb_rif.currentText() or "esterna").strip(),
            "extra_detrazione_mm": float(self.sp_extra.value()),
            "pezzi_totali": int(self.sp_pezzi.value()),
            "note": (self.ed_note.text() or "").strip(),
            "variabili_locali": vars_map,
            "componenti": comps
        }
        self.accept()

    def result_tipologia(self) -> Dict[str, Any]:
        out = dict(self.base or {})
        out.setdefault("variabili_locali", {})
        out.setdefault("options", {})
        out.setdefault("componenti", [])
        return out
