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

    - Barre su righe. (Richiesta: NESSUN sfondo speciale per la barra attiva.)
      Barre completate: sfondo grigio chiaro + bordo verde.
    - Pezzi come trapezi ribaltati: base maggiore in alto (punte), base minore in basso (base).
      Angoli preservati (offset orizzontali calcolati da tan(ang)*altezza), NON alterati.
    - Nessun accavallamento: gap tra pezzi = max(kerf_px, somma punte adiacenti + margine).
      Se necessario la scala orizzontale si riduce (solo lunghezze/gap, non gli angoli) così tutto rientra.
    - Dopo i pezzi, i “gap” vengono riempiti con il colore della barra per impedire che il colore dei pezzi
      invada visivamente la barra.
    - Colori pezzi alternati (blu / teal); pezzi tagliati in verde.
    - Stato “done” per indice con fallback per firma (se servisse).
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

        # Colori barra
        self._bg = QColor("#ffffff")
        self._bar_bg = QColor("#f0f2f5")        # sfondo normale (anche per barra attiva ora)
        self._bar_bg_active = QColor("#ffe7ba") # NON più usato (lasciato per retrocompatibilità)
        self._bar_bg_done = QColor("#e9edf2")
        self._bar_border_done = QColor("#27ae60")
        self._border = QColor("#3b4b5a")
        self._border_warn = QColor("#ff2d2d")

        # Colori pezzi
        self._piece_fg = QColor("#1976d2")
        self._piece_fg_alt = QColor("#26a69a")
        self._piece_done = QColor("#2ecc71")
        self._text = QColor("#2c3e50")

        # Stato “done”
        self._done_counts: Dict[Tuple[float, float, float], int] = {}
        self._done_by_index: Dict[int, List[bool]] = {}

        self.setMinimumSize(520, 220)

    def sizeHint(self) -> QSize:
        return QSize(760, 360)

    # ---------------- API ----------------

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
        self.reset_done()
        self.update()

    def reset_done(self):
        self._done_counts.clear()
        self._done_by_index = {i: [False] * len(b) for i, b in enumerate(self._bars)}
        self.update()

    def set_done_by_index(self, done_map: Dict[int, List[bool]]):
        self._done_by_index = {int(k): list(v) for k, v in (done_map or {}).items()}
        self.update()

    def mark_done_index(self, bar_idx: int, piece_idx: int):
        if bar_idx not in self._done_by_index and 0 <= bar_idx < len(self._bars):
            self._done_by_index[bar_idx] = [False] * len(self._bars[bar_idx])
        if bar_idx in self._done_by_index and 0 <= piece_idx < len(self._done_by_index[bar_idx]):
            self._done_by_index[bar_idx][piece_idx] = True
            self.update()

    def mark_done_by_signature(self,
                               length_mm: float,
                               ang_sx: float,
                               ang_dx: float,
                               len_tol: float = 0.01,
                               ang_tol: float = 0.05) -> bool:
        Lr = float(length_mm)
        Ax = float(ang_sx)
        Ad = float(ang_dx)
        for bi, bar in enumerate(self._bars):
            flags = self._done_by_index.get(bi, [])
            if not flags:
                flags = [False] * len(bar)
                self._done_by_index[bi] = flags
            for pi, p in enumerate(bar):
                if flags[pi]:
                    continue
                if (abs(float(p.get("len", 0.0)) - Lr) <= len_tol and
                    abs(float(p.get("ax", 0.0)) - Ax) <= ang_tol and
                    abs(float(p.get("ad", 0.0)) - Ad) <= ang_tol):
                    flags[pi] = True
                    self.update()
                    return True
        return False

    # ---------------- Helpers ----------------

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
        # Manteniamo per coerenza, anche se non usiamo highlight speciale.
        done_flags: List[bool] = []
        active_idx = -1
        for bi, bar in enumerate(self._bars):
            flags = self._done_by_index.get(bi, [])
            bar_all_done = (len(flags) == len(bar) and all(flags)) if bar else True
            done_flags.append(bar_all_done)
            if not bar_all_done and active_idx == -1:
                active_idx = bi
        return active_idx, done_flags

    def _precompute_active_bar_from_done_counts(self) -> Tuple[int, List[bool]]:
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
                if idx > done_quota:
                    bar_all_done = False
            done_flags.append(bar_all_done)
            if not bar_all_done and active_idx == -1:
                active_idx = bi
        return active_idx, done_flags

    def _required_width_px(self,
                           lengths_mm: List[float],
                           kerf_mm: List[float],
                           req_top_gap_px: List[float],
                           left_extra_px: float,
                           right_extra_px: float,
                           sx: float) -> float:
        total = left_extra_px + right_extra_px
        total += sum(L * sx for L in lengths_mm)
        for i in range(len(kerf_mm)):
            total += max(kerf_mm[i] * sx, req_top_gap_px[i])
        return total

    # ---------------- paint ----------------

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

        inner_pad_y = 2.0
        inner_pad_x = 4.0
        inner_w = (avail_w - 20) - inner_pad_x * 2
        base_scale_x = max(0.0001, inner_w / max(1.0, self._stock))

        if self._done_by_index:
            active_idx, bar_done_flags = self._precompute_active_bar_from_index_map()
        else:
            active_idx, bar_done_flags = self._precompute_active_bar_from_done_counts()

        font = p.font()
        font.setPointSizeF(9.0)
        p.setFont(font)

        encountered: Dict[Tuple[float, float, float], int] = {}

        for bi, bar in enumerate(self._bars):
            top = y0 + bi * (bar_h + vspace)
            bar_rect = QRectF(x0, top, avail_w - 20, bar_h)

            used_len_mm = bar_used_length(
                bar, self._kerf_base, self._ripasso_mm,
                self._reversible, self._thickness_mm,
                self._angle_tol, self._max_angle, self._max_factor
            )
            near_overflow = (self._stock - used_len_mm) <= self._warn_thr + 1e-6

            # Pen della barra (bordo verde se completata, rosso se near overflow)
            if bar_done_flags[bi]:
                pen_bar = QPen(self._bar_border_done)
            else:
                pen_bar = QPen(self._border_warn if near_overflow else self._border)
            pen_bar.setWidth(1)

            # Sfondo: NO highlight per barra attiva (richiesta utente)
            if bar_done_flags[bi]:
                bg = self._bar_bg_done
            else:
                bg = self._bar_bg

            p.setPen(pen_bar)
            p.fillRect(bar_rect, QBrush(bg))
            p.drawRect(bar_rect)

            piece_h = max(1.0, bar_h - inner_pad_y * 2)
            y_top = top + inner_pad_y
            y_bot = top + inner_pad_y + piece_h
            left_inner = x0 + inner_pad_x
            right_inner = x0 + bar_rect.width() - inner_pad_x
            bar_inner_w = right_inner - left_inner

            if not bar:
                p.setPen(QPen(self._border, 1))
                p.drawText(QRectF(x0 - 8, top - 1, 40, 16),
                           Qt.AlignRight | Qt.AlignVCenter, f"B{bi+1}")
                continue

            lengths_mm: List[float] = []
            off_l: List[float] = []
            off_r: List[float] = []
            kerf_mm: List[float] = []
            for i, piece in enumerate(bar):
                L = float(piece.get("len", 0.0))
                ax = float(piece.get("ax", 0.0))
                ad = float(piece.get("ad", 0.0))
                lengths_mm.append(max(0.0, L))
                ol = 0.0 if self._is_square_angle(ax) else self._offset_for_angle(piece_h, ax)
                orr = 0.0 if self._is_square_angle(ad) else self._offset_for_angle(piece_h, ad)
                off_l.append(ol)
                off_r.append(orr)
                if i < len(bar) - 1:
                    gap_mm, _, _, _ = joint_consumption(
                        piece, self._kerf_base, self._ripasso_mm,
                        self._reversible, self._thickness_mm,
                        self._angle_tol, self._max_angle, self._max_factor
                    )
                    kerf_mm.append(max(0.0, float(gap_mm)))

            margin_px = 1.0
            req_top_gap_px: List[float] = []
            for i in range(len(bar) - 1):
                req_top_gap_px.append(max(0.0, off_r[i] + off_l[i + 1] + margin_px))

            left_extra_px = max(0.0, off_l[0])
            right_extra_px = max(0.0, off_r[-1])

            # Binsearch scala
            low = 0.0
            high = base_scale_x
            for _ in range(24):
                mid = (low + high) * 0.5
                need = self._required_width_px(lengths_mm, kerf_mm, req_top_gap_px,
                                               left_extra_px, right_extra_px, mid)
                if need <= bar_inner_w:
                    low = mid
                else:
                    high = mid
            sx_bar = low

            base_left: List[float] = []
            base_right: List[float] = []
            top_lefts: List[float] = []
            top_rights: List[float] = []

            cursor_x = left_inner + left_extra_px
            for i in range(len(bar)):
                w = lengths_mm[i] * sx_bar
                bl = cursor_x
                br = cursor_x + w
                tl = bl - off_l[i]
                tr = br + off_r[i]
                base_left.append(bl)
                base_right.append(br)
                top_lefts.append(tl)
                top_rights.append(tr)
                if i < len(bar) - 1:
                    gap_px = max(kerf_mm[i] * sx_bar, req_top_gap_px[i])
                    cursor_x = br + gap_px

            # Disegna pezzi
            for pi, piece in enumerate(bar):
                L = lengths_mm[pi]
                bl = base_left[pi]; br = base_right[pi]
                tl = top_lefts[pi]; tr = top_rights[pi]

                poly = QPolygonF([
                    QPointF(tl, y_top),
                    QPointF(tr, y_top),
                    QPointF(br, y_bot),
                    QPointF(bl, y_bot),
                ])

                ax = float(piece.get("ax", 0.0))
                ad = float(piece.get("ad", 0.0))
                if bi in self._done_by_index and pi < len(self._done_by_index[bi]):
                    is_done = bool(self._done_by_index[bi][pi])
                else:
                    sig = (round(L, 2), round(ax, 1), round(ad, 1))
                    idx = encountered.get(sig, 0) + 1
                    encountered[sig] = idx
                    done_quota = self._done_counts.get(sig, 0)
                    is_done = idx <= done_quota

                fill = self._piece_done if is_done else (self._piece_fg if pi % 2 == 0 else self._piece_fg_alt)
                p.setPen(QPen(self._text, 1))
                p.setBrush(QBrush(fill))
                p.drawPolygon(poly)

                # Etichetta
                label = f"{L:.0f} mm"
                text_w = max(0.0, tr - tl)
                p.setPen(QPen(self._text))
                if text_w >= 46:
                    p.drawText(QRectF(tl, y_top, text_w, piece_h), Qt.AlignCenter, label)
                else:
                    p.drawText(QRectF(bl - 2, y_top - 12, max(46.0, text_w + 6), 12),
                               Qt.AlignLeft | Qt.AlignVCenter, label)

            # Riempimento gap con colore della barra (evita "invasione" colori pezzi)
            gap_brush = QBrush(bg)
            p.setPen(Qt.NoPen)
            for i in range(len(bar) - 1):
                gpoly = QPolygonF([
                    QPointF(top_rights[i],   y_top),
                    QPointF(top_lefts[i+1],  y_top),
                    QPointF(base_left[i+1],  y_bot),
                    QPointF(base_right[i],   y_bot),
                ])
                p.setBrush(gap_brush)
                p.drawPolygon(gpoly)

            # Etichetta barra
            p.setPen(QPen(self._border, 1))
            p.drawText(QRectF(x0 - 8, top - 1, 40, 16),
                       Qt.AlignRight | Qt.AlignVCenter, f"B{bi+1}")
