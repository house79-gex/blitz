from __future__ import annotations
from typing import List, Tuple, Optional
from math import hypot, cos, sin, radians
from pathlib import Path

from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QWheelEvent, QMouseEvent
from PySide6.QtWidgets import QWidget

def _dist_point_to_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    # distanza punto-segmento (clamp proiezione a [0,1])
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    c1 = vx * wx + vy * wy
    if c1 <= 0:
        return hypot(px - ax, py - ay)
    c2 = vx * vx + vy * vy
    if c2 <= c1:
        return hypot(px - bx, py - by)
    t = c1 / c2
    projx = ax + t * vx
    projy = ay + t * vy
    return hypot(px - projx, py - projy)

class DxfViewerWidget(QWidget):
    measurementChanged = Signal(float)  # mm
    MODE_DISTANCE = 0
    MODE_PERP = 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self._segments: List[Tuple[QPointF, QPointF]] = []
        self._bounds: Optional[QRectF] = None
        self._scale = 1.0
        self._offset = QPointF(0, 0)
        self._last_mouse = QPointF(0, 0)
        self._panning = False

        self._snap_radius_px = 12
        self._snap_points: List[QPointF] = []
        self._hover_snap: Optional[QPointF] = None

        # Misura: distanza (A-B) o perpendicolare (segmento + punto)
        self._mode = self.MODE_DISTANCE
        self._pt_a: Optional[QPointF] = None
        self._pt_b: Optional[QPointF] = None
        self._base_seg_index: Optional[int] = None  # per MODALITÀ PERP: indice segmento base
        self._meas_mm: float = 0.0

        self.setMouseTracking(True)

    # -------- public API --------
    def clear(self):
        self._segments.clear()
        self._snap_points.clear()
        self._bounds = None
        self._pt_a = self._pt_b = self._hover_snap = None
        self._base_seg_index = None
        self._meas_mm = 0.0
        self.update()

    def set_mode(self, mode: int):
        self._mode = mode
        # reset selezioni misura
        self._pt_a = self._pt_b = None
        self._base_seg_index = None
        self._update_measure()
        self.update()

    def load_dxf(self, path: str):
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(path)
        try:
            import ezdxf  # type: ignore
        except Exception as e:
            raise ImportError("Installa 'ezdxf' (pip install ezdxf)") from e

        doc = ezdxf.readfile(str(p))
        msp = doc.modelspace()
        segs: List[Tuple[QPointF, QPointF]] = []
        bounds: Optional[QRectF] = None

        def add_seg(x1, y1, x2, y2):
            a = QPointF(float(x1), float(y1))
            b = QPointF(float(x2), float(y2))
            segs.append((a, b))
            nonlocal bounds
            r = QRectF(a, b).normalized()
            bounds = r if bounds is None else bounds.united(r)

        # Helper: approssima un arco in N segmenti
        def arc_to_segments(cx, cy, r, start_deg, end_deg, steps=48):
            # normalizza direzione
            a0 = float(start_deg); a1 = float(end_deg)
            # gestisci archi "negativi"
            delta = a1 - a0
            if delta == 0:
                delta = 360.0
            steps = max(6, min(180, int(abs(delta) / 4) + 1))
            prevx = cx + r * cos(radians(a0))
            prevy = cy + r * sin(radians(a0))
            for i in range(1, steps + 1):
                t = a0 + delta * (i / steps)
                x = cx + r * cos(radians(t))
                y = cy + r * sin(radians(t))
                add_seg(prevx, prevy, x, y)
                prevx, prevy = x, y

        # LINE
        for e in msp.query("LINE"):
            try:
                add_seg(e.dxf.start.x, e.dxf.start.y, e.dxf.end.x, e.dxf.end.y)
            except Exception:
                pass

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
            for i in range(len(pts) - 1):
                add_seg(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])
            # chiusa?
            try:
                closed = bool(getattr(e.dxf, "flags", 0) & 1)
            except Exception:
                closed = False
            if closed and len(pts) >= 2:
                add_seg(pts[-1][0], pts[-1][1], pts[0][0], pts[0][1])

        # CIRCLE
        for e in msp.query("CIRCLE"):
            try:
                c = e.dxf.center; r = float(e.dxf.radius)
                arc_to_segments(c.x, c.y, r, 0, 360, steps=72)
            except Exception:
                pass

        # ARC
        for e in msp.query("ARC"):
            try:
                c = e.dxf.center; r = float(e.dxf.radius)
                a0 = float(e.dxf.start_angle); a1 = float(e.dxf.end_angle)
                arc_to_segments(c.x, c.y, r, a0, a1)
            except Exception:
                pass

        # ELLIPSE (approssima con polyline)
        for e in msp.query("ELLIPSE"):
            try:
                pts = e.flattening(distance=0.5)  # lista di (x,y,0)
                if len(pts) >= 2:
                    for i in range(len(pts) - 1):
                        add_seg(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])
            except Exception:
                pass

        # SPLINE (approssima)
        for e in msp.query("SPLINE"):
            try:
                pts = e.approximate(200)  # lista di (x,y,0)
                for i in range(len(pts) - 1):
                    add_seg(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])
            except Exception:
                pass

        # HATCH -> boundary path edges
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
                            elif et == "ArcEdge":
                                c = edge.center; r = float(edge.radius)
                                arc_to_segments(c[0], c[1], r, float(edge.start_angle), float(edge.end_angle))
                            elif et == "EllipseEdge":
                                # approssima ellisse parziale
                                pts = edge.flattening(distance=0.5)
                                for i in range(len(pts) - 1):
                                    add_seg(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])
                            elif et == "SplineEdge":
                                pts = edge.approximate(200)
                                for i in range(len(pts) - 1):
                                    add_seg(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])
                        except Exception:
                            pass
            except Exception:
                pass

        self._segments = segs
        self._bounds = bounds
        self._rebuild_snap_points()
        self._fit_to_view()
        self._pt_a = self._pt_b = self._hover_snap = None
        self._base_seg_index = None
        self._meas_mm = 0.0
        self.update()

    # -------- internals --------
    def _rebuild_snap_points(self):
        pts: List[QPointF] = []
        for a, b in self._segments:
            pts.append(a); pts.append(b)
            pts.append(QPointF((a.x()+b.x())/2.0, (a.y()+b.y())/2.0))
        self._snap_points = pts

    def _fit_to_view(self):
        if not self._bounds or self.width() <= 0 or self.height() <= 0:
            return
        bw = self._bounds.width()
        bh = self._bounds.height()
        if bw <= 0 or bh <= 0:
            self._scale = 1.0
            self._offset = QPointF(self.width()/2, self.height()/2)
            return
        sx = (self.width() * 0.9) / bw
        sy = (self.height() * 0.9) / bh
        self._scale = min(sx, sy)
        # centro
        cx = self._bounds.center().x()
        cy = self._bounds.center().y()
        self._offset = QPointF(self.width()/2.0 - cx*self._scale, self.height()/2.0 + cy*self._scale)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._fit_to_view()

    # world <-> view (y invertito)
    def _to_view(self, p: QPointF) -> QPointF:
        return QPointF(self._offset.x() + p.x()*self._scale, self._offset.y() - p.y()*self._scale)
    def _to_world(self, p: QPointF) -> QPointF:
        return QPointF((p.x() - self._offset.x())/self._scale, -(p.y() - self._offset.y())/self._scale)

    def wheelEvent(self, e: QWheelEvent):
        if self._scale <= 0: return
        angle = e.angleDelta().y()
        factor = 1.0 + (0.1 if angle > 0 else -0.1)
        # zoom attorno al mouse
        mouse_v = QPointF(e.position().x(), e.position().y())
        before = self._to_world(mouse_v)
        self._scale = max(1e-4, self._scale * factor)
        after = self._to_world(mouse_v)
        delta = after - before
        self._offset -= QPointF(delta.x()*self._scale, -delta.y()*self._scale)
        self.update()

    def _nearest_snap(self, wp: QPointF, use_radius: bool = False) -> QPointF:
        if not self._snap_points:
            return wp
        best = None
        bestd = 1e18
        for sp in self._snap_points:
            d = hypot(sp.x() - wp.x(), sp.y() - wp.y())
            if d < bestd:
                bestd = d; best = sp
        if use_radius:
            rad_w = self._snap_radius_px / max(self._scale, 1e-6)
            if best is not None and bestd <= rad_w:
                return best
            return wp
        return best or wp

    def _nearest_segment_index(self, wp: QPointF) -> Optional[int]:
        if not self._segments:
            return None
        best_i = None
        best_d = 1e18
        # raggio di cattura in world
        rad_w = self._snap_radius_px / max(self._scale, 1e-6)
        for i, (a, b) in enumerate(self._segments):
            d = _dist_point_to_segment(wp.x(), wp.y(), a.x(), a.y(), b.x(), b.y())
            if d < best_d:
                best_d = d; best_i = i
        if best_d <= rad_w * 2.0:
            return best_i
        return None

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.LeftButton:
            self._panning = False
            wp = self._to_world(QPointF(e.position().x(), e.position().y()))
            if self._mode == self.MODE_DISTANCE:
                p = self._nearest_snap(wp)
                if self._pt_a is None:
                    self._pt_a = p
                    self._pt_b = None
                else:
                    self._pt_b = p
                self._update_measure()
            else:
                # modalità perpendicolare: primo click seleziona segmento base, secondo click seleziona punto
                if self._base_seg_index is None:
                    idx = self._nearest_segment_index(wp)
                    self._base_seg_index = idx
                else:
                    p = self._nearest_snap(wp, use_radius=True)
                    self._pt_b = p
                self._update_measure()
            self.update()
        elif e.button() == Qt.MiddleButton:
            self._panning = True
            self._last_mouse = QPointF(e.position().x(), e.position().y())
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent):
        if self._panning:
            cur = QPointF(e.position().x(), e.position().y())
            delta = cur - self._last_mouse
            self._offset += delta
            self._last_mouse = cur
            self.update()
            return
        # hover snap
        wp = self._to_world(QPointF(e.position().x(), e.position().y()))
        self._hover_snap = self._nearest_snap(wp, use_radius=True)
        self.update()

    def mouseReleaseEvent(self, e: QMouseEvent):
        if e.button() == Qt.MiddleButton:
            self._panning = False
        super().mouseReleaseEvent(e)

    def _update_measure(self):
        if self._mode == self.MODE_DISTANCE:
            if self._pt_a is not None and self._pt_b is not None:
                dx = self._pt_b.x() - self._pt_a.x()
                dy = self._pt_b.y() - self._pt_a.y()
                self._meas_mm = float(hypot(dx, dy))
                self.measurementChanged.emit(self._meas_mm)
            else:
                self._meas_mm = 0.0
                self.measurementChanged.emit(0.0)
        else:
            # PERP: serve segmento base e punto
            if self._base_seg_index is not None and self._pt_b is not None:
                a, b = self._segments[self._base_seg_index]
                self._meas_mm = _dist_point_to_segment(self._pt_b.x(), self._pt_b.y(), a.x(), a.y(), b.x(), b.y())
                self.measurementChanged.emit(self._meas_mm)
            else:
                self._meas_mm = 0.0
                self.measurementChanged.emit(0.0)

    def last_measure_mm(self) -> float:
        return float(self._meas_mm)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#111"))
        p.setRenderHint(QPainter.Antialiasing, True)

        # disegna segmenti
        seg_pen = QPen(QColor("#cfd8dc")); seg_pen.setWidthF(1.0)
        p.setPen(seg_pen)
        for i, (a, b) in enumerate(self._segments):
            va = self._to_view(a); vb = self._to_view(b)
            # evidenzia il segmento selezionato in modalità PERP
            if self._mode == self.MODE_PERP and self._base_seg_index == i:
                p.setPen(QPen(QColor("#ff9800"), 2))
                p.drawLine(va, vb)
                p.setPen(seg_pen)
            else:
                p.drawLine(va, vb)

        # punti snap
        sp_pen = QPen(QColor("#64b5f6")); sp_pen.setWidth(1)
        p.setPen(sp_pen)
        for sp in self._snap_points:
            v = self._to_view(sp)
            p.drawEllipse(v, 3, 3)

        # hover snap
        if self._hover_snap is not None:
            p.setPen(QPen(QColor("#ffeb3b")))
            v = self._to_view(self._hover_snap)
            p.drawEllipse(v, 6, 6)

        # misura
        if self._mode == self.MODE_DISTANCE:
            if self._pt_a is not None:
                pa = self._to_view(self._pt_a)
                p.setPen(QPen(QColor("#00e676"), 2))
                p.drawEllipse(pa, 5, 5)
            if self._pt_a is not None and self._pt_b is not None:
                pa = self._to_view(self._pt_a); pb = self._to_view(self._pt_b)
                p.setPen(QPen(QColor("#00e676"), 2))
                p.drawLine(pa, pb)
        else:
            # PERP: mostra segmento base e, se punto selezionato, la perpendicolare
            if self._base_seg_index is not None:
                a, b = self._segments[self._base_seg_index]
                va = self._to_view(a); vb = self._to_view(b)
                p.setPen(QPen(QColor("#ff9800"), 2))
                p.drawLine(va, vb)
                if self._pt_b is not None:
                    pb = self._to_view(self._pt_b)
                    # traccia linea perpendicolare: proietta pb su segmento
                    ax, ay, bx, by = a.x(), a.y(), b.x(), b.y()
                    vx, vy = bx - ax, by - ay
                    wx, wy = self._pt_b.x() - ax, self._pt_b.y() - ay
                    c2 = vx*vx + vy*vy
                    t = 0.0 if c2 <= 1e-12 else max(0.0, min(1.0, (vx*wx + vy*wy)/c2))
                    proj = QPointF(ax + t*vx, ay + t*vy)
                    pp = self._to_view(proj)
                    p.setPen(QPen(QColor("#00e676"), 2))
                    p.drawLine(pb, pp)
                    p.drawEllipse(pb, 4, 4)
                    p.drawEllipse(pp, 4, 4)
