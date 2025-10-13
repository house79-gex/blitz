from __future__ import annotations
from pathlib import Path
from typing import Optional, List

from PySide6.QtCore import QSize, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import QWidget


class SectionPreviewWidget(QWidget):
    """
    Anteprima 2D semplificata (solo rendering, senza rotazione).
    - LINE, LWPOLYLINE/POLYLINE (via virtual_entities), ARC, CIRCLE, ELLIPSE, SPLINE, HATCH, INSERT
    - Fit automatico al widget (margine 5%)
    - Colori: sfondo bianco, linee nere
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._segments: List[tuple[QPointF, QPointF]] = []
        self._bounds: Optional[QRectF] = None
        self.setMinimumSize(120, 90)
        self._bg = QColor("#ffffff")
        self._fg = QColor("#000000")

    @property
    def bounds(self) -> Optional[QRectF]:
        return self._bounds

    def clear(self):
        self._segments.clear()
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
        try:
            doc = ezdxf.readfile(str(p))
            msp = doc.modelspace()
        except Exception:
            self.clear()
            return

        segs: List[tuple[QPointF, QPointF]] = []
        bounds: Optional[QRectF] = None

        def add_seg(x1, y1, x2, y2):
            a = QPointF(float(x1), float(y1))
            b = QPointF(float(x2), float(y2))
            segs.append((a, b))
            nonlocal bounds
            r = QRectF(a, b).normalized()
            bounds = r if bounds is None else bounds.united(r)

        def add_poly_pts(pts):
            pts = list(pts) if pts is not None else []
            if len(pts) < 2:
                return
            for i in range(len(pts) - 1):
                a = pts[i]; b = pts[i + 1]
                add_seg(a[0], a[1], b[0], b[1])

        def add_entity_generic(e):
            try:
                if hasattr(e, "flattening"):
                    pts = list(e.flattening(distance=0.6))
                    add_poly_pts(pts)
                elif hasattr(e, "approximate"):
                    pts = list(e.approximate(240))
                    add_poly_pts(pts)
            except Exception:
                pass

        def add_virtual_entities(e):
            try:
                for sub in e.virtual_entities():
                    dxft = sub.dxftype()
                    if dxft == "LINE":
                        add_seg(sub.dxf.start.x, sub.dxf.start.y, sub.dxf.end.x, sub.dxf.end.y)
                    else:
                        add_entity_generic(sub)
            except Exception:
                pass

        # Entities
        for e in msp.query("LINE"):
            try: add_seg(e.dxf.start.x, e.dxf.start.y, e.dxf.end.x, e.dxf.end.y)
            except Exception: pass

        for e in msp.query("LWPOLYLINE"):
            add_virtual_entities(e)
        for e in msp.query("POLYLINE"):
            add_virtual_entities(e)

        for e in msp.query("ARC"):
            add_entity_generic(e)
        for e in msp.query("CIRCLE"):
            try:
                pts = list(e.flattening(distance=0.6))
                if pts: pts.append(pts[0])
                add_poly_pts(pts)
            except Exception:
                pass
        for e in msp.query("ELLIPSE"):
            add_entity_generic(e)
        for e in msp.query("SPLINE"):
            add_entity_generic(e)

        for h in msp.query("HATCH"):
            try:
                for path in h.paths:
                    for edge in path.edges:
                        et = getattr(edge, "EDGE_TYPE", "")
                        try:
                            if et == "LineEdge":
                                add_seg(edge.start[0], edge.start[1], edge.end[0], edge.end[1])
                            elif et in ("ArcEdge", "EllipseEdge"):
                                pts = list(edge.flattening(distance=0.6))
                                add_poly_pts(pts)
                            elif et == "SplineEdge":
                                pts = list(edge.approximate(240))
                                add_poly_pts(pts)
                        except Exception:
                            pass
            except Exception:
                pass

        for ins in msp.query("INSERT"):
            add_virtual_entities(ins)

        self._segments = segs
        self._bounds = bounds
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(360, 260)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg)
        p.setRenderHint(QPainter.Antialiasing, True)
        if not self._segments or not self._bounds:
            return

        bw = max(1e-6, self._bounds.width())
        bh = max(1e-6, self._bounds.height())
        sx = (self.width() * 0.90) / bw
        sy = (self.height() * 0.90) / bh
        s = min(sx, sy)
        cx = self._bounds.center().x()
        cy = self._bounds.center().y()
        ox = self.width() / 2.0 - cx * s
        oy = self.height() / 2.0 + cy * s

        pen = QPen(self._fg)
        pen.setWidthF(1.2)
        p.setPen(pen)

        for a, b in self._segments:
            x1 = ox + a.x() * s
            y1 = oy - a.y() * s
            x2 = ox + b.x() * s
            y2 = oy - b.y() * s
            p.drawLine(x1, y1, x2, y2)
