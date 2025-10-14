from __future__ import annotations
from typing import List, Tuple, Optional, Iterable, Dict, Any
from dataclasses import dataclass
from math import hypot, atan2, degrees, sin, cos
from pathlib import Path
import os
import subprocess
import tempfile

from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import (
    QWheelEvent, QMouseEvent, QKeyEvent, QTransform, QPen, QColor,
    QPainterPath, QFont, QPainter
)
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsItemGroup, QGraphicsItem,
    QGraphicsLineItem, QGraphicsEllipseItem, QGraphicsPathItem,
    QGraphicsSimpleTextItem, QWidget
)


def _dist(a: QPointF, b: QPointF) -> float:
    return hypot(a.x() - b.x(), a.y() - b.y())


def _line_intersection(p1: QPointF, p2: QPointF, p3: QPointF, p4: QPointF) -> Optional[QPointF]:
    x1, y1 = p1.x(), p1.y()
    x2, y2 = p2.x(), p2.y()
    x3, y3 = p3.x(), p3.y()
    x4, y4 = p4.x(), p4.y()
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < 1e-12:
        return None
    px = ((x1*y2 - y1*x2)*(x3 - x4) - (x1 - x2)*(x3*y4 - y3*x4)) / den
    py = ((x1*y2 - y1*x2)*(y3 - y4) - (y1 - y2)*(x3*y4 - y3*x4)) / den

    def _on_seg(xa, ya, xb, yb, x, y):
        minx, maxx = (xa, xb) if xa <= xb else (xb, xa)
        miny, maxy = (ya, yb) if ya <= yb else (yb, ya)
        return minx - 1e-7 <= x <= maxx + 1e-7 and miny - 1e-7 <= y <= maxy + 1e-7

    if _on_seg(x1, y1, x2, y2, px, py) and _on_seg(x3, y3, x4, y4, px, py):
        return QPointF(px, py)
    return None


def _project_point_on_segment(p: QPointF, a: QPointF, b: QPointF) -> Tuple[QPointF, float]:
    ax, ay = a.x(), a.y()
    bx, by = b.x(), b.y()
    px, py = p.x(), p.y()
    vx, vy = bx - ax, by - ay
    c2 = vx*vx + vy*vy
    if c2 < 1e-12:
        return a, 0.0
    t = ((px - ax)*vx + (py - ay)*vy) / c2
    t = max(0.0, min(1.0, t))
    proj = QPointF(ax + t * vx, ay + t * vy)
    return proj, t


@dataclass
class CadSegment:
    a: QPointF
    b: QPointF
    item: Optional[QGraphicsLineItem] = None


