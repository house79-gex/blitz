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
    - Barre in righe con sfondi ben distinti dai pezzi.
    - Pezzi come trapezi ribaltati: base maggiore in alto, base minore in basso.
    - Nessun accavallamento: le punte superiori vengono "rifilate" per stare nel kerf visivo.
    - La lunghezza grafica si adatta alla barra: niente overflow del bordo barra.
    - Sfondo barra:
        * tratto "usato" (sotto i pezzi) evidenziato con un colore
        * tratto "residuo" evidenziato con un altro colore
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

        # Stili (sfondi barra ben distinti dai pezzi)
        self._bg = QColor("#ffffff")
        self._bar_bg = QColor("#f0f2f5")        # sfondo barra base
        self._bar_bg_active = QColor("#fff2cc") # barra attiva
        self._bar_bg_done = QColor("#e9edf2")   # barra completata
        self._bar_used_bg = QColor("#eaf4ff")   # tratto barra "usata" (sotto i pezzi)
        self._bar_res_bg = QColor("#ffeaea")    # tratto barra "residuo" finale
        self._border = QColor("#3b4b5a")
        self._border_warn = QColor("#ff2d2d")

        # Pezzi: alternanza per leggibilità + done in verde
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

        # Larghezza utile interna della barra, per scalare su stock
        # NB: scalatura su stock garantisce che le basi (sul fondo) stiano nel rettangolo barra.
        inner_pad = 2.0
        inner_hpad = 2.0
        bar_inner_w = (avail_w - 20) - inner_pad * 2 - inner_hpad * 2
        scale_x = max(0.0001, bar_inner_w / max(1.0, self._stock))

        # Active bar & done flags
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

            # Bordo/warn residuo
            used_len_mm = bar_used_length(
                bar, self._kerf_base, self._ripasso_mm,
                self._reversible, self._thickness_mm,
                self._angle_tol, self._max_angle, self._max_factor
            )
            near_overflow = (self._stock - used_len_mm) <= self._warn_thr + 1e-6

            p.setPen(pen_warn if near_overflow else pen_bar)
            # Sfondo barra base (chiaro)
            if bar_done_flags[bi]:
                bg = self._bar_bg_done
            elif bi == active_idx:
                bg = self._bar_bg_active
            else:
                bg = self._bar_bg
            p.fillRect(bar_rect, QBrush(bg))
            p.drawRect(bar_rect)

            # Geometria interna barra
            piece_h = max(1.0, bar_h - inner_pad * 2)
            y_top = top + inner_pad            # lato lungo (base maggiore) in alto
            y_bot = top + inner_pad + piece_h  # lato corto (base minore) in basso
            bar_left_inner = x0 + inner_pad + inner_hpad
            bar_right_inner = x0 + bar_rect.width() - inner_pad - inner_hpad

            # Pre-pass: calcolo w/off e gap bottom, e "rifilo" le punte per farle stare nel kerf (no accavallamento)
            n = len(bar)
            widths: List[float] = []
            off_l: List[float] = []
            off_r: List[float] = []
            kerf_gap_px: List[float] = [0.0] * max(0, n - 1)
            # calcolo base
            for i, piece in enumerate(bar):
                L = float(piece.get("len", 0.0))
                ax = float(piece.get("ax", 0.0))
                ad = float(piece.get("ad", 0.0))
                w = max(1.0, L * scale_x)
                widths.append(w)
                ol = 0.0 if self._is_square_angle(ax) else self._offset_for_angle(piece_h, ax)
                orr = 0.0 if self._is_square_angle(ad) else self._offset_for_angle(piece_h, ad)
                # limita offset rispetto alla larghezza per evitare esagerazioni
                max_off = max(0.0, w * 0.45)
                off_l.append(min(ol, max_off))
                off_r.append(min(orr, max_off))
                if i < n - 1:
                    gap_mm, _, _, _ = joint_consumption(
                        piece, self._kerf_base, self._ripasso_mm,
                        self._reversible, self._thickness_mm,
                        self._angle_tol, self._max_angle, self._max_factor
                    )
                    kerf_gap_px[i] = max(0.0, gap_mm * scale_x)

            # Rifilatura punte per farle stare nel kerf visivo (+1px di margine)
            margin_px = 1.0
            for i in range(n - 1):
                need = off_r[i] + off_l[i + 1]
                have = kerf_gap_px[i] + margin_px
                if need > have and need > 0:
                    f = have / need
                    off_r[i] *= f
                    off_l[i + 1] *= f

            # Calcolo fine "usato" in pixel (sulla base inferiore) per evidenziare tratto usato vs residuo
            used_end_x = bar_left_inner
            for i in range(n):
                used_end_x += widths[i]
                if i < n - 1:
                    used_end_x += (kerf_gap_px[i] + margin_px)
            used_end_x = min(used_end_x, bar_right_inner)

            # Sottofondo usato/residuo (diverso dal colore pezzi)
            if used_end_x > bar_left_inner:
                used_rect = QRectF(bar_left_inner, top + inner_pad, used_end_x - bar_left_inner, piece_h)
                p.fillRect(used_rect, QBrush(self._bar_used_bg))
            if used_end_x < bar_right_inner:
                res_rect = QRectF(used_end_x, top + inner_pad, bar_right_inner - used_end_x, piece_h)
                p.fillRect(res_rect, QBrush(self._bar_res_bg))

            # Disegno pezzi
            cursor_x = bar_left_inner
            for pi, piece in enumerate(bar):
                L = float(piece.get("len", 0.0))
                w = widths[pi]
                ol = off_l[pi]
                orr = off_r[pi]

                x_left = cursor_x
                x_right = cursor_x + w

                # Clamping offset per non uscire dalla barra sul lato alto
                if ol > 0:
                    ol = min(ol, max(0.0, x_left - bar_left_inner))
                if orr > 0:
                    orr = min(orr, max(0.0, bar_right_inner - x_right))
                # Aggiorna eventuali cambi (evita overflow su margini)
                off_l[pi] = ol
                off_r[pi] = orr

                # Trapezio ribaltato: espansione sul lato alto
                pts = [
                    QPointF(x_left  - ol, y_top),  # top-left (base maggiore)
                    QPointF(x_right + orr, y_top), # top-right
                    QPointF(x_right,        y_bot),# bottom-right (base minore)
                    QPointF(x_left,         y_bot) # bottom-left
                ]
                poly = QPolygonF(pts)

                # Stato done (preferisci per indice)
                if bi in self._done_by_index and pi < len(self._done_by_index[bi]):
                    is_done = bool(self._done_by_index[bi][pi])
                else:
                    ax = float(piece.get("ax", 0.0))
                    ad = float(piece.get("ad", 0.0))
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
                text_w = (x_right + orr) - (x_left - ol)
                if text_w >= 46:
                    p.drawText(QRectF(x_left - ol, y_top, text_w, piece_h), Qt.AlignCenter, label)
                else:
                    p.drawText(QRectF(x_left - 2, y_top - 12, max(46.0, text_w + 6), 12),
                               Qt.AlignLeft | Qt.AlignVCenter, label)

                # Avanzamento cursore: SOLO kerf bottom (+margine) per mantenere scala e non uscire
                if pi < len(bar) - 1:
                    cursor_x += w + (kerf_gap_px[pi] + margin_px)
                else:
                    cursor_x += w

            # Etichetta barra
            p.setPen(pen_bar)
            p.drawText(QRectF(x0 - 8, top - 1, 40, 16),
                       Qt.AlignRight | Qt.AlignVCenter, f"B{bi+1}")
