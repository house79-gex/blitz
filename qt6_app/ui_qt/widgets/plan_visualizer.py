from __future__ import annotations
from typing import List, Dict
import math

from PySide6.QtCore import Qt, QRectF, QPointF, QSize
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QPolygonF
from PySide6.QtWidgets import QWidget


class PlanVisualizerWidget(QWidget):
    """
    Visualizzazione grafica del piano barre/pezzi.
    - Ogni barra è una riga alta 20 px (rettangolo di sfondo).
    - Ogni pezzo è disegnato dentro la barra:
        * rettangolo se angoli ~0°,
        * trapezio con lati inclinati secondo l'angolo reale (offset = tan(ang) * altezza).
    - I pezzi sono separati dal kerf impostato (gap visivo).
    - Etichetta della lunghezza (mm) dentro al pezzo, se c'è spazio.
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
        self.setMinimumSize(500, 220)

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
    def _is_square_angle(a: float) -> bool:
        try:
            return abs(float(a)) <= 0.2  # tolleranza visiva ~0.2°
        except Exception:
            return True

    @staticmethod
    def _offset_for_angle(px_height: float, ang_deg: float) -> float:
        """
        Offset orizzontale per rappresentare lo smusso a 'ang_deg' reali:
        offset = tan(angolo) * altezza_pezzo (proiezione semplice).
        """
        try:
            a = abs(float(ang_deg))
        except Exception:
            a = 0.0
        if a <= 0.2:
            return 0.0
        return math.tan(math.radians(a)) * px_height

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

        # Ogni barra: altezza fissa 20 px, spaziata verticalmente
        bar_h = 20.0
        vspace = 10.0
        total_h = n_bars * bar_h + (n_bars - 1) * vspace
        # Se lo spazio verticale è poco, riduci lo spazio tra barre ma non l'altezza barra
        if total_h > avail_h:
            vspace = max(2.0, (avail_h - n_bars * bar_h) / max(1, n_bars - 1))
            total_h = n_bars * bar_h + (n_bars - 1) * vspace

        # Scala orizzontale: stock -> (avail_w - 80) per margini/etichette
        scale_x = (avail_w - 80) / max(1.0, self._stock)

        # Penne
        pen_bar = QPen(self._border); pen_bar.setWidth(1)
        pen_piece_border = QPen(QColor("#2c3e50")); pen_piece_border.setWidth(1)

        # Font
        font = p.font()
        font.setPointSizeF(9.0)
        p.setFont(font)

        for bi, bar in enumerate(self._bars):
            top = y0 + bi * (bar_h + vspace)
            # Rettangolo barra
            bar_rect = QRectF(x0, top, avail_w - 40, bar_h)
            p.setPen(pen_bar)
            p.fillRect(bar_rect, QBrush(self._bar_bg))
            p.drawRect(bar_rect)

            # Pezzi dentro la barra
            inner_pad = 3.0
            piece_h = max(1.0, bar_h - inner_pad * 2)
            piece_y = top + inner_pad

            cursor_x = x0 + inner_pad + 2.0  # piccolo margine sinistro

            for pi, piece in enumerate(bar):
                try:
                    L = float(piece.get("len", 0.0))
                    ax = float(piece.get("ax", 0.0))
                    ad = float(piece.get("ad", 0.0))
                except Exception:
                    continue

                w = max(1.0, L * scale_x)

                # Offset "reale" basato sull'angolo
                off_l = 0.0 if self._is_square_angle(ax) else self._offset_for_angle(piece_h, ax)
                off_r = 0.0 if self._is_square_angle(ad) else self._offset_for_angle(piece_h, ad)
                # Evita poligoni degeneri se pezzo molto corto
                max_off = max(0.0, (w * 0.49))
                off_l = min(off_l, max_off)
                off_r = min(off_r, max_off)

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
                poly = QPolygonF(pts)

                # Colori alternati per leggibilità
                fill = self._piece_fg if (pi % 2 == 0) else self._piece_fg_alt
                p.setPen(pen_piece_border)
                p.setBrush(QBrush(fill))
                p.drawPolygon(poly)

                # Etichetta lunghezza (se spazio sufficiente)
                label = f"{L:.0f} mm"
                p.setPen(QPen(self._text))
                if w >= 46:
                    p.drawText(QRectF(x_left, y_top, w, piece_h), Qt.AlignCenter, label)
                else:
                    p.drawText(QRectF(x_left - 2, y_top - 12, max(46.0, w + 6), 12),
                               Qt.AlignLeft | Qt.AlignVCenter, label)

                # Sposta di pezzo + kerf (gap visivo)
                cursor_x += w + max(0.0, self._kerf * scale_x)

            # Etichetta barra a sinistra
            p.setPen(pen_bar)
            p.drawText(QRectF(x0 - 8, top - 1, 36, 16), Qt.AlignRight | Qt.AlignVCenter, f"B{bi+1}")
