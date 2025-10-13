from __future__ import annotations
from typing import List, Tuple, Optional, Iterable, Dict, Any, Set
from dataclasses import dataclass
from math import hypot, atan2, degrees, radians, sin, cos, sqrt, isfinite
from pathlib import Path

from PySide6.QtCore import Qt, QPointF, QRectF, Signal, QLineF, QObject
from PySide6.QtGui import (
    QWheelEvent, QMouseEvent, QKeyEvent, QTransform, QPen, QColor, QPainterPath, QFont, QGuiApplication
)
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsItemGroup, QGraphicsItem, QGraphicsLineItem,
    QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsSimpleTextItem, QWidget
)


# --------------------- Geometria helper ---------------------
def _dist(a: QPointF, b: QPointF) -> float:
    return hypot(a.x() - b.x(), a.y() - b.y())


def _line_intersection(p1: QPointF, p2: QPointF, p3: QPointF, p4: QPointF) -> Optional[QPointF]:
    # Intersezione segmenti p1-p2 e p3-p4; ritorna punto o None se parallele o fuori dai segmenti
    x1, y1 = p1.x(), p1.y()
    x2, y2 = p2.x(), p2.y()
    x3, y3 = p3.x(), p3.y()
    x4, y4 = p4.x(), p4.y()
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < 1e-12:
        return None
    px = ((x1*y2 - y1*x2)*(x3 - x4) - (x1 - x2)*(x3*y4 - y3*x4)) / den
    py = ((x1*y2 - y1*x2)*(y3 - y4) - (y1 - y2)*(x3*y4 - y3*x4)) / den
    # verifica se il punto sta su entrambi i segmenti (con tolleranza)
    def _on_seg(xa, ya, xb, yb, x, y):
        minx, maxx = (xa, xb) if xa <= xb else (xb, xa)
        miny, maxy = (ya, yb) if ya <= yb else (yb, ya)
        return minx - 1e-7 <= x <= maxx + 1e-7 and miny - 1e-7 <= y <= maxy + 1e-7
    if _on_seg(x1, y1, x2, y2, px, py) and _on_seg(x3, y3, x4, y4, px, py):
        return QPointF(px, py)
    return None


def _project_point_on_segment(p: QPointF, a: QPointF, b: QPointF) -> Tuple[QPointF, float]:
    # Proiezione di p sul segmento a-b, ritorna (piede, t in [0..1])
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


