from __future__ import annotations
from typing import List, Dict, Any, Tuple
from collections import defaultdict

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QHBoxLayout, QAbstractItemView
)

class OptimizationRunDialog(QDialog):
    """
    Finestra di riepilogo ottimizzazione per profilo:
    - Mostra le righe della cutlist del profilo selezionato (aggregate per length/angoli).
    - Sola visualizzazione, evidenziazione selezione forte, righe finite in verde.
    - Si chiude automaticamente quando tutte le qty sono a zero (emit finished).
    """
    finished = Signal(str)  # profile

    def __init__(self, parent, profile: str, rows: List[Dict[str, Any]]):
        super().__init__(parent)
        self.setWindowTitle(f"Ottimizzazione - {profile}")
        self.setModal(False)
        self.resize(900, 520)
        self.profile = profile
        # Aggrega per (len, ang_sx, ang_dx) sommando qty
        agg = defaultdict(int)
        for r in rows:
            k = (round(float(r["length_mm"]), 2), float(r["ang_sx"]), float(r["ang_dx"]))
            agg[k] += int(r["qty"])
        self._data = [(L, ax, ad, q) for (L, ax, ad), q in agg.items()]
        self._build()
        self._fill()

    def _build(self):
        root = QVBoxLayout(self)
        root.addWidget(QLabel(f"Profilo: {self.profile}"))
        self.tbl = QTableWidget(0, 5)
        self.tbl.setHorizontalHeaderLabels(["Profilo", "Elemento", "Lunghezza (mm)", "Ang SX", "Ang DX"])
        hdr = self.tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setStyleSheet("""
            QTableWidget::item:selected { background:#1976d2; color:#ffffff; font-weight:700; }
        """)
        root.addWidget(self.tbl, 1)
        row = QHBoxLayout()
        self.btn_close = QPushButton("Chiudi"); self.btn_close.clicked.connect(self.close)
        row.addStretch(1); row.addWidget(self.btn_close)
        root.addLayout(row)

    def _fill(self):
        self.tbl.setRowCount(0)
        # ordina per lunghezza decrescente
        self._data.sort(key=lambda x: x[0], reverse=True)
        for (L, ax, ad, q) in self._data:
            r = self.tbl.rowCount(); self.tbl.insertRow(r)
            self.tbl.setItem(r, 0, QTableWidgetItem(self.profile))
            self.tbl.setItem(r, 1, QTableWidgetItem(f"— x{q}"))
            self.tbl.setItem(r, 2, QTableWidgetItem(f"{float(L):.2f}"))
            self.tbl.setItem(r, 3, QTableWidgetItem(f"{float(ax):.1f}"))
            self.tbl.setItem(r, 4, QTableWidgetItem(f"{float(ad):.1f}"))
            if q == 0:
                self._mark_finished_row(r)

    def _mark_finished_row(self, row: int):
        for c in range(self.tbl.columnCount()):
            it = self.tbl.item(row, c)
            if not it: continue
            it.setBackground(QBrush(QColor("#d5f5e3")))

    def update_after_cut(self, length_mm: float, ang_sx: float, ang_dx: float):
        """Scala qty per la riga che matcha e aggiorna UI; chiudi se tutte 0."""
        tgtL = round(float(length_mm), 2)
        ax = float(ang_sx); ad = float(ang_dx)
        # Trova riga
        for r in range(self.tbl.rowCount()):
            try:
                L = round(float(self.tbl.item(r, 2).text()), 2)
                a1 = float(self.tbl.item(r, 3).text())
                a2 = float(self.tbl.item(r, 4).text())
            except Exception:
                continue
            if abs(L - tgtL) <= 0.01 and abs(a1 - ax) <= 0.01 and abs(a2 - ad) <= 0.01:
                # parse qty in "— xQ"
                elem = self.tbl.item(r, 1).text()
                try:
                    q = int(elem.split("x")[-1].strip())
                except Exception:
                    q = 1
                q = max(0, q - 1)
                self.tbl.setItem(r, 1, QTableWidgetItem(f"— x{q}"))
                if q == 0:
                    self._mark_finished_row(r)
                break
        # verifica chiusura
        all_zero = True
        for r in range(self.tbl.rowCount()):
            elem = self.tbl.item(r, 1).text()
            try:
                q = int(elem.split("x")[-1].strip())
            except Exception:
                q = 0
            if q > 0:
                all_zero = False
                break
        if all_zero:
            self.finished.emit(self.profile)
            self.close()
