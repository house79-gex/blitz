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
    Visualizzazione grafica del piano (Automatico):
    - Barre in righe con sfondi chiari ben distinti dai pezzi.
    - Pezzi come trapezi ribaltati: base maggiore in alto, base minore in basso.
    - Gap tra pezzi = max(consumo giunto, somma punte superiori) per evitare accavallamenti.
    - Evidenziazione: pezzi tagliati in verde; pezzi non tagliati con colori alternati.
    - Barra attiva in ambra chiaro; barra completata in grigio chiaro.
    - Stato “done” deterministico per indice (con fallback per firma se serve).
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

        # Stili: sfondi barra neutri ben distinti dai pezzi
        self._bg = QColor("#ffffff")
        self._bar_bg = QColor("#f0f2f5")        # normale
        self._bar_bg_active = QColor("#fff2cc") # attiva
        self._bar_bg_done = QColor("#e9edf2")   # completata
        self._border = QColor("#3b4b5a")
        self._border_warn = QColor("#ff2d2d")

        # Pezzi: alternanza per leggibilità
        self._piece_fg = QColor("#1976d2")      # blu
        self._piece_fg_alt = QColor("#26a69a")  # teal
        self._piece_done = QColor("#2ecc71")    # verde fatto
        self._text = QColor("#2c3e50")

        # Stato
        self._done_counts: Dict[Tuple[float, float, float], int] = {}  # fallback legacy
        self._done_by_index: Dict[int, List[bool]] = {}                # bar_idx -> flags
        self._current_bar_index: Optional[int] = None

        self.setMinimumSize(520, 220)

    def sizeHint(self) -> QSize:
        return QSize(760, 360)

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
        # reset stato “done”
        self.reset_done()
        self.update()

    def reset_done(self):
        self._done_counts.clear()
        self._done_by_index = {i: [False]*len(b) for i, b in enumerate(self._bars)}
        self._current_bar_index = None
        self.update()

    def set_done_by_index(self, done_map: Dict[int, List[bool]]):
        self._done_by_index = {int(k): list(v) for k, v in (done_map or {}).items()}
        self.update()

    def set_current_bar(self, index: Optional[int]):
        if index is None or index < 0 or index >= len(self._bars):
            self._current_bar_index = None
        else:
            self._current_bar_index = int(index)
        self.update()

    def mark_done_index(self, bar_idx: int, piece_idx: int):
        if bar_idx not in self._done_by_index and 0 <= bar_idx < len(self._bars):
            self._done_by_index[bar_idx] = [False]*len(self._bars[bar_idx])
        if bar_idx in self._done_by_index and 0 <= piece_idx < len(self._done_by_index[bar_idx]):
            self._done_by_index[bar_idx][piece_idx] = True
            self.update()

    def mark_done_by_signature(self, length_mm: float, ang_sx: float, ang_dx: float,
                               len_tol: float = 0.01, ang_tol: float = 0.05) -> bool:
        """
        Marca il primo pezzo non ancora fatto che matcha la firma (L, ax, ad) con tolleranze.
        Ritorna True se trovato e marcato, altrimenti False.
        """
        Lr = float(length_mm)
        Ax = float(ang_sx)
        Ad = float(ang_dx)
        for bi, bar in enumerate(self._bars):
            flags = self._done_by_index.get(bi, [])
            if not flags:
                flags = [False]*len(bar)
                self._done_by_index[bi] = flags
            for pi, p in enumerate(bar):
                if flags[pi]:
                    continue
                if (abs(float(p.get("len", 0.0)) - Lr) <= len_tol and
                    abs(float(p.get("ax", 0.0)) - Ax) <= ang_tol and
                    abs(float(p.get("ad", 0.0)) - Ad) <= ang_tol):
                    flags[pi] = True
                    # aggiorna barra corrente per evidenza
                    self._current_bar_index = bi
                    self.update()
                    return True
        return False

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

    def _precompute_active_bar_from_index_map(self) -> Tuple[int, List[bool]]:
        done_flags: List[bool] = []
        active_idx = -1
        for bi, bar in enumerate(self._bars):
            flags = self._done_by_index.get(bi, [])
            bar_all_done = (len(flags) >= len(bar)) and all(bool(x) for x in flags[:len(bar)])
            done_flags.append(bar_all_done)
            if not bar_all_done and active_idx == -1:
                active_idx = bi
        return active_idx, done_flags

    def _precompute_active_bar_from_done_counts(self) -> Tuple[int, List[bool]]:
        # Fallback legacy (se non usi done_by_index)
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

    # ------------ paint ------------
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

        if self._done_by_index:
            computed_active_idx, bar_done_flags = self._precompute_active_bar_from_index_map()
        else:
            computed_active_idx, bar_done_flags = self._precompute_active_bar_from_done_counts()
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

            # Sfondo barra
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
            y_top = top + inner_pad            # lato lungo (base maggiore) in alto
            y_bot = top + inner_pad + piece_h  # lato corto (base minore) in basso
            cursor_x = x0 + inner_pad + 2.0

            for pi, piece in enumerate(bar):
                L = float(piece.get("len", 0.0))
                ax = float(piece.get("ax", 0.0))
                ad = float(piece.get("ad", 0.0))
                w = max(1.0, L * scale_x)

                off_l = 0.0 if self._is_square_angle(ax) else self._offset_for_angle(piece_h, ax)
                off_r = 0.0 if self._is_square_angle(ad) else self._offset_for_angle(piece_h, ad)
                max_off = max(0.0, w * 0.45)
                off_l = min(off_l, max_off); off_r = min(off_r, max_off)

                x_left = cursor_x; x_right = cursor_x + w

                # Trapezio ribaltato: espansione sul lato alto
                pts = [
                    QPointF(x_left  - off_l, y_top),  # top-left (base maggiore)
                    QPointF(x_right + off_r, y_top),  # top-right
                    QPointF(x_right,         y_bot),  # bottom-right (base minore)
                    QPointF(x_left,          y_bot),  # bottom-left
                ]
                poly = QPolygonF(pts)

                # Stato done (preferisci per indice)
                if bi in self._done_by_index and pi < len(self._done_by_index[bi]):
                    is_done = bool(self._done_by_index[bi][pi])
                else:
                    sig = (round(L, 2), round(ax, 1), round(ad, 1))
                    idx = encountered.get(sig, 0) + 1
                    encountered[sig] = idx
                    done_quota = self._done_counts.get(sig, 0)
                    is_done = idx <= done_quota

                fill = self._piece_done if is_done else (self._piece_fg if pi % 2 == 0 else self._piece_fg_alt)
                p.setPen(pen_piece_border)
                p.setBrush(QBrush(fill))
                p.drawPolygon(poly)

                # Etichetta
                label = f"{L:.0f} mm"
                p.setPen(QPen(self._text))
                text_w = (x_right + off_r) - (x_left - off_l)
                if text_w >= 46:
                    p.drawText(QRectF(x_left - off_l, y_top, text_w, piece_h), Qt.AlignCenter, label)
                else:
                    p.drawText(QRectF(x_left - 2, y_top - 12, max(46.0, text_w + 6), 12),
                               Qt.AlignLeft | Qt.AlignVCenter, label)

                # Avanzamento cursore con gap sicuro (no accavallamenti)
                if pi < len(bar) - 1:
                    gap_tot, _, _, _ = joint_consumption(
                        piece, self._kerf_base, self._ripasso_mm,
                        self._reversible, self._thickness_mm,
                        self._angle_tol, self._max_angle, self._max_factor
                    )
                    gap_px_bottom = max(0.0, gap_tot * scale_x)
                    nxt = bar[pi + 1]
                    nxt_ax = float(nxt.get("ax", 0.0))
                    nxt_off_l = 0.0 if self._is_square_angle(nxt_ax) else self._offset_for_angle(piece_h, nxt_ax)
                    nxt_w = max(1.0, float(nxt.get("len", 0.0)) * scale_x)
                    nxt_off_l = min(nxt_off_l, max(0.0, nxt_w * 0.45))
                    gap_px_vertices = off_r + nxt_off_l
                    req_gap_px = max(gap_px_bottom, gap_px_vertices) + 1.0  # margine visivo
                    cursor_x += w + req_gap_px
                else:
                    cursor_x += w

            p.setPen(pen_bar)
            p.drawText(QRectF(x0 - 8, top - 1, 40, 16),
                       Qt.AlignRight | Qt.AlignVCenter, f"B{bi+1}")
