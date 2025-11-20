from __future__ import annotations
from typing import List, Dict, Any, Optional, Tuple
import csv, contextlib
from datetime import datetime

from PySide6.QtCore import Qt, Signal, QRect, Slot, QEvent
from PySide6.QtGui import QKeyEvent, QTextDocument, QColor, QBrush, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox, QApplication,
    QWidget, QFileDialog, QScrollArea, QSizePolicy
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
        the_pdf = QPushButton("Esporta PDF")
        self.btn_close = QPushButton("Chiudi")
        btns.addWidget(self.btn_csv)
        btns.addWidget(the_pdf)
        btns.addWidget(self.btn_close)
        root.addLayout(btns)

        self.btn_close.clicked.connect(self.close)
        self.btn_csv.clicked.connect(self._export_csv)
        the_pdf.clicked.connect(self._export_pdf)

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

    GRAPH_BAR_H = 16
    GRAPH_V_GAP = 6
    TABLE_MIN_H = 180

    def __init__(self, parent, profile: str, rows: List[Dict[str, Any]], overlay_target: Optional[Widget] = None):
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

        self._overlay_target: Optional[Widget] = overlay_target
        self._show_graph = True if self._overlay_target is not None else bool(cfg.get("opt_show_graph", True))
        self._collapse_done_bars: bool = bool(cfg.get("opt_collapse_done_bars", True))

        self._bars: List[List[Dict[str, float]]] = []
        self._bars_residuals: List[float] = []
        self._done_by_index: Dict[int, List[bool]] = {}

        # container per scroll
        self._scroll: Optional[QScrollArea] = None
        self._graph_container: Optional[Widget] = None

        self.setFocusPolicy(Qt.StrongFocus)

        self._build()
        self._compute_plan_once()
        self._init_done_state()
        self._refresh_views()
        self._apply_geometry()
        self._resize_graph_area()

        # Scorciatoie tastiera
        self._sc_f7 = QShortcut(QKeySequence("F7"), self); self._sc_f7.activated.connect(self.simulationRequested.emit)
        self._sc_f9 = QShortcut(QKeySequence("F9"), self); self._sc_f9.activated.connect(self.startRequested.emit)
        self._sc_space = QShortcut(QKeySequence("Space"), self); self._sc_space.activated.connect(self.startRequested.emit)

    # ---------------- UI ----------------
    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(8, 8, 8, 8); root.setSpacing(6)

        opts = QFrame(); ol = QHBoxLayout(opts); ol.setContentsMargins(0,0,0,0); ol.setSpacing(6)
        self._chk_graph = QCheckBox("Mostra grafica piano"); self._chk_graph.setChecked(self._show_graph)
        self._chk_graph.toggled.connect(self._toggle_graph)
        self._chk_collapse = QCheckBox("Collassa barre completate"); self._chk_collapse.setChecked(self._collapse_done_bars)
        self._chk_collapse.toggled.connect(self._toggle_collapse_done)
        btn_summary = QPushButton("Riepilogo…"); btn_summary.clicked.connect(self._open_summary)
        btn_start = QPushButton("Avanza (F9 / Space)"); btn_start.clicked.connect(self.startRequested.emit)
        btn_cut = QPushButton("Simula taglio (F7)"); btn_cut.clicked.connect(self.simulationRequested.emit)
        ol.addWidget(self._chk_graph); ol.addWidget(self._chk_collapse); ol.addStretch(1)
        ol.addWidget(btn_summary); ol.addWidget(btn_start); ol.addWidget(btn_cut)
        root.addWidget(opts, 0)

        # pannello grafico con scrollbar verticale robusto
        self._panel_graph = QFrame()
        gl = QVBoxLayout(self._panel_graph); gl.setContentsMargins(6,6,6,6); gl.setSpacing(4)
        self._scroll = QScrollArea(self._panel_graph)
        self._scroll.setWidgetResizable(False)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # container contenuto scrollabile
        self._graph_container = QWidget()
        self._graph_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        cont_layout = QVBoxLayout(self._graph_container); cont_layout.setContentsMargins(0,0,0,0); cont_layout.setSpacing(0)

        self._graph = PlanVisualizerWidget(self._graph_container)
        self._graph.installEventFilter(self)

        cont_layout.addWidget(self._graph)
        self._scroll.setWidget(self._graph_container)
        gl.addWidget(self._scroll, 1)
        root.addWidget(self._panel_graph, 0)

        # tabella firme
        self._tbl = QTableWidget(0, 4)
        self._tbl.setHorizontalHeaderLabels(["Lunghezza (mm)", "Ang SX", "Ang DX", "Q.tà"])
        hdr = self._tbl.horizontalHeader()
        for i in range(4):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self._tbl.setMinimumHeight(self.TABLE_MIN_H)
        root.addWidget(self._tbl, 1)

        self._apply_toggles()

    def eventFilter(self, obj, e):
        if obj is self._graph and e.type() == QEvent.Type.Wheel and self._scroll:
            QApplication.sendEvent(self._scroll.verticalScrollBar(), e)
            return True
        return super().eventFilter(obj, e)

    def keyPressEvent(self, e: QKeyEvent):
        if e.key() == Qt.Key_F7:
            self.simulationRequested.emit(); e.accept(); return
        if e.key() in (Qt.Key_F9, Qt.Key_Space):
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
        self._refresh_graph_only()

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

        # ordina intra-barra per lunghezze decrescenti; barre per max lunghezza
        for b in bars:
            with contextlib.suppress(Exception):
                b.sort(key=lambda p:(-float(p["len"]),float(p["ax"]),float(p["ad"])))
        bars.sort(key=lambda b: max((float(p["len"]) for p in b), default=0.0), reverse=True)

        self._bars = bars
        self._bars_residuals = residuals(bars, self._stock, self._kerf_base, self._ripasso,
                                         self._reversible, self._thickness,
                                         self._angle_tol, self._max_angle, self._max_factor)

    # ---------------- Views & state ----------------
    def _init_done_state(self):
        self._done_by_index = {i: [False]*len(b) for i, b in enumerate(self._bars)}
        with contextlib.suppress(Exception):
            self._graph.set_done_by_index(self._done_by_index)

    def _effective_bars_for_view(self) -> List[List[Dict[str,float]]]:
        if not self._collapse_done_bars:
            return self._bars
        out: List[List[Dict[str,float]]] = []
        for i, b in enumerate(self._bars):
            flags = self._done_by_index.get(i, [])
            if not flags or not all(flags):
                out.append(b)
        return out

    def _refresh_graph_only(self):
        if not self._graph: return
        bars_view = self._effective_bars_for_view()
        with contextlib.suppress(Exception):
            self._graph.set_data(
                bars_view, stock_mm=self._stock,
                kerf_base=self._kerf_base, ripasso_mm=self._ripasso,
                reversible=self._reversible, thickness_mm=self._thickness,
                angle_tol=self._angle_tol, max_angle=self._max_angle,
                max_factor=self._max_factor, warn_threshold_mm=self._warn_thr
            )
            if not self._collapse_done_bars:
                self._graph.set_done_by_index(self._done_by_index)
        self._resize_graph_area()

    def _refresh_views(self):
        self._refresh_graph_only()
        self._reload_table()

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
                self.resize(max(980, self.width()), int(avail.height() - 32))
                self.move(avail.x() + 12, avail.y() + 12)

    def _remaining_bars_count(self) -> int:
        rem = 0
        for i, b in enumerate(self._bars):
            done_list = self._done_by_index.get(i, [])
            if not done_list or not all(done_list):
                rem += 1
        return rem

    def _estimate_content_height(self) -> int:
        n_bars = self._remaining_bars_count() if self._collapse_done_bars else len(self._bars)
        if n_bars<=0: return 120
        return n_bars * self.GRAPH_BAR_H + max(0, n_bars - 1) * self.GRAPH_V_GAP + 16

    def _resize_graph_area(self):
        if not (self._graph_container and self._graph): return
        content_h = max(120, self._estimate_content_height())
        self._graph_container.setMinimumHeight(int(content_h))
        self._graph_container.setMaximumHeight(int(content_h))
        self._graph.setMinimumHeight(int(content_h))
        self._graph.setMaximumHeight(int(content_h))
        with contextlib.suppress(Exception):
            self._graph.update()

    def resizeEvent(self, event):
        super().resizeEvent(event); self._resize_graph_area()

    # ---------------- Aggiornamenti dopo taglio ----------------
    def _mark_done_local(self, length_mm: float, ang_sx: float, ang_dx: float):
        tol_L = 1e-2; tol_A = 1e-2
        for i, bar in enumerate(self._bars):
            for j, p in enumerate(bar):
                if self._done_by_index.get(i, [])[j]:
                    continue
                try:
                    if abs(float(p.get("len",0.0)) - length_mm) <= tol_L and \
                       abs(float(p.get("ax",0.0)) - ang_sx) <= tol_A and \
                       abs(float(p.get("ad",0.0)) - ang_dx) <= tol_A:
                        self._done_by_index[i][j] = True
                        return
                except Exception:
                    continue

    def update_after_cut(self, length_mm: float, ang_sx: float, ang_dx: float):
        with contextlib.suppress(Exception):
            self._graph.mark_done_by_signature(length_mm, ang_sx, ang_dx)
        self._mark_done_local(length_mm, ang_sx, ang_dx)
        self._refresh_graph_only()

    # ---------------- Slot esterni (da AutomaticoPage) ----------------
    @Slot(dict)
    def onActivePieceChanged(self, piece: Dict[str,Any]):
        L = float(piece.get("len", piece.get("length", 0.0)))
        ax = float(piece.get("ax", piece.get("ang_sx", 0.0)))
        ad = float(piece.get("ad", piece.get("ang_dx", 0.0)))
        for meth in ("set_active_signature","highlight_active_signature","mark_active_by_signature","set_active_piece_by_signature"):
            with contextlib.suppress(Exception):
                getattr(self._graph, meth)(L, ax, ad)
                break

    @Slot(dict)
    def onPieceCut(self, piece: Dict[str,Any]):
        L = float(piece.get("len", piece.get("length", 0.0)))
        ax = float(piece.get("ax", piece.get("ang_sx", 0.0)))
        ad = float(piece.get("ad", piece.get("ang_dx", 0.0)))
        self.update_after_cut(L, ax, ad)
