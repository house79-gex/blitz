from __future__ import annotations
from pathlib import Path
from typing import Optional, List, Iterable

from PySide6.QtCore import QSize, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import QWidget


class SectionPreviewWidget(QWidget):
    """
    Anteprima 2D semplificata (solo rendering, senza rotazione).
    - LINE, LWPOLYLINE/POLYLINE (via virtual_entities), ARC, CIRCLE, ELLIPSE, SPLINE, HATCH, INSERT
    - Fit automatico al widget (margine 10%)
    - Colori: sfondo bianco, linee nere

    Miglioria:
    - Conversione OCS→WCS per archi/curve/hatch/spline e INSERT, così da evitare elementi mancanti o specchiati
      quando le entità sono definite in piani OCS (extrusion/elevation non di default).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._segments: List[tuple[QPointF, QPointF]] = []
        self._bounds: Optional[QRectF] = None
        self._bg = QColor("#ffffff")
        self._fg = QColor("#000000")
        self.setMinimumSize(120, 90)

    @property
    def bounds(self) -> Optional[QRectF]:
        return self._bounds

    def clear(self):
        self._segments.clear()
        self._bounds = None
        self.update()

    def load_dxf(self, path: str):
        """
        Carica DXF e costruisce segmenti in WCS (x,y).
        - Espansione virtual_entities per LWPOLYLINE/POLYLINE con bulge e INSERT.
        - flattening/approx per ARC/CIRCLE/ELLIPSE/SPLINE e HATCH edges.
        - Conversione OCS→WCS su tutte le coordinate generate (usa elevation quando pertinente).
        """
        p = Path(path)
        if not p.exists():
            self.clear()
            return
        try:
            import ezdxf  # type: ignore
            from ezdxf.math import OCS, Vec3  # type: ignore
        except Exception:
            # ezdxf mancante: fallback silenzioso
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

        def add_seg_wcs(a: "Vec3", b: "Vec3"):
            pa = QPointF(float(a.x), float(a.y))
            pb = QPointF(float(b.x), float(b.y))
            segs.append((pa, pb))
            nonlocal bounds
            r = QRectF(pa, pb).normalized()
            bounds = r if bounds is None else bounds.united(r)

        def to_wcs_pts(entity, pts: Iterable):
            """
            Converte una sequenza di (x, y[, z]) dall'OCS dell'entità al WCS.
            Usa entity.dxf.extrusion (default Z-up) e entity.dxf.elevation (per entità 2D).
            """
            try:
                extr = entity.dxf.extrusion
            except Exception:
                extr = (0, 0, 1)
            ocs = OCS(extr)
            elevation = 0.0
            try:
                elevation = float(getattr(entity.dxf, "elevation", 0.0) or 0.0)
            except Exception:
                pass
            out: List[Vec3] = []
            for pt in pts:
                try:
                    x = float(pt[0]); y = float(pt[1])
                    v = ocs.to_wcs((x, y, elevation))
                    if isinstance(v, Vec3):
                        out.append(v)
                    else:
                        out.append(Vec3(v[0], v[1], v[2]))
                except Exception:
                    continue
            return out

        def add_poly_from_pts_wcs(pts_wcs: List["Vec3"]):
            if len(pts_wcs) < 2:
                return
            for i in range(len(pts_wcs) - 1):
                add_seg_wcs(pts_wcs[i], pts_wcs[i + 1])

        def add_entity_generic(e):
            """
            Tenta flattening/approx e converte in WCS.
            Parametri:
              - flattening(distance=0.25)
              - approximate(240)
            """
            try:
                if hasattr(e, "flattening"):
                    pts = list(e.flattening(distance=0.25))
                    add_poly_from_pts_wcs(to_wcs_pts(e, pts))
                elif hasattr(e, "approximate"):
                    pts = list(e.approximate(240))
                    add_poly_from_pts_wcs(to_wcs_pts(e, pts))
            except Exception:
                pass

        def add_virtual_entities(e):
            """
            Espande virtual_entities per coprire bulge (LWPOLYLINE/POLYLINE) e contenuto di blocchi (INSERT).
            LINE: converte estremi via OCS dell'entità figlia. Altre: usa add_entity_generic.
            """
            try:
                for sub in e.virtual_entities():
                    dxft = sub.dxftype()
                    if dxft == "LINE":
                        try:
                            pts_w = to_wcs_pts(sub, [
                                (sub.dxf.start.x, sub.dxf.start.y),
                                (sub.dxf.end.x, sub.dxf.end.y)
                            ])
                            if len(pts_w) >= 2:
                                add_seg_wcs(pts_w[0], pts_w[1])
                        except Exception:
                            pass
                    else:
                        add_entity_generic(sub)
            except Exception:
                pass

        # LINE
        for e in msp.query("LINE"):
            try:
                pts_w = to_wcs_pts(e, [
                    (e.dxf.start.x, e.dxf.start.y),
                    (e.dxf.end.x, e.dxf.end.y)
                ])
                if len(pts_w) >= 2:
                    add_seg_wcs(pts_w[0], pts_w[1])
            except Exception:
                pass

        # LWPOLYLINE / POLYLINE via virtual_entities (gestisce bulge)
        for e in msp.query("LWPOLYLINE"):
            add_virtual_entities(e)
        for e in msp.query("POLYLINE"):
            add_virtual_entities(e)

        # ARC / CIRCLE / ELLIPSE / SPLINE
        for e in msp.query("ARC"):
            add_entity_generic(e)

        for e in msp.query("CIRCLE"):
            try:
                pts = list(e.flattening(distance=0.25))
                pts_w = to_wcs_pts(e, pts)
                if pts_w:
                    pts_w.append(pts_w[0])  # chiudi il cerchio
                add_poly_from_pts_wcs(pts_w)
            except Exception:
                pass

        for e in msp.query("ELLIPSE"):
            add_entity_generic(e)

        for e in msp.query("SPLINE"):
            add_entity_generic(e)

        # HATCH boundaries (usa OCS dell'HATCH per tutte le edge)
        for h in msp.query("HATCH"):
            try:
                for path in h.paths:
                    for edge in path.edges:
                        et = getattr(edge, "EDGE_TYPE", "")
                        try:
                            if et == "LineEdge":
                                pts_w = to_wcs_pts(h, [edge.start, edge.end])
                                if len(pts_w) >= 2:
                                    add_seg_wcs(pts_w[0], pts_w[1])
                            elif et in ("ArcEdge", "EllipseEdge"):
                                pts = list(edge.flattening(distance=0.25))
                                add_poly_from_pts_wcs(to_wcs_pts(h, pts))
                            elif et == "SplineEdge":
                                pts = list(edge.approximate(240))
                                add_poly_from_pts_wcs(to_wcs_pts(h, pts))
                        except Exception:
                            pass
            except Exception:
                pass

        # INSERT (blocchi) espansi
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

        # Fit-to-view con ~10% padding
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