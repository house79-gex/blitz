from __future__ import annotations
from pathlib import Path
from typing import Optional, List, Tuple

from PySide6.QtCore import QSize, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import QWidget


class SectionPreviewWidget(QWidget):
    """
    Anteprima 2D semplificata di una sezione DXF:
    - Rendering robusto di LINE, LWPOLYLINE (con bulge via virtual_entities), POLYLINE, ARC, CIRCLE, ELLIPSE, SPLINE, HATCH (boundary) e INSERT.
    - Fit automatico alla finestra.
    - Rotazione vista (deg) attorno al centro dei bounds.
    - Colori: sfondo bianco, linee nere.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._segments: List[Tuple[QPointF, QPointF]] = []
        self._bounds: Optional[QRectF] = None
        self._rotation_deg: float = 0.0

        # Stile
        self._bg_color = QColor("#ffffff")
        self._line_color = QColor("#000000")
        self._line_width = 1.2

        self.setMinimumSize(120, 90)

    # ---------------- Public API ----------------
    def clear(self):
        self._segments.clear()
        self._bounds = None
        self.update()

    def load_dxf(self, path: str):
        """
        Carica e converte le entità DXF in segmenti 2D.
        Usa virtual_entities/flattening per coprire archi/bulge/spline/ellipse/insert senza inversioni.
        """
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

        segs: List[Tuple[QPointF, QPointF]] = []
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
                a = pts[i]
                b = pts[i + 1]
                add_seg(a[0], a[1], b[0], b[1])

        def add_entity_generic(e):
            try:
                if hasattr(e, "flattening"):
                    pts = list(e.flattening(distance=0.6))
                    add_poly_pts(pts)
                elif hasattr(e, "approximate"):
                    pts = list(e.approximate(180))
                    add_poly_pts(pts)
            except Exception:
                pass

        def add_virtual_entities(e):
            try:
                for sub in e.virtual_entities():
                    dxft = sub.dxftype()
                    if dxft == "LINE":
                        add_seg(sub.dxf.start.x, sub.dxf.start.y, sub.dxf.end.x, sub.dxf.end.y)
                    elif dxft in ("ARC", "CIRCLE", "ELLIPSE"):
                        add_entity_generic(sub)
                    elif dxft in ("LWPOLYLINE", "POLYLINE", "SPLINE"):
                        add_entity_generic(sub)
                    else:
                        add_entity_generic(sub)
            except Exception:
                pass

        # LINE
        for e in msp.query("LINE"):
            try:
                add_seg(e.dxf.start.x, e.dxf.start.y, e.dxf.end.x, e.dxf.end.y)
            except Exception:
                pass

        # LWPOLYLINE / POLYLINE via virtual_entities (bulge)
        for e in msp.query("LWPOLYLINE"):
            add_virtual_entities(e)
        for e in msp.query("POLYLINE"):
            add_virtual_entities(e)

        # ARC / CIRCLE
        for e in msp.query("ARC"):
            add_entity_generic(e)
        for e in msp.query("CIRCLE"):
            try:
                pts = list(e.flattening(distance=0.6))
                if pts:
                    pts.append(pts[0])
                add_poly_pts(pts)
            except Exception:
                pass

        # ELLIPSE / SPLINE
        for e in msp.query("ELLIPSE"):
            add_entity_generic(e)
        for e in msp.query("SPLINE"):
            add_entity_generic(e)

        # HATCH boundary
        for h in msp.query("HATCH"):
            try:
                for path in h.paths:
                    for edge in path.edges:
                        try:
                            et = edge.EDGE_TYPE
                        except Exception:
                            continue
                        try:
                            if et == "LineEdge":
                                add_seg(edge.start[0], edge.start[1], edge.end[0], edge.end[1])
                            elif et in ("ArcEdge", "EllipseEdge"):
                                pts = list(edge.flattening(distance=0.6))
                                add_poly_pts(pts)
                            elif et == "SplineEdge":
                                pts = list(edge.approximate(180))
                                add_poly_pts(pts)
                        except Exception:
                            pass
            except Exception:
                pass

        # INSERT (blocchi)
        for ins in msp.query("INSERT"):
            add_virtual_entities(ins)

        self._segments = segs
        self._bounds = bounds
        self.update()

    def set_rotation(self, deg: float):
        self._rotation_deg = float(deg) % 360.0
        self.update()

    def rotate_by(self, deg: float):
        self._rotation_deg = (self._rotation_deg + float(deg)) % 360.0
        self.update()

    # ---------------- Rendering helpers ----------------
    def sizeHint(self) -> QSize:
        return QSize(420, 300)

    def _apply_rotation(self, pt: QPointF) -> QPointF:
        if not self._bounds or abs(self._rotation_deg) < 1e-6:
            return pt
        import math
        rad = math.radians(self._rotation_deg)
        cx = self._bounds.center().x()
        cy = self._bounds.center().y()
        x0 = pt.x() - cx
        y0 = pt.y() - cy
        x1 = x0 * math.cos(rad) - y0 * math.sin(rad)
        y1 = x0 * math.sin(rad) + y0 * math.cos(rad)
        return QPointF(x1 + cx, y1 + cy)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg_color)
        p.setRenderHint(QPainter.Antialiasing, True)

        if not self._segments or not self._bounds:
            return

        # Fit-to-box
        bw = max(1e-6, self._bounds.width())
        bh = max(1e-6, self._bounds.height())
        sx = (self.width() * 0.9) / bw
        sy = (self.height() * 0.9) / bh
        s = min(sx, sy)
        cx = self._bounds.center().x()
        cy = self._bounds.center().y()
        ox = self.width() / 2.0 - cx * s
        oy = self.height() / 2.0 + cy * s

        pen = QPen(self._line_color)
        pen.setWidthF(self._line_width)
        p.setPen(pen)

        for a, b in self._segments:
            va = self._apply_rotation(a)
            vb = self._apply_rotation(b)
            x1 = ox + va.x() * s
            y1 = oy - va.y() * s
            x2 = ox + vb.x() * s
            y2 = oy - vb.y() * s
            p.drawLine(x1, y1, x2, y2)
