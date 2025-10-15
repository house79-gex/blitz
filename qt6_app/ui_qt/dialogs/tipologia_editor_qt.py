from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QComboBox,
    QPushButton, QTableWidget, QTableWidgetItem, QSpinBox, QDoubleSpinBox,
    QGroupBox, QTextEdit, QMessageBox, QFileDialog
)

from ui_qt.services.legacy_formula import scan_variables, eval_formula, sanitize_name

# Usa lo stesso DB profili di Utility
try:
    from ui_qt.services.profiles_store import ProfilesStore
except Exception:
    ProfilesStore = None  # type: ignore


def _profiles_map() -> Dict[str, float]:
    try:
        store = ProfilesStore()
        out: Dict[str, float] = {}
        for r in store.list_profiles():
            n = str(r.get("name") or "")
            th = float(r.get("thickness") or 0.0)
            if n:
                out[n] = th
        return out
    except Exception:
        return {}


class ComponentEditorDialog(QDialog):
    """
    Editor di un componente singolo (nome, profilo, qta, angoli, formula, offset, note).
    Supporta: token rapidi H/L, legenda C_Rx dei precedenti, test formula, token profilo.
    """
    def __init__(self, parent, base: Dict[str, Any], prev_components: List[Dict[str, Any]], profiles: Dict[str, float]):
        super().__init__(parent)
        self.setWindowTitle("Componente")
        self.setModal(True)
        self.base = dict(base)
        self.prev_components = prev_components
        self.profiles = profiles
        self.created = False
        self._build()

    def _build(self):
        root = QVBoxLayout(self)

        g = QGridLayout()
        row = 0

        g.addWidget(QLabel("ID riga:"), row, 0)
        self.ed_id = QLineEdit(self.base.get("id_riga",""))
        self.ed_id.setReadOnly(True)
        g.addWidget(self.ed_id, row, 1); row += 1

        g.addWidget(QLabel("Nome:"), row, 0)
        self.ed_name = QLineEdit(self.base.get("nome",""))
        g.addWidget(self.ed_name, row, 1); row += 1

        g.addWidget(QLabel("Profilo:"), row, 0)
        self.cmb_prof = QComboBox()
        names = sorted(self.profiles.keys())
        self.cmb_prof.addItem("")
        for n in names: self.cmb_prof.addItem(n)
        if self.base.get("profilo_nome"):
            idx = self.cmb_prof.findText(self.base["profilo_nome"])
            if idx >= 0: self.cmb_prof.setCurrentIndex(idx)
        g.addWidget(self.cmb_prof, row, 1)

        self.lbl_token = QLabel("")  # token profilo
        g.addWidget(self.lbl_token, row, 2); row += 1

        g.addWidget(QLabel("Quantità:"), row, 0)
        self.sp_qta = QSpinBox(); self.sp_qta.setRange(0, 999)
        self.sp_qta.setValue(int(self.base.get("quantita",1) or 1))
        g.addWidget(self.sp_qta, row, 1); row += 1

        g.addWidget(QLabel("Angolo SX (°):"), row, 0)
        self.sp_ang_sx = QDoubleSpinBox(); self.sp_ang_sx.setRange(0.0, 90.0); self.sp_ang_sx.setDecimals(2)
        self.sp_ang_sx.setValue(float(self.base.get("ang_sx",0.0) or 0.0))
        g.addWidget(self.sp_ang_sx, row, 1)

        g.addWidget(QLabel("Angolo DX (°):"), row, 2)
        self.sp_ang_dx = QDoubleSpinBox(); self.sp_ang_dx.setRange(0.0, 90.0); self.sp_ang_dx.setDecimals(2)
        self.sp_ang_dx.setValue(float(self.base.get("ang_dx",0.0) or 0.0))
        g.addWidget(self.sp_ang_dx, row, 3); row += 1

        g.addWidget(QLabel("Offset (mm):"), row, 0)
        self.sp_off = QDoubleSpinBox(); self.sp_off.setRange(-1e6, 1e6); self.sp_off.setDecimals(3)
        self.sp_off.setValue(float(self.base.get("offset_mm",0.0) or 0.0))
        g.addWidget(self.sp_off, row, 1); row += 1

        g.addWidget(QLabel("Formula lunghezza:"), row, 0)
        self.ed_formula = QLineEdit(self.base.get("formula_lunghezza","H"))
        g.addWidget(self.ed_formula, row, 1, 1, 3); row += 1

        # Token rapidi e legenda componenti precedenti
        quick = QHBoxLayout()
        for t in ("H", "L"):
            b = QPushButton(t); b.clicked.connect(lambda _=None, v=t: self._ins_token(v))
            quick.addWidget(b)
        # legenda C_Rx
        quick.addWidget(QLabel("Componenti prec.:"))
        for c in self.prev_components:
            rid = c.get("id_riga","")
            if rid:
                t = f"C_{rid}"
                b = QPushButton(t); b.clicked.connect(lambda _=None, v=t: self._ins_token(v))
                quick.addWidget(b)
        quick.addStretch(1)
        root.addLayout(g)
        root.addLayout(quick)

        # Test formula
        test_box = QGroupBox("Test formula")
        tb = QVBoxLayout(test_box)
        tb.addWidget(QLabel("Valori test (es: H=1500; L=900)"))
        self.ed_test = QLineEdit()
        tb.addWidget(self.ed_test)
        self.lbl_test = QLabel("Risultato: —")
        tb.addWidget(self.lbl_test)

        rowt = QHBoxLayout()
        btn_an = QPushButton("Analizza"); btn_an.clicked.connect(self._analyze)
        btn_ts = QPushButton("Valuta"); btn_ts.clicked.connect(self._try_eval)
        rowt.addWidget(btn_an); rowt.addWidget(btn_ts); rowt.addStretch(1)
        tb.addLayout(rowt)
        root.addWidget(test_box)

        # Note
        root.addWidget(QLabel("Note:"))
        self.ed_note = QLineEdit(self.base.get("note",""))
        root.addWidget(self.ed_note)

        # Azioni
        acts = QHBoxLayout()
        btn_cancel = QPushButton("Annulla"); btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("Salva"); btn_ok.clicked.connect(self._save)
        acts.addWidget(btn_cancel); acts.addWidget(btn_ok); acts.addStretch(1)
        root.addLayout(acts)

        self._update_prof_token()

        self.cmb_prof.currentIndexChanged.connect(self._update_prof_token)

    def _ins_token(self, tok: str):
        if not tok: return
        t = self.ed_formula.text() or ""
        self.ed_formula.setText(t + ("" if not t or t.endswith(("+","-","*","/","(")) else "") + tok)

    def _update_prof_token(self):
        p = self.cmb_prof.currentText().strip()
        if p:
            self.lbl_token.setText(f"Token profilo: {sanitize_name(p)}")
        else:
            self.lbl_token.setText("")

    def _build_env(self) -> Dict[str, Any]:
        # Ambiente minimo per test: H/L default + token profilo (se scelto) + C_Rx prec.
        env: Dict[str, Any] = {"H": 1000.0, "L": 1000.0}
        # Inserisci token del profilo scelto con spessore
        p = self.cmb_prof.currentText().strip()
        if p and p in self.profiles:
            env[sanitize_name(p)] = float(self.profiles[p])
        # Componenti precedenti (assegna segnaposto 1000.0)
        for c in self.prev_components:
            rid = c.get("id_riga","")
            if rid:
                env[f"C_{rid}"] = 1000.0
        # Variabili locali verranno aggiunte dal chiamante (editor padre) quando serve
        # Eventuali override da campo test:
        raw = (self.ed_test.text() or "").strip()
        if raw:
            pairs = [x.strip() for x in raw.split(";") if x.strip()]
            for p in pairs:
                if "=" in p:
                    k, v = p.split("=", 1)
                    k = k.strip(); v = v.strip().replace(",", ".")
                    try:
                        env[k] = float(v)
                    except Exception:
                        pass
        return env

    def _analyze(self):
        try:
            names = scan_variables(self.ed_formula.text().strip())
            self.lbl_test.setText("Variabili: " + (", ".join(names) if names else "(nessuna)"))
        except Exception as e:
            self.lbl_test.setText(f"Errore parse: {e}")

    def _try_eval(self):
        env = self._build_env()
        try:
            val = eval_formula(self.ed_formula.text().strip(), env)
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
            QMessageBox.warning(self, "Angoli", "Angoli fuori range (0-90).")
            return

        self.base.update({
            "nome": name,
            "profilo_nome": prof,
            "quantita": qta,
            "ang_sx": angsx,
            "ang_dx": angdx,
            "formula_lunghezza": form,
            "offset_mm": offs,
            "note": note
        })
        self.created = True
        self.accept()

    def result_component(self) -> Dict[str, Any]:
        return dict(self.base)


