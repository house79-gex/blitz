from __future__ import annotations
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QRectF, QPointF
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
            self.clear()
            return
        try:
            import ezdxf  # type: ignore
        except Exception:
            self.clear()
            return
        doc = ezdxf.readfile(str(p))
        msp = doc.modelspace()
        segs = []
        bounds = None

        def add_seg(x1, y1, x2, y2):
            a = QPointF(float(x1), float(y1))
            b = QPointF(float(x2), float(y2))
            segs.append((a, b))
            nonlocal bounds
            r = QRectF(a, b).normalized()
            bounds = r if bounds is None else bounds.united(r)

        def add_poly_pts(pts):
            if not pts or len(pts) < 2:
                return
            for i in range(len(pts) - 1):
                a = pts[i]; b = pts[i + 1]
                add_seg(a[0], a[1], b[0], b[1])

        # LINE
        for e in msp.query("LINE"):
            try:
                add_seg(e.dxf.start.x, e.dxf.start.y, e.dxf.end.x, e.dxf.end.y)
            except Exception:
                pass

        # LWPOLYLINE / POLYLINE
        for e in msp.query("LWPOLYLINE"):
            try:
                pts = [(pt[0], pt[1]) for pt in e.get_points()]
                add_poly_pts(pts)
                try:
                    if e.closed and len(pts) >= 2:
                        add_seg(pts[-1][0], pts[-1][1], pts[0][0], pts[0][1])
                except Exception:
                    pass
            except Exception:
                pass

        for e in msp.query("POLYLINE"):
            try:
                v = [(vx.dxf.location.x, vx.dxf.location.y) for vx in e.vertices]
                add_poly_pts(v)
                try:
                    if e.is_closed and len(v) >= 2:
                        add_seg(v[-1][0], v[-1][1], v[0][0], v[0][1])
                except Exception:
                    pass
            except Exception:
                pass

        # ARC/CIRCLE/ELLIPSE/SPLINE -> flatten/approx per contorno base
        for e in msp.query("CIRCLE"):
            try:
                pts = list(e.flattening(1.0))
                add_poly_pts(pts + [pts[0]] if pts else pts)
            except Exception:
                pass

        for e in msp.query("ARC"):
            try:
                pts = list(e.flattening(1.0))
                add_poly_pts(pts)
            except Exception:
                pass

        for e in msp.query("ELLIPSE"):
            try:
                pts = list(e.flattening(1.0))
                add_poly_pts(pts)
            except Exception:
                pass

        for e in msp.query("SPLINE"):
            try:
                pts = list(e.approximate(120))
                add_poly_pts(pts)
            except Exception:
                pass

        self._segments = segs
        self._bounds = bounds
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        # sfondo bianco, linee nere
        p.fillRect(self.rect(), QColor("#ffffff"))
        p.setRenderHint(QPainter.Antialiasing, True)
        if not self._segments or not self._bounds:
            return
        # fit-to-box
        bw = self._bounds.width() or 1.0
        bh = self._bounds.height() or 1.0
        sx = (self.width() * 0.9) / bw
        sy = (self.height() * 0.9) / bh
        s = min(sx, sy)
        cx = self._bounds.center().x(); cy = self._bounds.center().y()
        ox = self.width() / 2.0 - cx * s
        oy = self.height() / 2.0 + cy * s
        pen = QPen(QColor("#000000")); pen.setWidthF(1.0); p.setPen(pen)
        for a, b in self._segments:
            va = QPointF(ox + a.x() * s, oy - a.y() * s)
            vb = QPointF(ox + b.x() * s, oy - b.y() * s)
            p.drawLine(va, vb)
