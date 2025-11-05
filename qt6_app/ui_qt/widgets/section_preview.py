from __future__ import annotations
from pathlib import Path
from typing import Optional, List, Tuple, Iterable

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
            from ezdxf.math import OCS  # type: ignore
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

        def add_seg_wcs(x1, y1, x2, y2):
            """Add a segment directly in WCS coordinates."""
            a = QPointF(float(x1), float(y1))
            b = QPointF(float(x2), float(y2))
            segs.append((a, b))
            nonlocal bounds
            r = QRectF(a, b).normalized()
            bounds = r if bounds is None else bounds.united(r)

        def to_wcs_pts(pts: Iterable, extrusion, elevation: float = 0.0) -> List[Tuple[float, float]]:
            """Convert a list of (x, y[, z]) points from OCS to WCS, returning (x, y) in WCS."""
            pts_list = list(pts) if pts is not None else []
            if not pts_list:
                return []
            try:
                ocs = OCS(extrusion)
                result = []
                for pt in pts_list:
                    # Handle 2D or 3D points
                    if len(pt) >= 3:
                        z = float(pt[2])
                    else:
                        z = elevation
                    ocs_point = (float(pt[0]), float(pt[1]), z)
                    wcs_point = ocs.to_wcs(ocs_point)
                    result.append((wcs_point.x, wcs_point.y))
                return result
            except Exception:
                # Fallback: return points as-is if conversion fails
                return [(float(pt[0]), float(pt[1])) for pt in pts_list]

        def add_poly_from_pts_wcs(wcs_pts: List[Tuple[float, float]]):
            """Add polyline segments from WCS points."""
            if len(wcs_pts) < 2:
                return
            for i in range(len(wcs_pts) - 1):
                a = wcs_pts[i]
                b = wcs_pts[i + 1]
                add_seg_wcs(a[0], a[1], b[0], b[1])

        def add_line_wcs(start_x, start_y, end_x, end_y, extrusion, elevation: float = 0.0):
            """Convert and add a LINE segment from OCS to WCS."""
            try:
                wcs_pts = to_wcs_pts([(start_x, start_y), (end_x, end_y)], extrusion, elevation)
                if len(wcs_pts) >= 2:
                    add_seg_wcs(wcs_pts[0][0], wcs_pts[0][1], 
                              wcs_pts[1][0], wcs_pts[1][1])
            except Exception:
                pass

        def flatten_entity(e):
            """Flatten/approximate entity and convert to WCS."""
            try:
                extrusion = getattr(e.dxf, "extrusion", (0, 0, 1))
                elevation = getattr(e.dxf, "elevation", 0.0)
                
                if hasattr(e, "flattening"):
                    pts = list(e.flattening(distance=0.25))
                    wcs_pts = to_wcs_pts(pts, extrusion, elevation)
                    add_poly_from_pts_wcs(wcs_pts)
                elif hasattr(e, "approximate"):
                    pts = list(e.approximate(240))
                    wcs_pts = to_wcs_pts(pts, extrusion, elevation)
                    add_poly_from_pts_wcs(wcs_pts)
            except Exception:
                pass

        def add_virtual(e):
            """Process virtual entities with OCS→WCS conversion."""
            try:
                for sub in e.virtual_entities():
                    dxft = sub.dxftype()
                    if dxft == "LINE":
                        # Convert LINE endpoints
                        extrusion = getattr(sub.dxf, "extrusion", (0, 0, 1))
                        elevation = getattr(sub.dxf, "elevation", 0.0)
                        add_line_wcs(sub.dxf.start.x, sub.dxf.start.y,
                                   sub.dxf.end.x, sub.dxf.end.y,
                                   extrusion, elevation)
                    else:
                        flatten_entity(sub)
            except Exception:
                pass

        # LINE entities
        for e in msp.query("LINE"):
            try:
                extrusion = getattr(e.dxf, "extrusion", (0, 0, 1))
                elevation = getattr(e.dxf, "elevation", 0.0)
                add_line_wcs(e.dxf.start.x, e.dxf.start.y,
                           e.dxf.end.x, e.dxf.end.y,
                           extrusion, elevation)
            except Exception:
                pass

        # LWPOLYLINE and POLYLINE (via virtual entities)
        for e in msp.query("LWPOLYLINE"):
            add_virtual(e)
        for e in msp.query("POLYLINE"):
            add_virtual(e)

        # ARC entities
        for e in msp.query("ARC"):
            flatten_entity(e)

        # CIRCLE entities - close the loop
        for e in msp.query("CIRCLE"):
            try:
                extrusion = getattr(e.dxf, "extrusion", (0, 0, 1))
                elevation = getattr(e.dxf, "elevation", 0.0)
                pts = list(e.flattening(distance=0.25))
                if pts:
                    pts.append(pts[0])  # Close the circle
                wcs_pts = to_wcs_pts(pts, extrusion, elevation)
                add_poly_from_pts_wcs(wcs_pts)
            except Exception:
                pass

        # ELLIPSE entities
        for e in msp.query("ELLIPSE"):
            flatten_entity(e)

        # SPLINE entities
        for e in msp.query("SPLINE"):
            flatten_entity(e)

        # HATCH entities - use HATCH's OCS for all edges
        for h in msp.query("HATCH"):
            try:
                h_extrusion = getattr(h.dxf, "extrusion", (0, 0, 1))
                h_elevation = getattr(h.dxf, "elevation", 0.0)
                
                for path in h.paths:
                    for edge in path.edges:
                        et = getattr(edge, "EDGE_TYPE", "")
                        try:
                            if et == "LineEdge":
                                pts = [edge.start, edge.end]
                                wcs_pts = to_wcs_pts(pts, h_extrusion, h_elevation)
                                if len(wcs_pts) >= 2:
                                    add_seg_wcs(wcs_pts[0][0], wcs_pts[0][1],
                                              wcs_pts[1][0], wcs_pts[1][1])
                            elif et in ("ArcEdge", "EllipseEdge"):
                                pts = list(edge.flattening(distance=0.25))
                                wcs_pts = to_wcs_pts(pts, h_extrusion, h_elevation)
                                add_poly_from_pts_wcs(wcs_pts)
                            elif et == "SplineEdge":
                                pts = list(edge.approximate(240))
                                wcs_pts = to_wcs_pts(pts, h_extrusion, h_elevation)
                                add_poly_from_pts_wcs(wcs_pts)
                        except Exception:
                            pass
            except Exception:
                pass

        # INSERT entities (blocks)
        for ins in msp.query("INSERT"):
            add_virtual(ins)

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