# --------------------- CAD Viewer Avanzato ---------------------
class AdvancedDxfCadView(QGraphicsView):
    """
    CAD avanzato su QGraphicsView:
    - Import DXF robusto (ezdxf.path.from_entity + fallback; OCS→WCS; include blocchi/curve/hatch)
    - Snap: endpoint, midpoint, intersezione
    - Misure: distanza, perpendicolare, angolare (overlay con testo in mm/gradi)
    - Rotazione/allineamento globale della vista (R/E/A)
    - Modifica 2D base: sposta/ruota selezione, trim/extend (LINE ↔ LINE)
    - Salvataggio stato vista (scala/rotazione/pan)
    Hotkeys:
      - P: perpendicolare, G: linear distance, O: angular, Esc: reset tool
      - R/E: ruota vista ±5°, A: allinea verticale al segmento sotto mouse
      - M: move selezione, Shift+R: ruota selezione, T: trim, X: extend
      - Shift per vincolo ortogonale nella misura lineare
      - Mouse: rotellina zoom, centrale pan
    """
    measurementChanged = Signal(float)   # per comunicare la misura in mm
    viewStateChanged = Signal(dict)      # {"rotation_deg","scale","dx","dy"}

    TOOL_DISTANCE = 1
    TOOL_PERP = 2
    TOOL_ANGLE = 3
    TOOL_MOVE = 4
    TOOL_ROTATE = 5
    TOOL_TRIM = 6
    TOOL_EXTEND = 7

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setRenderHints(self.renderHints() | self.viewportUpdateMode())
        self.setDragMode(QGraphicsView.NoDrag)
        self.setMouseTracking(True)

        # Scene + root
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self._root = QGraphicsItemGroup()
        self.scene.addItem(self._root)

        # Stato vista
        self._rotation_deg = 0.0
        self._scale_factor = 1.0
        self._panning = False
        self._last_mouse_pos = QPointF()

        # Dati CAD
        self._segments: List[CadSegment] = []  # solo per LINE e per snapping/intersezioni
        self._intersections: List[QPointF] = []
        self._all_items: List[QGraphicsItem] = []

        # Snap
        self._snap_radius_px = 12
        self._hover_snap_item: Optional[QGraphicsEllipseItem] = None
        self._hover_snap_point: Optional[QPointF] = None

        # Selezione
        self.setInteractive(True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self._selected_items: Set[QGraphicsItem] = set()

        # Tool/misure
        self._tool = self.TOOL_DISTANCE
        self._shift_down = False
        self._pt_a: Optional[QPointF] = None
        self._pt_b: Optional[QPointF] = None
        self._base_seg: Optional[CadSegment] = None
        self._live_line_item: Optional[QGraphicsLineItem] = None
        self._live_extra_item: Optional[QGraphicsItem] = None  # per arco angolare
        self._live_text: Optional[QGraphicsSimpleTextItem] = None

        self._measure_value = 0.0

        # Pen
        self._pen_entity = QPen(QColor("#000000"), 0)  # 0 = hairline
        self._pen_highlight = QPen(QColor("#ff9800"), 0)
        self._pen_measure = QPen(QColor("#00c853"), 0)
        self._pen_construction = QPen(QColor("#1976d2"), 0)

    # ----------------------- Import DXF -----------------------
    def clear(self):
        self.scene.clear()
        self._root = QGraphicsItemGroup()
        self.scene.addItem(self._root)
        self._segments.clear()
        self._intersections.clear()
        self._all_items.clear()
        self._reset_measure_overlay()

    def load_dxf(self, path: str):
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(path)
        try:
            import ezdxf  # type: ignore
            from ezdxf.math import OCS, Vec3  # type: ignore
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

        def add_path_from_points(points: List[QPointF]):
            if len(points) < 2:
                return
            path = QPainterPath(points[0])
            for pt in points[1:]:
                path.lineTo(pt)
            item = QGraphicsPathItem(path)
            item.setPen(self._pen_entity)
            self._root.addToGroup(item)
            self._all_items.append(item)
            # mantieni segments per snap/intersezioni
            for i in range(len(points)-1):
                a = points[i]; b = points[i+1]
                line_item = QGraphicsLineItem(a.x(), a.y(), b.x(), b.y())
                line_item.setPen(self._pen_entity)
                line_item.setVisible(False)  # ausiliario per segment registry
                self._root.addToGroup(line_item)
                self._segments.append(CadSegment(a, b, line_item))

        def add_line(a: QPointF, b: QPointF):
            line = QGraphicsLineItem(a.x(), a.y(), b.x(), b.y())
            line.setPen(self._pen_entity)
            line.setFlag(QGraphicsItem.ItemIsSelectable, True)
            self._root.addToGroup(line)
            self._all_items.append(line)
            self._segments.append(CadSegment(a, b, line))

        def flatten_by_path(entity) -> bool:
            try:
                path = ezpath.from_entity(entity, segments=0)  # auto densità
                if path:
                    pts = list(path.flattening(distance=0.25))
                    pts_w = to_wcs_pts(entity, pts)
                    add_path_from_points(pts_w)
                    return True
            except Exception:
                pass
            return False

        def flatten_entity(entity):
            if flatten_by_path(entity):
                return
            try:
                if hasattr(entity, "flattening"):
                    pts = list(entity.flattening(distance=0.25))
                    pts_w = to_wcs_pts(entity, pts)
                    add_path_from_points(pts_w)
                elif hasattr(entity, "approximate"):
                    pts = list(entity.approximate(360))
                    pts_w = to_wcs_pts(entity, pts)
                    add_path_from_points(pts_w)
            except Exception:
                pass

        def add_virtual(entity):
            try:
                for sub in entity.virtual_entities():
                    dxft = sub.dxftype()
                    if dxft == "LINE":
                        pts_w = to_wcs_pts(sub, [(sub.dxf.start.x, sub.dxf.start.y),
                                                 (sub.dxf.end.x, sub.dxf.end.y)])
                        if len(pts_w) >= 2:
                            add_line(pts_w[0], pts_w[1])
                    else:
                        if not flatten_by_path(sub):
                            flatten_entity(sub)
            except Exception:
                pass

        # Entità
        for e in msp.query("LINE"):
            try:
                pts_w = to_wcs_pts(e, [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)])
                if len(pts_w) >= 2:
                    add_line(pts_w[0], pts_w[1])
            except Exception:
                pass

        for e in msp.query("LWPOLYLINE"):
            add_virtual(e)
        for e in msp.query("POLYLINE"):
            add_virtual(e)

        for e in msp.query("ARC"):
            if not flatten_by_path(e): flatten_entity(e)
        for e in msp.query("CIRCLE"):
            if not flatten_by_path(e):
                try:
                    pts = list(e.flattening(distance=0.25))
                    pts_w = to_wcs_pts(e, pts)
                    if pts_w:
                        pts_w.append(pts_w[0])
                    add_path_from_points(pts_w)
                except Exception:
                    pass
        for e in msp.query("ELLIPSE"):
            if not flatten_by_path(e): flatten_entity(e)
        for e in msp.query("SPLINE"):
            if not flatten_by_path(e): flatten_entity(e)

        for h in msp.query("HATCH"):
            try:
                for path in h.paths:
                    for edge in path.edges:
                        et = getattr(edge, "EDGE_TYPE", "")
                        try:
                            if et == "LineEdge":
                                pts_w = to_wcs_pts(h, [edge.start, edge.end])
                                if len(pts_w) >= 2:
                                    add_line(pts_w[0], pts_w[1])
                            elif et in ("ArcEdge", "EllipseEdge"):
                                pts = list(edge.flattening(distance=0.25))
                                pts_w = to_wcs_pts(h, pts)
                                add_path_from_points(pts_w)
                            elif et == "SplineEdge":
                                pts = list(edge.approximate(360))
                                pts_w = to_wcs_pts(h, pts)
                                add_path_from_points(pts_w)
                        except Exception:
                            pass
            except Exception:
                pass

        for ins in msp.query("INSERT"):
            add_virtual(ins)

        # Fit alla vista
        self._fit_and_reset_view()
        # Intersezioni
        self._rebuild_intersections()

    # ----------------------- Vista/trasformazioni -----------------------
    def _fit_and_reset_view(self):
        rect = self._root.childrenBoundingRect()
        if not rect.isValid() or rect.width() < 1e-6 or rect.height() < 1e-6:
            rect = QRectF(-100, -100, 200, 200)
        self.setSceneRect(rect.adjusted(-10, -10, 10, 10))
        self.resetTransform()
        self._rotation_deg = 0.0
        self._scale_factor = 1.0
        # Fit 90%
        view_rect = self.viewport().rect()
        if not view_rect.isEmpty():
            self.fitInView(rect, Qt.KeepAspectRatio)
            # ricava lo scale attuale approssimando dalla transform
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
        seg = self._nearest_segment(self.mapToScene(self.mapFromGlobal(QGuiApplication.cursor().pos())))
        if not seg:
            return
        dx = seg.b.x() - seg.a.x()
        dy = seg.b.y() - seg.a.y()
        ang = degrees(atan2(dx, dy))  # verticalità: annulla componente X
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
        # Converti raggio pixel in raggio scene
        if tol_px is None:
            tol_px = float(self._snap_radius_px)
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
        # trova il punto più vicino tra snaps
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

    # ----------------------- Misure overlay -----------------------
    def _reset_measure_overlay(self):
        self._pt_a = None
        self._pt_b = None
        self._base_seg = None
        self._measure_value = 0.0
        if self._live_line_item:
            self.scene.removeItem(self._live_line_item)
            self._live_line_item = None
        if self._live_extra_item:
            self.scene.removeItem(self._live_extra_item)
            self._live_extra_item = None
        if self._live_text:
            self.scene.removeItem(self._live_text)
            self._live_text = None
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
            font = QFont(); font.setBold(True)
            t.setFont(font); t.setBrush(QColor("#000"))
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
            # vincolo orto
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

    def _update_angle_overlay(self, a1: QPointF, a2: QPointF, b1: QPointF, b2: QPointF, cursor: QPointF):
        # Calcola angolo tra segmenti a1-a2 e b1-b2 al loro punto più vicino al cursore (usa a2,b2 come vertici)
        v1 = QPointF(a2.x()-a1.x(), a2.y()-a1.y())
        v2 = QPointF(b2.x()-b1.x(), b2.y()-b1.y())
        ang1 = atan2(v1.y(), v1.x())
        ang2 = atan2(v2.y(), v2.x())
        ddeg = abs(degrees((ang2 - ang1)))
        while ddeg > 180.0:
            ddeg = abs(ddeg - 360.0)
        # arco semplice al centro vicino al cursore
        center = cursor
        r = max(20.0 / max(self._scale_factor, 1e-3), 5.0)
        start = min(ang1, ang2)
        end = max(ang1, ang2)
        # disegna arco
        path = QPainterPath()
        steps = 48
        for i in range(steps+1):
            t = start + (end-start)*i/steps
            pt = QPointF(center.x() + r*cos(t), center.y() + r*sin(t))
            if i == 0:
                path.moveTo(pt)
            else:
                path.lineTo(pt)
        extra = self._ensure_live_extra()
        extra.setPath(path)
        txt = self._ensure_live_text()
        txt.setText(f"{ddeg:.2f}°")
        txt.setPos(center)
        self._measure_value = ddeg
        self.measurementChanged.emit(ddeg)

    # ----------------------- Edit base (move/rotate/trim/extend) -----------------------
    def _selected_line_items(self) -> List[QGraphicsLineItem]:
        out: List[QGraphicsLineItem] = []
        for it in self.scene.selectedItems():
            if isinstance(it, QGraphicsLineItem):
                out.append(it)
        return out

    def _map_line_to_seg(self, li: QGraphicsLineItem) -> Optional[CadSegment]:
        for s in self._segments:
            if s.item is li:
                return s
        return None

    def _trim_lines(self, l1: QGraphicsLineItem, l2: QGraphicsLineItem):
        seg1 = self._map_line_to_seg(l1)
        seg2 = self._map_line_to_seg(l2)
        if not seg1 or not seg2:
            return
        ip = _line_intersection(seg1.a, seg1.b, seg2.a, seg2.b)
        if ip is None:
            return
        # trancia la linea 1 al punto più vicino
        if _dist(seg1.a, ip) < _dist(seg1.b, ip):
            seg1.b = ip
        else:
            seg1.a = ip
        l1.setLine(seg1.a.x(), seg1.a.y(), seg1.b.x(), seg1.b.y())
        self._rebuild_intersections()

    def _extend_line_to(self, l1: QGraphicsLineItem, l2: QGraphicsLineItem):
        seg1 = self._map_line_to_seg(l1)
        seg2 = self._map_line_to_seg(l2)
        if not seg1 or not seg2:
            return
        ip = _line_intersection(seg1.a, seg1.b, seg2.a, seg2.b)
        if ip is None:
            return
        # estendi l'estremo più vicino all'intersezione
        if _dist(seg1.a, ip) < _dist(seg1.b, ip):
            seg1.a = ip
        else:
            seg1.b = ip
        l1.setLine(seg1.a.x(), seg1.a.y(), seg1.b.x(), seg1.b.y())
        self._rebuild_intersections()

    # ----------------------- Input -----------------------
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
            e.accept()
            return
        if e.button() == Qt.LeftButton:
            # selezione standard + gestione tool
            if self._tool in (self.TOOL_DISTANCE, self.TOOL_PERP, self.TOOL_ANGLE):
                if self._tool == self.TOOL_DISTANCE:
                    if self._pt_a is None:
                        self._pt_a = self._snap_or_raw(pos_scene)
                    else:
                        self._pt_b = self._snap_or_raw(pos_scene)
                elif self._tool == self.TOOL_PERP:
                    if self._base_seg is None:
                        s = self._nearest_segment(pos_scene)
                        if s:
                            self._base_seg = s
                    else:
                        self._pt_b = self._snap_or_raw(pos_scene)
                elif self._tool == self.TOOL_ANGLE:
                    # usa pt_a come primo click (segmento 1), pt_b come secondo click (segmento 2)
                    if self._pt_a is None:
                        s = self._nearest_segment(pos_scene)
                        if s:
                            self._pt_a = QPointF(s.a)  # store come marker
                            self._pt_b = QPointF(s.b)
                    else:
                        s = self._nearest_segment(pos_scene)
                        if s:
                            # fissa misura
                            self._update_angle_overlay(self._pt_a, self._pt_b, s.a, s.b, pos_scene)
                self.scene.update()
                e.accept()
                return
            elif self._tool in (self.TOOL_MOVE, self.TOOL_ROTATE):
                # inizializza trasformazione su selezione
                self._transform_origin = pos_scene
                e.accept()
                return
            elif self._tool in (self.TOOL_TRIM, self.TOOL_EXTEND):
                # azione tra due linee selezionate
                lines = self._selected_line_items()
                if len(lines) == 2:
                    if self._tool == self.TOOL_TRIM:
                        self._trim_lines(lines[0], lines[1])
                    else:
                        self._extend_line_to(lines[0], lines[1])
                e.accept()
                return
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

        # hover snap
        self._update_hover_snap(pos_scene)

        # tool live
        if self._tool == self.TOOL_DISTANCE:
            if self._pt_a is not None and self._pt_b is None:
                self._update_distance_overlay(self._pt_a, self._snap_or_raw(pos_scene))
        elif self._tool == self.TOOL_PERP:
            if self._base_seg is not None and self._pt_b is None:
                self._update_perp_overlay(self._base_seg, self._snap_or_raw(pos_scene))
        elif self._tool == self.TOOL_ANGLE:
            if self._pt_a is not None and self._pt_b is not None:
                s = self._nearest_segment(pos_scene)
                if s:
                    self._update_angle_overlay(self._pt_a, self._pt_b, s.a, s.b, pos_scene)
        elif self._tool == self.TOOL_MOVE:
            if self.scene.selectedItems():
                delta = pos_scene - getattr(self, "_transform_origin", pos_scene)
                self._transform_origin = pos_scene
                for it in self.scene.selectedItems():
                    it.moveBy(delta.x(), delta.y())
                # aggiorna registry segments per linee
                for s in self._segments:
                    if s.item and s.item.isSelected():
                        ln = s.item.line()
                        s.a = QPointF(ln.x1(), ln.y1())
                        s.b = QPointF(ln.x2(), ln.y2())
                self._rebuild_intersections()
        elif self._tool == self.TOOL_ROTATE:
            if self.scene.selectedItems():
                center = getattr(self, "_transform_center", None)
                if center is None:
                    center = self._transform_origin
                    self._transform_center = center
                vec0 = getattr(self, "_transform_prev_vec", None)
                cur_vec = pos_scene - center
                if vec0 is None:
                    self._transform_prev_vec = cur_vec
                else:
                    ang0 = atan2(vec0.y(), vec0.x())
                    ang1 = atan2(cur_vec.y(), cur_vec.x())
                    ddeg = degrees(ang1 - ang0)
                    for it in self.scene.selectedItems():
                        tr = it.transform()
                        it.setTransformOriginPoint(center)
                        it.setRotation(it.rotation() + ddeg)
                    self._transform_prev_vec = cur_vec
                    # aggiorna segments
                    for s in self._segments:
                        if s.item and s.item.isSelected():
                            ln = s.item.line()
                            s.a = QPointF(ln.x1(), ln.y1())
                            s.b = QPointF(ln.x2(), ln.y2())
                    self._rebuild_intersections()

        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent):
        if e.button() == Qt.MiddleButton:
            self._panning = False
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e: QKeyEvent):
        k = e.key()
        if k == Qt.Key_Shift:
            self._shift_down = True
            e.accept(); return
        if k == Qt.Key_Escape:
            self._tool = self.TOOL_DISTANCE
            self._reset_measure_overlay()
            e.accept(); return
        # Tools
        if k == Qt.Key_G:  # distanza lineare
            self._tool = self.TOOL_DISTANCE; self._reset_measure_overlay(); e.accept(); return
        if k == Qt.Key_P:  # perpendicolare
            self._tool = self.TOOL_PERP; self._reset_measure_overlay(); e.accept(); return
        if k == Qt.Key_O:  # angolo
            self._tool = self.TOOL_ANGLE; self._reset_measure_overlay(); e.accept(); return
        if k == Qt.Key_M:  # move
            self._tool = self.TOOL_MOVE; e.accept(); return
        if k == Qt.Key_R and (e.modifiers() & Qt.ShiftModifier):  # rotate selection
            self._tool = self.TOOL_ROTATE; e.accept(); return
        if k == Qt.Key_T:  # trim
            self._tool = self.TOOL_TRIM; e.accept(); return
        if k == Qt.Key_X:  # extend
            self._tool = self.TOOL_EXTEND; e.accept(); return
        # Vista
        if k == Qt.Key_R and not (e.modifiers() & Qt.ShiftModifier):
            self.rotate_view(+5.0); e.accept(); return
        if k == Qt.Key_E:
            self.rotate_view(-5.0); e.accept(); return
        if k == Qt.Key_A:
            self.align_vertical_to_segment_under_cursor(); e.accept(); return

        super().keyPressEvent(e)

    def keyReleaseEvent(self, e: QKeyEvent):
        if e.key() == Qt.Key_Shift:
            self._shift_down = False
            e.accept(); return
        super().keyReleaseEvent(e)

    # ----------------------- API pubblica misure/stato -----------------------
    def set_tool_distance(self): self._tool = self.TOOL_DISTANCE; self._reset_measure_overlay()
    def set_tool_perpendicular(self): self._tool = self.TOOL_PERP; self._reset_measure_overlay()
    def set_tool_angle(self): self._tool = self.TOOL_ANGLE; self._reset_measure_overlay()

    def last_measure_value(self) -> float:
        return float(self._measure_value)

    def save_view_state(self) -> Dict[str, Any]:
        t: QTransform = self.transform()
        return {
            "rotation_deg": float(self._rotation_deg),
            "scale": float(self._scale_factor),
            "m11": float(t.m11()), "m12": float(t.m12()),
            "m21": float(t.m21()), "m22": float(t.m22()),
            "dx": float(t.dx()), "dy": float(t.dy()),
        }

    def restore_view_state(self, state: Dict[str, Any]):
        try:
            self.resetTransform()
            self._rotation_deg = float(state.get("rotation_deg", 0.0))
            self._scale_factor = float(state.get("scale", 1.0))
            # Ricrea una transform plausibile
            self.scale(self._scale_factor, self._scale_factor)
            self.rotate(self._rotation_deg)
            self.translate(float(state.get("dx", 0.0)), float(state.get("dy", 0.0)))
            self._emit_view_state()
        except Exception:
            pass


# Per retrocompatibilità con codice esistente
class DxfViewerWidget(AdvancedDxfCadView):
    pass
