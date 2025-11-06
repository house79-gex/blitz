from __future__ import annotations
from typing import List, Dict, Optional, Tuple

from PySide6.QtCore import Qt, QRectF, QPointF, QSize
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QPolygonF
from PySide6.QtWidgets import QWidget


class PlanVisualizerWidget(QWidget):
    """
    Visualizzazione grafica semplice del piano barre/pezzi.
    - Ogni barra è una riga orizzontale (rettangolo di sfondo).
    - Ogni pezzo è disegnato dentro la barra:
        * rettangolo se angoli = 0 (taglio a 90°),
        * trapezio se angoli > 0 (es. 45°).
    - All'interno di ciascun pezzo viene mostrata la sua lunghezza (mm).
    - Scala orizzontale proporzionale allo stock (stock_mm).
    - Non interattivo (solo viewer).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bars: List[List[Dict[str, float]]] = []
        self._stock: float = 6500.0
        self._kerf: float = 3.0
        self._bg = QColor("#ffffff")
        self._bar_bg = QColor("#ecf0f1")
        self._piece_fg = QColor("#1976d2")
        self._piece_fg_alt = QColor("#26a69a")
        self._text = QColor("#2c3e50")
        self._border = QColor("#3b4b5a")
        self.setMinimumSize(500, 260)

    def sizeHint(self) -> QSize:
        return QSize(900, 420)

    def set_data(self, bars: List[List[Dict[str, float]]], stock_mm: float, kerf_mm: float = 3.0):
        self._bars = bars or []
        try:
            self._stock = float(stock_mm) if stock_mm else 6500.0
        except Exception:
            self._stock = 6500.0
        try:
            self._kerf = float(kerf_mm) if kerf_mm else 3.0
        except Exception:
            self._kerf = 3.0
        self.update()

    @staticmethod
    def _angle_is_square(a: float) -> bool:
        # Angolo "quadrato": consideriamo 0±0.2° come 90° (taglio ortogonale)
        try:
            return abs(float(a)) <= 0.2
        except Exception:
            return True

    def _angle_offset_px(self, px_len: float, ang_deg: float, bar_h: float) -> float:
        """
        Offset orizzontale per simulare lo smusso in base all'angolo.
        Non è una proiezione geometrica reale; è una resa schematica e leggibile.
        """
        try:
            a = abs(float(ang_deg))
        except Exception:
            a = 0.0
        if self._angle_is_square(a):
            return 0.0
        # Limita l'effetto per non deformare troppo i pezzi corti:
        # max 18% della lunghezza, con tetto legato all'altezza barra
        return min(px_len * 0.18, (a / 45.0) * (bar_h * 0.45))

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), self._bg)

        if not self._bars:
            return

        margin = 10
        x0 = margin
        y0 = margin
        avail_w = max(1, self.width() - margin * 2)
        avail_h = max(1, self.height() - margin * 2)

        n_bars = len(self._bars)
        if n_bars <= 0:
            return

        # Layout verticale: ogni barra occupa una fascia, con spaziatura
        vspace = 12
        bar_h = max(26.0, (avail_h - (n_bars - 1) * vspace) / n_bars)

        # Scala orizzontale: stock -> (avail_w - 80) per lasciare label margini
        scale_x = (avail_w - 80) / max(1.0, self._stock)

        # Font
        font = p.font()
        font.setPointSizeF(9.5)
        p.setFont(font)

        # Penne
        pen_bar = QPen(self._border); pen_bar.setWidth(1)
        pen_piece_border = QPen(QColor("#2c3e50")); pen_piece_border.setWidth(1)

        for bi, bar in enumerate(self._bars):
            top = y0 + bi * (bar_h + vspace)
            # Rettangolo della barra
            bar_rect = QRectF(x0, top, avail_w - 40, bar_h)
            p.setPen(pen_bar)
            p.fillRect(bar_rect, QBrush(self._bar_bg))
            p.drawRect(bar_rect)

            # Disegna pezzi dentro la barra
            cursor_x = x0 + 8
            piece_h = bar_h - 12
            piece_y = top + 6

            for pi, piece in enumerate(bar):
                try:
                    L = float(piece.get("len", 0.0))
                    ax = float(piece.get("ax", 0.0))
                    ad = float(piece.get("ad", 0.0))
                except Exception:
                    continue

                w = max(1.0, L * scale_x)
                # Smussi ai lati in base agli angoli (0 => rettangolo)
                off_l = self._angle_offset_px(w, ax, piece_h)
                off_r = self._angle_offset_px(w, ad, piece_h)

                x_left = cursor_x
                x_right = cursor_x + w
                y_top = piece_y
                y_bot = piece_y + piece_h

                # Poligono del pezzo
                pts = [
                    QPointF(x_left + off_l, y_top),
                    QPointF(x_right - off_r, y_top),
                    QPointF(x_right, y_bot),
                    QPointF(x_left, y_bot),
                ]
                poly = QPolygonF(pts)

                # Riempimento alternato per leggibilità
                fill = self._piece_fg if (pi % 2 == 0) else self._piece_fg_alt
                p.setPen(pen_piece_border)
                p.setBrush(QBrush(fill))
                p.drawPolygon(poly)

                # Etichetta lunghezza dentro il pezzo (solo se c'è spazio)
                label = f"{L:.0f} mm"
                p.setPen(QPen(self._text))
                if w >= 48:
                    p.drawText(QRectF(x_left, y_top, w, piece_h), Qt.AlignCenter, label)
                else:
                    # Se troppo stretto, mostra il testo leggermente sopra
                    p.drawText(QRectF(x_left - 4, y_top - 14, max(48.0, w + 8), 14), Qt.AlignLeft | Qt.AlignVCenter, label)

                # Spostamento cursore di kerf + pezzo
                cursor_x += w + max(0.0, self._kerf * scale_x)

            # Etichetta barra a sinistra
            p.setPen(pen_bar)
            p.drawText(QRectF(x0 - 8, top - 2, 36, 16), Qt.AlignRight | Qt.AlignVCenter, f"B{bi+1}")
