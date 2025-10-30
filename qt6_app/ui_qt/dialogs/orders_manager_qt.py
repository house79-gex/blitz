from __future__ import annotations
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QHBoxLayout, QPushButton, QInputDialog, QMessageBox
)

class OrdersManagerDialog(QDialog):
    """
    Lista ordini (commesse o cutlist) con Apri / Rinomina / Elimina.
    """
    def __init__(self, parent, store):
        super().__init__(parent)
        self.setWindowTitle("Gestione ordini")
        self.resize(820, 520)
        self.store = store
        self.selected_order_id: Optional[int] = None
        self._build(); self._reload()

    def _build(self):
        root = QVBoxLayout(self)
        root.addWidget(QLabel("Ordini salvati"))
        self.tbl = QTableWidget(0, 4)
        self.tbl.setHorizontalHeaderLabels(["ID", "Nome", "Cliente", "Aggiornato"])
        hdr = self.tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        root.addWidget(self.tbl, 1)

        row = QHBoxLayout()
        btn_open = QPushButton("Apri"); btn_open.clicked.connect(self._open)
        btn_rename = QPushButton("Rinomina"); btn_rename.clicked.connect(self._rename)
        btn_delete = QPushButton("Elimina"); btn_delete.clicked.connect(self._delete)
        btn_refresh = QPushButton("Aggiorna"); btn_refresh.clicked.connect(self._reload)
        btn_close = QPushButton("Chiudi"); btn_close.clicked.connect(self.reject)
        row.addWidget(btn_open); row.addWidget(btn_rename); row.addWidget(btn_delete); row.addWidget(btn_refresh); row.addStretch(1); row.addWidget(btn_close)
        root.addLayout(row)

    def _reload(self):
        self.tbl.setRowCount(0)
        for o in self.store.list_orders(limit=500):
            r = self.tbl.rowCount(); self.tbl.insertRow(r)
            self.tbl.setItem(r, 0, QTableWidgetItem(str(o["id"])))
            self.tbl.setItem(r, 1, QTableWidgetItem(o["name"]))
            self.tbl.setItem(r, 2, QTableWidgetItem(o.get("customer") or ""))
            self.tbl.setItem(r, 3, QTableWidgetItem(str(o.get("updated_at") or "")))

    def _selected_id(self) -> Optional[int]:
        r = self.tbl.currentRow()
        if r < 0: return None
        try: return int(self.tbl.item(r, 0).text())
        except Exception: return None

    def _open(self):
        oid = self._selected_id()
        if not oid:
            QMessageBox.information(self, "Apri", "Seleziona un ordine."); return
        self.selected_order_id = oid
        self.accept()

    def _rename(self):
        oid = self._selected_id()
        if not oid:
            QMessageBox.information(self, "Rinomina", "Seleziona un ordine."); return
        cur = self.store.get_order(oid)
        if not cur:
            QMessageBox.information(self, "Rinomina", "Ordine non trovato."); return
        newname, ok = QInputDialog.getText(self, "Rinomina", "Nuovo nome:", text=cur.get("name") or "")
        if not ok or not (newname or "").strip(): return
        try:
            self.store.update_order(oid, newname.strip(), cur.get("customer") or "", cur.get("data") or {})
            self._reload()
            QMessageBox.information(self, "Rinomina", "Nome aggiornato.")
        except Exception as e:
            QMessageBox.critical(self, "Errore", str(e))

    def _delete(self):
        oid = self._selected_id()
        if not oid:
            QMessageBox.information(self, "Elimina", "Seleziona un ordine."); return
        from PySide6.QtWidgets import QMessageBox as _MB
        if _MB.question(self, "Elimina", "Eliminare l'ordine selezionato?") != _MB.Yes:
            return
        try:
            self.store.delete_order(oid)
            self._reload()
            QMessageBox.information(self, "Elimina", "Ordine eliminato.")
        except Exception as e:
            QMessageBox.critical(self, "Errore", str(e))
