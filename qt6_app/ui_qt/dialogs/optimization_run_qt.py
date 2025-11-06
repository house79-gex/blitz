from __future__ import annotations
from typing import List, Dict, Any, Optional, Tuple
import csv
from datetime import datetime

from PySide6.QtCore import Qt, Signal, QRect
from PySide6.QtGui import QKeyEvent, QTextDocument
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox, QApplication,
    QWidget, QFileDialog
)
try:
    from PySide6.QtPrintSupport import QPrinter
except Exception:
    QPrinter = None

try:
    from ui_qt.utils.settings import read_settings, write_settings
except Exception:
    def read_settings(): return {}
    def write_settings(_): pass

from ui_qt.widgets.plan_visualizer import PlanVisualizerWidget
from ui_qt.logic.refiner import refine_tail_ilp, pack_bars_knapsack_ilp


class OptimizationSummaryDialog(QDialog):
    def __init__(self, parent: QWidget, profile: str,
                 bars: List[List[Dict[str, float]]],
                 residuals: List[float],
                 stock_mm: float,
                 kerf_mm: float):
        super().__init__(parent)
        self.setWindowTitle(f"Riepilogo ottimizzazione — {profile}")
        self.setModal(False)
        self._profile = profile
        self._bars = bars or []
        self._residuals = residuals or []
        self._stock = float(stock_mm or 6500.0)
        self._kerf = float(kerf_mm or 3.0)

        root = QVBoxLayout(self); root.setContentsMargins(8, 8, 8, 8); root.setSpacing(6)
        hdr = QLabel(f"Profilo: {profile} — Stock: {self._stock:.0f} mm — Kerf: {self._kerf:.2f} mm")
        hdr.setStyleSheet("font-weight:700;")
        root.addWidget(hdr)

        self.tbl = QTableWidget(0, 6, self)
        self.tbl.setHorizontalHeaderLabels(["Barra", "Pezzi", "Usato (mm)", "Residuo (mm)", "Efficienza (%)", "Dettaglio"])
        hh = self.tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(5, QHeaderView.Stretch)
        root.addWidget(self.tbl, 1)

        btns = QHBoxLayout(); btns.addStretch(1)
        self.btn_csv = QPushButton("Esporta CSV")
        self.btn_pdf = QPushButton("Esporta PDF")
        self.btn_close = QPushButton("Chiudi")
        btns.addWidget(self.btn_csv); btns.addWidget(self.btn_pdf); btns.addWidget(self.btn_close)
        root.addLayout(btns)

        self.btn_close.clicked.connect(self.close)
        self.btn_csv.clicked.connect(self._export_csv)
        self.btn_pdf.clicked.connect(self._export_pdf)

        self._fill_table()
        try: self.resize(900, 500)
        except Exception: pass

    def _fill_table(self):
        self.tbl.setRowCount(0)
        for i, bar in enumerate(self._bars):
            pezzi = len(bar); used = 0.0; details: List[str] = []
            for idx, piece in enumerate(bar):
                try:
                    L = float(piece.get("len", 0.0))
                    ax = float(piece.get("ax", 0.0)); ad = float(piece.get("ad", 0.0))
                except Exception:
                    L, ax, ad = 0.0, 0.0, 0.0
                used += L; details.append(f"{L:.0f}({ax:.0f}/{ad:.0f})")
                if idx < len(bar) - 1: used += self._kerf
            residuo = float(self._residuals[i]) if i < len(self._residuals) else max(self._stock - used, 0.0)
            eff = (used / self._stock * 100.0) if self._stock > 0 else 0.0

            r = self.tbl.rowCount()
            self.tbl.insertRow(r)
            self.tbl.setItem(r, 0, QTableWidgetItem(f"B{i+1}"))
            self.tbl.setItem(r, 1, QTableWidgetItem(str(pezzi)))
            self.tbl.setItem(r, 2, QTableWidgetItem(f"{used:.1f}"))
            self.tbl.setItem(r, 3, QTableWidgetItem(f"{residuo:.1f}"))
            self.tbl.setItem(r, 4, QTableWidgetItem(f"{eff:.1f}"))
            self.tbl.setItem(r, 5, QTableWidgetItem(" + ".join(details)))

    def _export_csv(self):
        try:
            path, _ = QFileDialog.getSaveFileName(self, "Esporta CSV", f"riepilogo_{self._profile}_{datetime.now():%Y%m%d_%H%M%S}.csv", "CSV (*.csv)")
            if not path: return
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow([f"Profilo: {self._profile}", f"Stock: {self._stock:.0f} mm", f"Kerf: {self._kerf:.2f} mm"])
                w.writerow(["Barra", "Pezzi", "Usato (mm)", "Residuo (mm)", "Efficienza (%)", "Dettaglio"])
                for r in range(self.tbl.rowCount()):
                    row = [self.tbl.item(r, c).text() if self.tbl.item(r, c) else "" for c in range(self.tbl.columnCount())]
                    w.writerow(row)
        except Exception:
            pass

    def _export_pdf(self):
        if QPrinter is None:
            return
        try:
            path, _ = QFileDialog.getSaveFileName(self, "Esporta PDF", f"riepilogo_{self._profile}_{datetime.now():%Y%m%d_%H%M%S}.pdf", "PDF (*.pdf)")
            if not path: return
            html_rows = []
            for r in range(self.tbl.rowCount()):
                cols = [self.tbl.item(r, c).text() if self.tbl.item(r, c) else "" for c in range(self.tbl.columnCount())]
                tds = "".join(f"<td style='border:1px solid #999;padding:4px 6px'>{c}</td>" for c in cols)
                html_rows.append(f"<tr>{tds}</tr>")
            html = f"""
            <html><head><meta charset='utf-8'>
            <style>table{{border-collapse:collapse;width:100%;font-size:12px}} th,td{{border:1px solid #999;padding:4px 6px}}</style>
            </head><body>
            <h2>Riepilogo ottimizzazione — {self._profile}</h2>
            <div>Stock: {self._stock:.0f} mm — Kerf: {self._kerf:.2f} mm — Generato: {datetime.now():%Y-%m-%d %H:%M:%S}</div><br/>
            <table><thead><tr>
            <th>Barra</th><th>Pezzi</th><th>Usato (mm)</th><th>Residuo (mm)</th><th>Efficienza (%)</th><th>Dettaglio</th>
            </tr></thead><tbody>{''.join(html_rows)}</tbody></table></body></html>
            """
            doc = QTextDocument(); doc.setHtml(html)
            printer = QPrinter(QPrinter.HighResolution); printer.setOutputFormat(QPrinter.PdfFormat); printer.setOutputFileName(path)
            doc.print(printer)
        except Exception:
            pass


