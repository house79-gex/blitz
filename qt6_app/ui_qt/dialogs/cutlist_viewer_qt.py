from __future__ import annotations
from typing import List, Dict, Any
import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QFileDialog, QMessageBox
)

class CutlistViewerDialog(QDialog):
    """
    Finestra massimizzata per visualizzare una lista di taglio.
    Attesa struttura cuts: [{profile, element, length_mm, ang_sx, ang_dx, qty, note}]
    """
    def __init__(self, parent, cuts: List[Dict[str, Any]]):
        super().__init__(parent)
        self.setWindowTitle("Lista di taglio")
        self.setModal(True)
        self.setWindowState(Qt.WindowMaximized)
        self._cuts = cuts or []
        self._build()
        self._fill()

    def _build(self):
        root = QVBoxLayout(self)
        title = QLabel("LISTA DI TAGLIO")
        title.setStyleSheet("font-size:18px; font-weight:700;")
        root.addWidget(title)

        self.tbl = QTableWidget(0, 7)
        self.tbl.setHorizontalHeaderLabels(["Profilo", "Elemento", "Lunghezza (mm)", "Ang SX", "Ang DX", "Q.tà", "Note"])
        hdr = self.tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(6, QHeaderView.Stretch)
        root.addWidget(self.tbl, 1)

        row = QHBoxLayout()
        btn_close = QPushButton("Chiudi"); btn_close.clicked.connect(self.accept)
        btn_export_json = QPushButton("Salva JSON…"); btn_export_json.clicked.connect(self._export_json)
        btn_export_csv = QPushButton("Salva CSV…"); btn_export_csv.clicked.connect(self._export_csv)
        row.addStretch(1); row.addWidget(btn_export_json); row.addWidget(btn_export_csv); row.addWidget(btn_close)
        root.addLayout(row)

    def _fill(self):
        self.tbl.setRowCount(0)
        for c in self._cuts:
            r = self.tbl.rowCount(); self.tbl.insertRow(r)
            self.tbl.setItem(r, 0, QTableWidgetItem(str(c.get("profile",""))))
            self.tbl.setItem(r, 1, QTableWidgetItem(str(c.get("element",""))))
            self.tbl.setItem(r, 2, QTableWidgetItem(f"{float(c.get('length_mm',0.0)):.2f}"))
            self.tbl.setItem(r, 3, QTableWidgetItem(f"{float(c.get('ang_sx',0.0)):.1f}"))
            self.tbl.setItem(r, 4, QTableWidgetItem(f"{float(c.get('ang_dx',0.0)):.1f}"))
            self.tbl.setItem(r, 5, QTableWidgetItem(str(int(c.get("qty",0)))))
            self.tbl.setItem(r, 6, QTableWidgetItem(str(c.get("note",""))))

    def _export_json(self):
        path, _ = QFileDialog.getSaveFileName(self, "Salva lista (JSON)", "", "JSON (*.json)")
        if not path: return
        try:
            Path(path).write_text(json.dumps(self._cuts, indent=2, ensure_ascii=False), encoding="utf-8")
            QMessageBox.information(self, "Salva", "Salvato.")
        except Exception as e:
            QMessageBox.critical(self, "Errore", str(e))

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Salva lista (CSV)", "", "CSV (*.csv)")
        if not path: return
        try:
            import csv
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["Profilo","Elemento","Lunghezza (mm)","Ang SX","Ang DX","Q.tà","Note"])
                for c in self._cuts:
                    w.writerow([c.get("profile",""), c.get("element",""), f"{float(c.get('length_mm',0.0)):.2f}",
                                f"{float(c.get('ang_sx',0.0)):.1f}", f"{float(c.get('ang_dx',0.0)):.1f}",
                                int(c.get("qty",0)), c.get("note","")])
            QMessageBox.information(self, "Salva", "Salvato.")
        except Exception as e:
            QMessageBox.critical(self, "Errore", str(e))
