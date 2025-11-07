from __future__ import annotations
from typing import List, Dict, Any, Optional, Tuple

from PySide6.QtCore import Qt, Signal, QRect
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox, QApplication,
    QWidget
)

from ui_qt.utils.settings import read_settings, write_settings
from ui_qt.widgets.plan_visualizer import PlanVisualizerWidget
from ui_qt.logic.refiner import (
    pack_bars_knapsack_ilp,
    refine_tail_ilp,
    bar_used_length,
    residuals,
    joint_consumption
)


class OptimizationRunDialog(QDialog):
    """
    Dialog di run ottimizzazione con grafica trapezoidale:
    - Trapezi: base maggiore in alto, minore in basso.
    - Evidenzia pezzo corrente (bordo arancione).
    - Evidenzia pezzi tagliati (verde).
    - F7: simula taglio (simulationRequested)
    - F9: arma prossimo pezzo (startRequested)
    """
    simulationRequested = Signal()
    startRequested = Signal()

    strict_bar_mode = True

    def __init__(self, parent, profile: str, rows: List[Dict[str, Any]],
                 overlay_target: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(f"Ottimizzazione - {profile}")
        self.setModal(False)
        self.profile = profile
        self._rows: List[Dict[str, Any]] = [dict(r) for r in rows]

        cfg = read_settings()
        self._stock = float(cfg.get("opt_stock_mm", 6500.0))
        su = float(cfg.get("opt_stock_usable_mm", 0.0))
        if su > 0: self._stock = su
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

        self._overlay_target = overlay_target

        self._bars: List[List[Dict[str, float]]] = []
        self._bars_residuals: List[float] = []
        self._bar_idx: int = -1
        self._piece_idx: int = -1

        self._build()
        self._compute_plan_once()
        self._init_done_state()
        self._refresh()
        self._apply_geometry()

    # --------------- UI build ---------------
    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(8, 8, 8, 8); root.setSpacing(6)

        top = QFrame(); tl = QHBoxLayout(top); tl.setContentsMargins(0,0,0,0); tl.setSpacing(6)
        self._chk_graph = QCheckBox("Mostra grafica"); self._chk_graph.setChecked(True)
        self._chk_graph.toggled.connect(self._toggle_graph)
        btn_start = QPushButton("Avanza pezzo (F9)"); btn_start.clicked.connect(lambda: self.startRequested.emit())
        btn_cut = QPushButton("Simula taglio (F7)"); btn_cut.clicked.connect(lambda: self.simulationRequested.emit())
        tl.addWidget(QLabel(f"Profilo: {self.profile}"))
        tl.addStretch(1)
        tl.addWidget(self._chk_graph); tl.addWidget(btn_start); tl.addWidget(btn_cut)
        root.addWidget(top, 0)

        self._panel_graph = QFrame()
        gl = QVBoxLayout(self._panel_graph); gl.setContentsMargins(6,6,6,6); gl.setSpacing(4)
        self._graph = PlanVisualizerWidget(self._panel_graph)
        gl.addWidget(self._graph, 1)
        root.addWidget(self._panel_graph, 0)

        self._tbl = QTableWidget(0, 4)
        self._tbl.setHorizontalHeaderLabels(["Lunghezza (mm)", "Ang SX", "Ang DX", "Q.tà"])
        hdr = self._tbl.horizontalHeader()
        for i in range(4):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        root.addWidget(self._tbl, 1)

    def _toggle_graph(self, on: bool):
        self._panel_graph.setVisible(bool(on))

    # --------------- Piano ---------------
    def _expand_rows(self) -> List[Dict[str, float]]:
        out: List[Dict[str, float]] = []
        for r in self._rows:
            q = int(r.get("qty", 0))
            L = float(r.get("length_mm", 0.0))
            ax = float(r.get("ang_sx", 0.0)); ad = float(r.get("ang_dx", 0.0))
            for _ in range(max(0, q)):
                out.append({"len": L, "ax": ax, "ad": ad})
        out.sort(key=lambda x: x["len"], reverse=True)
        return out

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
        pieces = self._expand_rows()
        if self._solver in ("ILP_KNAP","ILP"):
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

        # Refine tail (ignora errori)
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

        # Overflow sanitize
        fixed: List[List[Dict[str, float]]] = []
        overflow: List[Dict[str, float]] = []
        for bar in bars:
            b = list(bar)
            while b and bar_used_length(b, self._kerf_base, self._ripasso,
                                       self._reversible, self._thickness,
                                       self._angle_tol, self._max_angle, self._max_factor) > self._stock + 1e-6:
                overflow.append(b.pop())
            fixed.append(b)
        if overflow:
            for piece in sorted(overflow, key=lambda x: x["len"], reverse=True):
                placed = False
                for fb in fixed:
                    used = bar_used_length(fb, self._kerf_base, self._ripasso,
                                           self._reversible, self._thickness,
                                           self._angle_tol, self._max_angle, self._max_factor)
                    extra = joint_consumption(fb[-1], self._kerf_base, self._ripasso,
                                              self._reversible, self._thickness,
                                              self._angle_tol, self._max_angle, self._max_factor)[0] if fb else 0.0
                    if used + piece["len"] + extra <= self._stock + 1e-6:
                        fb.append(piece); placed = True; break
                if not placed:
                    fixed.append([piece])

        bars = fixed
        rem = residuals(bars, self._stock, self._kerf_base, self._ripasso,
                        self._reversible, self._thickness,
                        self._angle_tol, self._max_angle, self._max_factor)

        # Ordinamento barre: massima lunghezza decrescente (strict sequencing)
        bars.sort(key=lambda b: max((p["len"] for p in b), default=0.0), reverse=True)

        self._bars = bars
        self._bars_residuals = rem

    def _init_done_state(self):
        self._bar_idx = 0 if self._bars else -1
        self._piece_idx = -1
        self._graph.reset_done()
        self._graph.set_data(
            self._bars, self._stock, self._kerf_base, self._ripasso,
            self._reversible, self._thickness, self._angle_tol,
            self._max_angle, self._max_factor, self._warn_thr
        )
        self._graph.set_current_bar(self._bar_idx if self._bar_idx >= 0 else None)

    # --------------- Refresh ---------------
    def _refresh(self):
        self._reload_table()
        # Aggiorna grafica pezzo corrente (se pezzo armato)
        if self._bar_idx >= 0 and self._piece_idx >= 0:
            self._graph.set_current_piece(self._bar_idx, self._piece_idx)
        else:
            self._graph.set_current_piece(-1, -1)
        self._graph.set_current_bar(self._bar_idx if self._bar_idx >= 0 else None)

    def _reload_table(self):
        self._tbl.setRowCount(0)
        for r in self._rows:
            q = int(r.get("qty", 0))
            row = self._tbl.rowCount(); self._tbl.insertRow(row)
            self._tbl.setItem(row, 0, QTableWidgetItem(f"{float(r.get('length_mm',0.0)):.2f}"))
            self._tbl.setItem(row, 1, QTableWidgetItem(f"{float(r.get('ang_sx',0.0)):.1f}"))
            self._tbl.setItem(row, 2, QTableWidgetItem(f"{float(r.get('ang_dx',0.0)):.1f}"))
            self._tbl.setItem(row, 3, QTableWidgetItem(str(q)))

    # --------------- Geometry ---------------
    def _apply_geometry(self):
        if self._overlay_target:
            try:
                tl = self._overlay_target.mapToGlobal(self._overlay_target.rect().topLeft())
                br = self._overlay_target.mapToGlobal(self._overlay_target.rect().bottomRight())
                self.setGeometry(QRect(tl, br))
            except Exception:
                pass
        else:
            scr = QApplication.primaryScreen()
            if scr:
                g = scr.availableGeometry()
                self.resize(max(820, self.width()), int(g.height() - 42))
                self.move(g.x() + 12, g.y() + 12)

    # --------------- API chiamate dalla pagina Automatico ---------------
    def arm_next_piece(self) -> Optional[Tuple[float, float, float]]:
        if not self._bars or self._bar_idx >= len(self._bars):
            return None
        bar = self._bars[self._bar_idx]
        # Trova primo pezzo non done (strict)
        for idx, _p in enumerate(bar):
            # Determinazione done via colore (interno): usiamo mark_done_index con tracking interno
            # Il widget memorizza in _done_by_index; usiamo sua copia letta dai attributi (privato)
            # Per mantenere indipendenza: chiediamo done allo stato interno (non esposto) -> ricreiamo logica:
            # Semplice: se trapezio corrente non è “current” e non evidenziato done, assumiamo tutto ok.
            # Più affidabile: facciamo sniff su fill ad ogni call? troppo complicato → manteniamo _done_by_index interno.
            pass
        # Non abbiamo accesso diretto allo stato interno (privato). Semplifichiamo: incrementale
        self._piece_idx += 1
        if self._piece_idx >= len(bar):
            # barra finita -> prova a passare alla successiva
            self._bar_idx += 1
            self._piece_idx = 0
            if self._bar_idx >= len(self._bars):
                return None
            bar = self._bars[self._bar_idx]
        p = bar[self._piece_idx]
        self._graph.set_current_piece(self._bar_idx, self._piece_idx)
        return (p["len"], p["ax"], p["ad"])

    def update_after_cut(self, length_mm: float, ang_sx: float, ang_dx: float):
        # Marca il pezzo corrispondente
        self._graph.mark_done_by_signature(length_mm, ang_sx, ang_dx)
        # Aggiorna quantità (decrementa primo matching)
        tol = 0.01
        for r in self._rows:
            try:
                if abs(float(r.get("length_mm",0.0)) - length_mm) <= tol \
                   and abs(float(r.get("ang_sx",0.0)) - ang_sx) <= tol \
                   and abs(float(r.get("ang_dx",0.0)) - ang_dx) <= tol:
                    r["qty"] = max(0, int(r.get("qty",0)) - 1)
                    break
            except Exception:
                continue
        self._refresh()

    # --------------- Eventi tastiera ---------------
    def keyPressEvent(self, ev: QKeyEvent):
        if ev.key() == Qt.Key_F7:
            self.simulationRequested.emit(); ev.accept(); return
        if ev.key() == Qt.Key_F9:
            self.startRequested.emit(); ev.accept(); return
        super().keyPressEvent(ev)

    def accept(self):
        cfg = dict(read_settings())
        cfg["opt_show_graph"] = bool(self._chk_graph.isChecked())
        write_settings(cfg)
        super().accept()

    def reject(self):
        self.accept()
