from __future__ import annotations
from typing import Optional, Dict, Any, List
from pathlib import Path
import json
import shutil

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QGridLayout, QLabel, QListWidget, QListWidgetItem,
    QWidget, QScrollArea, QPushButton, QFileDialog, QTableWidget, QTableWidgetItem,
    QSizePolicy, QLineEdit, QToolButton, QStyle, QMessageBox
)

from ui_qt.dialogs.tipologia_editor_qt import TipologiaEditorDialog

def _default_dirs() -> List[Path]:
    me = Path(__file__).resolve()
    return [
        me.parents[2] / "data" / "typologies",
        Path.cwd() / "data" / "typologies",
        Path.home() / "blitz" / "typologies"
    ]

class TipologiePage(QFrame):
    """
    Gestione tipologie (formato legacy JSON):
    - Selettore cartella .json
    - Lista file (riconosce anche schema parametric 'engine' ma mostra solo)
    - Nuova/Modifica/Duplica/Elimina (editor Qt completo)
    """
    def __init__(self, appwin, typologies_dir: Optional[str] = None):
        super().__init__()
        self.appwin = appwin
        self._dir_edit: Optional[QLineEdit] = None
        self._build()
        base = Path(typologies_dir) if typologies_dir else None
        if not base:
            for d in _default_dirs():
                if d.exists():
                    base = d; break
        if not base:
            base = _default_dirs()[0]
        try: base.mkdir(parents=True, exist_ok=True)
        except Exception: pass
        self._dir_edit.setText(str(base))
        self._reload()

    def _build(self):
        self.setStyleSheet("QFrame { border: 1px solid #3b4b5a; border-radius: 6px; }")
        root = QHBoxLayout(self); root.setContentsMargins(8,8,8,8); root.setSpacing(10)

        # SX: cartella + lista
        left = QFrame(); left.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding); left.setFixedWidth(360)
        ll = QVBoxLayout(left); ll.setContentsMargins(6,6,6,6); ll.setSpacing(6)

        rowp = QHBoxLayout()
        rowp.addWidget(QLabel("Cartella tipologie:"), 0)
        self._dir_edit = QLineEdit(); rowp.addWidget(self._dir_edit, 1)
        btn_dir = QToolButton(); btn_dir.setIcon(self.style().standardIcon(QStyle.SP_DirIcon))
        btn_dir.clicked.connect(self._browse_dir); rowp.addWidget(btn_dir, 0)
        btn_reload = QToolButton(); btn_reload.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        btn_reload.clicked.connect(self._reload); rowp.addWidget(btn_reload, 0)
        ll.addLayout(rowp)

        self.lst = QListWidget(); self.lst.currentItemChanged.connect(self._on_select)
        ll.addWidget(self.lst, 1)

        actions = QHBoxLayout()
        self.btn_new = QPushButton("Nuova…"); self.btn_new.clicked.connect(self._new)
        self.btn_edit = QPushButton("Modifica…"); self.btn_edit.clicked.connect(self._edit)
        self.btn_dup = QPushButton("Duplica"); self.btn_dup.clicked.connect(self._dup)
        self.btn_del = QPushButton("Elimina"); self.btn_del.clicked.connect(self._del)
        actions.addWidget(self.btn_new); actions.addWidget(self.btn_edit); actions.addWidget(self.btn_dup); actions.addWidget(self.btn_del); actions.addStretch(1)
        ll.addLayout(actions)

        # CX: meta
        center = QFrame(); center.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        cl = QVBoxLayout(center); cl.setContentsMargins(6,6,6,6); cl.setSpacing(6)
        self.lbl_meta = QLabel("Seleziona una tipologia"); self.lbl_meta.setStyleSheet("color:#ced6e0;")
        cl.addWidget(self.lbl_meta)
        self.scr = QScrollArea(); self.scr.setWidgetResizable(True)
        self.meta_host = QWidget(); self.grid = QGridLayout(self.meta_host)
        self.grid.setContentsMargins(4,4,4,4); self.grid.setHorizontalSpacing(8); self.grid.setVerticalSpacing(6)
        self.scr.setWidget(self.meta_host)
        cl.addWidget(self.scr, 1)

        # DX: dettagli
        right = QFrame(); rl = QVBoxLayout(right); rl.setContentsMargins(6,6,6,6); rl.setSpacing(6)
        rl.addWidget(QLabel("Dettagli"), 0)
        self.tbl = QTableWidget(0, 6)
        self.tbl.setHorizontalHeaderLabels(["Tipo","ID/Param","Nome/Ruolo","Profilo","Qty/Default","Altro"])
        self.tbl.horizontalHeader().setStretchLastSection(True)
        rl.addWidget(self.tbl, 1)

        root.addWidget(left, 0); root.addWidget(center, 1); root.addWidget(right, 1)

    def _browse_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Seleziona cartella tipologie", self._dir_edit.text() or "")
        if not path: return
        self._dir_edit.setText(path); self._reload()

    def _reload(self):
        base = Path(self._dir_edit.text().strip() or ".")
        self.lst.clear(); 
        if not base.exists():
            self.lbl_meta.setText("Cartella inesistente"); return
        files = sorted(base.glob("*.json"))
        for p in files:
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                it = QListWidgetItem(f"{p.stem} (JSON non valido)")
                it.setData(Qt.UserRole, {"type":"invalid","path":str(p)})
                self.lst.addItem(it); continue
            if "componenti" in data:
                name = str(data.get("nome") or p.stem)
                it = QListWidgetItem(f"{name}  [legacy]")
                it.setData(Qt.UserRole, {"type":"legacy","path":str(p)})
                self.lst.addItem(it)
            elif "parameters" in data and "elements" in data:
                name = str(data.get("name") or p.stem)
                it = QListWidgetItem(f"{name}  [engine]")
                it.setData(Qt.UserRole, {"type":"engine","path":str(p)})
                self.lst.addItem(it)
            else:
                it = QListWidgetItem(f"{p.stem} (schema non riconosciuto)")
                it.setData(Qt.UserRole, {"type":"unknown","path":str(p)})
                self.lst.addItem(it)
        if self.lst.count() > 0:
            self.lst.setCurrentRow(0)
        else:
            self._clear_preview("Nessuna tipologia trovata")

    def _clear_preview(self, msg: str):
        for i in reversed(range(self.grid.count())):
            w = self.grid.itemAt(i).widget()
            if w: w.deleteLater()
        self.tbl.setRowCount(0)
        self.lbl_meta.setText(msg)

    def _on_select(self, cur: Optional[QListWidgetItem], prev: Optional[QListWidgetItem]):
        self._clear_preview("Seleziona una tipologia")
        if not cur: return
        entry = cur.data(Qt.UserRole) or {}
        fpath = Path(entry.get("path",""))
        ftype = entry.get("type","")
        if not fpath.exists():
            self.lbl_meta.setText("File non presente"); return
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
        except Exception as e:
            self.lbl_meta.setText(f"JSON non leggibile: {e}"); return

        if ftype == "legacy" and "componenti" in data:
            self._render_legacy(data, fpath)
        elif ftype == "engine" and "parameters" in data and "elements" in data:
            self._render_engine(data, fpath)
        elif ftype == "invalid":
            self.lbl_meta.setText("JSON non valido")
        else:
            self.lbl_meta.setText("Schema non riconosciuto")

    def _render_legacy(self, d: Dict[str,Any], path: Path):
        nome = str(d.get("nome","")); cat = str(d.get("categoria",""))
        rif = str(d.get("riferimento_quota","")); pezzi = int(d.get("pezzi_totali",1) or 1)
        extra = float(d.get("extra_detrazione_mm",0.0) or 0.0); note = str(d.get("note",""))
        self.lbl_meta.setText(f"{nome} [legacy] — {path.name}")
        row = 0
        for label, val in (("Categoria",cat),("Riferimento quota",rif),("Pezzi totali",str(pezzi)),("Extra detrazione (mm)",f"{extra:.3f}"),("Note",note)):
            self.grid.addWidget(QLabel(label+":"), row, 0)
            v = QLabel(val); v.setStyleSheet("color:#0a0a0a;")
            self.grid.addWidget(v, row, 1, 1, 3); row += 1

        self.tbl.setRowCount(0)
        for c in d.get("componenti", []):
            r = self.tbl.rowCount(); self.tbl.insertRow(r)
            self.tbl.setItem(r, 0, QTableWidgetItem("comp"))
            self.tbl.setItem(r, 1, QTableWidgetItem(c.get("id_riga","")))
            self.tbl.setItem(r, 2, QTableWidgetItem(c.get("nome","")))
            self.tbl.setItem(r, 3, QTableWidgetItem(c.get("profilo_nome","")))
            self.tbl.setItem(r, 4, QTableWidgetItem(str(c.get("quantita",0))))
            self.tbl.setItem(r, 5, QTableWidgetItem(f"AngSX:{c.get('ang_sx',0)} AngDX:{c.get('ang_dx',0)} | {c.get('formula_lunghezza','')}"))

    def _render_engine(self, d: Dict[str,Any], path: Path):
        name = str(d.get("name","")); desc = str(d.get("description","")); ver = str(d.get("version",""))
        self.lbl_meta.setText(f"{name} [engine] — {path.name}")
        row = 0
        for label, val in (("Versione",ver),("Descrizione",desc)):
            self.grid.addWidget(QLabel(label+":"), row, 0)
            v = QLabel(val); v.setStyleSheet("color:#0a0a0a;")
            self.grid.addWidget(v, row, 1, 1, 3); row += 1
        self.tbl.setRowCount(0)
        for p in d.get("parameters", [])[:12]:
            r = self.tbl.rowCount(); self.tbl.insertRow(r)
            self.tbl.setItem(r, 0, QTableWidgetItem("param"))
            self.tbl.setItem(r, 1, QTableWidgetItem(p.get("name","")))
            self.tbl.setItem(r, 2, QTableWidgetItem(p.get("type","")))
            self.tbl.setItem(r, 3, QTableWidgetItem(str(p.get("default",""))))
            self.tbl.setItem(r, 4, QTableWidgetItem(""))
            self.tbl.setItem(r, 5, QTableWidgetItem(p.get("description","")))
        for e in d.get("elements", [])[:20]:
            r = self.tbl.rowCount(); self.tbl.insertRow(r)
            self.tbl.setItem(r, 0, QTableWidgetItem("elem"))
            self.tbl.setItem(r, 1, QTableWidgetItem(e.get("id","")))
            self.tbl.setItem(r, 2, QTableWidgetItem(e.get("role","")))
            self.tbl.setItem(r, 3, QTableWidgetItem(e.get("profile_var","")))
            self.tbl.setItem(r, 4, QTableWidgetItem(e.get("qty_expr","")))
            self.tbl.setItem(r, 5, QTableWidgetItem(e.get("length_expr","")))

    # -------- CRUD --------
    def _current_path(self) -> Optional[Path]:
        it = self.lst.currentItem()
        if not it: return None
        entry = it.data(Qt.UserRole) or {}
        p = Path(entry.get("path",""))
        return p if p.exists() else None

    def _new(self):
        dlg = TipologiaEditorDialog(self, is_new=True)
        if dlg.exec() == dlg.Accepted:
            data = dlg.result_tipologia()
            base = Path(self._dir_edit.text().strip() or ".")
            base.mkdir(parents=True, exist_ok=True)
            safe = "".join(ch for ch in data.get("nome","") if ch.isalnum() or ch in (" ","-","_")).strip().replace(" ","_") or "tipologia"
            out = base / f"{safe}.json"
            try:
                out.write_text(json.dumps(data, indent=2), encoding="utf-8")
                self._reload()
                # seleziona appena creato
                for i in range(self.lst.count()):
                    en = self.lst.item(i).data(Qt.UserRole) or {}
                    if Path(en.get("path","")) == out:
                        self.lst.setCurrentRow(i); break
            except Exception as e:
                QMessageBox.critical(self, "Errore salvataggio", str(e))

    def _edit(self):
        p = self._current_path()
        if not p: return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            QMessageBox.critical(self, "Errore", f"JSON non leggibile:\n{e}"); return
        if "componenti" not in data:
            QMessageBox.information(self, "Schema", "Questa tipologia non è legacy (engine). Modifica non supportata qui.")
            return
        dlg = TipologiaEditorDialog(self, base=data, is_new=False)
        if dlg.exec() == dlg.Accepted:
            out = dlg.result_tipologia()
            try:
                p.write_text(json.dumps(out, indent=2), encoding="utf-8")
                self._reload()
                # riposiziona selezione sul file
                for i in range(self.lst.count()):
                    en = self.lst.item(i).data(Qt.UserRole) or {}
                    if Path(en.get("path","")) == p:
                        self.lst.setCurrentRow(i); break
            except Exception as e:
                QMessageBox.critical(self, "Errore salvataggio", str(e))

    def _dup(self):
        p = self._current_path()
        if not p: return
        base = Path(self._dir_edit.text().strip() or ".")
        dst = base / f"{p.stem}_copia.json"
        try:
            shutil.copyfile(p, dst)
            self._reload()
            for i in range(self.lst.count()):
                en = self.lst.item(i).data(Qt.UserRole) or {}
                if Path(en.get("path","")) == dst:
                    self.lst.setCurrentRow(i); break
        except Exception as e:
            QMessageBox.critical(self, "Errore duplicazione", str(e))

    def _del(self):
        p = self._current_path()
        if not p: return
        if QMessageBox.question(self, "Elimina", f"Eliminare '{p.name}'?") != QMessageBox.Yes:
            return
        try:
            p.unlink(missing_ok=True)
            self._reload()
        except Exception as e:
            QMessageBox.critical(self, "Errore eliminazione", str(e))
