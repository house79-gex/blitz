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
    Visualizzazione grafica del piano di ottimizzazione:
    - Barre orizzontali (una riga per barra).
    - Pezzi come trapezi: base MINORE in basso, base MAGGIORE in alto (angoli che “aprono” verso l’alto).
    - Gap fra pezzi calcolato dal consumo giunto (joint_consumption).
    - Evidenzia:
        * pezzo corrente (bordo arancione)
        * pezzi tagliati (riempimento verde)
        * barra attiva (sfondo ambra chiaro)
    - Supporta marcatura pezzi per indice (done_by_index) e marcatura per firma (mark_done_by_signature).
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

        # Stili
        self._bg = QColor("#ffffff")
        self._bar_bg = QColor("#f5f7fa")
        self._bar_bg_active = QColor("#ffe7ba")
        self._bar_bg_done = QColor("#eef0f2")
        self._border = QColor("#3b4b5a")
        self._border_warn = QColor("#ff2d2d")

        self._piece_fg = QColor("#1976d2")
        self._piece_fg_alt = QColor("#26a69a")
        self._piece_done = QColor("#2ecc71")
        self._piece_current = QColor("#ffcc80")
        self._piece_current_border = QColor("#ff9800")
        self._text = QColor("#2c3e50")

        # Stato
        self._done_by_index: Dict[int, List[bool]] = {}
        self._current_bar_index: Optional[int] = None
        self._current_piece_index: Optional[int] = None

        self.setMinimumSize(520, 220)

    def sizeHint(self) -> QSize:
        return QSize(760, 360)

    # ---------- API ----------
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
        # Reset stato pezzi (mantieni eventuali done se dimensioni uguali? -> reset completo per coerenza)
        self.reset_done()
        self.update()

    def reset_done(self):
        self._done_by_index = {i: [False]*len(b) for i, b in enumerate(self._bars)}
        self._current_bar_index = None
        self._current_piece_index = None
        self.update()

    def set_current_bar(self, index: Optional[int]):
        if index is None or index < 0 or index >= len(self._bars):
            self._current_bar_index = None
        else:
            self._current_bar_index = int(index)
        self.update()

    def set_current_piece(self, bar_idx: int, piece_idx: int):
        if bar_idx < 0 or bar_idx >= len(self._bars):
            self._current_piece_index = None
            self._current_bar_index = None
            self.update()
            return
        bar = self._bars[bar_idx]
        if piece_idx < 0 or piece_idx >= len(bar):
            self._current_piece_index = None
            self._current_bar_index = bar_idx
            self.update()
            return
        self._current_bar_index = bar_idx
        self._current_piece_index = piece_idx
        self.update()

    def mark_done_index(self, bar_idx: int, piece_idx: int):
        if bar_idx in self._done_by_index and 0 <= piece_idx < len(self._done_by_index[bar_idx]):
            self._done_by_index[bar_idx][piece_idx] = True
            # Se era il pezzo corrente lo deseleziono (si avanzerà altrove)
            if self._current_bar_index == bar_idx and self._current_piece_index == piece_idx:
                self._current_piece_index = None
            self.update()

    def mark_done_by_signature(self, length_mm: float, ang_sx: float, ang_dx: float):
        # Trova il primo pezzo non done che matcha firma
        Lr = round(float(length_mm), 2)
        Ax = round(float(ang_sx), 2)
        Ad = round(float(ang_dx), 2)
        for bi, bar in enumerate(self._bars):
            flags = self._done_by_index.get(bi, [])
            for pi, p in enumerate(bar):
                if flags and flags[pi]:
                    continue
                if abs(p["len"] - Lr) <= 0.01 and abs(p["ax"] - Ax) <= 0.05 and abs(p["ad"] - Ad) <= 0.05:
                    self.mark_done_index(bi, pi)
                    return

    def set_done_by_index(self, done_map: Dict[int, List[bool]]):
        self._done_by_index = {int(k): list(v) for k, v in (done_map or {}).items()}
        self.update()

    # ---------- Helpers ----------
    @staticmethod
    def _is_square_angle(a: float) -> bool:
        try:
            return abs(float(a)) <= 0.2
        except Exception:
            return True

    @staticmethod
    def _offset_for_angle(px_height: float, ang_deg: float) -> float:
        # offset orizzontale proporzionale all'angolo (proiezione verso l'esterno in alto)
        try:
            a = abs(float(ang_deg))
        except Exception:
            a = 0.0
        if a <= 0.2:
            return 0.0
        return math.tan(math.radians(a)) * px_height

    def _bar_all_done(self, bar_idx: int) -> bool:
        if bar_idx not in self._done_by_index:
            return False
        flags = self._done_by_index[bar_idx]
        return len(flags) > 0 and all(flags)

    # ---------- paint ----------
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

        bar_h = 20.0
        vspace = 8.0
        total_h = n_bars * bar_h + (n_bars - 1) * vspace
        if total_h > avail_h:
            vspace = max(3.0, (avail_h - n_bars * bar_h) / max(1, n_bars - 1))
            total_h = n_bars * bar_h + (n_bars - 1) * vspace

        scale_x = (avail_w - 40) / max(1.0, self._stock)

        pen_bar = QPen(self._border); pen_bar.setWidth(1)
        pen_warn = QPen(self._border_warn); pen_warn.setWidth(2)
        pen_piece_border = QPen(QColor("#2c3e50")); pen_piece_border.setWidth(1)
        pen_piece_current = QPen(self._piece_current_border); pen_piece_current.setWidth(2)

        font = p.font()
        font.setPointSizeF(9.0)
        p.setFont(font)

        for bi, bar in enumerate(self._bars):
            top = y0 + bi * (bar_h + vspace)
            bar_rect = QRectF(x0, top, avail_w - 20, bar_h)

            used_len = bar_used_length(
                bar, self._kerf_base, self._ripasso_mm,
                self._reversible, self._thickness_mm,
                self._angle_tol, self._max_angle, self._max_factor
            )
            near_overflow = (self._stock - used_len) <= self._warn_thr + 1e-6

            # Sfondo barra
            p.setPen(pen_warn if near_overflow else pen_bar)
            if self._bar_all_done(bi):
                bg = self._bar_bg_done
            elif bi == self._current_bar_index:
                bg = self._bar_bg_active
            else:
                bg = self._bar_bg
            p.fillRect(bar_rect, QBrush(bg))
            p.drawRect(bar_rect)

            inner_pad = 2.0
            piece_h = max(1.0, bar_h - inner_pad * 2)
            piece_y_bottom = top + inner_pad + piece_h   # y della base maggiore (in alto)
            piece_y_top = top + inner_pad                # y della base minore (in basso)
            # NOTA: qui definiamo "alto" visivo come y minore (coordinate schermo), ma la base maggiore deve stare VISIVAMENTE più in alto:
            # Quindi: top (y_min) = base maggiore? -> Ci adeguiamo alla richiesta 'base minore in basso, maggiore in alto':
            # Implementiamo trapezio invertendo le denominazioni: y_top < y_bottom.
            # Gestione: base minore = line a y_bottom; base maggiore = line a y_top.

            # Correzione semantica: ridisegniamo:
            y_base_maggiore = piece_y_top
            y_base_minore = piece_y_bottom

            cursor_x = x0 + inner_pad + 2.0

            for pi, piece in enumerate(bar):
                L = float(piece.get("len", 0.0))
                ax = float(piece.get("ax", 0.0))
                ad = float(piece.get("ad", 0.0))
                w_bottom = max(6.0, L * scale_x)  # larghezza della base minore (in basso)
                off_l = 0.0 if self._is_square_angle(ax) else self._offset_for_angle(piece_h, ax)
                off_r = 0.0 if self._is_square_angle(ad) else self._offset_for_angle(piece_h, ad)
                max_off = max(0.0, w_bottom * 0.45)
                off_l = min(off_l, max_off)
                off_r = min(off_r, max_off)

                # Base minore (in basso) centrata sotto la base maggiore?
                # Manteniamo allineamento a sinistra per coerenza con spaziatura: la base minore parte da cursor_x
                x_left_bottom = cursor_x
                x_right_bottom = cursor_x + w_bottom

                # Base maggiore (in alto) espansa verso sx e dx
                x_left_top = x_left_bottom - off_l
                x_right_top = x_right_bottom + off_r

                pts = [
                    QPointF(x_left_top,  y_base_maggiore),  # top-left (base maggiore)
                    QPointF(x_right_top, y_base_maggiore),  # top-right
                    QPointF(x_right_bottom, y_base_minore), # bottom-right (base minore)
                    QPointF(x_left_bottom,  y_base_minore)  # bottom-left
                ]
                poly = QPolygonF(pts)

                # Stato done corrente
                is_done = bool(self._done_by_index.get(bi, [False]*len(bar))[pi])
                is_current = (bi == self._current_bar_index and pi == self._current_piece_index)

                fill_color = self._piece_done if is_done else (self._piece_current if is_current else (self._piece_fg if pi % 2 == 0 else self._piece_fg_alt))
                p.setPen(pen_piece_current if is_current else pen_piece_border)
                p.setBrush(QBrush(fill_color))
                p.drawPolygon(poly)

                # Etichetta lunghezza
                label = f"{L:.0f} mm"
                p.setPen(QPen(self._text))
                text_w = x_right_top - x_left_top
                if text_w >= 46:
                    p.drawText(QRectF(x_left_top, y_base_maggiore, text_w, piece_h),
                               Qt.AlignCenter, label)
                else:
                    p.drawText(QRectF(x_left_bottom - 2, y_base_maggiore - 12,
                                      max(46.0, text_w + 6), 12),
                               Qt.AlignLeft | Qt.AlignVCenter, label)

                # Avanza cursore considerando consumo giunto (sul w_bottom)
                if pi < len(bar) - 1:
                    gap_tot, _, _, _ = joint_consumption(
                        piece, self._kerf_base, self._ripasso_mm,
                        self._reversible, self._thickness_mm,
                        self._angle_tol, self._max_angle, self._max_factor
                    )
                    cursor_x += w_bottom + max(0.0, gap_tot * scale_x)
                else:
                    cursor_x += w_bottom

            # Etichetta barra
            p.setPen(pen_bar)
            p.drawText(QRectF(x0 - 8, top - 1, 40, 16),
                       Qt.AlignRight | Qt.AlignVCenter, f"B{bi+1}")
