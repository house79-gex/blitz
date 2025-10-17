from __future__ import annotations
from typing import Dict, Any, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit, QInputDialog, QMessageBox
)

class TypologyHardwareOptionsDialog(QDialog):
    """
    Gestisce le OPZIONI di ferramenta della tipologia (preset selezionabili in commessa):
    - Nome (etichetta utente)
    - Marca, Serie, Sottocategoria, Maniglia (opz.)
    """
    def __init__(self, parent, store, typology_id: int):
        super().__init__(parent)
        self.setWindowTitle("Opzioni ferramenta tipologia")
        self.resize(900, 560)
        self.setModal(True)
        self.store = store
        self.typology_id = int(typology_id)
        self._build()
        self._reload_all()

    def _build(self):
        root = QVBoxLayout(self)

        self.tbl = QTableWidget(0, 5)
        self.tbl.setHorizontalHeaderLabels(["ID", "Nome opzione", "Marca/Serie", "Sottocat.", "Maniglia"])
        hdr = self.tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.Stretch)
        root.addWidget(self.tbl, 1)

        row = QHBoxLayout()
        b_add = QPushButton("Aggiungi"); b_add.clicked.connect(self._add_option)
        b_edit = QPushButton("Modifica"); b_edit.clicked.connect(self._edit_option)
        b_del = QPushButton("Elimina"); b_del.clicked.connect(self._del_option)
        btn_close = QPushButton("Chiudi"); btn_close.clicked.connect(self.accept)
        row.addWidget(b_add); row.addWidget(b_edit); row.addWidget(b_del); row.addStretch(1); row.addWidget(btn_close)
        root.addLayout(row)

    def _reload_all(self):
        self.tbl.setRowCount(0)
        opts = self.store.list_typology_hw_options(self.typology_id)
        for o in opts:
            r = self.tbl.rowCount(); self.tbl.insertRow(r)
            self.tbl.setItem(r, 0, QTableWidgetItem(str(o["id"])))
            self.tbl.setItem(r, 1, QTableWidgetItem(o["name"]))
            self.tbl.setItem(r, 2, QTableWidgetItem(f"B{o['brand_id']}/S{o['series_id']}"))
            self.tbl.setItem(r, 3, QTableWidgetItem(o["subcat"]))
            self.tbl.setItem(r, 4, QTableWidgetItem(str(o["handle_id"] or "-")))

    def _add_option(self):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Opzione", "Nome opzione:")
        if not ok or not (name or "").strip():
            return
        try:
            brands = self.store.list_hw_brands()
        except Exception:
            brands = []
        if not brands:
            QMessageBox.information(self, "Ferramenta", "Prima crea una marca/serie nel catalogo.")
            return
        b_names = [b["name"] for b in brands]
        b_sel, ok = QInputDialog.getItem(self, "Marca", "Marca:", b_names, 0, False)
        if not ok: return
        brand_id = brands[b_names.index(b_sel)]["id"]

        series = self.store.list_hw_series(brand_id)
        if not series:
            QMessageBox.information(self, "Ferramenta", "Nessuna serie per la marca selezionata.")
            return
        s_names = [s["name"] for s in series]
        s_sel, ok = QInputDialog.getItem(self, "Serie", "Serie:", s_names, 0, False)
        if not ok: return
        series_id = series[s_names.index(s_sel)]["id"]

        subcats = self.store.list_hw_sash_subcats(brand_id, series_id)
        if not subcats:
            subc, ok = QInputDialog.getText(self, "Sottocategoria", "Sottocategoria:")
            if not ok or not (subc or "").strip(): return
        else:
            subc, ok = QInputDialog.getItem(self, "Sottocategoria", "Sottocategoria:", subcats, 0, False)
            if not ok: return

        handles = self.store.list_hw_handle_types(brand_id, series_id)
        handle_id = None
        if handles:
            h_labels = [f"{h['name']} ({h['handle_offset_mm']:.0f})" for h in handles]
            h_sel, ok = QInputDialog.getItem(self, "Maniglia (facolt.)", "Maniglia:", ["— Nessuna —"] + h_labels, 0, False)
            if ok and h_sel and h_sel != "— Nessuna —":
                handle_id = handles[h_labels.index(h_sel)]["id"]

        try:
            self.store.create_typology_hw_option(self.typology_id, name.strip(), int(brand_id), int(series_id), str(subc), handle_id)
            self._reload_all()
        except Exception as e:
            QMessageBox.critical(self, "Errore", str(e))

    def _get_selected_opt_id(self) -> Optional[int]:
        r = self.tbl.currentRow()
        if r < 0: return None
        try: return int(self.tbl.item(r, 0).text())
        except Exception: return None

    def _edit_option(self):
        opt_id = self._get_selected_opt_id()
        if not opt_id: return
        opt = self.store.get_typology_hw_option(opt_id)
        if not opt: return
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Opzione", "Nome opzione:", text=str(opt["name"]))
        if not ok or not (name or "").strip(): return

        brands = self.store.list_hw_brands(); b_map = {b["id"]: b["name"] for b in brands}
        b_names = [b_map[i] for i in b_map]
        cur_b = b_map.get(opt["brand_id"], b_names[0])
        b_sel, ok = QInputDialog.getItem(self, "Marca", "Marca:", b_names, b_names.index(cur_b) if cur_b in b_names else 0, False)
        if not ok: return
        brand_id = next(b["id"] for b in brands if b["name"] == b_sel)

        series = self.store.list_hw_series(brand_id); s_map = {s["id"]: s["name"] for s in series}
        s_names = [s_map[i] for i in s_map]
        cur_s = s_map.get(opt["series_id"], s_names[0])
        s_sel, ok = QInputDialog.getItem(self, "Serie", "Serie:", s_names, s_names.index(cur_s) if cur_s in s_names else 0, False)
        if not ok: return
        series_id = next(s["id"] for s in series if s["name"] == s_sel)

        subc, ok = QInputDialog.getText(self, "Sottocategoria", "Sottocategoria:", text=str(opt["subcat"]))
        if not ok or not (subc or "").strip(): return

        handles = self.store.list_hw_handle_types(brand_id, series_id)
        handle_id = opt["handle_id"]
        if handles:
            h_labels = [f"{h['name']} ({h['handle_offset_mm']:.0f})" for h in handles]
            if handle_id:
                cur_h = next((i for i, h in enumerate(handles) if int(h["id"]) == int(handle_id)), None)
                idx = (cur_h + 1) if cur_h is not None else 0
            else:
                idx = 0
            h_sel, ok = QInputDialog.getItem(self, "Maniglia (facolt.)", "Maniglia:", ["— Nessuna —"] + h_labels, idx, False)
            if not ok: return
            if h_sel and h_sel != "— Nessuna —":
                handle_id = handles[h_labels.index(h_sel)]["id"]
            else:
                handle_id = None

        try:
            self.store.update_typology_hw_option(opt_id, name.strip(), int(brand_id), int(series_id), str(subc), handle_id)
            self._reload_all()
        except Exception as e:
            QMessageBox.critical(self, "Errore", str(e))

    def _del_option(self):
        opt_id = self._get_selected_opt_id()
        if not opt_id: return
        from PySide6.QtWidgets import QMessageBox as _MB
        if _MB.question(self, "Conferma", "Eliminare l'opzione selezionata?") != _MB.Yes:
            return
        try:
            self.store.delete_typology_hw_option(opt_id)
            self._reload_all()
        except Exception as e:
            QMessageBox.critical(self, "Errore", str(e))
