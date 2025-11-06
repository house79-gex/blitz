from __future__ import annotations
from typing import List, Dict, Optional, Tuple

from PySide6.QtCore import Qt, QRectF, QPointF, QSize
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont
from PySide6.QtWidgets import QWidget


class PlanVisualizerWidget(QWidget):
    """
    Visualizzazione grafica semplice del piano barre/pezzi.
    - Ogni barra è una riga orizzontale.
    - Ogni pezzo è un rettangolo; se gli angoli != 0, gli estremi sono inclinati (trapezio).
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
        self.setMinimumSize(400, 220)

    def sizeHint(self) -> QSize:
        return QSize(720, 360)

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

    def _angle_offset_px(self, px_len: float, ang_deg: float, bar_h: float) -> float:
        """
        Offset orizzontale per simulare lo smusso in base all'angolo.
        Non è geometria reale: è una resa schematica limitata.
        """
        try:
            a = abs(float(ang_deg))
        except Exception:
            a = 0.0
        if a <= 0.01:
            return 0.0
        # max 20% della lunghezza pezzo; scala sull'altezza barra
        return min(px_len * 0.20, (a / 45.0) * (bar_h * 0.45))

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

        # Layout verticale: ogni barra occupa fascia con spaziatura
        vspace = 10
        bar_h = max(20.0, (avail_h - (n_bars - 1) * vspace) / n_bars)

        # Scala orizzontale: stock -> avail_w
        scale_x = (avail_w - 40) / max(1.0, self._stock)

        font = p.font()
        font.setPointSizeF(9.0)
        p.setFont(font)

        pen_bar = QPen(self._border)
        pen_bar.setWidth(1)
        p.setPen(pen_bar)

        for bi, bar in enumerate(self._bars):
            top = y0 + bi * (bar_h + vspace)
            # Disegna sfondo barra
            bar_rect = QRectF(x0, top, avail_w - 20, bar_h)
            p.fillRect(bar_rect, QBrush(self._bar_bg))
            p.drawRect(bar_rect)

            # Disegna pezzi in sequenza
            cursor_x = x0 + 6
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
                # Smussi
                off_l = self._angle_offset_px(w, ax, piece_h)
                off_r = self._angle_offset_px(w, ad, piece_h)

                # Poligono trapezoidale
                x_left = cursor_x
                x_right = cursor_x + w
                y_top = piece_y
                y_bot = piece_y + piece_h

                pts = [
                    QPointF(x_left + off_l, y_top),
                    QPointF(x_right - off_r, y_top),
                    QPointF(x_right, y_bot),
                    QPointF(x_left, y_bot),
                ]
                p.setBrush(QBrush(self._piece_fg if (pi % 2 == 0) else self._piece_fg_alt))
                p.drawPolygon(*pts)

                # Etichetta lunghezza
                label = f"{L:.0f} mm"
                p.setPen(QPen(self._text))
                p.drawText(QRectF(x_left, y_top, w, piece_h), Qt.AlignCenter, label)

                cursor_x += w + max(0.0, self._kerf * scale_x)

            # Testo barra a sinistra
            p.setPen(QPen(self._border))
            p.drawText(QRectF(x0 - 6, top - 2, 40, 16), Qt.AlignRight | Qt.AlignVCenter, f"B{bi+1}")
