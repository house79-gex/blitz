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

        for e in msp.query("LINE"):
            try: add_seg(e.dxf.start.x, e.dxf.start.y, e.dxf.end.x, e.dxf.end.y)
            except Exception: pass
        for e in list(msp.query("LWPOLYLINE")) + list(msp.query("POLYLINE")):
            pts = []
            try:
                pts = [(pt[0], pt[1]) for pt in e.get_points()] if hasattr(e, "get_points") else []
                if not pts and hasattr(e, "vertices"):
                    pts = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
            except Exception: pts = []
            for i in range(len(pts)-1):
                add_seg(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])
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
