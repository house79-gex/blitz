"""
PlanVisualizerWidget compatibile con OptimizationRunDialog
Caratteristiche:
- Altezza barra fissa: BAR_HEIGHT_PX (default 20 px).
- Larghezza barra adattata alla larghezza del widget meno un margine.
- Ogni pezzo disegnato come trapezio:
    * Base superiore = lunghezza esterna (len).
    * Base inferiore = len - offset_sx_mm - offset_dx_mm (offset = thickness_mm * tan(angle)).
    * Offset convertiti in pixel usando stessa scala orizzontale.
    * Offset minimi garantiti per angoli > 0° (OFFSET_MIN_PX).
- Colori:
    * Completato: verde
    * Attivo: arancione
    * Pendente: grigio
- mark_done_by_signature: marca solo la PRIMA occorrenza non completata (non tutte le firme).
- set_active_signature: evidenzia solo un pezzo (prima occorrenza non completata di quella firma).
- Supporta auto-continue senza che firme identiche generino highlight multipli.

Metodi supportati:
  set_data(...)
  set_done_by_index(...)
  mark_done_by_signature(...)
  set_active_signature(...)
  highlight_active_signature(...)
  mark_active_by_signature(...)
  set_active_piece_by_signature(...)
  set_active_position(bar_idx, piece_idx)
  set_active_piece_by_indices(bar_idx, piece_idx)
  mark_done_at(bar_idx, piece_idx)  (per eventuale uso diretto)
"""

from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF, QSize, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QPolygonF

import math
import logging

logger = logging.getLogger(__name__)

BAR_HEIGHT_PX = 20
BAR_VERTICAL_GAP = 8
LEFT_MARGIN_PX = 140
RIGHT_MARGIN_PX = 24
MIN_PIECE_WIDTH_PX = 14
OFFSET_MIN_PX = 2.0   # offset minimo visivo se angolo > 0
OFFSET_SCALE_BOOST = 1.0  # puoi aumentare (es. 1.5) se vuoi trapezi più evidenti


def _ext_len(p: Dict[str, Any]) -> float:
    return float(p.get("len", p.get("length_mm", p.get("length", 0.0))))


def _offsets_mm(p: Dict[str, Any], thickness_mm: float) -> Tuple[float, float]:
    if thickness_mm <= 0:
        return 0.0, 0.0
    ax = abs(float(p.get("ax", p.get("ang_sx", 0.0))))
    ad = abs(float(p.get("ad", p.get("ang_dx", 0.0))))
    try:
        sx = thickness_mm * math.tan(math.radians(ax))
    except Exception:
        sx = 0.0
    try:
        dx = thickness_mm * math.tan(math.radians(ad))
    except Exception:
        dx = 0.0
    return max(0.0, sx), max(0.0, dx)


def _signature(p: Dict[str, Any]) -> Tuple[float, float, float, str]:
    L = _ext_len(p)
    ax = float(p.get("ax", p.get("ang_sx", 0.0)))
    ad = float(p.get("ad", p.get("ang_dx", 0.0)))
    prof = str(p.get("profile", "")).strip()
    return (round(L, 2), round(ax, 1), round(ad, 1), prof)


class PlanVisualizerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bars: List[List[Dict[str, Any]]] = []
        self._stock_mm: float = 0.0
        self._thickness_mm: float = 0.0
        self._kerf_base: float = 0.0
        self._ripasso_mm: float = 0.0
        self._warn_thr: float = 0.0

        # done_map: bar_idx -> list[bool]
        self._done_map: Dict[int, List[bool]] = {}
        # Non usiamo più un set globale di firme completate per evitare green su tutte le uguali.
        # Manteniamo per compat, ma non lo usiamo per mass-mark.
        self._done_signatures: set[Tuple[float, float, float, str]] = set()

        # Pezzo attivo
        self._active_pos: Optional[Tuple[int, int]] = None
        self._active_sig: Optional[Tuple[float, float, float, str]] = None

        self.setMinimumHeight(120)
        self.setMouseTracking(True)

    # ---------------- Data setup ----------------
    def set_data(self,
                 bars: List[List[Dict[str, Any]]],
                 stock_mm: float,
                 kerf_base: float,
                 ripasso_mm: float,
                 reversible: bool,
                 thickness_mm: float,
                 angle_tol: float,
                 max_angle: float,
                 max_factor: float,
                 warn_threshold_mm: float):
        # 'reversible', 'angle_tol', 'max_angle', 'max_factor' non influenzano grafica qui
        self._bars = bars or []
        self._stock_mm = float(stock_mm or 0.0)
        self._kerf_base = float(kerf_base or 0.0)
        self._ripasso_mm = float(ripasso_mm or 0.0)
        self._thickness_mm = float(thickness_mm or 0.0)
        self._warn_thr = float(warn_threshold_mm or 0.0)
        # normalizza done map
        tmp_map: Dict[int, List[bool]] = {}
        for i, b in enumerate(self._bars):
            arr = self._done_map.get(i)
            if arr is None or len(arr) != len(b):
                tmp_map[i] = [False] * len(b)
            else:
                tmp_map[i] = arr
        self._done_map = tmp_map
        self._recalc_min_height()
        self.update()

    def _recalc_min_height(self):
        total_h = len(self._bars) * (BAR_HEIGHT_PX + BAR_VERTICAL_GAP) + 40
        self.setMinimumHeight(max(120, total_h))

    def sizeHint(self) -> QSize:
        return QSize(max(600, self.width()), self.minimumHeight())

    # ---------------- Done mapping ----------------
    def set_done_by_index(self, done_map: Dict[int, List[bool]]):
        for bi, arr in done_map.items():
            if bi < len(self._bars) and len(arr) == len(self._bars[bi]):
                self._done_map[bi] = [bool(x) for x in arr]
                # Evita di marcare tutte le firme come green massivo
        self.update()

    def mark_done_at(self, bar_idx: int, piece_idx: int):
        """Marca esattamente un pezzo come completato (preferibile)."""
        if 0 <= bar_idx < len(self._bars) and 0 <= piece_idx < len(self._bars[bar_idx]):
            self._done_map.setdefault(bar_idx, [False] * len(self._bars[bar_idx]))
            self._done_map[bar_idx][piece_idx] = True
            if self._active_pos == (bar_idx, piece_idx):
                self._active_pos = None
            self.update()

    def mark_done_by_signature(self, length_mm: float, ax: float, ad: float):
        """Compat: segna SOLO la prima occorrenza non completata di quella firma (non tutte)."""
        target = (round(float(length_mm), 2), round(float(ax), 1), round(float(ad), 1))
        for bi, bar in enumerate(self._bars):
            for pi, p in enumerate(bar):
                sig = _signature(p)
                if sig[0] == target[0] and sig[1] == target[1] and sig[2] == target[2]:
                    if not self._done_map.get(bi, [False] * len(bar))[pi]:
                        self.mark_done_at(bi, pi)
                        return
        # Se non trovata, nessuna azione.

    # ---------------- Active piece ----------------
    def set_active_signature(self, length_mm: float, ax: float, ad: float, profile: str = ""):
        target = (round(float(length_mm), 2), round(float(ax), 1), round(float(ad), 1), profile.strip())
        self._active_sig = target
        self._active_pos = None
        # Trova prima occorrenza non completata
        for bi, bar in enumerate(self._bars):
            for pi, p in enumerate(bar):
                sig = _signature(p)
                if sig[:3] == target[:3]:
                    if not self._done_map.get(bi, [False] * len(bar))[pi]:
                        self._active_pos = (bi, pi)
                        self.update()
                        return
        self.update()

    highlight_active_signature = set_active_signature
    mark_active_by_signature = set_active_signature
    set_active_piece_by_signature = set_active_signature

    def set_active_position(self, bar_idx: int, piece_idx: int):
        if 0 <= bar_idx < len(self._bars) and 0 <= piece_idx < len(self._bars[bar_idx]):
            if not self._done_map.get(bar_idx, [False] * len(self._bars[bar_idx]))[piece_idx]:
                self._active_pos = (bar_idx, piece_idx)
                self._active_sig = None
                self.update()

    set_active_piece_by_indices = set_active_position

    # ---------------- Paint ----------------
    def paintEvent(self, ev):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        try:
            W = self.width()
            x_start = LEFT_MARGIN_PX
            x_end = W - RIGHT_MARGIN_PX
            usable_width = max(100, x_end - x_start)

            y = 8
            font = QFont()
            font.setPointSize(7)
            painter.setFont(font)

            if not self._bars:
                painter.setPen(QPen(QColor("#555"), 1))
                painter.drawText(self.rect(), Qt.AlignCenter, "Nessun piano")
                return

            # Disegna ogni barra
            for bi, bar in enumerate(self._bars):
                # Lunghezza totale (stock) e scala
                stock = max(1.0, self._stock_mm)
                scale = usable_width / stock

                # Sfondo barra (linea base)
                bar_rect = QRectF(x_start - 4, y - 2, usable_width + 8, BAR_HEIGHT_PX + 4)
                painter.setPen(QPen(QColor("#d0d0d0"), 1))
                painter.setBrush(QColor("#fafafa"))
                painter.drawRoundedRect(bar_rect, 4, 4)

                # Titolo
                painter.setPen(QPen(QColor("#222"), 1))
                painter.drawText(QRectF(8, y, LEFT_MARGIN_PX - 12, BAR_HEIGHT_PX),
                                 Qt.AlignLeft | Qt.AlignVCenter,
                                 f"Barra {bi+1}")

                x_cursor = x_start

                # Disegna pezzi
                for pi, p in enumerate(bar):
                    ext_len = _ext_len(p)
                    off_sx_mm, off_dx_mm = _offsets_mm(p, self._thickness_mm)
                    off_sx_mm *= OFFSET_SCALE_BOOST
                    off_dx_mm *= OFFSET_SCALE_BOOST

                    piece_w = max(MIN_PIECE_WIDTH_PX, ext_len * scale)
                    # Offset in pixel
                    off_sx_px = off_sx_mm * scale if off_sx_mm > 0 else 0.0
                    off_dx_px = off_dx_mm * scale if off_dx_mm > 0 else 0.0
                    if off_sx_px > 0 and off_sx_px < OFFSET_MIN_PX: off_sx_px = OFFSET_MIN_PX
                    if off_dx_px > 0 and off_dx_px < OFFSET_MIN_PX: off_dx_px = OFFSET_MIN_PX

                    max_total_taper = piece_w * 0.65
                    taper_sum = off_sx_px + off_dx_px
                    if taper_sum > max_total_taper:
                        ratio = max_total_taper / (taper_sum + 1e-9)
                        off_sx_px *= ratio
                        off_dx_px *= ratio
                        taper_sum = off_sx_px + off_dx_px

                    bottom_w = max(4.0, piece_w - taper_sum)

                    top_left = QPointF(x_cursor, y)
                    top_right = QPointF(x_cursor + piece_w, y)
                    bottom_left = QPointF(x_cursor + off_sx_px, y + BAR_HEIGHT_PX)
                    bottom_right = QPointF(x_cursor + off_sx_px + bottom_w, y + BAR_HEIGHT_PX)

                    poly = QPolygonF([top_left, top_right, bottom_right, bottom_left])

                    done = self._done_map.get(bi, [False]*len(bar))[pi]
                    active = (self._active_pos == (bi, pi))

                    if done:
                        fill_col = QColor(115, 215, 115)
                        edge_col = QColor(70, 160, 70)
                        txt_col = QColor(255, 255, 255)
                    elif active:
                        fill_col = QColor(255, 195, 110)
                        edge_col = QColor(255, 140, 0)
                        txt_col = QColor(0, 0, 0)
                    else:
                        fill_col = QColor(205, 205, 205)
                        edge_col = QColor(150, 150, 150)
                        txt_col = QColor(0, 0, 0)

                    painter.setPen(Qt.NoPen)
                    painter.setBrush(fill_col)
                    painter.drawPolygon(poly)
                    painter.setPen(QPen(edge_col, 1))
                    painter.drawPolygon(poly)

                    # Testo lunghezza / angoli
                    sig = _signature(p)
                    text = f"{sig[0]:.0f}"
                    axi = int(round(sig[1])); adi = int(round(sig[2]))
                    if (axi != 0 or adi != 0) and piece_w > 55:
                        text += f"\n{axi}/{adi}"
                    painter.setPen(QPen(txt_col, 1))
                    painter.drawText(QRectF(x_cursor, y, piece_w, BAR_HEIGHT_PX),
                                     Qt.AlignCenter, text)

                    if active:
                        painter.setPen(QPen(QColor(255, 100, 0), 2))
                        painter.drawPolygon(poly)

                    x_cursor += piece_w

                # Residuo (se c'è spazio)
                residuo = max(0.0, self._stock_mm - sum(_ext_len(p) for p in bar))
                if residuo > 0:
                    rw = residuo * scale
                    if rw > 4:
                        r_rect = QRectF(x_cursor, y, rw, BAR_HEIGHT_PX)
                        warn = residuo <= self._warn_thr + 1e-6
                        painter.setPen(Qt.NoPen)
                        painter.setBrush(QColor(255, 210, 210) if warn else QColor(255, 230, 230))
                        painter.drawRect(r_rect)
                        painter.setPen(QPen(QColor(200, 90 if warn else 120, 90), 1))
                        painter.drawRect(r_rect)
                        painter.setPen(QPen(QColor(0, 0, 0), 1))
                        painter.drawText(r_rect, Qt.AlignCenter, f"{residuo:.0f}")

                y += BAR_HEIGHT_PX + BAR_VERTICAL_GAP

        except Exception as e:
            logger.error(f"Errore paintEvent PlanVisualizer: {e}", exc_info=True)

    # (Eventuale futura interazione)
    def mousePressEvent(self, ev):
        super().mousePressEvent(ev)


# Alias compatibilità
PlanVisualizer = PlanVisualizerWidget
