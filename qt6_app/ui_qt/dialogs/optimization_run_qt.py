from __future__ import annotations
from typing import List, Dict, Any, Optional, Tuple
import csv
from datetime import datetime
import contextlib

from PySide6.QtCore import Qt, Signal, QRect, Slot, QTimer
from PySide6.QtGui import (
    QKeyEvent, QTextDocument, QColor, QBrush, QKeySequence, QShortcut
)
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

        self._overlay_target: Optional[QWidget] = overlay_target
        self._show_graph = True if self._overlay_target is not None else bool(cfg.get("opt_show_graph", True))

        self._bars: List[List[Dict[str, float]]] = []
        self._bars_residuals: List[float] = []
        self._done_by_index: Dict[int, List[bool]] = {}

        # Collassa barre completate (default ON)
        self._collapse_done_bars: bool = bool(cfg.get("opt_collapse_done_bars", True))

        # Overlay chip
        self._overlay_label: Optional[QLabel] = None
        self._overlay_timer: Optional[QTimer] = None

        self.setFocusPolicy(Qt.StrongFocus)

        self._build()
        self._init_overlay()
        self._compute_plan_once()
        self._init_done_state()
        self._refresh_views()
        self._apply_geometry()
        self._resize_graph_area()

        # Scorciatoie tastiera
        self._sc_f7 = QShortcut(QKeySequence("F7"), self)
        self._sc_f7.activated.connect(lambda: self.simulationRequested.emit())
        self._sc_f9 = QShortcut(QKeySequence("F9"), self)
        self._sc_f9.activated.connect(lambda: self.startRequested.emit())
        self._sc_space = QShortcut(QKeySequence("Space"), self)
        self._sc_space.activated.connect(lambda: self.startRequested.emit())

    # Banner (opzionale, visibilità)
    def show_banner(self, msg: str, level: str = "info"):
        styles = {
            "info": "background:#ffe7ba; color:#1b1b1b; border:1px solid #c49a28;",
            "ok":   "background:#d4efdf; color:#145a32; border:1px solid #27ae60;",
            "warn": "background:#fdecea; color:#7b241c; border:1px solid #c0392b;",
        }
        sty = styles.get(level, styles["info"])
        if not hasattr(self, "_banner"):
            return
        self._banner.setText(msg)
        self._banner.setStyleSheet(f"QLabel {{{sty} font-size:20px; font-weight:900; padding:10px 14px; border-radius:8px;}}")
        self._banner.setVisible(True)
        try:
            self._banner.raise_()
            self.raise_()
            self.activateWindow()
        except Exception:
            pass

    def hide_banner(self):
        if hasattr(self, "_banner") and self._banner:
            self._banner.setVisible(False)
            self._banner.setText("")

    # ---------------- UI build ----------------
    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(8, 8, 8, 8); root.setSpacing(6)

        self._banner = QLabel("")
        self._banner.setVisible(False)
        self._banner.setAlignment(Qt.AlignCenter)
        self._banner.setStyleSheet("QLabel { background:#ffe7ba; color:#1b1b1b; font-size:18px; font-weight:800; padding:8px 12px; border:1px solid #c49a28; border-radius:6px; }")
        root.addWidget(self._banner)

        opts = QFrame(); ol = QHBoxLayout(opts); ol.setContentsMargins(0,0,0,0); ol.setSpacing(6)
        self._chk_graph = QCheckBox("Mostra grafica piano"); self._chk_graph.setChecked(self._show_graph)
        self._chk_graph.toggled.connect(self._toggle_graph)
        btn_summary = QPushButton("Riepilogo…"); btn_summary.clicked.connect(self._open_summary)
        btn_start = QPushButton("Avanza (F9 / Space)"); btn_start.clicked.connect(lambda: self.startRequested.emit())
        btn_cut = QPushButton("Simula taglio (F7)"); btn_cut.clicked.connect(lambda: self.simulationRequested.emit())
        # Collassa barre completate
        self._chk_collapse = QCheckBox("Collassa barre completate")
        self._chk_collapse.setChecked(self._collapse_done_bars)
        self._chk_collapse.toggled.connect(self._toggle_collapse_done)
        ol.addWidget(self._chk_graph)
        ol.addWidget(self._chk_collapse)
        ol.addStretch(1)
        ol.addWidget(btn_summary); ol.addWidget(btn_start); ol.addWidget(btn_cut)
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

    def keyPressEvent(self, e: QKeyEvent):
        if e.key() == Qt.Key_F7:
            self.simulationRequested.emit(); e.accept(); return
        if e.key() == Qt.Key_F9 or e.key() == Qt.Key_Space:
            self.startRequested.emit(); e.accept(); return
        super().keyPressEvent(e)

    def _apply_toggles(self):
        self._panel_graph.setVisible(self._show_graph)

    def _toggle_graph(self, on: bool):
        self._show_graph = bool(on); self._apply_toggles()
        if self._overlay_target is None:
            cfg = dict(read_settings()); cfg["opt_show_graph"] = self._show_graph; write_settings(cfg)
        self._resize_graph_area()

    def _toggle_collapse_done(self, on: bool):
        self._collapse_done_bars = bool(on)
        cfg = dict(read_settings()); cfg["opt_collapse_done_bars"] = self._collapse_done_bars; write_settings(cfg)
        self._resize_graph_area()

    def _open_summary(self):
        dlg = OptimizationSummaryDialog(self, self.profile, self._bars, self._bars_residuals, self._stock)
        dlg.setAttribute(Qt.WA_DeleteOnClose, True)
        dlg.show()

    # ---------------- Overlay chip helpers ----------------
    def _init_overlay(self):
        # Create floating label for visual "chip" on top-left of overlay target/dialog
        target = self._overlay_target if self._overlay_target is not None else self
        self._overlay_label = QLabel(target)
        self._overlay_label.setVisible(False)
        self._overlay_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._overlay_label.setStyleSheet("QLabel { background: transparent; border: none; }")
        self._overlay_timer = QTimer(self)
        self._overlay_timer.setSingleShot(True)
        self._overlay_timer.timeout.connect(lambda: self._overlay_label.setVisible(False))

    def _show_chip(self, piece: Dict[str, Any], bg_hex: str, ttl_ms: int):
        if not self._overlay_label:
            return
        L = piece.get("len", piece.get("length", 0.0))
        ax = piece.get("ax", piece.get("ang_sx", 0.0))
        ad = piece.get("ad", piece.get("ang_dx", 0.0))
        elem = piece.get("element", "")
        html = (
            f'<div style="background:{bg_hex}; border:2px solid rgba(0,0,0,0.25); '
            f'border-radius:10px; padding:6px 10px; color:#0d0d0d; font-weight:900;">'
            f'{elem}  L={float(L):.2f}  AX={float(ax):.1f}  AD={float(ad):.1f}'
            f'</div>'
        )
        self._overlay_label.setText(html)
        self._overlay_label.adjustSize()
        self._overlay_label.move(12, 12)
        self._overlay_label.setVisible(True)
        if ttl_ms > 0:
            self._overlay_timer.start(ttl_ms)
        else:
            self._overlay_timer.stop()

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

        bars, rem = pack_bars_knapsack_ilp(
            pieces=pieces,
            stock=self._stock,
            kerf_base=self._kerf_base,
            ripasso_mm=self._ripasso,
            conservative_angle_deg=float(read_settings().get("opt_knap_conservative_angle_deg", 45.0)),
            max_angle=self._max_angle,
            max_factor=self._max_factor,
            reversible=self._reversible,
            thickness_mm=self._thickness,
            angle_tol=self._angle_tol,
            per_bar_time_s=int(read_settings().get("opt_time_limit_s", 15))
        )
        if not bars:
            bars, rem = self._pack_bfd(pieces)

        try:
            bars, rem = refine_tail_ilp(
                bars, self._stock, self._kerf_base,
                self._ripasso, self._reversible, self._thickness,
                self._angle_tol, tail_bars=int(read_settings().get("opt_refine_tail_bars", 6)),
                time_limit_s=int(read_settings().get("opt_refine_time_s", 25)),
                max_angle=self._max_angle, max_factor=self._max_factor
            )
        except Exception:
            pass

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

        bars.sort(key=lambda b: max((p["len"] for p in b), default=0.0), reverse=True)

        self._bars = bars
        self._bars_residuals = rem

    # ---------------- Views & state ----------------
    def _init_done_state(self):
        self._done_by_index = {i: [False]*len(b) for i, b in enumerate(self._bars)}
        with contextlib.suppress(Exception):
            self._graph.set_done_by_index(self._done_by_index)

    def _refresh_views(self):
        with contextlib.suppress(Exception):
            self._graph.set_data(
                self._bars, stock_mm=self._stock,
                kerf_base=self._kerf_base, ripasso_mm=self._ripasso,
                reversible=self._reversible, thickness_mm=self._thickness,
                angle_tol=self._angle_tol, max_angle=self._max_angle,
                max_factor=self._max_factor, warn_threshold_mm=self._warn_thr
            )
        with contextlib.suppress(Exception):
            self._graph.set_done_by_index(self._done_by_index)
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

    def _remaining_bars_count(self) -> int:
        # Conta quante barre NON sono completamente completate
        rem = 0
        for i, b in enumerate(self._bars):
            done_list = self._done_by_index.get(i, [])
            if not done_list or not all(done_list):
                rem += 1
        return rem

    def _desired_graph_height(self, n_bars: int) -> int:
        if n_bars <= 0: return 120
        bars_h = n_bars * self.GRAPH_BAR_H + max(0, n_bars - 1) * self.GRAPH_V_GAP
        return max(100, bars_h + 16)

    def _resize_graph_area(self):
        if not (self._panel_graph and self._graph and self._tbl): return
        total_h = self.height()
        hdr_h = 40
        table_min = self.TABLE_MIN_H
        margins = 8 + 8 + 6
        avail_for_graph = max(100, total_h - (hdr_h + margins + table_min))
        # Se collasso barre finite, uso solo quelle rimanenti
        n_for_height = self._remaining_bars_count() if self._collapse_done_bars else len(self._bars)
        desired = self._desired_graph_height(n_for_height)
        gh = min(desired, avail_for_graph)
        with contextlib.suppress(Exception):
            self._graph.setMinimumHeight(int(gh))
            self._graph.setMaximumHeight(int(gh))

    def resizeEvent(self, event):
        super().resizeEvent(event); self._resize_graph_area()

    # ---------------- Evidenziazione e aggiornamenti da AutomaticoPage ----------------
    @Slot(dict)
    def onActivePieceChanged(self, piece: Dict[str, Any]):
        # Mostra chip ciano
        self._show_chip(piece, "#00bcd4", ttl_ms=0)
        # Prova ad evidenziare in PlanVisualizerWidget (se implementato)
        L = float(piece.get("len", piece.get("length", 0.0)))
        ax = float(piece.get("ax", piece.get("ang_sx", 0.0)))
        ad = float(piece.get("ad", piece.get("ang_dx", 0.0)))
        for meth in ("set_active_signature", "highlight_active_signature", "mark_active_by_signature", "set_active_piece_by_signature"):
            with contextlib.suppress(Exception):
                getattr(self._graph, meth)(L, ax, ad)
                break

    @Slot(dict)
    def onPieceCut(self, piece: Dict[str, Any]):
        # Mostra chip verde
        self._show_chip(piece, "#2ecc71", ttl_ms=900)
        # Aggiorna stato grafico e tabella
        L = float(piece.get("len", piece.get("length", 0.0)))
        ax = float(piece.get("ax", piece.get("ang_sx", 0.0)))
        ad = float(piece.get("ad", piece.get("ang_dx", 0.0)))
        self.update_after_cut(L, ax, ad)
        # Pulisce evidenziazione attiva (se supportata)
        for meth in ("clear_active_signature", "clear_active_highlight", "clear_active"):
            with contextlib.suppress(Exception):
                getattr(self._graph, meth)()
                break

    # ---------------- Mark done after cut ----------------
    def update_after_cut(self, length_mm: float, ang_sx: float, ang_dx: float):
        with contextlib.suppress(Exception):
            self._graph.mark_done_by_signature(length_mm, ang_sx, ang_dx)

        tol_L = 0.01; tol_A = 0.01
        for i in range(self._tbl.rowCount()):
            try:
                L = float(self._tbl.item(i, 0).text())
                ax = float(self._tbl.item(i, 1).text())
                ad = float(self._tbl.item(i, 2).text())
                q = int(self._tbl.item(i, 3).text())
            except Exception:
                continue
            if abs(L - length_mm) <= tol_L and abs(ax - ang_sx) <= tol_A and abs(ad - ang_dx) <= tol_A:
                self._tbl.setItem(i, 3, QTableWidgetItem(str(max(q - 1, 0))))
                break

        with contextlib.suppress(Exception):
            self._graph.update()
        self._resize_graph_area()
