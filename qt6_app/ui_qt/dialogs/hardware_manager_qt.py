from __future__ import annotations
from typing import Dict, Any, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit, QSpinBox, QDoubleSpinBox, QMessageBox
)

class HardwareManagerDialog(QDialog):
    """
    Gestione catalogo ferramenta:
    - Marche / Serie
    - Maniglie (offset)
    - Regole Bracci (range L → arm_code)
    - Formule Astina (per sottocategoria, opzionalmente per arm_code)
    NB: Dialog compatto: CRUD elementare inline; salva direttamente sullo store.
    """
    def __init__(self, parent, store):
        super().__init__(parent)
        self.setWindowTitle("Gestisci ferramenta")
        self.resize(980, 720)
        self.setModal(True)
        self.store = store
        self._build()
        self._reload_all()

    def _build(self):
        root = QVBoxLayout(self)

        # Marca/Serie
        row = QHBoxLayout()
        row.addWidget(QLabel("Marca:"))
        self.cmb_brand = QComboBox(); self.cmb_brand.currentIndexChanged.connect(self._on_brand_changed)
        row.addWidget(self.cmb_brand)
        btn_add_b = QPushButton("Nuova marca"); btn_add_b.clicked.connect(self._add_brand)
        row.addWidget(btn_add_b)

        row.addWidget(QLabel("Serie:"))
        self.cmb_series = QComboBox(); self.cmb_series.currentIndexChanged.connect(self._on_series_changed)
        row.addWidget(self.cmb_series)
        btn_add_s = QPushButton("Nuova serie"); btn_add_s.clicked.connect(self._add_series)
        row.addWidget(btn_add_s)

        root.addLayout(row)

        # Maniglie
        root.addWidget(QLabel("Maniglie (offset mm):"))
        self.tbl_handles = QTableWidget(0, 3)
        self.tbl_handles.setHorizontalHeaderLabels(["ID", "Nome", "Offset (mm)"])
        hdr = self.tbl_handles.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        root.addWidget(self.tbl_handles)
        r1 = QHBoxLayout()
        b_h_add = QPushButton("Aggiungi"); b_h_add.clicked.connect(self._add_handle)
        b_h_del = QPushButton("Elimina"); b_h_del.clicked.connect(self._del_handle)
        r1.addWidget(b_h_add); r1.addWidget(b_h_del); r1.addStretch(1)
        root.addLayout(r1)

        # Regole Bracci
        root.addWidget(QLabel("Regole Bracci (sottocategoria, L min/max → arm_code/nome):"))
        self.tbl_arms = QTableWidget(0, 6)
        self.tbl_arms.setHorizontalHeaderLabels(["ID", "Sottocat", "L min", "L max", "Arm code", "Arm nome"])
        hdr = self.tbl_arms.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.Stretch)
        hdr.setSectionResizeMode(5, QHeaderView.Stretch)
        root.addWidget(self.tbl_arms)
        r2 = QHBoxLayout()
        b_a_add = QPushButton("Aggiungi"); b_a_add.clicked.connect(self._add_arm_rule)
        b_a_del = QPushButton("Elimina"); b_a_del.clicked.connect(self._del_arm_rule)
        r2.addWidget(b_a_add); r2.addWidget(b_a_del); r2.addStretch(1)
        root.addLayout(r2)

        # Formule Astina
        root.addWidget(QLabel("Formule Astina (per sottocategoria, opzionale per arm_code):"))
        self.tbl_astina = QTableWidget(0, 4)
        self.tbl_astina.setHorizontalHeaderLabels(["ID", "Sottocat", "Arm code (facol.)", "Formula"])
        hdr = self.tbl_astina.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)
        root.addWidget(self.tbl_astina)
        r3 = QHBoxLayout()
        b_f_add = QPushButton("Aggiungi"); b_f_add.clicked.connect(self._add_astina_formula)
        b_f_del = QPushButton("Elimina"); b_f_del.clicked.connect(self._del_astina_formula)
        r3.addWidget(b_f_add); r3.addWidget(b_f_del); r3.addStretch(1)
        root.addLayout(r3)

        # Close
        rr = QHBoxLayout()
        btn_close = QPushButton("Chiudi"); btn_close.clicked.connect(self.accept)
        rr.addStretch(1); rr.addWidget(btn_close)
        root.addLayout(rr)

    def _reload_all(self):
        # Brands
        self.cmb_brand.clear()
        try:
            brands = self.store.list_hw_brands()
        except Exception:
            brands = []
        for b in brands:
            self.cmb_brand.addItem(b["name"], int(b["id"]))
        self._on_brand_changed()

    def _on_brand_changed(self):
        self.cmb_series.clear()
        bid = self.cmb_brand.currentData()
        if not bid:
            return
        series = self.store.list_hw_series(int(bid))
        for s in series:
            self.cmb_series.addItem(s["name"], int(s["id"]))
        self._on_series_changed()

    def _on_series_changed(self):
        self._reload_handles()
        self._reload_arms()
        self._reload_astine()

    def _reload_handles(self):
        self.tbl_handles.setRowCount(0)
        bid = self.cmb_brand.currentData(); sid = self.cmb_series.currentData()
        if not (bid and sid): return
        rows = self.store.list_hw_handle_types(int(bid), int(sid))
        for r in rows:
            ri = self.tbl_handles.rowCount(); self.tbl_handles.insertRow(ri)
            self.tbl_handles.setItem(ri, 0, QTableWidgetItem(str(r["id"])))
            self.tbl_handles.setItem(ri, 1, QTableWidgetItem(r["name"]))
            self.tbl_handles.setItem(ri, 2, QTableWidgetItem(f"{r['handle_offset_mm']:.1f}"))

    def _reload_arms(self):
        self.tbl_arms.setRowCount(0)
        bid = self.cmb_brand.currentData(); sid = self.cmb_series.currentData()
        if not (bid and sid): return
        subcats = self.store.list_hw_sash_subcats(int(bid), int(sid))
        # Carica tutte le regole per comodità
        for sc in subcats:
            # non c'è una API per elenco regole, ma possiamo leggere direttamente via query pick per un range fittizio
            # In mancanza, lasciamo la tabella gestita via add manuale (vedi _add_arm_rule): qui non ricarichiamo nulla extra.
            pass

        # Non abbiamo una funzione per elencare tutte le regole in store: potresti implementarla in futuro.
        # Per ora questa tabella viene popolata solo dagli inserimenti fatti nel dialog corrente (non persistenti se non via add).
        # Se serve, si può estendere TypologiesStore con list_hw_arm_rules().

    def _reload_astine(self):
        self.tbl_astina.setRowCount(0)
        # Come per arms: non abbiamo una list API generalizzata; gestiamo nuovi inserimenti per ora.
        # Estendibile con una API store per elencare tutte le formule.

    # --- CRUD di base ---
    def _add_brand(self):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Nuova marca", "Nome marca:")
        if not ok or not (name or "").strip():
            return
        try:
            # insert brand
            self.store._conn.execute("INSERT INTO hw_brand(name) VALUES(?)", (name.strip(),))
            self.store._conn.commit()
            self._reload_all()
        except Exception as e:
            QMessageBox.critical(self, "Errore", str(e))

    def _add_series(self):
        bid = self.cmb_brand.currentData()
        if not bid:
            return
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Nuova serie", "Nome serie:")
        if not ok or not (name or "").strip():
            return
        try:
            self.store._conn.execute("INSERT INTO hw_series(brand_id,name) VALUES(?,?)", (int(bid), name.strip()))
            self.store._conn.commit()
            self._on_brand_changed()
        except Exception as e:
            QMessageBox.critical(self, "Errore", str(e))

    def _add_handle(self):
        bid = self.cmb_brand.currentData(); sid = self.cmb_series.currentData()
        if not (bid and sid): return
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Maniglia", "Nome maniglia:")
        if not ok or not (name or "").strip():
            return
        off, ok2 = QInputDialog.getDouble(self, "Offset", "Offset (mm):", 100.0, 0, 5000, 1)
        if not ok2:
            return
        try:
            # code = name senza spazi come semplice esempio
            code = "".join(ch for ch in name if ch.isalnum() or ch in ("-","_")).upper() or "H"
            self.store._conn.execute(
                "INSERT INTO hw_handle_type(brand_id,series_id,code,name,handle_offset_mm) VALUES(?,?,?,?,?)",
                (int(bid), int(sid), code, name.strip(), float(off))
            )
            self.store._conn.commit()
            self._reload_handles()
        except Exception as e:
            QMessageBox.critical(self, "Errore", str(e))

    def _del_handle(self):
        row = self.tbl_handles.currentRow()
        if row < 0: return
        hid = int(self.tbl_handles.item(row, 0).text())
        try:
            self.store._conn.execute("DELETE FROM hw_handle_type WHERE id=?", (hid,))
            self.store._conn.commit()
            self._reload_handles()
        except Exception as e:
            QMessageBox.critical(self, "Errore", str(e))

    def _add_arm_rule(self):
        bid = self.cmb_brand.currentData(); sid = self.cmb_series.currentData()
        if not (bid and sid): return
        from PySide6.QtWidgets import QInputDialog
        subc, ok = QInputDialog.getText(self, "Sottocategoria", "Sottocategoria (es. battente_standard):")
        if not ok or not (subc or "").strip():
            return
        wmin, ok2 = QInputDialog.getDouble(self, "Larghezza minima", "L min (mm):", 400, 0, 5000, 1)
        if not ok2: return
        wmax, ok3 = QInputDialog.getDouble(self, "Larghezza massima", "L max (mm):", 800, 0, 5000, 1)
        if not ok3: return
        arm_code, ok4 = QInputDialog.getText(self, "Braccio", "Arm code:")
        if not ok4 or not (arm_code or "").strip(): return
        arm_name, ok5 = QInputDialog.getText(self, "Braccio", "Arm nome (facoltativo):")
        if not ok5: arm_name = ""
        try:
            self.store._conn.execute(
                "INSERT INTO hw_arm_rule(brand_id,series_id,sash_subcat,w_min,w_max,