class TipologiaEditorDialog(QDialog):
    """
    Editor completo tipologia (formato 'legacy' compatibile con vecchio TK):
    {
      nome, categoria, materiale, riferimento_quota, extra_detrazione_mm, pezzi_totali, note,
      variabili_locali: {k: num}, componenti: [ {id_riga,...} ]
    }
    """
    def __init__(self, parent, base: Optional[Dict[str, Any]] = None, is_new: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Nuova Tipologia" if is_new else "Modifica Tipologia")
        self.setModal(True)
        self.base = dict(base or {})
        self.is_new = is_new
        self.profiles = _profiles_map()
        self._build()
        self._load_base()

    def _build(self):
        root = QVBoxLayout(self)

        meta = QGridLayout()
        row = 0
        meta.addWidget(QLabel("Nome:"), row, 0)
        self.ed_name = QLineEdit(); meta.addWidget(self.ed_name, row, 1); row += 1

        meta.addWidget(QLabel("Categoria:"), row, 0)
        self.ed_cat = QLineEdit(); meta.addWidget(self.ed_cat, row, 1); row += 1

        meta.addWidget(QLabel("Materiale:"), row, 0)
        self.ed_mat = QLineEdit(); meta.addWidget(self.ed_mat, row, 1); row += 1

        meta.addWidget(QLabel("Rif. quota:"), row, 0)
        self.cmb_rif = QComboBox(); self.cmb_rif.addItems(["esterna","interna"])
        meta.addWidget(self.cmb_rif, row, 1); row += 1

        meta.addWidget(QLabel("Extra detrazione (mm):"), row, 0)
        self.sp_extra = QDoubleSpinBox(); self.sp_extra.setRange(-1e6, 1e6); self.sp_extra.setDecimals(3)
        meta.addWidget(self.sp_extra, row, 1); row += 1

        meta.addWidget(QLabel("Pezzi totali:"), row, 0)
        self.sp_pezzi = QSpinBox(); self.sp_pezzi.setRange(1, 999)
        meta.addWidget(self.sp_pezzi, row, 1); row += 1

        meta.addWidget(QLabel("Note:"), row, 0)
        self.ed_note = QLineEdit(); meta.addWidget(self.ed_note, row, 1); row += 1

        root.addLayout(meta)

        # Variabili locali
        root.addWidget(QLabel("Variabili locali (nome → valore):"))
        self.tbl_vars = QTableWidget(0, 2)
        self.tbl_vars.setHorizontalHeaderLabels(["Nome", "Valore"])
        self.tbl_vars.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.tbl_vars)

        rowv = QHBoxLayout()
        btn_add_v = QPushButton("Aggiungi variabile"); btn_add_v.clicked.connect(self._add_var)
        btn_edit_v = QPushButton("Modifica"); btn_edit_v.clicked.connect(self._edit_var)
        btn_del_v = QPushButton("Elimina"); btn_del_v.clicked.connect(self._del_var)
        rowv.addWidget(btn_add_v); rowv.addWidget(btn_edit_v); rowv.addWidget(btn_del_v); rowv.addStretch(1)
        root.addLayout(rowv)

        # Componenti
        root.addWidget(QLabel("Componenti:"))
        self.tbl_comp = QTableWidget(0, 9)
        self.tbl_comp.setHorizontalHeaderLabels(["ID","Nome","Profilo","Spess.","Q.tà","Ang SX","Ang DX","Formula","Offset"])
        self.tbl_comp.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.tbl_comp)

        rowc = QHBoxLayout()
        btn_add_c = QPushButton("Aggiungi"); btn_add_c.clicked.connect(self._add_comp)
        btn_edit_c = QPushButton("Modifica"); btn_edit_c.clicked.connect(self._edit_comp)
        btn_dup_c = QPushButton("Duplica"); btn_dup_c.clicked.connect(self._dup_comp)
        btn_del_c = QPushButton("Elimina"); btn_del_c.clicked.connect(self._del_comp)
        rowc.addWidget(btn_add_c); rowc.addWidget(btn_edit_c); rowc.addWidget(btn_dup_c); rowc.addWidget(btn_del_c); rowc.addStretch(1)
        root.addLayout(rowc)

        # Azioni finali
        acts = QHBoxLayout()
        btn_cancel = QPushButton("Annulla"); btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Salva"); btn_save.clicked.connect(self._save)
        acts.addWidget(btn_cancel); acts.addWidget(btn_save); acts.addStretch(1)
        root.addLayout(acts)

    def _load_base(self):
        b = self.base
        self.ed_name.setText(str(b.get("nome","")))
        self.ed_cat.setText(str(b.get("categoria","")))
        self.ed_mat.setText(str(b.get("materiale","")))
        rif = str(b.get("riferimento_quota","esterna")).lower()
        idx = self.cmb_rif.findText(rif) if rif else 0
        self.cmb_rif.setCurrentIndex(idx if idx >= 0 else 0)
        self.sp_extra.setValue(float(b.get("extra_detrazione_mm",0.0) or 0.0))
        self.sp_pezzi.setValue(int(b.get("pezzi_totali",1) or 1))
        self.ed_note.setText(str(b.get("note","")))

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

    def _add_var(self):
        self.tbl_vars.insertRow(self.tbl_vars.rowCount())
        # lascia celle modificabili inline

    def _edit_var(self):
        # editing inline già possibile: niente da fare
        pass

    def _del_var(self):
        r = self.tbl_vars.currentRow()
        if r >= 0:
            self.tbl_vars.removeRow(r)

    def _next_component_id(self) -> str:
        ids: Set[str] = set()
        for r in range(self.tbl_comp.rowCount()):
            ids.add(self.tbl_comp.item(r, 0).text() if self.tbl_comp.item(r,0) else "")
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
            rid = gi(0); nome = gi(1); prof = gi(2); sp = gi(3)
            qta = gi(4); asx = gi(5); adx = gi(6); form = gi(7); off = gi(8)
            try:
                comps.append({
                    "id_riga": rid,
                    "nome": nome,
                    "profilo_nome": prof,
                    "quantita": int(float(qta or "0")),
                    "ang_sx": float(asx or "0"),
                    "ang_dx": float(adx or "0"),
                    "formula_lunghezza": form or "H",
                    "offset_mm": float(off or "0"),
                    "note": ""
                })
            except Exception:
                continue
        return comps

    def _comp_insert_row(self, c: Dict[str, Any]):
        r = self.tbl_comp.rowCount(); self.tbl_comp.insertRow(r)
        sp = ""
        prof = c.get("profilo_nome","")
        if prof in self.profiles:
            sp = f"{float(self.profiles[prof]):.3f}"
        vals = [
            c.get("id_riga",""), c.get("nome",""), prof, sp,
            str(c.get("quantita",0)), f"{float(c.get('ang_sx',0.0)):.2f}",
            f"{float(c.get('ang_dx',0.0)):.2f}", c.get("formula_lunghezza",""),
            f"{float(c.get('offset_mm',0.0)):.3f}"
        ]
        for i, v in enumerate(vals):
            self.tbl_comp.setItem(r, i, QTableWidgetItem(v))

    def _add_comp(self):
        rid = self._next_component_id()
        comps = self._collect_components_list()
        dlg = ComponentEditorDialog(self, {
            "id_riga": rid, "nome": "", "profilo_nome": "", "quantita": 1,
            "ang_sx": 0.0, "ang_dx": 0.0, "formula_lunghezza": "H", "offset_mm": 0.0, "note": ""
        }, prev_components=comps, profiles=self.profiles)
        if dlg.exec() == dlg.Accepted and dlg.created:
            self._comp_insert_row(dlg.result_component())

    def _edit_comp(self):
        r = self.tbl_comp.currentRow()
        if r < 0: return
        comp = self._collect_components_list()[r]
        prev = self._collect_components_list()[:r]  # precedenti
        dlg = ComponentEditorDialog(self, comp, prev_components=prev, profiles=self.profiles)
        if dlg.exec() == dlg.Accepted and dlg.created:
            # sovrascrivi riga
            for i in range(self.tbl_comp.columnCount()):
                self.tbl_comp.takeItem(r, i)
            self._comp_insert_row(dlg.result_component())

    def _dup_comp(self):
        r = self.tbl_comp.currentRow()
        if r < 0: return
        comp = self._collect_components_list()[r]
        comp["id_riga"] = self._next_component_id()
        comp["nome"] = (comp.get("nome") or "") + " (copia)"
        self._comp_insert_row(comp)

    def _del_comp(self):
        r = self.tbl_comp.currentRow()
        if r >= 0:
            self.tbl_comp.removeRow(r)

    def _save(self):
        name = (self.ed_name.text() or "").strip()
        if not name:
            QMessageBox.warning(self, "Dati", "Inserisci un nome tipologia.")
            return
        # variabili locali
        local_vars: Dict[str, float] = {}
        for r in range(self.tbl_vars.rowCount()):
            k = self.tbl_vars.item(r, 0).text() if self.tbl_vars.item(r, 0) else ""
            v = self.tbl_vars.item(r, 1).text() if self.tbl_vars.item(r, 1) else "0"
            k = (k or "").strip()
            if not k: continue
            try:
                local_vars[k] = float((v or "0").replace(",", "."))
            except Exception:
                QMessageBox.warning(self, "Variabili", f"Valore non numerico per '{k}'.")
                return
        # componenti
        comps = self._collect_components_list()
        if len(comps) == 0:
            if QMessageBox.question(self, "Conferma", "Nessun componente. Salvare comunque?") != QMessageBox.Yes:
                return

        self.base = {
            "nome": name,
            "categoria": (self.ed_cat.text() or "").strip(),
            "materiale": (self.ed_mat.text() or "").strip(),
            "riferimento_quota": (self.cmb_rif.currentText() or "esterna").strip(),
            "extra_detrazione_mm": float(self.sp_extra.value()),
            "pezzi_totali": int(self.sp_pezzi.value()),
            "note": (self.ed_note.text() or "").strip(),
            "variabili_locali": local_vars,
            "componenti": comps
        }
        self.accept()

    def result_tipologia(self) -> Dict[str, Any]:
        return dict(self.base)
