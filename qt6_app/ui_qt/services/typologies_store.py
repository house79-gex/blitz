from __future__ import annotations
from typing import Optional, Dict, Any, List
from pathlib import Path
import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QGridLayout, QLabel, QListWidget, QListWidgetItem,
    QWidget, QScrollArea, QPushButton, QFileDialog, QTableWidget, QTableWidgetItem,
    QSizePolicy, QLineEdit, QToolButton, QStyle, QMessageBox, QHeaderView, QInputDialog
)

from ui_qt.dialogs.tipologia_editor_qt import TipologiaEditorDialog
from ui_qt.services.typologies_store import TypologiesStore, default_db_path

class TipologiePage(QFrame):
    """
    Gestione tipologie su SQLite:
    - Selezione file DB (.db), creazione automatica schema
    - Lista tipologie dal DB
    - Nuova / Modifica / Duplica / Elimina
    - Home per tornare alla pagina principale
    """
    def __init__(self, appwin, db_path: Optional[str] = None):
        super().__init__()
        self.appwin = appwin
        self._db_edit: Optional[QLineEdit] = None
        self._store: Optional[TypologiesStore] = None
        self._build()
        path = Path(db_path) if db_path else default_db_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self._db_edit.setText(str(path))
        self._open_store()
        self._reload()

    # ------------ UI ------------
    def _build(self):
        self.setStyleSheet("QFrame { border: 1px solid #3b4b5a; border-radius: 6px; }")
        root = QHBoxLayout(self); root.setContentsMargins(8,8,8,8); root.setSpacing(10)

        # SX: DB + lista
        left = QFrame(); left.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding); left.setFixedWidth(420)
        ll = QVBoxLayout(left); ll.setContentsMargins(6,6,6,6); ll.setSpacing(6)

        rowp = QHBoxLayout()
        btn_home = QPushButton("Home"); btn_home.setToolTip("Torna alla Home")
        btn_home.clicked.connect(self._go_home)
        rowp.addWidget(btn_home, 0)

        rowp.addWidget(QLabel("Database tipologie (.db):"), 0)
        self._db_edit = QLineEdit(); self._db_edit.setPlaceholderText("Percorso file SQLite (.db)")
        rowp.addWidget(self._db_edit, 1)
        btn_dir = QToolButton(); btn_dir.setIcon(self.style().standardIcon(QStyle.SP_DirIcon))
        btn_dir.clicked.connect(self._browse_db); rowp.addWidget(btn_dir, 0)
        btn_open = QToolButton(); btn_open.setIcon(self.style().standardIcon(QStyle.SP_DialogOpenButton))
        btn_open.setToolTip("Apri/crea DB"); btn_open.clicked.connect(self._open_store)
        rowp.addWidget(btn_open, 0)
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
        self.tbl.setHorizontalHeaderLabels(["Campo","Valore 1","Valore 2","Valore 3","Valore 4","Altro"])
        hdr = self.tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.Stretch)
        rl.addWidget(self.tbl, 1)

        root.addWidget(left, 0); root.addWidget(center, 1); root.addWidget(right, 1)

    # ------------ Store/DB ------------
    def _browse_db(self):
        path, _ = QFileDialog.getSaveFileName(self, "Scegli o crea database tipologie", str(self._db_edit.text() or default_db_path()), "SQLite DB (*.db)")
        if not path:
            return
        self._db_edit.setText(path)
        self._open_store()
        self._reload()

    def _open_store(self):
        if self._store:
            self._store.close()
            self._store = None
        dbp = Path(self._db_edit.text().strip() or default_db_path())
        try:
            dbp.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        try:
            self._store = TypologiesStore(str(dbp))
            self.lbl_meta.setText(f"DB: {dbp.name}")
        except Exception as e:
            QMessageBox.critical(self, "Errore DB", f"Impossibile aprire/creare il DB:\n{e}")
            self._store = None

    # ------------ Lista/preview ------------
    def _reload(self):
        self.lst.clear()
        self._clear_preview("Seleziona una tipologia")
        if not self._store:
            return
        rows = self._store.list_typologies()
        for r in rows:
            it = QListWidgetItem(f"{r['name']}")
            it.setData(Qt.UserRole, r["id"])
            self.lst.addItem(it)
        if self.lst.count() > 0:
            self.lst.setCurrentRow(0)

    def _clear_preview(self, msg: str):
        for i in reversed(range(self.grid.count())):
            w = self.grid.itemAt(i).widget()
            if w: w.deleteLater()
        self.tbl.setRowCount(0)
        self.lbl_meta.setText(msg)

    def _on_select(self, cur: Optional[QListWidgetItem], prev: Optional[QListWidgetItem]):
        self._clear_preview("Seleziona una tipologia")
        if not cur or not self._store:
            return
        tid = int(cur.data(Qt.UserRole))
        data = self._store.get_typology_full(tid)
        if not data:
            self.lbl_meta.setText("Tipologia non trovata")
            return
        self._render_legacy(data)

    def _render_legacy(self, d: Dict[str,Any]):
        nome = str(d.get("nome","")); cat = str(d.get("categoria",""))
        rif = str(d.get("riferimento_quota","")); pezzi = int(d.get("pezzi_totali",1) or 1)
        extra = float(d.get("extra_detrazione_mm",0.0) or 0.0); note = str(d.get("note",""))
        self.lbl_meta.setText(f"{nome}")
        row = 0
        for label, val in (("Categoria",cat),("Riferimento quota",rif),("Pezzi totali",str(pezzi)),("Extra detrazione (mm)",f"{extra:.3f}"),("Note",note)):
            lab = QLabel(label + ":"); self.grid.addWidget(lab, row, 0)
            v = QLabel(val); v.setWordWrap(True); v.setStyleSheet("color:#0a0a0a;")
            self.grid.addWidget(v, row, 1, 1, 3); row += 1

        self.tbl.setRowCount(0)
        for c in d.get("componenti", []):
            r = self.tbl.rowCount(); self.tbl.insertRow(r)
            self.tbl.setItem(r, 0, QTableWidgetItem(c.get("id_riga","")))
            self.tbl.setItem(r, 1, QTableWidgetItem(c.get("nome","")))
            self.tbl.setItem(r, 2, QTableWidgetItem(c.get("profilo_nome","")))
            self.tbl.setItem(r, 3, QTableWidgetItem(str(c.get("quantita",0))))
            self.tbl.setItem(r, 4, QTableWidgetItem(f"AngSX:{c.get('ang_sx',0)} AngDX:{c.get('ang_dx',0)}"))
            self.tbl.setItem(r, 5, QTableWidgetItem(c.get("formula_lunghezza","")))

    # ------------ Azioni ------------
    def _go_home(self):
        try:
            if hasattr(self.appwin, "show_page"): self.appwin.show_page("home")
            elif hasattr(self.appwin, "go_home"): self.appwin.go_home()
        except Exception:
            pass

    def _current_id(self) -> Optional[int]:
        it = self.lst.currentItem()
        if not it: return None
        return int(it.data(Qt.UserRole))

    def _new(self):
        dlg = TipologiaEditorDialog(self, is_new=True)
        from PySide6
