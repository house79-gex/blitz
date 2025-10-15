from __future__ import annotations
from typing import Optional, Dict, Any, List
from pathlib import Path
import json
from dataclasses import asdict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QGridLayout, QLabel, QListWidget, QListWidgetItem,
    QWidget, QScrollArea, QLineEdit, QComboBox, QPushButton, QFileDialog, QTableWidget,
    QTableWidgetItem, QSizePolicy, QMessageBox
)

# Motore parametrico (obbligatorio)
from ui_qt.services.parametric_engine import TypologyDef, Parameter, ElementDef, ParametricEngine, Part


class TipologiePage(QFrame):
    """
    Progettazione parametrica (separata dalla gestione commessa).
    - Carica tipologie JSON da data/typologies
    - Editor parametri (H, L, ecc.) + mapping profili (dal ProfilesStore condiviso)
    - Valuta e mostra anteprima elementi (qty, lunghezza, angoli A/B)
    - Salva una configurazione istanziata (per 'Quote vani luce' o altri moduli)
    """
    def __init__(self, appwin, profiles_store, typologies_dir: Optional[str] = None):
        super().__init__()
        self.appwin = appwin
        self.profiles = profiles_store
        self.typologies_dir = typologies_dir or str(Path("data") / "typologies")

        self._typ_paths: Dict[str, Path] = {}
        self._current_typ: Optional[TypologyDef] = None
        self._param_widgets: Dict[str, QWidget] = {}
        self._engine: Optional[ParametricEngine] = None
        self._parts: List[Part] = []
        self._env: Dict[str, Any] = {}

        self._build()
        self._load_typologies_list()

    # ------------------------- UI -------------------------
    def _build(self):
        self.setStyleSheet("QFrame { border: 1px solid #3b4b5a; border-radius: 6px; }")
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        # Colonna sinistra: elenco tipologie
        left = QFrame()
        left.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        left.setFixedWidth(260)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(6, 6, 6, 6)
        ll.setSpacing(6)
        ll.addWidget(QLabel("Tipologie"))
        self.lst_typs = QListWidget()
        self.lst_typs.currentItemChanged.connect(self._on_select_typology)
        ll.addWidget(self.lst_typs, 1)

        # Colonna centrale: editor parametri
        center = QFrame()
        center.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        cl = QVBoxLayout(center)
        cl.setContentsMargins(6, 6, 6, 6)
        cl.setSpacing(6)

        self.lbl_meta = QLabel("Seleziona una tipologia")
        self.lbl_meta.setStyleSheet("color:#ced6e0;")
        cl.addWidget(self.lbl_meta)

        self.scr = QScrollArea()
        self.scr.setWidgetResizable(True)
        self.param_host = QWidget()
        self.grid = QGridLayout(self.param_host)
        self.grid.setContentsMargins(4, 4, 4, 4)
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(6)
        self.scr.setWidget(self.param_host)
        cl.addWidget(self.scr, 1)

        btn_row = QHBoxLayout()
        self.btn_eval = QPushButton("Valuta")
        self.btn_eval.clicked.connect(self._evaluate)
        btn_row.addWidget(self.btn_eval)

        self.btn_save_cfg = QPushButton("Salva configurazione…")
        self.btn_save_cfg.clicked.connect(self._save_configuration)
        btn_row.addWidget(self.btn_save_cfg)
        btn_row.addStretch(1)
        cl.addLayout(btn_row)

        # Colonna destra: anteprima tabellare elementi
        right = QFrame()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(6, 6, 6, 6)
        rl.setSpacing(6)
        rl.addWidget(QLabel("Anteprima elementi"), 0)

        self.tbl = QTableWidget(0, 8)
        self.tbl.setHorizontalHeaderLabels(["ID", "Ruolo", "Profilo", "Q.tà", "Lunghezza (mm)", "Ang A (°)", "Ang B (°)", "Note"])
        self.tbl.horizontalHeader().setStretchLastSection(True)
        rl.addWidget(self.tbl, 1)

        root.addWidget(left, 0)
        root.addWidget(center, 1)
        root.addWidget(right, 1)

    # -------------------- Tipologie load -------------------
    def _load_typologies_list(self):
        self.lst_typs.clear()
        self._typ_paths.clear()

        base = Path(self.typologies_dir)
        if not base.exists():
            base.mkdir(parents=True, exist_ok=True)

        for p in sorted(base.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                name = str(data.get("name") or p.stem)
                self.lst_typs.addItem(QListWidgetItem(name))
                self._typ_paths[name] = p
            except Exception:
                continue

        if self.lst_typs.count() > 0:
            self.lst_typs.setCurrentRow(0)

    def _on_select_typology(self, cur: Optional[QListWidgetItem], prev: Optional[QListWidgetItem]):
        if not cur:
            return
        name = cur.text()
        path = self._typ_paths.get(name)
        if not path:
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            typ = TypologyDef(
                name=data.get("name", ""),
                version=data.get("version", ""),
                description=data.get("description", ""),
                parameters=[Parameter(**p) for p in data.get("parameters", [])],
                derived=data.get("derived", {}),
                elements=[ElementDef(**e) for e in data.get("elements", [])],
            )
        except Exception as e:
            QMessageBox.critical(self, "Errore tipologia", f"Impossibile caricare la tipologia:\n{e}")
            return

        self._current_typ = typ
        self._engine = ParametricEngine(typ)
        self._render_param_editors()

    # -------------------- Param editors -------------------
    def _render_param_editors(self):
        # Pulisci griglia
        for i in reversed(range(self.grid.count())):
            w = self.grid.itemAt(i).widget()
            if w:
                w.deleteLater()
        self._param_widgets.clear()

        if not self._current_typ:
            self.lbl_meta.setText("Seleziona una tipologia")
            return

        t = self._current_typ
        self.lbl_meta.setText(f"{t.name} v{t.version} — {t.description}")

        row = 0
        # Parametri base
        for p in t.parameters:
            self.grid.addWidget(QLabel(p.name + ":"), row, 0)
            # Widget per tipo
            if p.type == "bool":
                cb = QComboBox()
                cb.addItems(["False", "True"])
                cb.setCurrentIndex(1 if bool(p.default) else 0)
                w = cb
            elif p.type == "select":
                cb = QComboBox()
                # Per compatibilità con il DB profili condiviso:
                if p.name.startswith("prof_") and self.profiles:
                    try:
                        names: List[str] = []
                        rows = self.profiles.list_profiles()
                        for r in rows:
                            n = str(r.get("name") or "")
                            if n:
                                names.append(n)
                        cb.addItem("")  # nessuno
                        for n in sorted(names):
                            cb.addItem(n)
                    except Exception:
                        cb.addItem("")
                else:
                    cb.addItem("")
                    for c in (getattr(p, "choices", None) or []):
                        cb.addItem(str(c))
                if p.default:
                    idx = cb.findText(str(p.default))
                    if idx >= 0:
                        cb.setCurrentIndex(idx)
                w = cb
            else:
                # float/int come line edit semplice (conversione alla valutazione)
                edit = QLineEdit()
                edit.setPlaceholderText(str(p.default))
                if p.default not in (None, ""):
                    edit.setText(str(p.default))
                w = edit

            self.grid.addWidget(w, row, 1, 1, 2)
            desc = QLabel(getattr(p, "description", "") or "")
            desc.setStyleSheet("color:#7f8c8d;")
            self.grid.addWidget(desc, row, 3)
            self._param_widgets[p.name] = w
            row += 1

        # Sezione variabili derivate (valorizzate dopo 'Valuta')
        self.grid.addWidget(QLabel("Variabili derivate (dopo valutazione):"), row, 0, 1, 4)
        row += 1
        self._derived_labels: Dict[str, QLabel] = {}
        for k in sorted(t.derived.keys()):
            self.grid.addWidget(QLabel(f"{k}:"), row, 0)
            lab = QLabel("—")
            lab.setStyleSheet("color:#0a0a0a;")
            self.grid.addWidget(lab, row, 1, 1, 3)
            self._derived_labels[k] = lab
            row += 1

    def _collect_inputs(self) -> Dict[str, Any]:
        vals: Dict[str, Any] = {}
        if not self._current_typ:
            return vals
        for p in self._current_typ.parameters:
            w = self._param_widgets.get(p.name)
            if not w:
                vals[p.name] = getattr(p, "default", None)
                continue
            if p.type == "bool":
                vals[p.name] = (w.currentText() == "True")  # type: ignore
            elif p.type == "int":
                s = (w.text() if hasattr(w, "text") else "").strip()  # type: ignore
                try:
                    vals[p.name] = int(float(s.replace(",", "."))) if s else int(getattr(p, "default", 0) or 0)
                except Exception:
                    vals[p.name] = int(getattr(p, "default", 0) or 0)
            elif p.type == "select":
                vals[p.name] = w.currentText()  # type: ignore
            else:
                s = (w.text() if hasattr(w, "text") else "").strip()  # type: ignore
                try:
                    vals[p.name] = float(s.replace(",", ".")) if s else float(getattr(p, "default", 0.0) or 0.0)
                except Exception:
                    vals[p.name] = float(getattr(p, "default", 0.0) or 0.0)
        return vals

    # ----------------- Eval / Anteprima -------------------
    def _evaluate(self):
        if not self._engine or not self._current_typ:
            return
        inputs = self._collect_inputs()
        try:
            parts, env = self._engine.evaluate(inputs)
        except Exception as e:
            QMessageBox.critical(self, "Errore formula", f"Errore nella valutazione:\n{e}")
            return
        self._parts = parts
        self._env = env

        # Aggiorna derivate
        for k, lab in getattr(self, "_derived_labels", {}).items():
            val = env.get(k, "—")
            try:
                lab.setText(f"{float(val):.3f}")
            except Exception:
                lab.setText(str(val))

        # Aggiorna tabella
        self._fill_table()

    def _fill_table(self):
        self.tbl.setRowCount(0)
        for p in self._parts:
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)
            self.tbl.setItem(r, 0, QTableWidgetItem(str(p.id)))
            self.tbl.setItem(r, 1, QTableWidgetItem(str(p.role)))
            self.tbl.setItem(r, 2, QTableWidgetItem(str(p.profile)))
            self.tbl.setItem(r, 3, QTableWidgetItem(str(p.qty)))
            self.tbl.setItem(r, 4, QTableWidgetItem(f"{p.length:.3f}"))
            self.tbl.setItem(r, 5, QTableWidgetItem(f"{p.angle_a:.2f}"))
            self.tbl.setItem(r, 6, QTableWidgetItem(f"{p.angle_b:.2f}"))
            self.tbl.setItem(r, 7, QTableWidgetItem(str(p.note or "")))

    # ----------------- Salva configurazione ----------------
    def _save_configuration(self):
        if not self._current_typ:
            return
        if not self._parts:
            self._evaluate()
            if not self._parts:
                return
        cfg = {
            "typology": self._current_typ.name,
            "version": self._current_typ.version,
            "inputs": self._collect_inputs(),
            "env": self._env,
            "parts": [asdict(p) for p in self._parts],
        }
        path, _ = QFileDialog.getSaveFileName(self, "Salva configurazione", "", "JSON (*.json)")
        if not path:
            return
        try:
            Path(path).write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        except Exception as e:
            QMessageBox.critical(self, "Errore salvataggio", f"Impossibile salvare il file:\n{e}")
