from __future__ import annotations
from typing import Optional, Dict, Any, List
from pathlib import Path
import traceback

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QLineEdit, QToolButton, QStyle, QMessageBox,
    QTreeWidget, QTreeWidgetItem
)

from ui_qt.dialogs.tipologia_editor_qt import TipologiaEditorDialog
from ui_qt.services.typologies_store import TypologiesStore, default_db_path

class TipologiePage(QFrame):
    """
    Vista semplificata:
    - Elenco tipologie raggruppate per categoria (albero)
    - Ricerca veloce
    - Nuova / Modifica / Duplica / Elimina
    Nessun riepilogo componenti in questa pagina.
    """
    def __init__(self, appwin, db_path: Optional[str] = None):
        super().__init__()
        self.appwin = appwin
        self._store = TypologiesStore(str(default_db_path()))
        self._build()
        self._reload()

    def _build(self):
        self.setStyleSheet("QFrame { border: 1px solid #3b4b5a; border-radius: 6px; }")
        root = QVBoxLayout(self); root.setContentsMargins(8,8,8,8); root.setSpacing(8)

        # Barra comandi
        top = QHBoxLayout()
        btn_home = QPushButton("Home"); btn_home.clicked.connect(self._go_home); top.addWidget(btn_home)
        top.addSpacing(8)
        top.addWidget(QLabel("Cerca:"))
        self.ed_search = QLineEdit(); self.ed_search.setPlaceholderText("Filtra per nome o categoria")
        self.ed_search.textChanged.connect(self._reload)
        top.addWidget(self.ed_search, 1)

        self.btn_new = QPushButton("Nuova…"); self.btn_new.clicked.connect(self._new)
        self.btn_edit = QPushButton("Modifica…"); self.btn_edit.clicked.connect(self._edit)
        self.btn_dup = QPushButton("Duplica"); self.btn_dup.clicked.connect(self._dup)
        self.btn_del = QPushButton("Elimina"); self.btn_del.clicked.connect(self._del)
        top.addWidget(self.btn_new); top.addWidget(self.btn_edit); top.addWidget(self.btn_dup); top.addWidget(self.btn_del)
        root.addLayout(top)

        # Albero categorie -> tipologie
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Categoria / Tipologia"])
        self.tree.setColumnCount(1)
        self.tree.itemDoubleClicked.connect(self._edit_on_double)
        root.addWidget(self.tree, 1)

        # Nota
        note = QLabel("Suggerimento: doppio click su una tipologia per modificarla. Le categorie sono generate dinamicamente.")
        note.setStyleSheet("color:#7f8c8d;")
        root.addWidget(note)

    def _go_home(self):
        try:
            if hasattr(self.appwin, "show_page"): self.appwin.show_page("home")
            elif hasattr(self.appwin, "go_home"): self.appwin.go_home()
        except Exception: pass

    def _reload(self):
        self.tree.clear()
        rows = self._store.list_typologies()
        q = (self.ed_search.text() or "").lower().strip()
        # group by category
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            if q:
                name = (r["name"] or "").lower()
                cat = (r["category"] or "").lower()
                if q not in name and q not in cat:
                    continue
            cat = r["category"] or "(senza categoria)"
            groups.setdefault(cat, []).append(r)
        # build tree
        for cat, items in sorted(groups.items(), key=lambda kv: kv[0].lower()):
            root = QTreeWidgetItem([cat])
            root.setFlags(root.flags() & ~Qt.ItemIsSelectable)
            self.tree.addTopLevelItem(root)
            for r in sorted(items, key=lambda x: (x["name"] or "").lower()):
                leaf = QTreeWidgetItem([r["name"]])
                leaf.setData(0, Qt.UserRole, int(r["id"]))
                root.addChild(leaf)
            root.setExpanded(True)

    def _current_id(self) -> Optional[int]:
        it = self.tree.currentItem()
        if not it:
            return None
        # se è una categoria, non ha UserRole
        val = it.data(0, Qt.UserRole)
        return int(val) if val is not None else None

    def _new(self):
        dlg = TipologiaEditorDialog(self, is_new=True)
        from PySide6.QtWidgets import QDialog as _QDialog
        try:
            if dlg.exec() == _QDialog.DialogCode.Accepted:
                data = dlg.result_tipologia()
                # garantisco che la struttura sia completa (minimi)
                if not isinstance(data, dict):
                    QMessageBox.critical(self, "Errore", "Dati tipologia non validi (formato).")
                    return
                data.setdefault("variabili_locali", {})
                data.setdefault("options", {})
                data.setdefault("componenti", [])
                try:
                    tid = self._store.create_typology(data)
                    QMessageBox.information(self, "OK", f"Tipologia creata (id={tid}).")
                    self._reload()
                except Exception as e:
                    tb = traceback.format_exc()
                    QMessageBox.critical(self, "Errore salvataggio", f"{e}\n\n{tb}")
        except Exception as e:
            tb = traceback.format_exc()
            QMessageBox.critical(self, "Errore dialog", f"{e}\n\n{tb}")

    def _edit(self):
        tid = self._current_id()
        if not tid: return
        try:
            data = self._store.get_typology_full(tid)
            if not data:
                QMessageBox.critical(self, "Errore", "Tipologia non trovata nel DB.")
                return
            dlg = TipologiaEditorDialog(self, base=data, is_new=False)
            from PySide6.QtWidgets import QDialog as _QDialog
            if dlg.exec() == _QDialog.DialogCode.Accepted:
                out = dlg.result_tipologia()
                out.setdefault("variabili_locali", {})
                out.setdefault("options", {})
                out.setdefault("componenti", [])
                try:
                    self._store.update_typology(tid, out)
                    QMessageBox.information(self, "OK", "Tipologia aggiornata.")
                    self._reload()
                except Exception as e:
                    tb = traceback.format_exc()
                    QMessageBox.critical(self, "Errore salvataggio", f"{e}\n\n{tb}")
        except Exception as e:
            tb = traceback.format_exc()
            QMessageBox.critical(self, "Errore", f"{e}\n\n{tb}")

    def _edit_on_double(self, item: QTreeWidgetItem, _col: int):
        if item and item.data(0, Qt.UserRole) is not None:
            self._edit()

    def _dup(self):
        tid = self._current_id()
        if not tid: return
        from PySide6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(self, "Duplica tipologia", "Nuovo nome:")
        if not ok or not (new_name or "").strip(): return
        try:
            new_id = self._store.duplicate_typology(tid, (new_name or "").strip())
            if new_id:
                QMessageBox.information(self, "OK", f"Tipologia duplicata (id={new_id}).")
                self._reload()
        except Exception as e:
            tb = traceback.format_exc()
            QMessageBox.critical(self, "Errore duplicazione", f"{e}\n\n{tb}")

    def _del(self):
        tid = self._current_id()
        if not tid: return
        from PySide6.QtWidgets import QMessageBox as _MB
        if _MB.question(self, "Elimina", "Eliminare la tipologia selezionata?") != _MB.Yes:
            return
        try:
            self._store.delete_typology(tid)
            self._reload()
        except Exception as e:
            tb = traceback.format_exc()
            QMessageBox.critical(self, "Errore eliminazione", f"{e}\n\n{tb}")
