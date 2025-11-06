from __future__ import annotations
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QCheckBox, QApplication,
)

try:
    from ui_qt.utils.settings import read_settings, write_settings
except Exception:
    def read_settings(): return {}
    def write_settings(_): pass

from ui_qt.widgets.plan_visualizer import PlanVisualizerWidget


class OptimizationRunDialog(QDialog):
    """
    Dialog ottimizzazione:
    - Tabella riepilogo pezzi
    - Riepilogo barre (numero/residui)
    - Visualizzazione grafica piano (trapezi/rette) con evidenziazione pezzi tagliati
    - Opzioni: mostra/nascondi riepilogo e grafica

    Estensioni:
    - startRequested (F9) e simulationRequested (F7)
    - altezza grafica adattiva in base al numero di barre
    - dialog massimizzato in altezza, larghezza ottimizzata tenendo libero lo spazio destro
      riservato ai pannelli della pagina Automatico (reserved_right_px)
    - chiusura automatica al termine (tutte qty==0)

    API:
    - update_after_cut(length_mm, ang_sx, ang_dx)
    - proprietà 'profile'
    """
    simulationRequested = Signal()
    startRequested = Signal()

    def __init__(self, parent, profile: str, rows: List[Dict[str, Any]], reserved_right_px: int = 0):
        super().__init__(parent)
        self.setWindowTitle(f"Ottimizzazione - {profile}")
        self.setModal(False)
        self.profile = profile
        # rows: [{length_mm, ang_sx, ang_dx, qty}]
        self._rows: List[Dict[str, Any]] = [dict(r) for r in rows]

        self._tbl: Optional[QTableWidget] = None
        self._lbl_bars: Optional[QLabel] = None
        self._panel_summary: Optional[QFrame] = None
        self._panel_graph: Optional[QFrame] = None
        self._chk_summary: Optional[QCheckBox] = None
        self._chk_graph: Optional[QCheckBox] = None
        self._graph: Optional[PlanVisualizerWidget] = None

        # Settings
        cfg = read_settings()
        self._stock = float(cfg.get("opt_stock_mm", 6500.0))
        self._kerf = float(cfg.get("opt_kerf_mm", 3.0))
        self._show_summary = bool(cfg.get("opt_show_summary", True))
        self._show_graph = bool(cfg.get("opt_show_graph", True))

        # Piano calcolato localmente (BFD) una sola volta
        self._bars: List[List[Dict[str, float]]] = []
        self._bars_residuals: List[float] = []

        # Spazio da riservare a destra per i pannelli della pagina Automatico
        self._reserved_right_px = max(0, int(reserved_right_px))

        self._build()
        self._compute_plan_once()
        self._refresh_views()
        self._apply_geometry()

    # ---------- Build UI ----------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Top options
        opts = QHBoxLayout()
        self._chk_summary = QCheckBox("Mostra riepilogo barre"); self._chk_summary.setChecked(self._show_summary)
        self._chk_summary.toggled.connect(self._toggle_summary)
        self._chk_graph = QCheckBox("Mostra grafica piano"); self._chk_graph.setChecked(self._show_graph)
        self._chk_graph.toggled.connect(self._toggle_graph)
        btn_start = QPushButton("Simula Avanzamento (F9)")
        btn_start.setToolTip("Simula un evento START")
        btn_start.clicked.connect(lambda: self.startRequested.emit())
        btn_sim = QPushButton("Simula START (F7)")
        btn_sim.setToolTip("Simula un taglio come pulse lama")
        btn_sim.clicked.connect(lambda: self.simulationRequested.emit())
        opts.addWidget(self._chk_summary)
        opts.addWidget(self._chk_graph)
        opts.addStretch(1)
        opts.addWidget(btn_start)
        opts.addWidget(btn_sim)
        root.addLayout(opts)

        # Riepilogo barre
        self._panel_summary = QFrame()
        self._panel_summary.setStyleSheet("QFrame { border:1px solid #3b4b5a; border-radius:6px; }")
        sl = QVBoxLayout(self._panel_summary); sl.setContentsMargins(8,8,8,8); sl.setSpacing(6)
        sl.addWidget(QLabel("Riepilogo barre"))
        self._lbl_bars = QLabel("—"); sl.addWidget(self._lbl_bars)
        root.addWidget(self._panel_summary, 0)

        # Grafica piano
        self._panel_graph = QFrame()
        self._panel_graph.setStyleSheet("QFrame { border:1px solid #3b4b5a; border-radius:6px; }")
        gl = QVBoxLayout(self._panel_graph); gl.setContentsMargins(8,8,8,8); gl.setSpacing(6)
        self._graph = PlanVisualizerWidget(self)
        gl.addWidget(self._graph, 1)
        root.addWidget(self._panel_graph, 1)

        # Tabella pezzi
        self._tbl = QTableWidget(0, 4)
        self._tbl.setHorizontalHeaderLabels(["Lunghezza (mm)", "Ang SX", "Ang DX", "Q.tà"])
        hdr = self._tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        root.addWidget(self._tbl, 0)

        self._apply_toggles()

    def _apply_toggles(self):
        if self._panel_summary: self._panel_summary.setVisible(self._show_summary)
        if self._panel_graph: self._panel_graph.setVisible(self._show_graph)

    def _toggle_summary(self, on: bool):
        self._show_summary = bool(on)
        self._apply_toggles()
        cfg = dict(read_settings()); cfg["opt_show_summary"] = self._show_summary; write_settings(cfg)
        self._apply_geometry()

    def _toggle_graph(self, on: bool):
        self._show_graph = bool(on)
        self._apply_toggles()
        cfg = dict(read_settings()); cfg["opt_show_graph"] = self._show_graph; write_settings(cfg)
        self._apply_geometry()

    # ---------- Plan computation ----------
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

    def _pack_bars_bfd(self, pieces: List[Dict[str, float]]) -> Tuple[List[List[Dict[str, float]]], List[float]]:
        bars: List[List[Dict[str, float]]] = []
        rem: List[float] = []
        kerf = float(self._kerf)
        stock = float(self._stock)
        for p in pieces:
            need = float(p["len"])
            placed = False
            for i in range(len(bars)):
                extra = kerf if bars[i] else 0.0
                if rem[i] >= (need + extra):
                    bars[i].append(p); rem[i] -= (need + extra); placed = True; break
            if not placed:
                bars.append([p]); rem.append(max(stock - need, 0.0))
        return bars, rem

    def _compute_plan_once(self):
        pieces = self._expand_rows_to_unit_pieces()
        bars, rem = self._pack_bars_bfd(pieces)
        # Ordine barre: lascia per ultima quella con residuo massimo
        if rem:
            max_idx = max(range(len(rem)), key=lambda i: rem[i])
            if 0 <= max_idx < len(bars) and max_idx != len(bars) - 1:
                last_bar = bars.pop(max_idx); bars.append(last_bar)
                last_res = rem.pop(max_idx); rem.append(last_res)
        self._bars, self._bars_residuals = bars, rem

    # ---------- Views refresh ----------
    def _desired_graph_height(self, n_bars: int) -> int:
        if n_bars <= 0:
            return 160
        bar_h = 20
        vgap = 10
        padding = 8 + 8 + 6 + 6  # margini pannello e layout
        bars_h = n_bars * bar_h + (n_bars - 1) * vgap
        return max(140, bars_h + padding)

    def _refresh_views(self):
        # Riepilogo barre
        nb = len(self._bars)
        if nb == 0:
            txt = "Nessuna barra necessaria."
        else:
            residui = " | ".join([f"B{i+1} residuo: {r:.1f} mm" for i, r in enumerate(self._bars_residuals)])
            txt = f"Barre necessarie: {nb} — {residui}"
        if self._lbl_bars:
            self._lbl_bars.setText(txt)

        # Grafica
        if self._graph:
            self._graph.set_data(self._bars, stock_mm=self._stock, kerf_mm=self._kerf)
            # Altezza grafica adattiva (limita a ~2/3 dello schermo)
            try:
                screen = QApplication.primaryScreen()
                avail = screen.availableGeometry().height() if screen else 1080
                gh = self._desired_graph_height(nb)
                gh = min(gh, int(avail * 0.66))
                self._graph.setMinimumHeight(gh)
                self._graph.setMaximumHeight(gh)
            except Exception:
                pass

        # Tabella
        self._reload_table()

        # Se tutto finito → chiudi
        if self._all_done():
            self._close_and_focus_parent()

    # ---------- Dimensionamento dialog ----------
    def _apply_geometry(self):
        try:
            screen = QApplication.primaryScreen()
            if not screen:
                return
            avail = screen.availableGeometry()
            # Altezza quasi massima
            h = int(avail.height() - 32)
            # Larghezza: lascia libero uno spazio a destra pari a reserved_right_px
            margin = 24
            w = max(720, avail.width() - self._reserved_right_px - margin)
            self.resize(w, h)
            # Posiziona verso sinistra
            self.move(avail.x() + 12, avail.y() + 12)
        except Exception:
            pass

    # ---------- Table ----------
    def _reload_table(self):
        if not self._tbl:
            return
        self._tbl.setRowCount(0)
        for r in self._rows:
            q = int(r.get("qty", 0))
            if q < 0:
                q = 0
            row = self._tbl.rowCount()
            self._tbl.insertRow(row)
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
            parent = self.parent()
            self.close()
            if parent is not None:
                try:
                    parent.raise_()
                    parent.activateWindow()
                except Exception:
                    pass
        except Exception:
            pass

    # ---------- Public API ----------
    def update_after_cut(self, length_mm: float, ang_sx: float, ang_dx: float):
        """Evidenzia un pezzo come tagliato, decrementa la riga corrispondente e aggiorna viste (senza ricomporre il piano)."""
        # 1) Evidenziazione nel grafico
        if self._graph:
            try:
                self._graph.mark_done(length_mm, ang_sx, ang_dx)
            except Exception:
                pass

        # 2) Decremento qty in tabella (matching numerico poi stringhe)
        tol_L = 0.01; tol_A = 0.01
        matched = False
        for r in self._rows:
            try:
                if abs(float(r.get("length_mm", 0.0)) - float(length_mm)) <= tol_L \
                   and abs(float(r.get("ang_sx", 0.0)) - float(ang_sx)) <= tol_A \
                   and abs(float(r.get("ang_dx", 0.0)) - float(ang_dx)) <= tol_A:
                    r["qty"] = max(0, int(r.get("qty", 0)) - 1)
                    matched = True
                    break
            except Exception:
                continue
        if not matched:
            Ls = f"{float(length_mm):.2f}"; Axs = f"{float(ang_sx):.1f}"; Ads = f"{float(ang_dx):.1f}"
            for r in self._rows:
                try:
                    if f"{float(r.get('length_mm', 0.0)):.2f}" == Ls \
                       and f"{float(r.get('ang_sx', 0.0)):.1f}" == Axs \
                       and f"{float(r.get('ang_dx', 0.0)):.1f}" == Ads:
                        r["qty"] = max(0, int(r.get("qty", 0)) - 1)
                        break
                except Exception:
                    continue

        # 3) Aggiorna views e chiudi se tutto finito
        self._refresh_views()

    # ---------- Keyboard handling ----------
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

    # ---------- Lifecycle ----------
    def accept(self):
        cfg = dict(read_settings())
        cfg["opt_show_summary"] = bool(self._chk_summary and self._chk_summary.isChecked())
        cfg["opt_show_graph"] = bool(self._chk_graph and self._chk_graph.isChecked())
        write_settings(cfg)
        super().accept()

    def reject(self):
        self.accept()
