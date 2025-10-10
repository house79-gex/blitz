from __future__ import annotations
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import QWidget

class SectionPreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._segments = []
        self._bounds: Optional[QRectF] = None

    def clear(self):
        self._segments = []
        self._bounds = None
        self.update()

    def load_dxf(self, path: str):
        p = Path(path)
        if not p.exists():
            self.clear(); return
        try:
            import ezdxf  # type: ignore
        except Exception:
            self.clear(); return
        doc = ezdxf.readfile(str(p))
        msp = doc.modelspace()
        segs = []
        bounds = None

        def add_seg(x1, y1, x2, y2):
            a = QPointF(float(x1), float(y1)); b = QPointF(float(x2), float(y2))
            segs.append((a, b))
            nonlocal bounds
            r = QRectF(a, b).normalized()
            bounds = r if bounds is None else bounds.united(r)

        # LINE
        for e in msp.query("LINE"):
            try: add_seg(e.dxf.start.x, e.dxf.start.y, e.dxf.end.x, e.dxf.end.y)
            except Exception: pass

        # LWPOLYLINE / POLYLINE
        for e in list(msp.query("LWPOLYLINE")) + list(msp.query("POLYLINE")):
            pts = []
            try:
                if hasattr(e, "get_points"):
                    pts = [(pt[0], pt[1]) for pt in e.get_points()]
                elif hasattr(e, "vertices"):
                    pts = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
            except Exception:
                pts = []
            for i in range(len(pts)-1):
                add_seg(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])
            try:
                closed = bool(getattr(e.dxf, "flags", 0) & 1)
            except Exception:
                closed = False
            if closed and len(pts) >= 2:
                add_seg(pts[-1][0], pts[-1][1], pts[0][0], pts[0][1])

        # ARC/CIRCLE/ELLIPSE/SPLINE/HATCH semplificati: rimando al viewer per precisione
        # Per anteprima basta un contorno base: tentativo con flattening dove possibile
        for e in msp.query("CIRCLE"):
            try:
                c = e.dxf.center; r = float(e.dxf.radius)
                # 36 segmenti
                import math
                prevx = c.x + r; prevy = c.y
                for i in range(1, 37):
                    a = 2*math.pi*i/36.0
                    x = c.x + r*math.cos(a); y = c.y + r*math.sin(a)
                    add_seg(prevx, prevy, x, y); prevx, prevy = x, y
            except Exception: pass

        for e in msp.query("ARC"):
            try:
                import math
                c = e.dxf.center; r = float(e.dxf.radius)
                a0 = math.radians(float(e.dxf.start_angle))
                a1 = math.radians(float(e.dxf.end_angle))
                steps = 24
                prevx = c.x + r*math.cos(a0); prevy = c.y + r*math.sin(a0)
                for i in range(1, steps+1):
                    t = a0 + (a1-a0)*i/steps
                    x = c.x + r*math.cos(t); y = c.y + r*math.sin(t)
                    add_seg(prevx, prevy, x, y); prevx, prevy = x, y
            except Exception: pass

        self._segments = segs
        self._bounds = bounds
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0b0b0b"))
        p.setRenderHint(QPainter.Antialiasing, True)
        if not self._segments or not self._bounds:
            return
        # fit-to-box
        bw = self._bounds.width() or 1.0
        bh = self._bounds.height() or 1.0
        sx = (self.width()*0.9)/bw
        sy = (self.height()*0.9)/bh
        s = min(sx, sy)
        cx = self._bounds.center().x(); cy = self._bounds.center().y()
        ox = self.width()/2.0 - cx*s
        oy = self.height()/2.0 + cy*s
        pen = QPen(QColor("#e0e0e0")); pen.setWidthF(1.0); p.setPen(pen)
        for a, b in self._segments:
            va = QPointF(ox + a.x()*s, oy - a.y()*s)
            vb = QPointF(ox + b.x()*s, oy - b.y()*s)
            p.drawLine(va, vb)
