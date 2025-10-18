from __future__ import annotations
from typing import Dict, Any, List, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QInputDialog, QMessageBox
)

class HardwareMechanismManagerDialog(QDialog):
    """
    Gestione Meccanismi e Parti:
    - Meccanismi: code/name/descr (CRUD)
    - Parti/template: per meccanismo definisci parts con (part_key, display_name, profile_name, qty, angoli, formula)
    """
    def __init__(self, parent, store):
        super().__init__(parent)
        self.setWindowTitle("Gestione Meccanismi Ferramenta")
        self.resize(1000, 680)
        self.setModal(True)
        self.store = store
        self._cur_mech: Optional[str] = None
        self._build()
        self._reload_mechs()

    def _build(self):
        root = QVBoxLayout(self)

        # Meccanismi
        root.addWidget(QLabel("Meccanismi"))
        self.tbl_mech = QTableWidget(0, 3)
        self.tbl_mech.setHorizontalHeaderLabels(["Code", "Nome", "Descrizione"])
        hdr = self.tbl_mech.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        root.addWidget(self.tbl_mech)
        r1 = QHBoxLayout()
        b_add = QPushButton("Aggiungi"); b_add.clicked.connect(self._add_mech)
        b_edit = QPushButton("Modifica"); b_edit.clicked.connect(self._edit_mech)
        b_del = QPushButton("Elimina"); b_del.clicked.connect(self._del_mech)
        r1.addWidget(b_add); r1.addWidget(b_edit); r1.addWidget(b_del); r1.addStretch(1)
        root.addLayout(r1)

        # Parti
        root.addWidget(QLabel("Parti del meccanismo selezionato"))
        self.tbl_parts = QTableWidget(0, 8)
        self.tbl_parts.setHorizontalHeaderLabels(["Key","Nome","Profilo","Q.tà","Ang SX","Ang DX","Formula","ID"])
        hp = self.tbl_parts.horizontalHeader()
        hp.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hp.setSectionResizeMode(1, QHeaderView.Stretch)
        hp.setSectionResizeMode(2, QHeaderView.Stretch)
        hp.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hp.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        hp.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        hp.setSectionResizeMode(6, QHeaderView.Stretch)
        hp.setSectionResizeMode(7, QHeaderView.ResizeToContents)
        root.addWidget(self.tbl_parts)
        r2 = QHBoxLayout()
        b_p_add = QPushButton("Aggiungi/Modifica"); b_p_add.clicked.connect(self._add_or_edit_part)
        b_p_del = QPushButton("Elimina"); b_p_del.clicked.connect(self._del_part)
        btn_close = QPushButton("Chiudi"); btn_close.clicked.connect(self.accept)
        r2.addWidget(b_p_add); r2.addWidget(b_p_del); r2.addStretch(1); r2.addWidget(btn_close)
        root.addLayout(r2)

        self.tbl_mech.itemSelectionChanged.connect(self._on_mech_sel)

    def _reload_mechs(self):
        self.tbl_mech.setRowCount(0)
        for m in self.store.list_mechanisms():
            r = self.tbl_mech.rowCount(); self.tbl_mech.insertRow(r)
            self.tbl_mech.setItem(r, 0, QTableWidgetItem(m["code"]))
            self.tbl_mech.setItem(r, 1, QTableWidgetItem(m["name"]))
            self.tbl_mech.setItem(r, 2, QTableWidgetItem(m["description"]))
        self._cur_mech = None
        self._reload_parts()

    def _cur_mech_code(self) -> Optional[str]:
        r = self.tbl_mech.currentRow()
        if r < 0: return None
        return self.tbl_mech.item(r, 0).text()

    def _on_mech_sel(self):
        self._cur_mech = self._cur_mech_code()
        self._reload_parts()

    def _reload_parts(self):
        self.tbl_parts.setRowCount(0)
        if not self._cur_mech: return
        rows = self.store.list_mech_parts(self._cur_mech)
        for p in rows:
            r = self.tbl_parts.rowCount(); self.tbl_parts.insertRow(r)
            self.tbl_parts.setItem(r, 0, QTableWidgetItem(p["part_key"]))
            self.tbl_parts.setItem(r, 1, QTableWidgetItem(p["display_name"]))
            self.tbl_parts.setItem(r, 2, QTableWidgetItem(p["profile_name"]))
            self.tbl_parts.setItem(r, 3, QTableWidgetItem(str(p["qty"])))
            self.tbl_parts.setItem(r, 4, QTableWidgetItem(f"{float(p['ang_sx']):.1f}"))
            self.tbl_parts.setItem(r, 5, QTableWidgetItem(f"{float(p['ang_dx']):.1f}"))
            self.tbl_parts.setItem(r, 6, QTableWidgetItem(p["formula"]))
            self.tbl_parts.setItem(r, 7, QTableWidgetItem(str(p["id"])))

    def _add_mech(self):
        code, ok = QInputDialog.getText(self, "Nuovo meccanismo", "Codice (es. ribalta_dk):")
        if not ok or not (code or "").strip(): return
        name, ok = QInputDialog.getText(self, "Nuovo meccanismo", "Nome:")
        if not ok or not (name or "").strip(): return
        desc, ok = QInputDialog.getMultiLineText(self, "Nuovo meccanismo", "Descrizione:", "")
        if not ok: return
        try:
            self.store.create_mechanism(code.strip(), name.strip(), desc or "")
            self._reload_mechs()
        except Exception as e:
            QMessageBox.critical(self, "Errore", str(e))

    def _edit_mech(self):
        code = self._cur_mech_code()
        if not code: return
        name, ok = QInputDialog.getText(self, "Meccanismo", "Nome:", text=self.tbl_mech.item(self.tbl_mech.currentRow(), 1).text())
        if not ok or not (name or "").strip(): return
        desc, ok = QInputDialog.getMultiLineText(self, "Meccanismo", "Descrizione:", self.tbl_mech.item(self.tbl_mech.currentRow(), 2).text())
        if not ok: return
        try:
            self.store.update_mechanism(code, name.strip(), desc or "")
            self._reload_mechs()
        except Exception as e:
            QMessageBox.critical(self, "Errore", str(e))

    def _del_mech(self):
        code = self._cur_mech_code()
        if not code: return
        from PySide6.QtWidgets import QMessageBox as _MB
        if _MB.question(self, "Elimina", f"Eliminare meccanismo '{code}' e le sue parti?") != _MB.Yes:
            return
        try:
            self.store.delete_mechanism(code)
            self._reload_mechs()
        except Exception as e:
            QMessageBox.critical(self, "Errore", str(e))

    def _add_or_edit_part(self):
        if not self._cur_mech:
            QMessageBox.information(self, "Parti", "Seleziona prima un meccanismo.")
            return
        part_key, ok = QInputDialog.getText(self, "Parte", "Key (es. AST_INF_MONT):")
        if not ok or not (part_key or "").strip(): return
        disp, ok = QInputDialog.getText(self, "Parte", "Nome visuale:")
        if not ok or not (disp or "").strip(): return
        prof, ok = QInputDialog.getText(self, "Parte", "Profilo per aggregazione (es. ASTINA):", text="ASTINA")
        if not ok or not (prof or "").strip(): return
        try:
            qty, ok_qty = QInputDialog.getInt(self, "Parte", "Quantità:", 1, 1, 999, 1)
            if not ok_qty: return
            ang_sx, ok1 = QInputDialog.getDouble(self, "Parte", "Ang SX (°):", 0.0, 0.0, 90.0, 1)
            if not ok1: return
            ang_dx, ok2 = QInputDialog.getDouble(self, "Parte", "Ang DX (°):", 0.0, 0.0, 90.0, 1)
            if not ok2: return
        except Exception:
            return
        formula, ok = QInputDialog.getMultiLineText(self, "Parte", "Formula lunghezza (usa H,L,handle_offset,arm_code,arm_class,arm_len):", "H - 80")
        if not ok or not (formula or "").strip(): return
        try:
            self.store.upsert_mech_part(self._cur_mech, part_key.strip(), disp.strip(), prof.strip(), int(qty), float(ang_sx), float(ang_dx), formula.strip())
            self._reload_parts()
        except Exception as e:
            QMessageBox.critical(self, "Errore", str(e))

    def _del_part(self):
        if not self._cur_mech: return
        r = self.tbl_parts.currentRow()
        if r < 0: return
        key = self.tbl_parts.item(r, 0).text()
        from PySide6.QtWidgets import QMessageBox as _MB
        if _MB.question(self, "Elimina", f"Eliminare parte '{key}'?") != _MB.Yes:
            return
        try:
            self.store.delete_mech_part(self._cur_mech, key)
            self._reload_parts()
        except Exception as e:
            QMessageBox.critical(self, "Errore", str(e))
