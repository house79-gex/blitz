from __future__ import annotations
from typing import List, Tuple, Optional
from math import hypot
from pathlib import Path

from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import (
    QPainter, QColor, QPen, QWheelEvent, QMouseEvent, QKeyEvent, QFont, QFontMetrics
)
from PySide6.QtWidgets import QWidget


def _dist_point_to_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> Tuple[float, float, float]:
    """
    Distanza punto-segmento con proiezione clampata.
    Ritorna (distanza, t, (projx, projy) implicito via t).
    t in [0,1] indica la posizione del piede della perpendicolare sul segmento AB.
    """
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    c2 = vx * vx + vy * vy
    if c2 <= 1e-12:
        # segmento degenerato -> distanza al punto A
        return hypot(px - ax, py - ay), 0.0, 0.0
    t = (vx * wx + vy * wy) / c2
    t = max(0.0, min(1.0, t))
    projx = ax + t * vx
    projy = ay + t * vy
    return hypot(px - projx, py - projy), t, 0.0


class DxfViewerWidget(QWidget):
    """
    Viewer DXF semplificato per sezioni profilo con:
    - Rendering robusto: LINE, LWPOLYLINE (con bulge via virtual_entities), POLYLINE, ARC, CIRCLE, ELLIPSE, SPLINE, HATCH (boundary) con flatten/approx.
    - Pan (tasto centrale), Zoom con rotellina centrato sul mouse.
    - Modalità misura:
        - Distanza (due click): con vincolo ortogonale (Shift) orizz/vert su secondo punto.
        - Perpendicolare (P): primo click seleziona segmento base, secondo click un punto. Mostra distanza perpendicolare.
    - Snap: solo al passaggio del mouse (endpoint e midpoint del segmento più vicino).
    - Testo quota (mm) sul disegno.
    - Rotazione vista (R/E, ±5°). Allinea verticale (A: segment sotto mouse).
    """
    measurementChanged = Signal(float)  # mm

    MODE_DISTANCE = 0
    MODE_PERP = 1

    def __init__(self, parent=None):
        super().__init__(parent)
        # Geometria modellata in "world" (coordinate DXF)
        self._segments: List[Tuple[QPointF, QPointF]] = []
        self._bounds: Optional[QRectF] = None

        # Vista
        self._scale = 1.0
        self._offset = QPointF(0, 0)  # traslazione in pixel (view)
        self._rotation_deg = 0.0      # rotazione della vista attorno al centro dei bounds (deg)

        # Interazione
        self._last_mouse_view = QPointF(0, 0)
        self._panning = False
        self._snap_radius_px = 12
        self._hover_snap: Optional[QPointF] = None
        self._hover_seg_index: Optional[int] = None
        self._shift_down = False

        # Misura
        self._mode = self.MODE_DISTANCE
        self._pt_a: Optional[QPointF] = None
        self._pt_b: Optional[QPointF] = None
        self._base_seg_index: Optional[int] = None  # segmento per modalità PERP
        self._meas_mm: float = 0.0

        # UI
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    # ------------- API pubblica -------------
    def clear(self):
        self._segments.clear()
        self._bounds = None
        self._reset_measure()
        self.update()

    def set_mode(self, mode: int):
        self._mode = mode
        self._reset_measure()
        self.update()

    def rotate_by(self, deg: float):
        self._rotation_deg = (self._rotation_deg + deg) % 360.0
        self.update()

    def set_rotation(self, deg: float):
        self._rotation_deg = float(deg) % 360.0
        self.update()

    def align_segment_vertical(self, seg_index: Optional[int]):
        """
        Ruota la vista così che il segmento indicato (in world) diventi verticale (Y-up) in vista.
        Se seg_index è None, prova a usare quello sotto il mouse.
        """
        idx = seg_index
        if idx is None:
            idx = self._hover_seg_index
        if idx is None or not (0 <= idx < len(self._segments)):
            return
        a, b = self._segments[idx]
        dx = b.x() - a.x()
        dy = b.y() - a.y()
        # vogliamo che il segmento appaia verticale in vista.
        # Con il nostro sistema y-view = -y-world, la verticale in vista non richiede aggiustamenti di segno,
        # basta azzerare la componente X dopo rotazione.
        # Angolo tra vettore (dx,dy) e l'asse Y: atan2(dx, dy) (notare l'ordine invertito)
        import math
        angle = math.degrees(math.atan2(dx, dy))  # se dx=0 -> 0°, già verticale
        self.set_rotation(angle)

    def last_measure_mm(self) -> float:
        return float(self._meas_mm)

    def load_dxf(self, path: str):
        """
        Carica e flattenta un DXF in una lista di segmenti world-2D.
        Usa virtual_entities per gestire bulge e path complessi.
        """
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

        def add_poly_pts(pts):
            # pts: iterable di (x,y[,z]) o Vec3
            pts = list(pts) if pts is not None else []
            if len(pts) < 2:
                return
            for i in range(len(pts) - 1):
                a = pts[i]; b = pts[i + 1]
                add_seg(a[0], a[1], b[0], b[1])

        # Helper: virtualizza entità in primitive
        def add_virtual_entities(entity):
            try:
                for sub in entity.virtual_entities():
                    dxft = sub.dxftype()
                    if dxft == "LINE":
                        add_seg(sub.dxf.start.x, sub.dxf.start.y, sub.dxf.end.x, sub.dxf.end.y)
                    elif dxft == "ARC":
                        try:
                            pts = list(sub.flattening(distance=0.5))
                            add_poly_pts(pts)
                        except Exception:
                            pass
                    elif dxft == "CIRCLE":
                        try:
                            pts = list(sub.flattening(distance=0.5))
                            add_poly_pts(pts + [pts[0]] if pts else pts)
                        except Exception:
                            pass
                    else:
                        # tentativo generico di flatten
                        try:
                            if hasattr(sub, "flattening"):
                                pts = list(sub.flattening(distance=0.5))
                                add_poly_pts(pts)
                            elif hasattr(sub, "approximate"):
                                pts = list(sub.approximate(200))
                                add_poly_pts(pts)
                        except Exception:
                            pass
            except Exception:
                pass

        # LINE
        for e in msp.query("LINE"):
            try:
                add_seg(e.dxf.start.x, e.dxf.start.y, e.dxf.end.x, e.dxf.end.y)
            except Exception:
                pass

        # LWPOLYLINE con bulge via virtual_entities
        for e in msp.query("LWPOLYLINE"):
            # preferisci virtual_entities: include archi dei bulge
            add_virtual_entities(e)

        # POLYLINE 2D via virtual_entities
        for e in msp.query("POLYLINE"):
            add_virtual_entities(e)

        # ARC / CIRCLE
        for e in msp.query("ARC"):
            try:
                pts = list(e.flattening(distance=0.5))
                add_poly_pts(pts)
            except Exception:
                pass
        for e in msp.query("CIRCLE"):
            try:
                pts = list(e.flattening(distance=0.5))
                add_poly_pts(pts + [pts[0]] if pts else pts)
            except Exception:
                pass

        # ELLIPSE
        for e in msp.query("ELLIPSE"):
            try:
                pts = list(e.flattening(distance=0.5))
                add_poly_pts(pts)
            except Exception:
                pass

        # SPLINE
        for e in msp.query("SPLINE"):
            try:
                pts = list(e.approximate(200))
                add_poly_pts(pts)
            except Exception:
                pass

        # HATCH: boundary path edges
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
        self._normalize_view()
        self._reset_measure()
        self.update()

    # ------------- Interni: trasformazioni e vista -------------
    def _normalize_view(self):
        """Fit-to-view iniziale e reset offset/zoom se mancano bounds."""
        if not self._bounds or self.width() <= 0 or self.height() <= 0:
            self._scale = 1.0
            self._offset = QPointF(self.width() / 2, self.height() / 2)
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
        cx = self._bounds.center().x()
        cy = self._bounds.center().y()
        self._offset = QPointF(self.width() / 2.0 - cx * self._scale, self.height() / 2.0 + cy * self._scale)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._normalize_view()

    def _rotate_world_point(self, pt: QPointF, deg: float) -> QPointF:
        """Ruota punto world attorno al centro bounds di 'deg' gradi."""
        if not self._bounds or abs(deg) < 1e-6:
            return pt
        import math
        rad = math.radians(deg)
        cx = self._bounds.center().x()
        cy = self._bounds.center().y()
        x0 = pt.x() - cx
        y0 = pt.y() - cy
        x1 = x0 * math.cos(rad) - y0 * math.sin(rad)
        y1 = x0 * math.sin(rad) + y0 * math.cos(rad)
        return QPointF(x1 + cx, y1 + cy)

    def _world_to_view(self, pt_world: QPointF) -> QPointF:
        """Applica prima rotazione di vista, poi scala+offset e inversione Y per schermo."""
        pr = self._rotate_world_point(pt_world, self._rotation_deg)
        return QPointF(self._offset.x() + pr.x() * self._scale, self._offset.y() - pr.y() * self._scale)

    def _view_to_world(self, pt_view: QPointF) -> QPointF:
        """Inverso di world_to_view: rimuove scala+offset, poi ruota inversamente."""
        if self._scale <= 1e-12:
            return QPointF(0, 0)
        xr = (pt_view.x() - self._offset.x()) / self._scale
        yr = -(pt_view.y() - self._offset.y()) / self._scale
        # un-rotate
        return self._rotate_world_point(QPointF(xr, yr), -self._rotation_deg)

    # ------------- Interazione -------------
    def wheelEvent(self, e: QWheelEvent):
        if self._scale <= 0:
            return
        angle = e.angleDelta().y()
        factor = 1.0 + (0.1 if angle > 0 else -0.1)
        # zoom attorno al mouse
        mouse_v = QPointF(e.position().x(), e.position().y())
        before_w = self._view_to_world(mouse_v)
        self._scale = max(1e-4, self._scale * factor)
        after_w = self._view_to_world(mouse_v)
        delta_w = after_w - before_w
        # convertirlo in delta view e aggiornare offset
        self._offset -= QPointF(delta_w.x() * self._scale, -delta_w.y() * self._scale)
        self.update()

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.LeftButton:
            self._panning = False
            wp = self._view_to_world(QPointF(e.position().x(), e.position().y()))
            if self._mode == self.MODE_DISTANCE:
                p = self._snap_point(wp)
                if self._pt_a is None:
                    self._pt_a = p
                    self._pt_b = None
                else:
                    # vincolo ortogonale se Shift
                    if self._shift_down and self._pt_a is not None:
                        dx = p.x() - self._pt_a.x()
                        dy = p.y() - self._pt_a.y()
                        if abs(dx) >= abs(dy):
                            p = QPointF(self._pt_a.x() + dx, self._pt_a.y())  # orizzontale
                        else:
                            p = QPointF(self._pt_a.x(), self._pt_a.y() + dy)  # verticale
                    self._pt_b = p
                self._update_measure()
            else:
                # PERP: primo click seleziona segmento base, secondo click definisce punto
                if self._base_seg_index is None:
                    self._base_seg_index = self._nearest_segment_index(wp)
                else:
                    p = self._snap_point(wp)
                    self._pt_b = p
                self._update_measure()
            self.update()
        elif e.button() == Qt.MiddleButton:
            self._panning = True
            self._last_mouse_view = QPointF(e.position().x(), e.position().y())
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent):
        if self._panning:
            cur = QPointF(e.position().x(), e.position().y())
            delta = cur - self._last_mouse_view
            self._offset += delta
            self._last_mouse_view = cur
            self.update()
            return

        # hover: aggiorna snap e segmento-nearest
        v = QPointF(e.position().x(), e.position().y())
        w = self._view_to_world(v)
        self._hover_seg_index = self._nearest_segment_index(w)
        self._hover_snap = self._compute_hover_snap(w)
        self.update()

    def mouseReleaseEvent(self, e: QMouseEvent):
        if e.button() == Qt.MiddleButton:
            self._panning = False
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e: QKeyEvent):
        if e.key() == Qt.Key_Shift:
            self._shift_down = True
            e.accept()
            return
        # toggle PERP
        if e.key() == Qt.Key_P:
            self.set_mode(self.MODE_PERP if self._mode == self.MODE_DISTANCE else self.MODE_DISTANCE)
            e.accept()
            return
        # rotazione R/E
        if e.key() == Qt.Key_R:
            self.rotate_by(+5.0); e.accept(); return
        if e.key() == Qt.Key_E:
            self.rotate_by(-5.0); e.accept(); return
        # allinea verticale (segmento sotto mouse)
        if e.key() == Qt.Key_A:
            self.align_segment_vertical(self._hover_seg_index); e.accept(); return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e: QKeyEvent):
        if e.key() == Qt.Key_Shift:
            self._shift_down = False
            e.accept()
            return
        super().keyReleaseEvent(e)

    # ------------- Snap / selezioni -------------
    def _nearest_segment_index(self, wp: QPointF) -> Optional[int]:
        if not self._segments:
            return None
        best_i = None
        best_d = 1e18
        rad_w = self._snap_radius_px / max(self._scale, 1e-6)
        for i, (a, b) in enumerate(self._segments):
            d, _, _ = _dist_point_to_segment(wp.x(), wp.y(), a.x(), a.y(), b.x(), b.y())
            if d < best_d:
                best_d = d
                best_i = i
        if best_d <= rad_w * 2.0:
            return best_i
        return None

    def _compute_hover_snap(self, wp: QPointF) -> Optional[QPointF]:
        idx = self._nearest_segment_index(wp)
        if idx is None:
            return None
        a, b = self._segments[idx]
        mid = QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0)
        cand = [a, b, mid]
        best = None
        bestd = 1e18
        for sp in cand:
            d = hypot(sp.x() - wp.x(), sp.y() - wp.y())
            if d < bestd:
                bestd = d
                best = sp
        rad_w = self._snap_radius_px / max(self._scale, 1e-6)
        if best is not None and bestd <= rad_w:
            return best
        return None

    def _snap_point(self, wp: QPointF) -> QPointF:
        """Snap al punto hover se presente, altrimenti usa il punto raw world."""
        return self._hover_snap if self._hover_snap is not None else wp

    def _reset_measure(self):
        self._pt_a = None
        self._pt_b = None
        self._base_seg_index = None
        self._meas_mm = 0.0
        self.measurementChanged.emit(0.0)

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
            # PERP
            if self._base_seg_index is not None and self._pt_b is not None:
                a, b = self._segments[self._base_seg_index]
                d, t, _ = _dist_point_to_segment(self._pt_b.x(), self._pt_b.y(), a.x(), a.y(), b.x(), b.y())
                self._meas_mm = float(d)
                self.measurementChanged.emit(self._meas_mm)
            else:
                self._meas_mm = 0.0
                self.measurementChanged.emit(0.0)

    # ------------- Rendering -------------
    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#ffffff"))  # sfondo bianco
        p.setRenderHint(QPainter.Antialiasing, True)

        # contenuto
        if not self._segments or not self._bounds:
            # hint overlay
            self._draw_hint_text(p, "Carica un DXF (mouse: pan=centrale, zoom=rotellina, R/E=rotazione, A=allinea, P=perpendicolare)")
            return

        # segmenti
        seg_pen = QPen(QColor("#000000"))
        seg_pen.setWidthF(1.2)
        p.setPen(seg_pen)
        for (a, b) in self._segments:
            va = self._world_to_view(a)
            vb = self._world_to_view(b)
            p.drawLine(va, vb)

        # hover: segmento più vicino evidenziato
        if self._hover_seg_index is not None and 0 <= self._hover_seg_index < len(self._segments):
            a, b = self._segments[self._hover_seg_index]
            va = self._world_to_view(a)
            vb = self._world_to_view(b)
            p.setPen(QPen(QColor("#ff9800"), 2))
            p.drawLine(va, vb)

        # hover snap marker (solo punto corrente)
        if self._hover_snap is not None:
            p.setPen(QPen(QColor("#1976d2"), 2))
            v = self._world_to_view(self._hover_snap)
            p.drawEllipse(v, 5, 5)

        # misura
        if self._mode == self.MODE_DISTANCE:
            self._draw_distance_measure(p)
        else:
            self._draw_perp_measure(p)

        # overlay hint
        self._draw_overlay_mode(p)

    def _draw_distance_measure(self, p: QPainter):
        if self._pt_a is None:
            return
        pa = self._world_to_view(self._pt_a)
        p.setPen(QPen(QColor("#00c853"), 2))
        p.drawEllipse(pa, 4, 4)

        if self._pt_b is not None:
            pb = self._world_to_view(self._pt_b)
            p.drawLine(pa, pb)
            p.drawEllipse(pb, 4, 4)
            # testo quota nel punto medio
            mid = QPointF((pa.x() + pb.x()) / 2.0, (pa.y() + pb.y()) / 2.0)
            self._draw_measure_text(p, mid, self._meas_mm)

    def _draw_perp_measure(self, p: QPainter):
        if self._base_seg_index is None:
            return
        a, b = self._segments[self._base_seg_index]
        va = self._world_to_view(a)
        vb = self._world_to_view(b)
        p.setPen(QPen(QColor("#ff9800"), 2))
        p.drawLine(va, vb)

        if self._pt_b is None:
            return

        # piede perpendicolare
        d, t, _ = _dist_point_to_segment(self._pt_b.x(), self._pt_b.y(), a.x(), a.y(), b.x(), b.y())
        projx = a.x() + t * (b.x() - a.x())
        projy = a.y() + t * (b.y() - a.y())
        pp = QPointF(projx, projy)

        v_point = self._world_to_view(self._pt_b)
        v_proj = self._world_to_view(pp)

        p.setPen(QPen(QColor("#00c853"), 2))
        p.drawLine(v_point, v_proj)
        p.drawEllipse(v_point, 4, 4)
        p.drawEllipse(v_proj, 4, 4)
        # testo quota nel punto medio
        mid = QPointF((v_point.x() + v_proj.x()) / 2.0, (v_point.y() + v_proj.y()) / 2.0)
        self._draw_measure_text(p, mid, self._meas_mm)

    def _draw_measure_text(self, p: QPainter, pos_view: QPointF, value_mm: float):
        txt = f"{value_mm:.2f} mm"
        font = QFont()
        font.setBold(True)
        p.setFont(font)
        fm = QFontMetrics(font)
        w = fm.horizontalAdvance(txt) + 8
        h = fm.height() + 4
        x = pos_view.x() - w / 2.0
        y = pos_view.y() - h / 2.0
        # sfondo semitrasparente
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 220))
        p.drawRect(int(x), int(y), int(w), int(h))
        p.setPen(QPen(QColor("#000000")))
        p.drawText(int(x) + 4, int(y) + h - fm.descent() - 2, txt)

    def _draw_overlay_mode(self, p: QPainter):
        txt = "Modalità: Perpendicolare (P)" if self._mode == self.MODE_PERP else "Modalità: Distanza (P=Perp)"
        sub = "Shift=orto | R/E=rotazione | A=allinea"
        font = QFont()
        font.setPointSize(9)
        p.setFont(font)
        fm = QFontMetrics(font)
        txt_w = fm.horizontalAdvance(txt)
        sub_w = fm.horizontalAdvance(sub)
        pad = 6
        total_w = max(txt_w, sub_w) + pad * 2
        total_h = fm.height() * 2 + pad * 3
        x = 8
        y = 8
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 100))
        p.drawRoundedRect(x, y, total_w, total_h, 6, 6)
        p.setPen(QPen(QColor("#ffffff")))
        p.drawText(x + pad, y + pad + fm.ascent(), txt)
        p.drawText(x + pad, y + pad + fm.height() + fm.ascent() + 2, sub)

    def _draw_hint_text(self, p: QPainter, text: str):
        font = QFont()
        font.setPointSize(9)
        p.setFont(font)
        fm = QFontMetrics(font)
        w = fm.horizontalAdvance(text) + 16
        h = fm.height() + 10
        x = 10
        y = self.height() - h - 10
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 90))
        p.drawRoundedRect(x, y, w, h, 6, 6)
        p.setPen(QPen(QColor("#ffffff")))
        p.drawText(x + 8, y + h - fm.descent() - 4, text)
