from __future__ import annotations
from typing import List, Dict, Any, Optional, Tuple
import csv
from datetime import datetime

from PySide6.QtCore import Qt, Signal, QRect
from PySide6.QtGui import QKeyEvent, QTextDocument, QColor, QBrush
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox, QApplication,
    QWidget, QFileDialog
)

try:
    from PySide6.QtPrintSupport import QPrinter
except Exception:
    QPrinter = None

# Settings with fallback
try:
    from ui_qt.utils.settings import read_settings, write_settings
except Exception:
    def read_settings(): return {}
    def write_settings(_): pass

from ui_qt.widgets.plan_visualizer import PlanVisualizerWidget
from ui_qt.logic.refiner import (
    pack_bars_knapsack_ilp,
    refine_tail_ilp,
    bar_used_length,
    residuals,
    joint_consumption,
    compute_bar_breakdown
)


class OptimizationSummaryDialog(QDialog):
    COLS = ["Barra","Pezzi","Usato (mm)","Residuo (mm)","Efficienza (%)",
            "Kerf ang (mm)","Ripasso (mm)","Recupero (mm)","Dettaglio","Warn"]

    def __init__(self, parent: QWidget, profile: str,
                 bars: List[List[Dict[str, float]]],
                 residuals_list: List[float],
                 stock_mm: float):
        super().__init__(parent)
        self.setWindowTitle(f"Riepilogo ottimizzazione — {profile}")
        self.setModal(False)
        self._profile = profile
        self._bars = bars or []
        self._residuals = residuals_list or []
        self._stock = float(stock_mm or 6500.0)

        cfg = read_settings()
        self._kerf_base = float(cfg.get("opt_kerf_mm", 3.0))
        self._ripasso = float(cfg.get("opt_ripasso_mm", 0.0))
        self._reversible = bool(cfg.get("opt_current_profile_reversible", False))
        self._thickness = float(cfg.get("opt_current_profile_thickness_mm", 0.0))
        self._angle_tol = float(cfg.get("opt_reversible_angle_tol_deg", 0.5))
        self._max_angle = float(cfg.get("opt_kerf_max_angle_deg", 60.0))
        self._max_factor = float(cfg.get("opt_kerf_max_factor", 2.0))
        self._warn_thr = float(cfg.get("opt_warn_overflow_mm", 0.5))

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        hdr = QLabel(f"Profilo: {profile} — Stock: {self._stock:.0f} mm")
        hdr.setStyleSheet("font-weight:700;")
        root.addWidget(hdr)

        self.tbl = QTableWidget(0, len(self.COLS), self)
        self.tbl.setHorizontalHeaderLabels(self.COLS)
        hh = self.tbl.horizontalHeader()
        for i in range(len(self.COLS)):
            hh.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(8, QHeaderView.Stretch)
        root.addWidget(self.tbl, 1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_csv = QPushButton("Esporta CSV")
        self.btn_pdf = QPushButton("Esporta PDF")
        self.btn_close = QPushButton("Chiudi")
        btns.addWidget(self.btn_csv)
        btns.addWidget(self.btn_pdf)
        btns.addWidget(self.btn_close)
        root.addLayout(btns)

        self.btn_close.clicked.connect(self.close)
        self.btn_csv.clicked.connect(self._export_csv)
        self.btn_pdf.clicked.connect(self._export_pdf)

        self._fill_table()
        self.resize(1120, 520)

    def _fill_table(self):
        warn_color = QColor("#ffcccc")
        self.tbl.setRowCount(0)
        for i, bar in enumerate(self._bars):
            pezzi = len(bar)
            bd = compute_bar_breakdown(
                bar, self._kerf_base, self._ripasso,
                self._reversible, self._thickness,
                self._angle_tol, self._max_angle, self._max_factor
            )
            used = bd["used_total"]
            kerf_ang = bd["kerf_proj_sum"]
            ripasso_sum = bd["ripasso_sum"]
            recovery_sum = bd["recovery_sum"]
            residuo = float(self._residuals[i]) if i < len(self._residuals) else max(self._stock - used, 0.0)
            eff = (used / self._stock * 100.0) if self._stock > 0 else 0.0
            details = []
            for piece in bar:
                L = float(piece.get("len", 0.0)); ax = float(piece.get("ax", 0.0)); ad = float(piece.get("ad", 0.0))
                details.append(f"{L:.0f}({ax:.0f}/{ad:.0f})")
            warn = ""
            if self._stock - used <= self._warn_thr + 1e-6:
                warn = f"<{self._warn_thr:.2f}mm"
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)
            vals = [
                f"B{i+1}", str(pezzi), f"{used:.1f}", f"{residuo:.1f}",
                f"{eff:.1f}", f"{kerf_ang:.1f}", f"{ripasso_sum:.1f}",
                f"{recovery_sum:.1f}", " + ".join(details), warn
            ]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if warn and c == 9:
                    it.setBackground(QBrush(warn_color))
                self.tbl.setItem(r, c, it)

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Esporta CSV",
            f"riepilogo_{self._profile}_{datetime.now():%Y%m%d_%H%M%S}.csv",
            "CSV (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow([f"Profilo: {self._profile}", f"Stock: {self._stock:.0f} mm"])
                w.writerow(self.COLS)
                for r in range(self.tbl.rowCount()):
                    row = [self.tbl.item(r, c).text() if self.tbl.item(r, c) else "" for c in range(self.tbl.columnCount())]
                    w.writerow(row)
        except Exception:
            pass

    def _export_pdf(self):
        if QPrinter is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Esporta PDF",
            f"riepilogo_{self._profile}_{datetime.now():%Y%m%d_%H%M%S}.pdf",
            "PDF (*.pdf)"
        )
        if not path:
            return
        html_rows = []
        for r in range(self.tbl.rowCount()):
            cols = [self.tbl.item(r, c).text() if self.tbl.item(r, c) else "" for c in range(self.tbl.columnCount())]
            tds = "".join(f"<td style='border:1px solid #999;padding:4px 6px'>{c}</td>" for c in cols)
            html_rows.append(f"<tr>{tds}</tr>")
        html = f"""
        <html><head><meta charset='utf-8'><style>
        table{{border-collapse:collapse;width:100%;font-size:12px}}
        th,td{{border:1px solid #999;padding:4px 6px}}
        th{{background:#f0f0f0}}
        </style></head><body>
        <h2>Riepilogo ottimizzazione — {self._profile}</h2>
        <div>Stock: {self._stock:.0f} mm — Generato: {datetime.now():%Y-%m-%d %H:%M:%S}</div><br/>
        <table><thead><tr>{''.join(f'<th>{c}</th>' for c in self.COLS)}</tr></thead>
        <tbody>{''.join(html_rows)}</tbody></table></body></html>
        """
        doc = QTextDocument(); doc.setHtml(html)
        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(path)
        # PySide6: il metodo è print_ (non print)
        doc.print_(printer)


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

        cfg = read_settings()
        self._stock = float(cfg.get("opt_stock_mm", 6500.0))
        stock_use = float(cfg.get("opt_stock_usable_mm", 0.0))
        if stock_use > 0:
            self._stock = stock_use
        self._kerf_base = float(cfg.get("opt_kerf_mm", 3.0))
        self._ripasso = float(cfg.get("opt_ripasso_mm", 0.0))
        self._reversible = bool(cfg.get("opt_current_profile_reversible", False))
        self._thickness = float(cfg.get("opt_current_profile_thickness_mm", 0.0))
        self._angle_tol = float(cfg.get("opt_reversible_angle_tol_deg", 0.5))
        self._max_angle = float(cfg.get("opt_kerf_max_angle_deg", 60.0))
        self._max_factor = float(cfg.get("opt_kerf_max_factor", 2.0))
        self._warn_thr = float(cfg.get("opt_warn_overflow_mm", 0.5))
        self._solver = str(cfg.get("opt_solver", "ILP_KNAP")).upper()
        self._per_bar_time = int(cfg.get("opt_time_limit_s", 15))
        self._tail_n = int(cfg.get("opt_refine_tail_bars", 6))
        self._tail_t = int(cfg.get("opt_refine_time_s", 25))
        self._cons_angle = float(cfg.get("opt_knap_conservative_angle_deg", 45.0))

        self._overlay_target: Optional[QWidget] = overlay_target
        self._show_graph = True if self._overlay_target is not None else bool(cfg.get("opt_show_graph", True))

        self._bars: List[List[Dict[str, float]]] = []
        self._bars_residuals: List[float] = []
        # Stato "done" per evidenziare in verde
        self._done_by_index: Dict[int, List[bool]] = {}

        self._build()
        self._compute_plan_once()
        self._init_done_state()
        self._refresh_views()
        self._apply_geometry()
        self._resize_graph_area()

    # ---------------- UI build ----------------
    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(8, 8, 8, 8); root.setSpacing(6)

        opts = QFrame(); ol = QHBoxLayout(opts); ol.setContentsMargins(0,0,0,0); ol.setSpacing(6)
        self._chk_graph = QCheckBox("Mostra grafica piano"); self._chk_graph.setChecked(self._show_graph)
        self._chk_graph.toggled.connect(self._toggle_graph)
        btn_summary = QPushButton("Riepilogo…"); btn_summary.clicked.connect(self._open_summary)
        btn_start = QPushButton("Avanza (F9)"); btn_start.clicked.connect(lambda: self.startRequested.emit())
        btn_cut = QPushButton("Simula taglio (F7)"); btn_cut.clicked.connect(lambda: self.simulationRequested.emit())
        ol.addWidget(self._chk_graph); ol.addStretch(1); ol.addWidget(btn_summary); ol.addWidget(btn_start); ol.addWidget(btn_cut)
        root.addWidget(opts, 0)

        self._panel_graph = QFrame()
        gl = QVBoxLayout(self._panel_graph); gl.setContentsMargins(6,6,6,6); gl.setSpacing(4)
        self._graph = PlanVisualizerWidget(self)
        gl.addWidget(self._graph, 1)
        root.addWidget(self._panel_graph, 0)

        self._tbl = QTableWidget(0, 4)
        self._tbl.setHorizontalHeaderLabels(["Lunghezza (mm)", "Ang SX", "Ang DX", "Q.tà"])
        hdr = self._tbl.horizontalHeader()
        for i in range(4):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self._tbl.setMinimumHeight(self.TABLE_MIN_H)
        root.addWidget(self._tbl, 1)

        self._apply_toggles()

    def _apply_toggles(self):
        self._panel_graph.setVisible(self._show_graph)

    def _toggle_graph(self, on: bool):
        self._show_graph = bool(on); self._apply_toggles()
        if self._overlay_target is None:
            cfg = dict(read_settings()); cfg["opt_show_graph"] = self._show_graph; write_settings(cfg)
        self._resize_graph_area()

    def _open_summary(self):
        dlg = OptimizationSummaryDialog(self, self.profile, self._bars, self._bars_residuals, self._stock)
        dlg.setAttribute(Qt.WA_DeleteOnClose, True)
        dlg.show()

    # ---------------- Helpers (data) ----------------
    def _expand_rows_to_unit_pieces(self) -> List[Dict[str, float]]:
        pieces: List[Dict[str, float]] = []
        for r in self._rows:
            q = int(r.get("qty", 0)); L = float(r.get("length_mm", 0.0))
            ax = float(r.get("ang_sx", 0.0)); ad = float(r.get("ang_dx", 0.0))
            for _ in range(max(0, q)):
                pieces.append({"len": L, "ax": ax, "ad": ad})
        pieces.sort(key=lambda x: x["len"], reverse=True)
        return pieces

    def _pack_bfd(self, pieces: List[Dict[str, float]]) -> Tuple[List[List[Dict[str, float]]], List[float]]:
        bars: List[List[Dict[str, float]]] = []
        for p in pieces:
            placed = False
            for b in bars:
                used = bar_used_length(b, self._kerf_base, self._ripasso,
                                       self._reversible, self._thickness,
                                       self._angle_tol, self._max_angle, self._max_factor)
                extra = joint_consumption(b[-1], self._kerf_base, self._ripasso,
                                          self._reversible, self._thickness,
                                          self._angle_tol, self._max_angle, self._max_factor)[0] if b else 0.0
                if used + p["len"] + extra <= self._stock + 1e-6:
                    b.append(p); placed = True; break
            if not placed:
                bars.append([p])
        rem = residuals(bars, self._stock, self._kerf_base, self._ripasso,
                        self._reversible, self._thickness,
                        self._angle_tol, self._max_angle, self._max_factor)
        return bars, rem

    def _compute_plan_once(self):
        pieces = self._expand_rows_to_unit_pieces()
        # Solver: ILP_KNAP/ILP preferiti, fallback BFD
        if self._solver in ("ILP_KNAP", "ILP"):
            bars, rem = pack_bars_knapsack_ilp(
                pieces=pieces,
                stock=self._stock,
                kerf_base=self._kerf_base,
                ripasso_mm=self._ripasso,
                conservative_angle_deg=self._cons_angle,
                max_angle=self._max_angle,
                max_factor=self._max_factor,
                reversible=self._reversible,
                thickness_mm=self._thickness,
                angle_tol=self._angle_tol,
                per_bar_time_s=self._per_bar_time
            )
            if not bars:
                bars, rem = self._pack_bfd(pieces)
        else:
            bars, rem = self._pack_bfd(pieces)

        # Refine tail (best-effort)
        try:
            bars, rem = refine_tail_ilp(
                bars, self._stock, self._kerf_base,
                self._ripasso, self._reversible, self._thickness,
                self._angle_tol, tail_bars=self._tail_n,
                time_limit_s=self._tail_t,
                max_angle=self._max_angle, max_factor=self._max_factor
            )
        except Exception:
            pass

        # Sanitize overflow (pezzi eccedenti rimessi in altre barre)
        fixed_bars: List[List[Dict[str, float]]] = []
        overflow: List[Dict[str, float]] = []
        for bar in bars:
            b = list(bar)
            while b and bar_used_length(b, self._kerf_base, self._ripasso,
                                       self._reversible, self._thickness,
                                       self._angle_tol, self._max_angle, self._max_factor) > self._stock + 1e-6:
                overflow.append(b.pop())
            fixed_bars.append(b)
        if overflow:
            for piece in sorted(overflow, key=lambda x: x["len"], reverse=True):
                placed = False
                for fb in fixed_bars:
                    used = bar_used_length(fb, self._kerf_base, self._ripasso,
                                           self._reversible, self._thickness,
                                           self._angle_tol, self._max_angle, self._max_factor)
                    extra = joint_consumption(fb[-1], self._kerf_base, self._ripasso,
                                              self._reversible, self._thickness,
                                              self._angle_tol, self._max_angle, self._max_factor)[0] if fb else 0.0
                    if used + piece["len"] + extra <= self._stock + 1e-6:
                        fb.append(piece); placed = True; break
                if not placed:
                    fixed_bars.append([piece])

        bars = fixed_bars
        rem = residuals(bars, self._stock, self._kerf_base, self._ripasso,
                        self._reversible, self._thickness,
                        self._angle_tol, self._max_angle, self._max_factor)

        # Ordinamento: barre con pezzo più lungo prima
        bars.sort(key=lambda b: max((p["len"] for p in b), default=0.0), reverse=True)

        self._bars = bars
        self._bars_residuals = rem

    # ---------------- Views & state ----------------
    def _init_done_state(self):
        self._done_by_index = {i: [False]*len(b) for i, b in enumerate(self._bars)}
        # imposta barra corrente a prima incompleta
        self._graph.set_done_by_index(self._done_by_index)
        self._graph.set_current_bar(self._current_bar_index())

    def _current_bar_index(self) -> Optional[int]:
        for i, b in enumerate(self._bars):
            flags = self._done_by_index.get(i, [])
            if not (len(flags) == len(b) and all(flags)):
                return i
        return None

    def _refresh_views(self):
        self._graph.set_data(
            self._bars, stock_mm=self._stock,
            kerf_base=self._kerf_base, ripasso_mm=self._ripasso,
            reversible=self._reversible, thickness_mm=self._thickness,
            angle_tol=self._angle_tol, max_angle=self._max_angle,
            max_factor=self._max_factor, warn_threshold_mm=self._warn_thr
        )
        self._graph.set_done_by_index(self._done_by_index)
        self._graph.set_current_bar(self._current_bar_index())
        self._reload_table()
        self._resize_graph_area()

    def _reload_table(self):
        self._tbl.setRowCount(0)
        for r in self._rows:
            q = int(r.get("qty", 0))
            row = self._tbl.rowCount(); self._tbl.insertRow(row)
            self._tbl.setItem(row, 0, QTableWidgetItem(f"{float(r.get('length_mm',0.0)):.2f}"))
            self._tbl.setItem(row, 1, QTableWidgetItem(f"{float(r.get('ang_sx',0.0)):.1f}"))
            self._tbl.setItem(row, 2, QTableWidgetItem(f"{float(r.get('ang_dx',0.0)):.1f}"))
            self._tbl.setItem(row, 3, QTableWidgetItem(str(q)))

    # ---------------- Geometry / sizing ----------------
    def _apply_geometry(self):
        if self._overlay_target is not None:
            try:
                tl = self._overlay_target.mapToGlobal(self._overlay_target.rect().topLeft())
                br = self._overlay_target.mapToGlobal(self._overlay_target.rect().bottomRight())
                self.setGeometry(QRect(tl, br))
            except Exception:
                pass
        else:
            screen = QApplication.primaryScreen()
            if screen:
                avail = screen.availableGeometry()
                self.resize(max(820, self.width()), int(avail.height() - 32))
                self.move(avail.x() + 12, avail.y() + 12)

    def _desired_graph_height(self, n_bars: int) -> int:
        if n_bars <= 0: return 120
        bars_h = n_bars * self.GRAPH_BAR_H + max(0, n_bars - 1) * self.GRAPH_V_GAP
        return max(100, bars_h + 16)

    def _resize_graph_area(self):
        if not (self._panel_graph and self._graph and self._tbl): return
        total_h = self.height()
        opts_h = self._chk_graph.sizeHint().height()
        table_min = self.TABLE_MIN_H
        margins = 8 + 8 + 6
        avail_for_graph = max(100, total_h - (opts_h + margins + table_min))
        desired = self._desired_graph_height(len(self._bars))
        gh = min(desired, avail_for_graph)
        self._graph.setMinimumHeight(int(gh))
        self._graph.setMaximumHeight(int(gh))

    def resizeEvent(self, event):
        super().resizeEvent(event); self._resize_graph_area()

    # ---------------- Mark done after cut ----------------
    def _mark_first_match_done_local(self, length_mm: float, ang_sx: float, ang_dx: float,
                                     len_tol: float = 0.01, ang_tol: float = 0.05) -> Optional[Tuple[int,int]]:
        """
        Trova e marca nel nostro stato locale (_done_by_index) il primo pezzo non fatto che corrisponde a (L, angoli).
        Ritorna (bar_idx, piece_idx) se trovato, altrimenti None.
        """
        for bi, bar in enumerate(self._bars):
            flags = self._done_by_index.get(bi, [])
            if not flags:
                flags = [False]*len(bar)
                self._done_by_index[bi] = flags
            for pi, p in enumerate(bar):
                if flags[pi]:
                    continue
                if (abs(float(p.get("len",0.0)) - float(length_mm)) <= len_tol and
                    abs(float(p.get("ax",0.0)) - float(ang_sx))   <= ang_tol and
                    abs(float(p.get("ad",0.0)) - float(ang_dx))   <= ang_tol):
                    flags[pi] = True
                    return (bi, pi)
        return None

    def update_after_cut(self, length_mm: float, ang_sx: float, ang_dx: float):
        """
        Chiamata dal chiamante (Automatico) ogni volta che un pezzo è tagliato:
        - Colora SUBITO in verde il pezzo nel grafico (mark per firma).
        - Decrementa la quantità nella tabella di input (primo matching).
        - Aggiorna barra corrente e, se piano completato, chiude il dialog.
        """
        # 1) Stato locale + grafico
        idx = self._mark_first_match_done_local(length_mm, ang_sx, ang_dx)
        try:
            # marca anche nel widget (cerca il primo non-fatto che matcha)
            self._graph.mark_done_by_signature(length_mm, ang_sx, ang_dx)
        except Exception:
            pass

        # 2) Decrementa la riga corrispondente in tabella (se presente)
        tol_L = 0.01; tol_A = 0.01
        for r in self._rows:
            try:
                if abs(float(r.get("length_mm",0.0)) - length_mm) <= tol_L \
                   and abs(float(r.get("ang_sx",0.0)) - ang_sx) <= tol_A \
                   and abs(float(r.get("ang_dx",0.0)) - ang_dx) <= tol_A:
                    r["qty"] = max(0, int(r.get("qty",0)) - 1)
                    break
            except Exception:
                continue

        # 3) Aggiorna views: barra corrente = prima incompleta
        self._graph.set_done_by_index(self._done_by_index)
        self._graph.set_current_bar(self._current_bar_index())
        self._reload_table()

        # 4) Se tutto finito, chiudi
        if self._current_bar_index() is None:
            # Tutte le barre sono complete
            try:
                self.accept()
            except Exception:
                try: self.close()
                except Exception: pass
            return

    # ---------------- Events & persist ----------------
    def keyPressEvent(self, ev: QKeyEvent):
        try:
            if ev.key() == Qt.Key_F7:
                self.simulationRequested.emit()
                ev.accept(); return
            if ev.key() == Qt.Key_F9:
                self.startRequested.emit()
                ev.accept(); return
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