class AdvancedDxfCadView(QGraphicsView):
    """
    CAD avanzato su QGraphicsView:
    - Import DXF robusto (ezdxf.path.from_entity + fallback; OCS→WCS; blocchi, curve, hatch, 3DFACE/TRACE/SOLID)
    - Import DWG via converter ODA/Teigha (se configurato) -> DWG→DXF
    - Snap: endpoint, midpoint, intersezione
    - Misure: distanza (G), perpendicolare (P), angolare (O) [overlay]
    - Quote persistenti:
        - Allineata (D) lungo il segmento AB
        - Lineare (L) orizzontale/verticale (proiezione su asse)
        - Angolare (K) tra due segmenti (arco, frecce, testo)
    - Vista: rotazione ±5° (R/E), allinea verticale (A), sfondo chiaro
    """
    measurementChanged = Signal(float)      # misura live (overlay)
    dimensionCommitted = Signal(float)      # valore della quota creata (allineata/lineare/angolare)
    viewStateChanged = Signal(dict)

    TOOL_DISTANCE = 1
    TOOL_PERP = 2
    TOOL_ANGLE = 3
    TOOL_DIM_ALIGNED = 4
    TOOL_DIM_LINEAR = 5
    TOOL_DIM_ANGULAR = 6

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setMouseTracking(True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)

        # Sfondo chiaro
        self.setBackgroundBrush(QColor("#f5f7fb"))

        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self._root = QGraphicsItemGroup()
        self.scene.addItem(self._root)

        # Vista
        self._rotation_deg = 0.0
        self._scale_factor = 1.0
        self._panning = False
        self._last_mouse_pos = QPointF()

        # Dati
        self._segments: List[CadSegment] = []  # per snap/intersezioni
        self._intersections: List[QPointF] = []
        self._all_items: List[QGraphicsItem] = []

        # Snap
        self._snap_radius_px = 12
        self._hover_snap_item: Optional[QGraphicsEllipseItem] = None
        self._hover_snap_point: Optional[QPointF] = None

        # Stato strumenti
        self._tool = self.TOOL_DISTANCE
        self._shift_down = False
        self._pt_a: Optional[QPointF] = None
        self._pt_b: Optional[QPointF] = None
        self._base_seg: Optional[CadSegment] = None
        self._dim_ang_seg1: Optional[CadSegment] = None

        # Overlay live
        self._live_line_item: Optional[QGraphicsLineItem] = None
        self._live_extra_item: Optional[QGraphicsItem] = None
        self._live_text: Optional[QGraphicsSimpleTextItem] = None
        self._measure_value = 0.0

        # Penne
        self._pen_entity = QPen(QColor("#121212"), 0)   # hairline scuro
        self._pen_highlight = QPen(QColor("#ff9800"), 0)
        self._pen_measure = QPen(QColor("#00c853"), 0)
        self._pen_construction = QPen(QColor("#1976d2"), 0)
        self._pen_dimension = QPen(QColor("#1e88e5"), 0)

        # Ultima quota
        self._last_dimension_value = 0.0

        # Converter ODA
        self._oda_converter_path: Optional[str] = None

    # ------------------------ Import files (DXF/DWG) ------------------------
    def set_oda_converter_path(self, path: Optional[str]):
        self._oda_converter_path = path

    def load_file(self, path: str):
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(path)
        if p.suffix.lower() == ".dwg":
            dxf_path = self._convert_dwg_to_dxf(p)
            self.load_dxf(str(dxf_path))
        else:
            self.load_dxf(str(p))

    def _convert_dwg_to_dxf(self, dwg_path: Path) -> Path:
        exe = self._resolve_oda_converter()
        if exe is None:
            raise RuntimeError("Converter ODA/Teigha non trovato. Imposta ODA_CONVERTER o il percorso nelle impostazioni CAD.")
        tmp_out = Path(tempfile.mkdtemp(prefix="dwg2dxf_"))
        in_dir = dwg_path.parent
        mask = dwg_path.name
        cmd = [exe, str(in_dir), str(tmp_out), "2018", "2018", "ascii", "-y", mask]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out_dxf = tmp_out / (dwg_path.stem + ".dxf")
        if not out_dxf.exists():
            cands = list(tmp_out.glob("*.dxf"))
            if not cands:
                raise RuntimeError("DXF non generato dal converter ODA.")
            out_dxf = cands[0]
        return out_dxf

    def _resolve_oda_converter(self) -> Optional[str]:
        env = os.environ.get("ODA_CONVERTER") or os.environ.get("TEIGHA_CONVERTER")
        candidates = [self._oda_converter_path, env]
        exe_names = ["ODAFileConverter", "TeighaFileConverter", "ODAFileConverter.exe", "TeighaFileConverter.exe"]
        for c in [x for x in candidates if x]:
            cp = Path(c)
            if cp.is_file() and os.access(str(cp), os.X_OK):
                return str(cp)
            if cp.is_dir():
                for n in exe_names:
                    cand = cp / n
                    if cand.exists() and os.access(str(cand), os.X_OK):
                        return str(cand)
        return None

    # ------------------------ Import DXF ------------------------
    def clear(self):
        self.scene.clear()
        self._root = QGraphicsItemGroup()
        self.scene.addItem(self._root)
        self._segments.clear()
        self._intersections.clear()
        self._all_items.clear()
        self._reset_overlay()
        self._last_dimension_value = 0.0

    def load_dxf(self, path: str):
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(path)
        try:
            import ezdxf  # type: ignore
            from ezdxf.math import OCS  # type: ignore
            from ezdxf import path as ezpath  # type: ignore
        except Exception as e:
            raise ImportError("Installa 'ezdxf' (pip install ezdxf)") from e

        self.clear()
        doc = ezdxf.readfile(str(p))
        msp = doc.modelspace()

        def to_wcs_pts(entity, pts: Iterable) -> List[QPointF]:
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
            out: List[QPointF] = []
            for pt in pts:
                try:
                    x = float(pt[0]); y = float(pt[1])
                    v = ocs.to_wcs((x, y, elevation))
                    out.append(QPointF(float(v[0]), float(v[1])))
                except Exception:
                    continue
            return out

        def add_path(points: List[QPointF], selectable: bool = False):
            if len(points) < 2:
                return
            path = QPainterPath(points[0])
            for pt in points[1:]:
                path.lineTo(pt)
            item = QGraphicsPathItem(path)
            item.setPen(self._pen_entity)
            item.setFlag(QGraphicsItem.ItemIsSelectable, selectable)
            self._root.addToGroup(item)
            self._all_items.append(item)
            for i in range(len(points)-1):
                a = points[i]; b = points[i+1]
                li = QGraphicsLineItem(a.x(), a.y(), b.x(), b.y())
                li.setPen(self._pen_entity); li.setVisible(False)
                self._root.addToGroup(li)
                self._segments.append(CadSegment(a, b, li))

        def add_line(a: QPointF, b: QPointF):
            li = QGraphicsLineItem(a.x(), a.y(), b.x(), b.y())
            li.setPen(self._pen_entity)
            li.setFlag(QGraphicsItem.ItemIsSelectable, True)
            self._root.addToGroup(li)
            self._all_items.append(li)
            self._segments.append(CadSegment(a, b, li))

        def flatten_by_path(e) -> bool:
            try:
                path = ezpath.from_entity(e, segments=0)
                if path:
                    pts = list(path.flattening(distance=0.25))
                    add_path(to_wcs_pts(e, pts))
                    return True
            except Exception:
                pass
            return False

        def flatten_generic(e):
            if flatten_by_path(e):
                return
            try:
                if hasattr(e, "flattening"):
                    pts = list(e.flattening(distance=0.25))
                    add_path(to_wcs_pts(e, pts))
                elif hasattr(e, "approximate"):
                    pts = list(e.approximate(480))
                    add_path(to_wcs_pts(e, pts))
            except Exception:
                pass

        def add_virtual(e):
            try:
                for sub in e.virtual_entities():
                    if sub.dxftype() == "LINE":
                        pts = to_wcs_pts(sub, [(sub.dxf.start.x, sub.dxf.start.y),
                                               (sub.dxf.end.x, sub.dxf.end.y)])
                        if len(pts) >= 2:
                            add_line(pts[0], pts[1])
                    else:
                        if not flatten_by_path(sub):
                            flatten_generic(sub)
            except Exception:
                pass

        # LINE
        for e in msp.query("LINE"):
            try:
                pts = to_wcs_pts(e, [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)])
                if len(pts) >= 2:
                    add_line(pts[0], pts[1])
            except Exception:
                pass

        # 3DFACE/TRACE/SOLID -> spigoli via virtual
        for e in msp.query("3DFACE"): add_virtual(e)
        for e in msp.query("TRACE"): add_virtual(e)
        for e in msp.query("SOLID"): add_virtual(e)

        # Polilinee
        for e in msp.query("LWPOLYLINE"): add_virtual(e)
        for e in msp.query("POLYLINE"): add_virtual(e)

        # Curve
        for e in msp.query("ARC"):
            if not flatten_by_path(e): flatten_generic(e)
        for e in msp.query("CIRCLE"):
            if not flatten_by_path(e):
                try:
                    pts = list(e.flattening(distance=0.25))
                    pts_w = to_wcs_pts(e, pts)
                    if pts_w:
                        pts_w.append(pts_w[0])
                    add_path(pts_w)
                except Exception:
                    pass
        for e in msp.query("ELLIPSE"):
            if not flatten_by_path(e): flatten_generic(e)
        for e in msp.query("SPLINE"):
            if not flatten_by_path(e): flatten_generic(e)

        # HATCH
        for h in msp.query("HATCH"):
            try:
                for path in h.paths:
                    for edge in path.edges:
                        et = getattr(edge, "EDGE_TYPE", "")
                        try:
                            if et == "LineEdge":
                                pts = to_wcs_pts(h, [edge.start, edge.end])
                                if len(pts) >= 2: add_line(pts[0], pts[1])
                            elif et in ("ArcEdge", "EllipseEdge"):
                                pts = list(edge.flattening(distance=0.25))
                                add_path(to_wcs_pts(h, pts))
                            elif et == "SplineEdge":
                                pts = list(edge.approximate(480))
                                add_path(to_wcs_pts(h, pts))
                        except Exception:
                            pass
            except Exception:
                pass

        # Blocchi
        for ins in msp.query("INSERT"): add_virtual(ins)

        self._fit_and_reset_view()
        self._rebuild_intersections()

    # ------------------ Vista/trasformazioni ------------------
    def _fit_and_reset_view(self):
        rect = self._root.childrenBoundingRect()
        if not rect.isValid() or rect.width() < 1e-6 or rect.height() < 1e-6:
            rect = QRectF(-100, -100, 200, 200)
        self.setSceneRect(rect.adjusted(-10, -10, 10, 10))
        self.resetTransform()
        self._rotation_deg = 0.0
        self._scale_factor = 1.0
        if not self.viewport().rect().isEmpty():
            self.fitInView(rect, Qt.KeepAspectRatio)
            m = self.transform()
            self._scale_factor = m.m11()
        self._emit_view_state()

    def _emit_view_state(self):
        t: QTransform = self.transform()
        self.viewStateChanged.emit({
            "rotation_deg": float(self._rotation_deg),
            "scale": float(self._scale_factor),
            "dx": float(t.dx()),
            "dy": float(t.dy()),
        })

    def rotate_view(self, deg: float):
        self._rotation_deg = (self._rotation_deg + deg) % 360.0
        self.rotate(deg)
        self._emit_view_state()

    def align_vertical_to_segment_under_cursor(self):
        pos_scene = self.mapToScene(self.mapFromGlobal(self.cursor().pos()))
        seg = self._nearest_segment(pos_scene)
        if not seg:
            return
        dx = seg.b.x() - seg.a.x()
        dy = seg.b.y() - seg.a.y()
        ang = degrees(atan2(dx, dy))
        self.rotate_view(ang)

    # ----------------------- Snap -----------------------
    def _rebuild_intersections(self):
        inter: List[QPointF] = []
        n = len(self._segments)
        for i in range(n):
            a1 = self._segments[i].a; b1 = self._segments[i].b
            for j in range(i+1, n):
                a2 = self._segments[j].a; b2 = self._segments[j].b
                ip = _line_intersection(a1, b1, a2, b2)
                if ip is not None:
                    inter.append(ip)
        self._intersections = inter

    def _nearest_segment(self, pos_scene: QPointF, tol_px: Optional[float] = None) -> Optional[CadSegment]:
        if not self._segments:
            return None
        tol_px = float(self._snap_radius_px if tol_px is None else tol_px)
        radius_scene = tol_px / max(self._scale_factor, 1e-6)
        best: Optional[CadSegment] = None
        best_d = 1e18
        for s in self._segments:
            proj, _ = _project_point_on_segment(pos_scene, s.a, s.b)
            d = _dist(proj, pos_scene)
            if d < best_d:
                best_d = d; best = s
        if best and best_d <= radius_scene * 2.0:
            return best
        return None

    def _candidate_snaps(self) -> List[QPointF]:
        snaps: List[QPointF] = []
        for s in self._segments:
            snaps.append(s.a)
            snaps.append(s.b)
            snaps.append(QPointF((s.a.x()+s.b.x())/2.0, (s.a.y()+s.b.y())/2.0))
        snaps.extend(self._intersections)
        return snaps

    def _update_hover_snap(self, pos_scene: QPointF):
        snaps = self._candidate_snaps()
        if not snaps:
            self._clear_hover_snap()
            return
        radius_scene = self._snap_radius_px / max(self._scale_factor, 1e-6)
        best = None; best_d = 1e18
        for sp in snaps:
            d = _dist(sp, pos_scene)
            if d < best_d:
                best_d = d; best = sp
        if best is not None and best_d <= radius_scene:
            self._show_hover_snap(best)
        else:
            self._clear_hover_snap()

    def _show_hover_snap(self, p: QPointF):
        self._hover_snap_point = p
        if self._hover_snap_item is None:
            e = QGraphicsEllipseItem(-3, -3, 6, 6)
            e.setPen(self._pen_construction)
            e.setZValue(9e6)
            self.scene.addItem(e)
            self._hover_snap_item = e
        self._hover_snap_item.setPos(p)

    def _clear_hover_snap(self):
        self._hover_snap_point = None
        if self._hover_snap_item:
            self.scene.removeItem(self._hover_snap_item)
            self._hover_snap_item = None

    def _snap_or_raw(self, p: QPointF) -> QPointF:
        return self._hover_snap_point if self._hover_snap_point is not None else p

    # ---------------- Misure/overlay ----------------
    def _reset_overlay(self):
        self._pt_a = None
        self._pt_b = None
        self._base_seg = None
        self._dim_ang_seg1 = None
        self._measure_value = 0.0
        if self._live_line_item:
            self.scene.removeItem(self._live_line_item); self._live_line_item = None
        if self._live_extra_item:
            self.scene.removeItem(self._live_extra_item); self._live_extra_item = None
        if self._live_text:
            self.scene.removeItem(self._live_text); self._live_text = None
        self.measurementChanged.emit(0.0)

    def _ensure_live_line(self) -> QGraphicsLineItem:
        if self._live_line_item is None:
            li = QGraphicsLineItem()
            li.setPen(self._pen_measure)
            li.setZValue(9e6)
            self.scene.addItem(li)
            self._live_line_item = li
        return self._live_line_item

    def _ensure_live_text(self) -> QGraphicsSimpleTextItem:
        if self._live_text is None:
            t = QGraphicsSimpleTextItem("")
            font = QFont(); font.setPointSizeF(10.0); font.setBold(True)
            t.setFont(font); t.setBrush(QColor("#0a0a0a"))
            t.setZValue(9e6)
            self.scene.addItem(t)
            self._live_text = t
        return self._live_text

    def _ensure_live_extra(self) -> QGraphicsPathItem:
        if self._live_extra_item is None or not isinstance(self._live_extra_item, QGraphicsPathItem):
            if self._live_extra_item:
                self.scene.removeItem(self._live_extra_item)
            p = QGraphicsPathItem()
            p.setPen(self._pen_measure)
            p.setZValue(9e6)
            self.scene.addItem(p)
            self._live_extra_item = p
        return self._live_extra_item  # type: ignore

    def _update_distance_overlay(self, a: QPointF, b: QPointF):
        if self._shift_down:
            dx = b.x()-a.x(); dy = b.y()-a.y()
            b = QPointF(a.x()+dx if abs(dx)>=abs(dy) else a.x(), a.y() if abs(dx)>=abs(dy) else a.y()+dy)
        line = self._ensure_live_line()
        line.setLine(a.x(), a.y(), b.x(), b.y())
        d = _dist(a, b)
        self._measure_value = d
        self.measurementChanged.emit(d)
        mid = QPointF((a.x()+b.x())/2.0, (a.y()+b.y())/2.0)
        txt = self._ensure_live_text()
        txt.setText(f"{d:.2f} mm")
        txt.setPos(mid)

    def _update_perp_overlay(self, seg: CadSegment, p: QPointF):
        foot, _ = _project_point_on_segment(p, seg.a, seg.b)
        line = self._ensure_live_line()
        line.setLine(p.x(), p.y(), foot.x(), foot.y())
        d = _dist(p, foot)
        self._measure_value = d
        self.measurementChanged.emit(d)
        mid = QPointF((p.x()+foot.x())/2.0, (p.y()+foot.y())/2.0)
        txt = self._ensure_live_text()
        txt.setText(f"{d:.2f} mm")
        txt.setPos(mid)

    def _update_angle_overlay(self, a1: QPointF, a2: QPointF, b1: QPointF, b2: QPointF, center: QPointF):
        v1x, v1y = a2.x()-a1.x(), a2.y()-a1.y()
        v2x, v2y = b2.x()-b1.x(), b2.y()-b1.y()
        ang1 = atan2(v1y, v1x)
        ang2 = atan2(v2y, v2x)
        ddeg = abs(degrees(ang2 - ang1))
        while ddeg > 180.0:
            ddeg = abs(ddeg - 360.0)
        r = max(20.0 / max(self._scale_factor, 1e-3), 5.0)
        path = QPainterPath()
        steps = 48
        start = min(ang1, ang2); end = max(ang1, ang2)
        for i in range(steps+1):
            t = start + (end-start)*i/steps
            pt = QPointF(center.x() + r*cos(t), center.y() + r*sin(t))
            if i == 0: path.moveTo(pt)
            else: path.lineTo(pt)
        extra = self._ensure_live_extra()
        extra.setPath(path)
        txt = self._ensure_live_text()
        txt.setText(f"{ddeg:.2f}°")
        txt.setPos(center)
        self._measure_value = ddeg
        self.measurementChanged.emit(ddeg)

    # ---------------- Quote persistenti ----------------
    def _arrowhead(self, p: QPointF, dirx: float, diry: float, size: float = 5.0, pen: Optional[QPen] = None):
        L = max(1e-9, hypot(dirx, diry))
        tx, ty = dirx / L, diry / L
        ox, oy = -ty, tx
        p1 = QPointF(p.x(), p.y())
        p2 = QPointF(p.x() - tx*size + ox*size*0.6, p.y() - ty*size + oy*size*0.6)
        p3 = QPointF(p.x() - tx*size - ox*size*0.6, p.y() - ty*size - oy*size*0.6)
        path = QPainterPath(p1); path.lineTo(p2); path.lineTo(p3); path.closeSubpath()
        tri = QGraphicsPathItem(path); tri.setPen(pen or self._pen_dimension); tri.setBrush(QColor("#1e88e5")); tri.setZValue(8e6)
        self.scene.addItem(tri)

    def _dim_text(self, value: float, pos: QPointF) -> QGraphicsSimpleTextItem:
        txt = QGraphicsSimpleTextItem(f"{value:.2f}")
        font = QFont(); font.setPointSizeF(10.0); font.setBold(True)
        txt.setFont(font); txt.setBrush(QColor("#0a0a0a")); txt.setZValue(8e6)
        txt.setPos(pos)
        self.scene.addItem(txt)
        return txt

    def _create_aligned_dimension(self, a: QPointF, b: QPointF, offset_scene: float):
        vx, vy = b.x()-a.x(), b.y()-a.y()
        L = max(1e-9, hypot(vx, vy))
        nx, ny = -vy / L, vx / L  # normale
        qa = QPointF(a.x() + nx*offset_scene, a.y() + ny*offset_scene)
        qb = QPointF(b.x() + nx*offset_scene, b.y() + ny*offset_scene)

        pen = self._pen_dimension
        ext1 = QGraphicsLineItem(a.x(), a.y(), qa.x(), qa.y()); ext1.setPen(pen); ext1.setZValue(8e6); self.scene.addItem(ext1)
        ext2 = QGraphicsLineItem(b.x(), b.y(), qb.x(), qb.y()); ext2.setPen(pen); ext2.setZValue(8e6); self.scene.addItem(ext2)
        dim_line = QGraphicsLineItem(qa.x(), qa.y(), qb.x(), qb.y()); dim_line.setPen(pen); dim_line.setZValue(8e6); self.scene.addItem(dim_line)
        self._arrowhead(qa, vx, vy, size=6.0, pen=pen)
        self._arrowhead(qb, -vx, -vy, size=6.0, pen=pen)

        val = hypot(vx, vy)
        mid = QPointF((qa.x()+qb.x())/2.0, (qa.y()+qb.y())/2.0)
        self._dim_text(val, mid)
        self._last_dimension_value = float(val); self.dimensionCommitted.emit(self._last_dimension_value)

    def _create_linear_dimension(self, a: QPointF, b: QPointF, offset_scene: float):
        dx = b.x()-a.x(); dy = b.y()-a.y()
        pen = self._pen_dimension
        if abs(dx) >= abs(dy):
            # orizzontale: misura |dx|
            yline = ((a.y()+b.y())/2.0) + offset_scene
            qa = QPointF(a.x(), yline); qb = QPointF(b.x(), yline)
            ext1 = QGraphicsLineItem(a.x(), a.y(), a.x(), yline); ext1.setPen(pen); ext1.setZValue(8e6); self.scene.addItem(ext1)
            ext2 = QGraphicsLineItem(b.x(), b.y(), b.x(), yline); ext2.setPen(pen); ext2.setZValue(8e6); self.scene.addItem(ext2)
            dim_line = QGraphicsLineItem(qa.x(), qa.y(), qb.x(), qb.y()); dim_line.setPen(pen); dim_line.setZValue(8e6); self.scene.addItem(dim_line)
            self._arrowhead(qa, +1, 0, size=6.0, pen=pen)
            self._arrowhead(qb, -1, 0, size=6.0, pen=pen)
            val = abs(dx)
            mid = QPointF((qa.x()+qb.x())/2.0, yline)
            self._dim_text(val, mid)
            self._last_dimension_value = float(val); self.dimensionCommitted.emit(self._last_dimension_value)
        else:
            # verticale: misura |dy|
            xline = ((a.x()+b.x())/2.0) + offset_scene
            qa = QPointF(xline, a.y()); qb = QPointF(xline, b.y())
            ext1 = QGraphicsLineItem(a.x(), a.y(), xline, a.y()); ext1.setPen(pen); ext1.setZValue(8e6); self.scene.addItem(ext1)
            ext2 = QGraphicsLineItem(b.x(), b.y(), xline, b.y()); ext2.setPen(pen); ext2.setZValue(8e6); self.scene.addItem(ext2)
            dim_line = QGraphicsLineItem(qa.x(), qa.y(), qb.x(), qb.y()); dim_line.setPen(pen); dim_line.setZValue(8e6); self.scene.addItem(dim_line)
            self._arrowhead(qa, 0, +1, size=6.0, pen=pen)
            self._arrowhead(qb, 0, -1, size=6.0, pen=pen)
            val = abs(dy)
            mid = QPointF(xline, (qa.y()+qb.y())/2.0)
            self._dim_text(val, mid)
            self._last_dimension_value = float(val); self.dimensionCommitted.emit(self._last_dimension_value)

    def _create_angular_dimension(self, s1: CadSegment, s2: CadSegment, radius_scene: float):
        ip = _line_intersection(s1.a, s1.b, s2.a, s2.b)
        if ip is None:
            return
        v1x, v1y = s1.b.x()-s1.a.x(), s1.b.y()-s1.a.y()
        v2x, v2y = s2.b.x()-s2.a.x(), s2.b.y()-s2.a.y()
        a1 = atan2(v1y, v1x); a2 = atan2(v2y, v2x)
        ang_start = min(a1, a2); ang_end = max(a1, a2)
        deg_val = abs(degrees(a2 - a1))
        while deg_val > 180.0:
            deg_val = abs(deg_val - 360.0)

        pen = self._pen_dimension
        p1 = QPointF(ip.x() + radius_scene*cos(a1), ip.y() + radius_scene*sin(a1))
        p2 = QPointF(ip.x() + radius_scene*cos(a2), ip.y() + radius_scene*sin(a2))
        r1 = QGraphicsLineItem(ip.x(), ip.y(), p1.x(), p1.y()); r1.setPen(pen); r1.setZValue(8e6); self.scene.addItem(r1)
        r2 = QGraphicsLineItem(ip.x(), ip.y(), p2.x(), p2.y()); r2.setPen(pen); r2.setZValue(8e6); self.scene.addItem(r2)

        path = QPainterPath()
        steps = 64
        for i in range(steps+1):
            t = ang_start + (ang_end-ang_start)*i/steps
            pt = QPointF(ip.x() + radius_scene*cos(t), ip.y() + radius_scene*sin(t))
            if i == 0: path.moveTo(pt)
            else: path.lineTo(pt)
        arc = QGraphicsPathItem(path); arc.setPen(pen); arc.setZValue(8e6); self.scene.addItem(arc)

        self._arrowhead(p1, -cos(a1), -sin(a1), size=6.0, pen=pen)
        self._arrowhead(p2, -cos(a2), -sin(a2), size=6.0, pen=pen)

        mid_ang = (ang_start + ang_end) / 2.0
        tpos = QPointF(ip.x() + (radius_scene+8.0)*cos(mid_ang), ip.y() + (radius_scene+8.0)*sin(mid_ang))
        txt = self._dim_text(deg_val, tpos)
        txt.setText(f"{deg_val:.2f}°")

        self._last_dimension_value = float(deg_val); self.dimensionCommitted.emit(self._last_dimension_value)

    # ---------------- Input ----------------
    def wheelEvent(self, e: QWheelEvent):
        angle = e.angleDelta().y()
        factor = 1.0 + (0.1 if angle > 0 else -0.1)
        self._scale_factor = max(1e-4, self._scale_factor * factor)
        self.scale(factor, factor)
        self._emit_view_state()

    def mousePressEvent(self, e: QMouseEvent):
        pos_view = e.position()
        pos_scene = self.mapToScene(int(pos_view.x()), int(pos_view.y()))
        if e.button() == Qt.MiddleButton:
            self._panning = True
            self._last_mouse_pos = pos_view
            e.accept(); return

        if e.button() == Qt.LeftButton:
            if self._tool in (self.TOOL_DISTANCE, self.TOOL_PERP, self.TOOL_ANGLE,
                              self.TOOL_DIM_ALIGNED, self.TOOL_DIM_LINEAR, self.TOOL_DIM_ANGULAR):
                if self._tool == self.TOOL_DISTANCE:
                    if self._pt_a is None: self._pt_a = self._snap_or_raw(pos_scene)
                    else: self._pt_b = self._snap_or_raw(pos_scene)
                elif self._tool == self.TOOL_PERP:
                    if self._base_seg is None:
                        s = self._nearest_segment(pos_scene)
                        if s: self._base_seg = s
                    else:
                        self._pt_b = self._snap_or_raw(pos_scene)
                elif self._tool == self.TOOL_ANGLE:
                    if self._pt_a is None:
                        s = self._nearest_segment(pos_scene)
                        if s:
                            self._pt_a = QPointF(s.a); self._pt_b = QPointF(s.b)
                    else:
                        s = self._nearest_segment(pos_scene)
                        if s:
                            self._update_angle_overlay(self._pt_a, self._pt_b, s.a, s.b, pos_scene)
                elif self._tool == self.TOOL_DIM_ALIGNED:
                    if self._pt_a is None:
                        self._pt_a = self._snap_or_raw(pos_scene)
                    else:
                        self._pt_b = self._snap_or_raw(pos_scene)
                        self._create_aligned_dimension(self._pt_a, self._pt_b, offset_scene=15.0 / max(self._scale_factor, 1e-6))
                        self._reset_overlay()
                elif self._tool == self.TOOL_DIM_LINEAR:
                    if self._pt_a is None:
                        self._pt_a = self._snap_or_raw(pos_scene)
                    else:
                        self._pt_b = self._snap_or_raw(pos_scene)
                        self._create_linear_dimension(self._pt_a, self._pt_b, offset_scene=15.0 / max(self._scale_factor, 1e-6))
                        self._reset_overlay()
                elif self._tool == self.TOOL_DIM_ANGULAR:
                    if self._dim_ang_seg1 is None:
                        s = self._nearest_segment(pos_scene)
                        if s: self._dim_ang_seg1 = s
                    else:
                        s2 = self._nearest_segment(pos_scene)
                        if s2:
                            self._create_angular_dimension(self._dim_ang_seg1, s2, radius_scene=40.0 / max(self._scale_factor, 1e-6))
                        self._reset_overlay()
                self.scene.update()
                e.accept(); return

        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent):
        pos_view = e.position()
        pos_scene = self.mapToScene(int(pos_view.x()), int(pos_view.y()))
        if self._panning:
            delta = pos_view - self._last_mouse_pos
            self._last_mouse_pos = pos_view
            self.translate(delta.x(), delta.y())
            self._emit_view_state()
            return

        self._update_hover_snap(pos_scene)

        if self._tool == self.TOOL_DISTANCE and self._pt_a is not None and self._pt_b is None:
            self._update_distance_overlay(self._pt_a, self._snap_or_raw(pos_scene))
        elif self._tool == self.TOOL_PERP and self._base_seg is not None and self._pt_b is None:
            self._update_perp_overlay(self._base_seg, self._snap_or_raw(pos_scene))
        elif self._tool == self.TOOL_ANGLE and self._pt_a is not None and self._pt_b is not None:
            s = self._nearest_segment(pos_scene)
            if s: self._update_angle_overlay(self._pt_a, self._pt_b, s.a, s.b, pos_scene)
        elif self._tool == self.TOOL_DIM_ALIGNED and self._pt_a is not None and self._pt_b is None:
            self._update_distance_overlay(self._pt_a, self._snap_or_raw(pos_scene))
        elif self._tool == self.TOOL_DIM_LINEAR and self._pt_a is not None and self._pt_b is None:
            self._update_distance_overlay(self._pt_a, self._snap_or_raw(pos_scene))

        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent):
        if e.button() == Qt.MiddleButton:
            self._panning = False
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e: QKeyEvent):
        k = e.key()
        if k == Qt.Key_Shift:
            self._shift_down = True; e.accept(); return
        if k == Qt.Key_Escape:
            self._tool = self.TOOL_DISTANCE; self._reset_overlay(); e.accept(); return

        # Tools
        if k == Qt.Key_G: self._tool = self.TOOL_DISTANCE; self._reset_overlay(); e.accept(); return
        if k == Qt.Key_P: self._tool = self.TOOL_PERP; self._reset_overlay(); e.accept(); return
        if k == Qt.Key_O: self._tool = self.TOOL_ANGLE; self._reset_overlay(); e.accept(); return
        if k == Qt.Key_D: self._tool = self.TOOL_DIM_ALIGNED; self._reset_overlay(); e.accept(); return
        if k == Qt.Key_L: self._tool = self.TOOL_DIM_LINEAR; self._reset_overlay(); e.accept(); return
        if k == Qt.Key_K: self._tool = self.TOOL_DIM_ANGULAR; self._reset_overlay(); e.accept(); return

        # Vista
        if k == Qt.Key_R and not (e.modifiers() & Qt.ShiftModifier): self.rotate_view(+5.0); e.accept(); return
        if k == Qt.Key_E: self.rotate_view(-5.0); e.accept(); return
        if k == Qt.Key_A: self.align_vertical_to_segment_under_cursor(); e.accept(); return

        super().keyPressEvent(e)

    def keyReleaseEvent(self, e: QKeyEvent):
        if e.key() == Qt.Key_Shift:
            self._shift_down = False; e.accept(); return
        super().keyReleaseEvent(e)

    # ---------------- API pubblica ----------------
    def set_tool_distance(self): self._tool = self.TOOL_DISTANCE; self._reset_overlay()
    def set_tool_perpendicular(self): self._tool = self.TOOL_PERP; self._reset_overlay()
    def set_tool_angle(self): self._tool = self.TOOL_ANGLE; self._reset_overlay()
    def set_tool_dim_aligned(self): self._tool = self.TOOL_DIM_ALIGNED; self._reset_overlay()
    def set_tool_dim_linear(self): self._tool = self.TOOL_DIM_LINEAR; self._reset_overlay()
    def set_tool_dim_angular(self): self._tool = self.TOOL_DIM_ANGULAR; self._reset_overlay()

    def last_measure_value(self) -> float: return float(self._measure_value)
    def last_dimension_value(self) -> float: return float(self._last_dimension_value)

    def save_view_state(self) -> Dict[str, Any]:
        t: QTransform = self.transform()
        return {"rotation_deg": float(self._rotation_deg), "scale": float(self._scale_factor), "dx": float(t.dx()), "dy": float(t.dy())}

    def restore_view_state(self, state: Dict[str, Any]):
        try:
            self.resetTransform()
            self._rotation_deg = float(state.get("rotation_deg", 0.0))
            self._scale_factor = float(state.get("scale", 1.0))
            self.scale(self._scale_factor, self._scale_factor)
            self.rotate(self._rotation_deg)
            self.translate(float(state.get("dx", 0.0)), float(state.get("dy", 0.0)))
            self._emit_view_state()
        except Exception:
            pass


class DxfViewerWidget(AdvancedDxfCadView):
    pass
