from __future__ import annotations
from typing import Dict, Any, List, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QInputDialog, QMessageBox
)

class TypologyHardwareOptionsDialog(QDialog):
    """
    Opzioni ferramenta della tipologia:
    - Nome opzione
    - Marca, Serie, Sottocategoria, Maniglia (facoltativa)
    - Meccanismo (normale / ribalta_cremonese / ribalta_dk / custom)
    """
    def __init__(self, parent, store, typology_id: int):
        super().__init__(parent)
        self.setWindowTitle("Opzioni ferramenta tipologia")
        self.resize(920, 560)
        self.setModal(True)
        self.store = store
        self.typology_id = int(typology_id)
        self._build()
        self._reload_all()

    def _build(self):
        root = QVBoxLayout(self)
        self.tbl = QTableWidget(0, 6)
        self.tbl.setHorizontalHeaderLabels(["ID", "Opzione", "Marca/Serie", "Sottocat.", "Maniglia", "Meccanismo"])
        hdr = self.tbl.horizontalHeader()
        for i, mode in enumerate([QHeaderView.ResizeToContents, QHeaderView.Stretch, QHeaderView.Stretch,
                                  QHeaderView.ResizeToContents, QHeaderView.Stretch, QHeaderView.ResizeToContents]):
            hdr.setSectionResizeMode(i, mode)
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
            mech = o.get("mechanism_code") or "-"
            self.tbl.setItem(r, 0, QTableWidgetItem(str(o["id"])))
            self.tbl.setItem(r, 1, QTableWidgetItem(o["name"]))
            self.tbl.setItem(r, 2, QTableWidgetItem(f"B{o['brand_id']}/S{o['series_id']}"))
            self.tbl.setItem(r, 3, QTableWidgetItem(o["subcat"]))
            self.tbl.setItem(r, 4, QTableWidgetItem(str(o["handle_id"] or "-")))
            self.tbl.setItem(r, 5, QTableWidgetItem(mech))

    def _choose_brand_series(self) -> Optional[tuple[int,int]]:
        brands = self.store.list_hw_brands()
        if not brands:
            QMessageBox.information(self, "Ferramenta", "Nessuna marca disponibile."); return None
        b_names = [b["name"] for b in brands]
        b_sel, ok = QInputDialog.getItem(self, "Marca", "Marca:", b_names, 0, False)
        if not ok: return None
        brand_id = brands[b_names.index(b_sel)]["id"]
        series = self.store.list_hw_series(brand_id)
        if not series:
            QMessageBox.information(self, "Ferramenta", "Nessuna serie per la marca selezionata."); return None
        s_names = [s["name"] for s in series]
        s_sel, ok = QInputDialog.getItem(self, "Serie", "Serie:", s_names, 0, False)
        if not ok: return None
        series_id = series[s_names.index(s_sel)]["id"]
        return brand_id, series_id

    def _choose_subcat_and_handle(self, brand_id: int, series_id: int) -> tuple[str, Optional[int]]:
        subcats = self.store.list_hw_sash_subcats(brand_id, series_id)
        if subcats:
            subc, ok = QInputDialog.getItem(self, "Sottocategoria", "Sottocategoria:", subcats, 0, False)
            if not ok: return "", None
        else:
            subc, ok = QInputDialog.getText(self, "Sottocategoria", "Sottocategoria:")
            if not ok or not (subc or "").strip(): return "", None
        handle_id = None
        handles = self.store.list_hw_handle_types(brand_id, series_id)
        if handles:
            labels = ["— Nessuna —"] + [f"{h['name']} ({h['handle_offset_mm']:.0f})" for h in handles]
            h_sel, ok = QInputDialog.getItem(self, "Maniglia (facolt.)", "Maniglia:", labels, 0, False)
            if ok and h_sel and h_sel != "— Nessuna —":
                handle_id = handles[labels.index(h_sel)-1]["id"]
        return subc, handle_id

    def _choose_mechanism(self) -> Optional[str]:
        mechs = self.store.list_mechanisms()
        if not mechs:
            QMessageBox.information(self, "Meccanismi", "Nessun meccanismo definito. Crea meccanismi nel relativo manager."); return None
        labels = [f"{m['name']} ({m['code']})" for m in mechs]
        sel, ok = QInputDialog.getItem(self, "Meccanismo", "Seleziona meccanismo:", labels, 0, False)
        if not ok: return None
        idx = labels.index(sel)
        return mechs[idx]["code"]

    def _add_option(self):
        name, ok = QInputDialog.getText(self, "Opzione", "Nome opzione:")
        if not ok or not (name or "").strip(): return
        bs = self._choose_brand_series()
        if not bs: return
        brand_id, series_id = bs
        subc, handle_id = self._choose_subcat_and_handle(brand_id, series_id)
        if not subc: return
        mech = self._choose_mechanism()
        if mech is None: return
        try:
            self.store.create_typology_hw_option(self.typology_id, name.strip(), int(brand_id), int(series_id), subc, handle_id, mech)
            self._reload_all()
        except Exception as e:
            QMessageBox.critical(self, "Errore", str(e))

    def _get_sel_id(self) -> Optional[int]:
        r = self.tbl.currentRow()
        if r < 0: return None
        try: return int(self.tbl.item(r, 0).text())
        except Exception: return None

    def _edit_option(self):
        opt_id = self._get_sel_id()
        if not opt_id: return
        opt = self.store.get_typology_hw_option(opt_id)
        if not opt: return
        name, ok = QInputDialog.getText(self, "Opzione", "Nome opzione:", text=str(opt["name"]))
        if not ok or not (name or "").strip(): return
        # brand/series
        bs = self._choose_brand_series()
        if not bs: return
        brand_id, series_id = bs
        subc, handle_id = self._choose_subcat_and_handle(brand_id, series_id)
        if not subc: return
        mech = self._choose_mechanism()
        if mech is None: return
        try:
            self.store.update_typology_hw_option(opt_id, name.strip(), int(brand_id), int(series_id), subc, handle_id, mech)
            self._reload_all()
        except Exception as e:
            QMessageBox.critical(self, "Errore", str(e))

    def _del_option(self):
        opt_id = self._get_sel_id()
        if not opt_id: return
        from PySide6.QtWidgets import QMessageBox as _MB
        if _MB.question(self, "Elimina", "Eliminare l'opzione selezionata?") != _MB.Yes:
            return
        try:
            self.store.delete_typology_hw_option(opt_id)
            self._reload_all()
        except Exception as e:
            QMessageBox.critical(self, "Errore", str(e))
