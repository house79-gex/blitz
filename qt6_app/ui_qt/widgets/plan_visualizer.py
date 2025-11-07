from __future__ import annotations
from typing import List, Dict, Tuple, Optional
import math

from PySide6.QtCore import Qt, QRectF, QPointF, QSize
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QPolygonF
from PySide6.QtWidgets import QWidget

from ui_qt.logic.refiner import (
    joint_consumption,
    bar_used_length
)

class PlanVisualizerWidget(QWidget):
    """
    Visualizzazione grafica del piano barre (Automatico):
    - Gap tra pezzi = consumo giunto (kerf effettivo dopo recupero + ripasso).
    - Bordi rossi per barre quasi overflow (usato > stock - warn_threshold).
    - Evidenzia pezzi tagliati (stato done).
    - SPECCHIO VERTICALE (invert_vertical): gli angoli di taglio sono rappresentati specularmente in verticale.
    - Supporto 'barra corrente' impostata dalla logica di Automatico (set_current_bar).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bars: List[List[Dict[str, float]]] = []
        self._stock: float = 6500.0

        # Parametri consumi
        self._kerf_base: float = 3.0
        self._ripasso_mm: float = 0.0
        self._reversible: bool = False
        self._thickness_mm: float = 0.0
        self._angle_tol: float = 0.5
        self._max_angle: float = 60.0
        self._max_factor: float = 2.0
        self._warn_thr: float = 0.5

        # Stili (barre più distinguibili dai pezzi)
        self._bg = QColor("#ffffff")
        self._bar_bg = QColor("#f5f7fa")         # sfondo barra default (molto chiaro)
        self._bar_bg_active = QColor("#ffe7ba")  # barra attiva (ambra chiaro)
        self._bar_bg_done = QColor("#eef0f2")    # barra completata
        self._border = QColor("#3b4b5a")
        self._border_warn = QColor("#ff2d2d")
        self._piece_fg = QColor("#1976d2")
        self._piece_fg_alt = QColor("#26a69a")
        self._piece_done = QColor("#9ccc65")
        self._text = QColor("#2c3e50")

        # Stato pezzi fatti e barra corrente
        self._done_counts: Dict[Tuple[float, float, float], int] = {}
        self._current_bar_index: Optional[int] = None  # se None → calcolo automatico

        # Rappresentazione speculare verticale degli angoli
        self._invert_vertical: bool = True

        self.setMinimumSize(480, 200)

    def sizeHint(self) -> QSize:
        return QSize(720, 360)

    # ------------ API ------------
    def set_data(self,
                 bars: List[List[Dict[str, float]]],
                 stock_mm: float,
                 kerf_base: float,
                 ripasso_mm: float,
                 reversible: bool,
                 thickness_mm: float,
                 angle_tol: float,
                 max_angle: float,
                 max_factor: float,
                 warn_threshold_mm: float):
        self._bars = bars or []
        self._stock = float(stock_mm)
        self._kerf_base = float(kerf_base)
        self._ripasso_mm = float(ripasso_mm)
        self._reversible = bool(reversible)
        self._thickness_mm = float(thickness_mm)
        self._angle_tol = float(angle_tol)
        self._max_angle = float(max_angle)
        self._max_factor = float(max_factor)
        self._warn_thr = float(warn_threshold_mm)
        self.update()

    def reset_done(self):
        self._done_counts.clear()
        self.update()

    def mark_done(self, length_mm: float, ang_sx: float, ang_dx: float):
        sig = (round(float(length_mm), 2), round(float(ang_sx), 1), round(float(ang_dx), 1))
        self._done_counts[sig] = self._done_counts.get(sig, 0) + 1
        self.update()

    def set_current_bar(self, index: Optional[int]):
        """Imposta la barra corrente (evidenziata). Se None, la deduco dai pezzi 'done'."""
        if index is None:
            self._current_bar_index = None
        else:
            try:
                idx = int(index)
                if 0 <= idx < len(self._bars):
                    self._current_bar_index = idx
                else:
                    self._current_bar_index = None
            except Exception:
                self._current_bar_index = None
        self.update()

    def set_invert_vertical(self, on: bool):
        """Abilita/disabilita l'inversione verticale nella rappresentazione degli angoli."""
        self._invert_vertical = bool(on)
        self.update()

    # ------------ Helpers ------------
    @staticmethod
    def _is_square_angle(a: float) -> bool:
        try:
            return abs(float(a)) <= 0.2
        except Exception:
            return True

    @staticmethod
    def _offset_for_angle(px_height: float, ang_deg: float) -> float:
        try:
            a = abs(float(ang_deg))
        except Exception:
            a = 0.0
        if a <= 0.2:
            return 0.0
        return math.tan(math.radians(a)) * px_height

    def _precompute_active_bar(self) -> Tuple[int, List[bool]]:
        """
        Deduco la barra attiva scorrendo le barre in ordine e “consumando” i pezzi fatti
        per firma (len, ax, ad) man mano (encountered).
        Ritorna (indice_barra_attiva, flags_barra_finita[]).
        """
        encountered: Dict[Tuple[float, float, float], int] = {}
        active_idx = -1
        done_flags: List[bool] = []
        for bi, bar in enumerate(self._bars):
            bar_all_done = True
            for piece in bar:
                L = float(piece.get("len", 0.0))
                ax = float(piece.get("ax", 0.0))
                ad = float(piece.get("ad", 0.0))
                sig = (round(L, 2), round(ax, 1), round(ad, 1))
                idx = encountered.get(sig, 0) + 1
                encountered[sig] = idx
                done_quota = self._done_counts.get(sig, 0)
                is_done = idx <= done_quota
                if not is_done:
                    bar_all_done = False
            done_flags.append(bar_all_done)
            if not bar_all_done and active_idx == -1:
                active_idx = bi
        return active_idx, done_flags

    # ------------ paintEvent ------------
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), self._bg)

        if not self._bars:
            return

        margin = 8
        x0 = margin
        y0 = margin
        avail_w = max(1, self.width() - margin * 2)
        avail_h = max(1, self.height() - margin * 2)

        n_bars = len(self._bars)
        if n_bars <= 0:
            return

        bar_h = 16.0
        vspace = 6.0
        total_h = n_bars * bar_h + (n_bars - 1) * vspace
        if total_h > avail_h:
            vspace = max(2.0, (avail_h - n_bars * bar_h) / max(1, n_bars - 1))
            total_h = n_bars * bar_h + (n_bars - 1) * vspace

        scale_x = (avail_w - 40) / max(1.0, self._stock)

        # Deduci barra attiva dai pezzi fatti, poi eventualmente sovrascrivi con quella imposta dall'esterno
        computed_active_idx, bar_done_flags = self._precompute_active_bar()
        active_idx = computed_active_idx if (self._current_bar_index is None) else min(max(self._current_bar_index, 0), n_bars - 1)

        pen_bar = QPen(self._border); pen_bar.setWidth(1)
        pen_warn = QPen(self._border_warn); pen_warn.setWidth(2)
        pen_piece_border = QPen(QColor("#2c3e50")); pen_piece_border.setWidth(1)

        font = p.font()
        font.setPointSizeF(9.0)
        p.setFont(font)

        encountered: Dict[Tuple[float, float, float], int] = {}

        for bi, bar in enumerate(self._bars):
            top = y0 + bi * (bar_h + vspace)
            bar_rect = QRectF(x0, top, avail_w - 20, bar_h)

            used_len = bar_used_length(
                bar, self._kerf_base, self._ripasso_mm,
                self._reversible, self._thickness_mm,
                self._angle_tol, self._max_angle, self._max_factor
            )
            near_overflow = (self._stock - used_len) <= self._warn_thr + 1e-6

            p.setPen(pen_warn if near_overflow else pen_bar)
            if bar_done_flags[bi]:
                bg = self._bar_bg_done
            elif bi == active_idx:
                bg = self._bar_bg_active
            else:
                bg = self._bar_bg
            p.fillRect(bar_rect, QBrush(bg))
            p.drawRect(bar_rect)

            inner_pad = 2.0
            piece_h = max(1.0, bar_h - inner_pad * 2)
            piece_y = top + inner_pad
            cursor_x = x0 + inner_pad + 2.0

            for pi, piece in enumerate(bar):
                L = float(piece.get("len", 0.0))
                ax = float(piece.get("ax", 0.0))
                ad = float(piece.get("ad", 0.0))
                w = max(1.0, L * scale_x)

                off_l = 0.0 if self._is_square_angle(ax) else self._offset_for_angle(piece_h, ax)
                off_r = 0.0 if self._is_square_angle(ad) else self._offset_for_angle(piece_h, ad)
                max_off = max(0.0, w * 0.49)
                off_l = min(off_l, max_off); off_r = min(off_r, max_off)

                x_left = cursor_x; x_right = cursor_x + w
                y_top = piece_y; y_bot = piece_y + piece_h

                if not self._invert_vertical:
                    # Angoli applicati sul bordo superiore (rappresentazione originale)
                    pts = [
                        QPointF(x_left + off_l,  y_top),  # top-left
                        QPointF(x_right - off_r, y_top),  # top-right
                        QPointF(x_right,         y_bot),  # bottom-right
                        QPointF(x_left,          y_bot),  # bottom-left
                    ]
                else:
                    # SPECCHIO VERTICALE: angoli applicati sul bordo inferiore
                    pts = [
                        QPointF(x_left,          y_top),                  # top-left
                        QPointF(x_right,         y_top),                  # top-right
                        QPointF(x_right - off_r, y_bot),                  # bottom-right (taglio DX)
                        QPointF(x_left + off_l,  y_bot),                  # bottom-left (taglio SX)
                    ]
                poly = QPolygonF(pts)

                sig = (round(L, 2), round(ax, 1), round(ad, 1))
                idx = encountered.get(sig, 0) + 1
                encountered[sig] = idx
                done_quota = self._done_counts.get(sig, 0)
                is_done = idx <= done_quota

                fill = self._piece_done if is_done else (self._piece_fg if pi % 2 == 0 else self._piece_fg_alt)
                p.setPen(pen_piece_border)
                p.setBrush(QBrush(fill))
                p.drawPolygon(poly)

                label = f"{L:.0f} mm"
                p.setPen(QPen(self._text))
                if w >= 46:
                    p.drawText(QRectF(x_left, y_top, w, piece_h), Qt.AlignCenter, label)
                else:
                    p.drawText(QRectF(x_left - 2, y_top - 12, max(46.0, w + 6), 12),
                               Qt.AlignLeft | Qt.AlignVCenter, label)

                if pi < len(bar) - 1:
                    gap_tot, _, _, _ = joint_consumption(
                        piece, self._kerf_base, self._ripasso_mm,
                        self._reversible, self._thickness_mm,
                        self._angle_tol, self._max_angle, self._max_factor
                    )
                    cursor_x += w + max(0.0, gap_tot * scale_x)
                else:
                    cursor_x += w

            p.setPen(pen_bar)
            p.drawText(QRectF(x0 - 8, top - 1, 36, 16),
                       Qt.AlignRight | Qt.AlignVCenter, f"B{bi+1}")
