from __future__ import annotations
from typing import List, Dict, Any
from collections import defaultdict

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush, QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QFileDialog, QMessageBox, QAbstractItemView
)

class CutlistViewerDialog(QDialog):
    """
    Viewer sola-visualizzazione della lista di taglio, raggruppata per profilo.
    - Righe di intestazione per ciascun profilo (bold, grigio).
    - Evidenziazione selezione forte.
    - Nessun callback/azione: è solamente una finestra di visualizzazione/esportazione.
    """
    def __init__(self, parent, cuts: List[Dict[str, Any]]):
        super().__init__(parent)
        self.setWindowTitle("Lista di taglio")
        self.setModal(True)
        self.setWindowState(Qt.WindowMaximized)
        self._cuts = cuts or []
        self._build()
        self._fill_grouped()

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

        # Sola visualizzazione
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setStyleSheet("""
            QTableWidget::item:selected { background:#1976d2; color:#ffffff; font-weight:700; }
        """)

        root.addWidget(self.tbl, 1)

        row = QHBoxLayout()
        btn_export_json = QPushButton("Salva JSON…"); btn_export_json.setToolTip("Esporta la lista in JSON")
        btn_export_json.clicked.connect(self._export_json)
        btn_export_csv = QPushButton("Salva CSV…"); btn_export_csv.setToolTip("Esporta la lista in CSV")
        btn_export_csv.clicked.connect(self._export_csv)
        btn_close = QPushButton("Chiudi"); btn_close.clicked.connect(self.accept)
        row.addStretch(1); row.addWidget(btn_export_json); row.addWidget(btn_export_csv); row.addWidget(btn_close)
        root.addLayout(row)

    def _header_row(self, profile: str) -> List[QTableWidgetItem]:
        it_prof = QTableWidgetItem(profile)
        it_prof.setData(Qt.UserRole, {"type": "header", "profile": profile})
        it_prof.setForeground(QBrush(Qt.black))
        font = QFont(); font.setBold(True)
        it_prof.setFont(font)
        bg = QBrush(QColor("#ecf0f1"))
        items = [it_prof]
        for _ in range(6):
            it = QTableWidgetItem("")
            it.setBackground(bg)
            it.setFont(font)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            items.append(it)
        for it in items:
            it.setBackground(bg)
        return items

    def _fill_grouped(self):
        # Raggruppa per profilo mantenendo ordine d'apparizione
        groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        order: List[str] = []
        for c in self._cuts:
            p = str(c.get("profile", "")).strip()
            if p not in groups:
                order.append(p)
            groups[p].append(c)

        self.tbl.setRowCount(0)
        for prof in order:
            # Intestazione profilo
            r = self.tbl.rowCount(); self.tbl.insertRow(r)
            hdr_items = self._header_row(prof)
            for col, it in enumerate(hdr_items):
                self.tbl.setItem(r, col, it)
            # Righe elementi del profilo
            for c in groups[prof]:
                r = self.tbl.rowCount(); self.tbl.insertRow(r)
                row_items = [
                    QTableWidgetItem(str(c.get("profile",""))),
                    QTableWidgetItem(str(c.get("element",""))),
                    QTableWidgetItem(f"{float(c.get('length_mm',0.0)):.2f}"),
                    QTableWidgetItem(f"{float(c.get('ang_sx',0.0)):.1f}"),
                    QTableWidgetItem(f"{float(c.get('ang_dx',0.0)):.1f}"),
                    QTableWidgetItem(str(int(c.get("qty",0)))),
                    QTableWidgetItem(str(c.get("note","")))
                ]
                # metadata per distinguere item/header
                row_items[0].setData(Qt.UserRole, {"type": "item", "profile": prof})
                for col, it in enumerate(row_items):
                    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    self.tbl.setItem(r, col, it)

    def _export_json(self):
        path, _ = QFileDialog.getSaveFileName(self, "Salva lista (JSON)", "", "JSON (*.json)")
        if not path: return
        import json
        from pathlib import Path
        try:
            Path(path).write_text(json.dumps(self._cuts, indent=2, ensure_ascii=False), encoding="utf-8")
            QMessageBox.information(self, "Salva", "Salvato.")
        except Exception as e:
            QMessageBox.critical(self, "Errore", str(e))

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Salva lista (CSV)", "", "CSV (*.csv)")
        if not path: return
        import csv
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["Profilo","Elemento","Lunghezza (mm)","Ang SX","Ang DX","Q.tà","Note"])
                for c in self._cuts:
                    w.writerow([
                        c.get("profile",""), c.get("element",""),
                        f"{float(c.get('length_mm',0.0)):.2f}",
                        f"{float(c.get('ang_sx',0.0)):.1f}",
                        f"{float(c.get('ang_dx',0.0)):.1f}",
                        int(c.get("qty",0)), c.get("note","")
                    ])
            QMessageBox.information(self, "Salva", "Salvato.")
        except Exception as e:
            QMessageBox.critical(self, "Errore", str(e))
