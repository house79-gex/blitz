from __future__ import annotations
from typing import List, Tuple, Optional
from math import hypot
from pathlib import Path

from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QWheelEvent, QMouseEvent, QKeyEvent
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
        self._hover_snap: Optional[QPointF] = None

        # Misura: distanza (A-B) o perpendicolare (segmento + punto)
        self._mode = self.MODE_DISTANCE
        self._pt_a: Optional[QPointF] = None
        self._pt_b: Optional[QPointF] = None
        self._base_seg_index: Optional[int] = None  # per MODALITÀ PERP: indice segmento base
        self._meas_mm: float = 0.0

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    # -------- public API --------
    def clear(self):
        self._segments.clear()
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

        # Helper: aggiungi segmenti per una lista di punti (Vec3-like)
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

        # LWPOLYLINE
        for e in msp.query("LWPOLYLINE"):
            try:
                pts = [(pt[0], pt[1]) for pt in e.get_points()]  # bulge ignorato (semplificazione)
                add_poly_pts(pts)
                try:
                    if e.closed and len(pts) >= 2:
                        add_seg(pts[-1][0], pts[-1][1], pts[0][0], pts[0][1])
                except Exception:
                    pass
            except Exception:
                pass

        # POLYLINE (2D)
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

        # CIRCLE -> flattening
        for e in msp.query("CIRCLE"):
            try:
                pts = list(e.flattening(distance=0.5))
                add_poly_pts(pts + [pts[0]] if pts else pts)
            except Exception:
                pass

        # ARC -> flattening
        for e in msp.query("ARC"):
            try:
                pts = list(e.flattening(distance=0.5))
                add_poly_pts(pts)
            except Exception:
                pass

        # ELLIPSE -> flattening
        for e in msp.query("ELLIPSE"):
            try:
                pts = list(e.flattening(distance=0.5))
                add_poly_pts(pts)
            except Exception:
                pass

        # SPLINE -> approximate
        for e in msp.query("SPLINE"):
            try:
                pts = list(e.approximate(200))
                add_poly_pts(pts)
            except Exception:
                pass

        # HATCH -> boundary path edges (flattening/approx dove possibile)
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
                                pts = list(edge.flattening(distance=0.5))
                                add_poly_pts(pts)
                            elif et == "EllipseEdge":
                                pts = list(edge.flattening(distance=0.5))
                                add_poly_pts(pts)
                            elif et == "SplineEdge":
                                pts = list(edge.approximate(200))
                                add_poly_pts(pts)
                        except Exception:
                            pass
            except Exception:
                pass

        self._segments = segs
        self._bounds = bounds
        self._fit_to_view()
        # reset misura
        self._pt_a = self._pt_b = self._hover_snap = None
        self._base_seg_index = None
        self._meas_mm = 0.0
        self.update()

    # -------- internals --------
    def _fit_to_view(self):
        if not self._bounds or self.width() <= 0 or self.height() <= 0:
            return
        bw = self._bounds.width()
        bh = self._bounds.height()
        if bw <= 0 or bh <= 0:
            self._scale = 1.0
            self._offset = QPointF(self.width() / 2, self.height() / 2)
            return
        sx = (self.width() * 0.9) / bw
        sy = (self.height() * 0.9) / bh
        self._scale = min(sx, sy)
        # centro
        cx = self._bounds.center().x()
        cy = self._bounds.center().y()
        self._offset = QPointF(self.width() / 2.0 - cx * self._scale, self.height() / 2.0 + cy * self._scale)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._fit_to_view()

    # world <-> view (y invertito)
    def _to_view(self, p: QPointF) -> QPointF:
        return QPointF(self._offset.x() + p.x() * self._scale, self._offset.y() - p.y() * self._scale)

    def _to_world(self, p: QPointF) -> QPointF:
        return QPointF((p.x() - self._offset.x()) / self._scale, -(p.y() - self._offset.y()) / self._scale)

    def wheelEvent(self, e: QWheelEvent):
        if self._scale <= 0:
            return
        angle = e.angleDelta().y()
        factor = 1.0 + (0.1 if angle > 0 else -0.1)
        # zoom attorno al mouse
        mouse_v = QPointF(e.position().x(), e.position().y())
        before = self._to_world(mouse_v)
        self._scale = max(1e-4, self._scale * factor)
        after = self._to_world(mouse_v)
        delta = after - before
        self._offset -= QPointF(delta.x() * self._scale, -delta.y() * self._scale)
        self.update()

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
                best_d = d
                best_i = i
        if best_d <= rad_w * 2.0:
            return best_i
        return None

    def _nearest_snap(self, wp: QPointF) -> QPointF:
        # snap su estremità e midpoint del segmento più vicino
        idx = self._nearest_segment_index(wp)
        if idx is None:
            return wp
        a, b = self._segments[idx]
        # valuta a, b, midpoint
        c = QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0)
        cand = [a, b, c]
        best = wp
        bestd = 1e18
        for sp in cand:
            d = hypot(sp.x() - wp.x(), sp.y() - wp.y())
            if d < bestd:
                bestd = d
                best = sp
        # se troppo lontano, niente snap
        rad_w = self._snap_radius_px / max(self._scale, 1e-6)
        if bestd <= rad_w:
            return best
        return wp

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
                    p = self._nearest_snap(wp)
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
        # hover snap (solo marker, niente griglia di punti)
        wp = self._to_world(QPointF(e.position().x(), e.position().y()))
        self._hover_snap = self._nearest_snap(wp)
        self.update()

    def mouseReleaseEvent(self, e: QMouseEvent):
        if e.button() == Qt.MiddleButton:
            self._panning = False
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e: QKeyEvent):
        # toggle modalità con 'P'
        if e.key() in (Qt.Key_P,):
            self.set_mode(self.MODE_PERP if self._mode == self.MODE_DISTANCE else self.MODE_DISTANCE)
            e.accept()
            return
        super().keyPressEvent(e)

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
        p.fillRect(self.rect(), QColor("#ffffff"))  # sfondo bianco per coerenza con anteprima
        p.setRenderHint(QPainter.Antialiasing, True)

        # disegna segmenti
        seg_pen = QPen(QColor("#000000"))  # linee nere
        seg_pen.setWidthF(1.0)
        p.setPen(seg_pen)
        for i, (a, b) in enumerate(self._segments):
            va = self._to_view(a)
            vb = self._to_view(b)
            # evidenzia il segmento selezionato in modalità PERP
            if self._mode == self.MODE_PERP and self._base_seg_index == i:
                p.setPen(QPen(QColor("#ff9800"), 2))
                p.drawLine(va, vb)
                p.setPen(seg_pen)
            else:
                p.drawLine(va, vb)

        # hover snap marker
        if self._hover_snap is not None:
            p.setPen(QPen(QColor("#1976d2"), 2))
            v = self._to_view(self._hover_snap)
            p.drawEllipse(v, 5, 5)

        # misura
        if self._mode == self.MODE_DISTANCE:
            if self._pt_a is not None and self._pt_b is not None:
                pa = self._to_view(self._pt_a)
                pb = self._to_view(self._pt_b)
                p.setPen(QPen(QColor("#00e676"), 2))
                p.drawLine(pa, pb)
                p.drawEllipse(pa, 4, 4)
                p.drawEllipse(pb, 4, 4)
        else:
            if self._base_seg_index is not None:
                a, b = self._segments[self._base_seg_index]
                va = self._to_view(a)
                vb = self._to_view(b)
                p.setPen(QPen(QColor("#ff9800"), 2))
                p.drawLine(va, vb)
                if self._pt_b is not None:
                    pb = self._to_view(self._pt_b)
                    # traccia perpendicolare
                    ax, ay, bx, by = a.x(), a.y(), b.x(), b.y()
                    vx, vy = bx - ax, by - ay
                    wx, wy = self._pt_b.x() - ax, self._pt_b.y() - ay
                    c2 = vx * vx + vy * vy
                    t = 0.0 if c2 <= 1e-12 else max(0.0, min(1.0, (vx * wx + vy * wy) / c2))
                    proj = QPointF(ax + t * vx, ay + t * vy)
                    pp = self._to_view(proj)
                    p.setPen(QPen(QColor("#00e676"), 2))
                    p.drawLine(pb, pp)
                    p.drawEllipse(pb, 4, 4)
                    p.drawEllipse(pp, 4, 4)