class OptimizationRunDialog(QDialog):
    simulationRequested = Signal()
    startRequested = Signal()

    TABLE_MIN_H = 180
    GRAPH_BAR_H = 16
    GRAPH_V_GAP = 6

    def __init__(self, parent, profile: str, rows: List[Dict[str, Any]], overlay_target: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(f"Ottimizzazione - {profile}")
        self.setModal(False)
        self.profile = profile
        self._rows: List[Dict[str, Any]] = [dict(r) for r in rows]

        self._opts_bar: Optional[QFrame] = None
        self._panel_graph: Optional[QFrame] = None
        self._graph: Optional[PlanVisualizerWidget] = None
        self._tbl: Optional[QTableWidget] = None
        self._chk_graph: Optional[QCheckBox] = None

        cfg = read_settings()
        self._stock = float(cfg.get("opt_stock_mm", 6500.0))
        self._kerf = float(cfg.get("opt_kerf_mm", 3.0))
        self._overlay_target: Optional[QWidget] = overlay_target
        self._show_graph = True if self._overlay_target is not None else bool(cfg.get("opt_show_graph", True))

        self._bars: List[List[Dict[str, float]]] = []
        self._bars_residuals: List[float] = []

        self._build()
        self._compute_plan_once()
        self._refresh_views()

        self._apply_geometry()
        self._resize_graph_area()

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(8, 8, 8, 8); root.setSpacing(6)

        self._opts_bar = QFrame(self); opts_lay = QHBoxLayout(self._opts_bar)
        opts_lay.setContentsMargins(0, 0, 0, 0); opts_lay.setSpacing(6)

        self._chk_graph = QCheckBox("Mostra grafica piano"); self._chk_graph.setChecked(self._show_graph)
        self._chk_graph.toggled.connect(self._toggle_graph)

        btn_summary = QPushButton("Riepilogo…"); btn_summary.setToolTip("Tabella riassuntiva ed export CSV/PDF")
        btn_summary.clicked.connect(self._open_summary)
        btn_start = QPushButton("Simula Avanzamento (F9)"); btn_start.clicked.connect(lambda: self.startRequested.emit())
        btn_sim = QPushButton("Simula START (F7)"); btn_sim.clicked.connect(lambda: self.simulationRequested.emit())

        opts_lay.addWidget(self._chk_graph); opts_lay.addStretch(1); opts_lay.addWidget(btn_summary); opts_lay.addWidget(btn_start); opts_lay.addWidget(btn_sim)
        root.addWidget(self._opts_bar, 0)

        self._panel_graph = QFrame()
        self._panel_graph.setStyleSheet("QFrame { border:1px solid #3b4b5a; border-radius:6px; }")
        gl = QVBoxLayout(self._panel_graph); gl.setContentsMargins(6, 6, 6, 6); gl.setSpacing(4)
        self._graph = PlanVisualizerWidget(self); gl.addWidget(self._graph, 1)
        root.addWidget(self._panel_graph, 0)

        self._tbl = QTableWidget(0, 4)
        self._tbl.setHorizontalHeaderLabels(["Lunghezza (mm)", "Ang SX", "Ang DX", "Q.tà"])
        hdr = self._tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        root.addWidget(self._tbl, 1)
        self._tbl.setMinimumHeight(self.TABLE_MIN_H)

        self._apply_toggles()

    def _apply_toggles(self):
        if self._panel_graph:
            self._panel_graph.setVisible(self._show_graph)

    def _toggle_graph(self, on: bool):
        self._show_graph = bool(on)
        self._apply_toggles()
        if self._overlay_target is None:
            cfg = dict(read_settings()); cfg["opt_show_graph"] = self._show_graph; write_settings(cfg)
        self._resize_graph_area()

    def _open_summary(self):
        try:
            dlg = OptimizationSummaryDialog(self, self.profile, self._bars, self._bars_residuals, self._stock, self._kerf)
            dlg.setAttribute(Qt.WA_DeleteOnClose, True)
            dlg.show()
        except Exception:
            pass

    def _expand_rows_to_unit_pieces(self) -> List[Dict[str, float]]:
        pieces: List[Dict[str, float]] = []
        for r in self._rows:
            try:
                q = int(r.get("qty", 0))
                L = float(r.get("length_mm", 0.0))
                ax = float(r.get("ang_sx", 0.0))
                ad = float(r.get("ang_dx", 0.0))
            except Exception:
                continue
            for _ in range(max(0, q)):
                pieces.append({"len": L, "ax": ax, "ad": ad})
        pieces.sort(key=lambda x: x["len"], reverse=True)
        return pieces

    def _pack_bfd(self, pieces: List[Dict[str, float]], stock: float, kerf: float) -> Tuple[List[List[Dict[str, float]]], List[float]]:
        bars: List[List[Dict[str, float]]] = []; rem: List[float] = []
        for p in pieces:
            need = p["len"]; placed = False
            for i in range(len(bars)):
                extra = kerf if bars[i] else 0.0
                if rem[i] >= (need + extra):
                    bars[i].append(p); rem[i] -= (need + extra); placed = True; break
            if not placed:
                bars.append([p]); rem.append(max(stock - need, 0.0))
        if rem:
            max_idx = max(range(len(rem)), key=lambda i: rem[i])
            if 0 <= max_idx < len(bars) and max_idx != len(bars) - 1:
                bars.append(bars.pop(max_idx)); rem.append(rem.pop(max_idx))
        return bars, rem

    def _compute_plan_once(self):
        cfg = read_settings()
        pieces = self._expand_rows_to_unit_pieces()
        solver = str(cfg.get("opt_solver", "ILP_KNAP")).upper()
        stock = float(cfg.get("opt_stock_mm", 6500.0))
        kerf = float(cfg.get("opt_kerf_mm", 3.0))
        per_bar_time = int(cfg.get("opt_time_limit_s", 15))
        tail_n = int(cfg.get("opt_refine_tail_bars", 6))
        tail_t = int(cfg.get("opt_refine_time_s", 25))

        if solver == "ILP_KNAP":
            bars, rem = pack_bars_knapsack_ilp(pieces, stock=stock, kerf=kerf, per_bar_time_s=per_bar_time)
            if not bars:
                bars, rem = self._pack_bfd(pieces, stock, kerf)
        elif solver == "ILP":
            bars, rem = pack_bars_knapsack_ilp(pieces, stock=stock, kerf=kerf, per_bar_time_s=per_bar_time)
            if not bars:
                bars, rem = self._pack_bfd(pieces, stock, kerf)
        else:
            bars, rem = self._pack_bfd(pieces, stock, kerf)

        try:
            bars, rem = refine_tail_ilp(bars, stock=stock, kerf=kerf, tail_bars=tail_n, time_limit_s=tail_t)
        except Exception:
            pass

        self._bars, self._bars_residuals = bars, rem

    def _refresh_views(self):
        if self._graph:
            self._graph.set_data(self._bars, stock_mm=self._stock, kerf_mm=self._kerf)
        self._reload_table()
        self._resize_graph_area()
        if self._all_done():
            self._close_and_focus_parent()

    def _desired_graph_height(self, n_bars: int) -> int:
        if n_bars <= 0: return 120
        bars_h = n_bars * self.GRAPH_BAR_H + max(0, (n_bars - 1)) * self.GRAPH_V_GAP
        padding = 6 + 6 + 4
        return max(100, bars_h + padding)

    def _apply_geometry(self):
        if self._overlay_target is not None:
            try:
                tl_global = self._overlay_target.mapToGlobal(self._overlay_target.rect().topLeft())
                br_global = self._overlay_target.mapToGlobal(self._overlay_target.rect().bottomRight())
                rect = QRect(tl_global, br_global); self.setGeometry(rect)
            except Exception:
                pass
        else:
            try:
                screen = QApplication.primaryScreen()
                if not screen: return
                avail = screen.availableGeometry()
                w = max(720, self.width() or 900); h = int(avail.height() - 32)
                self.resize(w, h); self.move(avail.x() + 12, avail.y() + 12)
            except Exception:
                pass

    def _resize_graph_area(self):
        try:
            if not (self._panel_graph and self._graph and self._tbl): return
            total_h = max(0, self.height())
            opts_h = self._opts_bar.sizeHint().height() if self._opts_bar else 0
            margins = 8 + 8 + 6
            table_min = self.TABLE_MIN_H
            avail_for_graph = max(100, total_h - (opts_h + margins + table_min))
            desired = self._desired_graph_height(len(self._bars))
            gh = min(desired, avail_for_graph)
            self._graph.setMinimumHeight(int(gh)); self._graph.setMaximumHeight(int(gh))
            self._panel_graph.updateGeometry(); self._graph.updateGeometry()
        except Exception:
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_graph_area()

    def _reload_table(self):
        if not self._tbl: return
        self._tbl.setRowCount(0)
        for r in self._rows:
            q = int(max(0, r.get("qty", 0)))
            row = self._tbl.rowCount(); self._tbl.insertRow(row)
            self._tbl.setItem(row, 0, QTableWidgetItem(f"{float(r.get('length_mm', 0.0)):.2f}"))
            self._tbl.setItem(row, 1, QTableWidgetItem(f"{float(r.get('ang_sx', 0.0)):.1f}"))
            self._tbl.setItem(row, 2, QTableWidgetItem(f"{float(r.get('ang_dx', 0.0)):.1f}"))
            self._tbl.setItem(row, 3, QTableWidgetItem(str(q)))

    def _all_done(self) -> bool:
        try:
            return sum(int(max(0, r.get("qty", 0))) for r in self._rows) == 0
        except Exception:
            return False

    def _close_and_focus_parent(self):
        try:
            parent = self.parent(); self.close()
            if parent is not None:
                try: parent.raise_(); parent.activateWindow()
                except Exception: pass
        except Exception:
            pass

    def update_after_cut(self, length_mm: float, ang_sx: float, ang_dx: float):
        if self._graph:
            try: self._graph.mark_done(length_mm, ang_sx, ang_dx)
            except Exception: pass
        tol_L = 0.01; tol_A = 0.01; matched = False
        for r in self._rows:
            try:
                if abs(float(r.get("length_mm", 0.0)) - float(length_mm)) <= tol_L \
                   and abs(float(r.get("ang_sx", 0.0)) - float(ang_sx)) <= tol_A \
                   and abs(float(r.get("ang_dx", 0.0)) - float(ang_dx)) <= tol_A:
                    r["qty"] = max(0, int(r.get("qty", 0)) - 1); matched = True; break
            except Exception:
                continue
        if not matched:
            Ls = f"{float(length_mm):.2f}"; Axs = f"{float(ang_sx):.1f}"; Ads = f"{float(ang_dx):.1f}"
            for r in self._rows:
                try:
                    if f"{float(r.get('length_mm', 0.0)):.2f}" == Ls \
                       and f"{float(r.get('ang_sx', 0.0)):.1f}" == Axs \
                       and f"{float(r.get('ang_dx', 0.0)):.1f}" == Ads:
                        r["qty"] = max(0, int(r.get("qty", 0)) - 1); break
                except Exception:
                    continue
        self._refresh_views()

    def keyPressEvent(self, ev: QKeyEvent):
        try:
            if ev.key() == Qt.Key_F7: self.simulationRequested.emit(); ev.accept(); return
            if ev.key() == Qt.Key_F9: self.startRequested.emit(); ev.accept(); return
        except Exception:
            pass
        super().keyPressEvent(ev)

    def accept(self):
        if self._overlay_target is None:
            cfg = dict(read_settings())
            cfg["opt_show_graph"] = bool(self._chk_graph and self._chk_graph.isChecked())
            write_settings(cfg)
        super().accept()

    def reject(self):
        self.accept()
