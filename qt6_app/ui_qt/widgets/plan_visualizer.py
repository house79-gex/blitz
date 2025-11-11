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
    - Barre su righe. Barra attiva evidenziata (ambra). Barre completate con cornice verde + sfondo grigio chiaro.
    - Pezzi come trapezi ribaltati: base maggiore in alto, base minore in basso (angoli preservati, NON modificati).
      La lunghezza (base minore) viene scalata per entrare nella larghezza interna della barra.
      Gli angoli (offset superiori) NON vengono ridotti: se espandono fuori dai margini, il pezzo viene traslato
      orizzontalmente per rientrare, mantenendo la forma.
    - Colori pezzi alternati (blu / teal) per leggibilità, pezzi tagliati in verde.
    - Gap tra pezzi = kerf (joint_consumption) sul fondo + piccolo margine visivo.
    - Done deterministico per indice (fallback per firma se non presente).
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
        self._bar_bg = QColor("#f0f2f5")
        self._bar_bg_active = QColor("#ffe7ba")
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

    def mark_done_by_signature(self,
                               length_mm: float,
                               ang_sx: float,
                               ang_dx: float,
                               len_tol: float = 0.01,
                               ang_tol: float = 0.05) -> bool:
        """
        Marca il primo pezzo non fatto che matcha (L, ax, ad).
        Ritorna True se trovato.
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

        # Area interna disponibile (dove disegnare basi dei pezzi)
        inner_pad_y = 2.0
        inner_pad_x = 4.0  # margine orizzontale interno
        inner_w = (avail_w - 20) - inner_pad_x * 2
        scale_x = max(0.0001, inner_w / max(1.0, self._stock))

        # Determina barra attiva
        if self._done_by_index:
            computed_active_idx, bar_done_flags = self._precompute_active_bar_from_index_map()
        else:
            computed_active_idx, bar_done_flags = self._precompute_active_bar_from_done_counts()

        # Se non è stato forzato manualmente un indice, usa il calcolato (anche la prima barra verrà evidenziata)
        active_idx = computed_active_idx if (self._current_bar_index is None) else \
            min(max(self._current_bar_index, 0), n_bars - 1)

        font = p.font()
        font.setPointSizeF(9.0)
        p.setFont(font)

        encountered: Dict[Tuple[float, float, float], int] = {}

        for bi, bar in enumerate(self._bars):
            top = y0 + bi * (bar_h + vspace)
            bar_rect = QRectF(x0, top, avail_w - 20, bar_h)

            # Lunghezza usata (mm)
            used_len_mm = bar_used_length(
                bar, self._kerf_base, self._ripasso_mm,
                self._reversible, self._thickness_mm,
                self._angle_tol, self._max_angle, self._max_factor
            )
            near_overflow = (self._stock - used_len_mm) <= self._warn_thr + 1e-6

            # Pen della barra (se completata: bordo verde)
            if bar_done_flags[bi]:
                pen_bar = QPen(self._bar_border_done)
            else:
                pen_bar = QPen(self._border_warn if near_overflow else self._border)
            pen_bar.setWidth(1)

            # Sfondo barra base (non viene coperto dai pezzi)
            if bar_done_flags[bi]:
                bg = self._bar_bg_done
            elif bi == active_idx:
                bg = self._bar_bg_active
            else:
                bg = self._bar_bg

            p.setPen(pen_bar)
            p.fillRect(bar_rect, QBrush(bg))
            p.drawRect(bar_rect)

            # Geometria interna per pezzi
            piece_h = max(1.0, bar_h - inner_pad_y * 2)
            y_top = top + inner_pad_y            # base maggiore (alto)
            y_bot = top + inner_pad_y + piece_h  # base minore (basso)
            left_inner = x0 + inner_pad_x
            right_inner = x0 + bar_rect.width() - inner_pad_x

            cursor_x = left_inner
            margin_px = 1.0  # piccolo margine visivo sui gap

            for pi, piece in enumerate(bar):
                L = float(piece.get("len", 0.0))
                ax = float(piece.get("ax", 0.0))
                ad = float(piece.get("ad", 0.0))

                # Larghezza base minore (basso) scalata
                w = max(1.0, L * scale_x)

                # Offsets angolari (NON modificati / rifilati)
                ol = 0.0 if self._is_square_angle(ax) else self._offset_for_angle(piece_h, ax)
                orr = 0.0 if self._is_square_angle(ad) else self._offset_for_angle(piece_h, ad)

                # Limite ragionevole (visuale) proporzionale alla larghezza (non riduciamo oltre)
                max_off = max(0.0, w * 0.6)
                ol = min(ol, max_off)
                orr = min(orr, max_off)

                # Base inferiore
                base_left = cursor_x
                base_right = cursor_x + w

                # Posizione desiderata delle punte superiori
                top_left = base_left - ol
                top_right = base_right + orr

                # Se escono dai margini orizzontali della barra, TRASLIAMO il pezzo (non cambiamo gli angoli)
                shift = 0.0
                if top_left < left_inner:
                    shift = left_inner - top_left
                if top_right + shift > right_inner:
                    shift -= (top_right + shift - right_inner)

                base_left += shift
                base_right += shift
                top_left += shift
                top_right += shift

                # Clamp finale per sicurezza (non uscire col fondo)
                overflow_left = left_inner - base_left
                overflow_right = base_right - right_inner
                if overflow_left > 0:
                    base_left += overflow_left
                    base_right += overflow_left
                    top_left += overflow_left
                    top_right += overflow_left
                if overflow_right > 0:
                    base_left -= overflow_right
                    base_right -= overflow_right
                    top_left -= overflow_right
                    top_right -= overflow_right

                # Trapezio (base maggiore in alto)
                pts = [
                    QPointF(top_left,  y_top),   # top-left
                    QPointF(top_right, y_top),   # top-right
                    QPointF(base_right, y_bot),  # bottom-right
                    QPointF(base_left,  y_bot)   # bottom-left
                ]
                poly = QPolygonF(pts)

                # Stato done
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

                # Etichetta lunghezza (centro lato alto)
                label = f"{L:.0f} mm"
                text_w = top_right - top_left
                p.setPen(QPen(self._text))
                if text_w >= 46:
                    p.drawText(QRectF(top_left, y_top, text_w, piece_h),
                               Qt.AlignCenter, label)
                else:
                    p.drawText(QRectF(base_left - 2, y_top - 12,
                                      max(46.0, text_w + 6), 12),
                               Qt.AlignLeft | Qt.AlignVCenter, label)

                # Gap (kerf) solo sulla base minore (non modifichiamo angoli)
                if pi < len(bar) - 1:
                    gap_mm, _, _, _ = joint_consumption(
                        piece, self._kerf_base, self._ripasso_mm,
                        self._reversible, self._thickness_mm,
                        self._angle_tol, self._max_angle, self._max_factor
                    )
                    gap_px = max(0.0, gap_mm * scale_x) + margin_px
                    cursor_x = base_right + gap_px
                else:
                    cursor_x = base_right

                # Evita overflow base sul lato destro (clamp finale)
                if cursor_x > right_inner:
                    cursor_x = right_inner

            # Etichetta barra (a sinistra)
            lab_rect = QRectF(x0 - 8, top - 1, 40, 16)
            p.setPen(QPen(self._border, 1))
            p.drawText(lab_rect, Qt.AlignRight | Qt.AlignVCenter, f"B{bi+1}")
