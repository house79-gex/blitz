from __future__ import annotations
from typing import List, Tuple, Optional
from math import hypot
from pathlib import Path

from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import (
    QPainter, QColor, QPen, QWheelEvent, QMouseEvent, QKeyEvent, QFont, QFontMetrics
)
from PySide6.QtWidgets import QWidget


def _dist_point_to_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> Tuple[float, float]:
    """
    Distanza punto-segmento con proiezione clampata.
    Ritorna (distanza, t), dove t in [0,1] è la posizione del piede della perpendicolare su AB.
    """
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    c2 = vx * vx + vy * vy
    if c2 <= 1e-12:
        return hypot(px - ax, py - ay), 0.0
    t = (vx * wx + vy * wy) / c2
    t = max(0.0, min(1.0, t))
    projx = ax + t * vx
    projy = ay + t * vy
    return hypot(px - projx, py - projy), t


class DxfViewerWidget(QWidget):
    """
    Viewer DXF semplificato per sezioni profilo:
    - Rendering robusto: LINE, LWPOLYLINE (bulge via virtual_entities), POLYLINE, ARC, CIRCLE, ELLIPSE, SPLINE,
      HATCH (boundary) e INSERT (blocchi) via virtual_entities, con flatten/approx accurato.
    - Pan (tasto centrale), Zoom (rotellina) centrato sul mouse.
    - Misura:
        - Distanza: 2 click; anteprima live tra primo click e cursore. Shift = vincolo ortogonale (orizz/vert).
        - Perpendicolare (P): 1° click seleziona il lato (segmento), 2° click il punto; anteprima live.
    - Snap: solo marker sotto il mouse (endpoint/midpoint del segmento più vicino).
    - Testo quota (mm) sul disegno.
    - Rotazione (R/E ±5°), allineamento verticale (A: usa il segmento sotto il mouse).
    - Tasto destro: reset misurazione corrente.
    """
    measurementChanged = Signal(float)  # mm

    MODE_DISTANCE = 0
    MODE_PERP = 1

    def __init__(self, parent=None):
        super().__init__(parent)
        # Geometria in world (coordinate DXF)
        self._segments: List[Tuple[QPointF, QPointF]] = []
        self._bounds: Optional[QRectF] = None

        # Vista
        self._scale = 1.0
        self._offset = QPointF(0, 0)
        self._rotation_deg = 0.0

        # Interazione
        self._last_mouse_view = QPointF(0, 0)
        self._panning = False
        self._shift_down = False
        self._snap_radius_px = 12

        # Hover
        self._hover_seg_index: Optional[int] = None
        self._hover_snap: Optional[QPointF] = None

        # Misura
        self._mode = self.MODE_DISTANCE
        self._pt_a: Optional[QPointF] = None
        self._pt_b: Optional[QPointF] = None  # fissata al secondo click
        self._live_b: Optional[QPointF] = None  # anteprima live durante il movimento
        self._base_seg_index: Optional[int] = None  # per PERP
        self._meas_mm: float = 0.0

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    # ---------------- Public API ----------------
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
        idx = seg_index if seg_index is not None else self._hover_seg_index
        if idx is None or not (0 <= idx < len(self._segments)):
            return
        a, b = self._segments[idx]
        dx = b.x() - a.x()
        dy = b.y() - a.y()
        import math
        angle = math.degrees(math.atan2(dx, dy))  # rende il segmento verticale in vista
        self.set_rotation(angle)

    def last_measure_mm(self) -> float:
        return float(self._meas_mm)

    def load_dxf(self, path: str):
        """
        Carica il DXF e produce una lista di segmenti world.
        Gestisce anche i blocchi (INSERT) espandendoli in primitive via virtual_entities.
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
            pts = list(pts) if pts is not None else []
            if len(pts) < 2:
                return
            for i in range(len(pts) - 1):
                a = pts[i]
                b = pts[i + 1]
                add_seg(a[0], a[1], b[0], b[1])

        def add_entity_generic(e):
            # fallback generico: tenta flattening/approx
            try:
                if hasattr(e, "flattening"):
                    pts = list(e.flattening(distance=0.25))
                    add_poly_pts(pts)
                elif hasattr(e, "approximate"):
                    pts = list(e.approximate(240))
                    add_poly_pts(pts)
            except Exception:
                pass

        def add_virtual(e):
            # Espandi entità complesse (bulge, hatch edges, blocchi) in primitive
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

        # Passo 1: entità principali
        # LINE
        for e in msp.query("LINE"):
            try:
                add_seg(e.dxf.start.x, e.dxf.start.y, e.dxf.end.x, e.dxf.end.y)
            except Exception:
                pass

        # LWPOLYLINE/POLYLINE via virtual_entities (copre bulge)
        for e in msp.query("LWPOLYLINE"):
            add_virtual(e)
        for e in msp.query("POLYLINE"):
            add_virtual(e)

        # Curvilinee
        for e in msp.query("ARC"):
            add_entity_generic(e)
        for e in msp.query("CIRCLE"):
            try:
                pts = list(e.flattening(distance=0.25))
                if pts:
                    pts.append(pts[0])
                add_poly_pts(pts)
            except Exception:
                pass
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
                                pts = list(edge.flattening(distance=0.25))
                                add_poly_pts(pts)
                            elif et == "SplineEdge":
                                pts = list(edge.approximate(240))
                                add_poly_pts(pts)
                        except Exception:
                            pass
            except Exception:
                pass

        # INSERT (blocchi) espansi
        for ins in msp.query("INSERT"):
            add_virtual(ins)

        self._segments = segs
        self._bounds = bounds
        self._normalize_view()
        self._reset_measure()
        self.update()

    # ---------------- Trasformazioni vista ----------------
    def _normalize_view(self):
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
        if not self._bounds or abs(deg) < 1e-9:
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
        pr = self._rotate_world_point(pt_world, self._rotation_deg)
        return QPointF(self._offset.x() + pr.x() * self._scale, self._offset.y() - pr.y() * self._scale)

    def _view_to_world(self, pt_view: QPointF) -> QPointF:
        if self._scale <= 1e-12:
            return QPointF(0, 0)
        xr = (pt_view.x() - self._offset.x()) / self._scale
        yr = -(pt_view.y() - self._offset.y()) / self._scale
        return self._rotate_world_point(QPointF(xr, yr), -self._rotation_deg)

    # ---------------- Interazione ----------------
    def wheelEvent(self, e: QWheelEvent):
        if self._scale <= 0:
            return
        angle = e.angleDelta().y()
        factor = 1.0 + (0.1 if angle > 0 else -0.1)
        mouse_v = QPointF(e.position().x(), e.position().y())
        before_w = self._view_to_world(mouse_v)
        self._scale = max(1e-4, self._scale * factor)
        after_w = self._view_to_world(mouse_v)
        delta_w = after_w - before_w
        self._offset -= QPointF(delta_w.x() * self._scale, -delta_w.y() * self._scale)
        self.update()

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.RightButton:
            self._reset_measure()
            self.update()
            e.accept()
            return

        if e.button() == Qt.LeftButton:
            self._panning = False
            wp = self._view_to_world(QPointF(e.position().x(), e.position().y()))
            if self._mode == self.MODE_DISTANCE:
                p = self._snap_or_raw(wp)
                if self._pt_a is None:
                    self._pt_a = p
                    self._pt_b = None
                    self._live_b = None
                else:
                    # secondo click: fissa pt_b con eventuale vincolo orto
                    if self._shift_down and self._pt_a is not None:
                        p = self._apply_ortho(self._pt_a, p)
                    self._pt_b = p
                    self._live_b = None
                self._update_measure()
            else:
                # PERP: primo click seleziona segmento base, secondo click definisce punto
                if self._base_seg_index is None:
                    self._base_seg_index = self._nearest_segment_index(wp)
                else:
                    self._pt_b = self._snap_or_raw(wp)
                    self._live_b = None
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

        v = QPointF(e.position().x(), e.position().y())
        w = self._view_to_world(v)
        self._hover_seg_index = self._nearest_segment_index(w)
        self._hover_snap = self._compute_hover_snap(w)

        # anteprima live misura
        if self._mode == self.MODE_DISTANCE:
            if self._pt_a is not None and self._pt_b is None:
                p = self._snap_or_raw(w)
                if self._shift_down:
                    p = self._apply_ortho(self._pt_a, p)
                self._live_b = p
                self._update_measure(live=True)
        else:
            if self._base_seg_index is not None and self._pt_b is None:
                self._live_b = self._snap_or_raw(w)
                self._update_measure(live=True)

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
        if e.key() == Qt.Key_P:
            self.set_mode(self.MODE_PERP if self._mode == self.MODE_DISTANCE else self.MODE_DISTANCE)
            e.accept()
            return
        if e.key() == Qt.Key_R:
            self.rotate_by(+5.0); e.accept(); return
        if e.key() == Qt.Key_E:
            self.rotate_by(-5.0); e.accept(); return
        if e.key() == Qt.Key_A:
            self.align_segment_vertical(self._hover_seg_index); e.accept(); return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e: QKeyEvent):
        if e.key() == Qt.Key_Shift:
            self._shift_down = False
            e.accept()
            return
        super().keyReleaseEvent(e)

    # ---------------- Snap / selezioni ----------------
    def _nearest_segment_index(self, wp: QPointF) -> Optional[int]:
        if not self._segments:
            return None
        best_i = None
        best_d = 1e18
        rad_w = self._snap_radius_px / max(self._scale, 1e-6)
        for i, (a, b) in enumerate(self._segments):
            d, _ = _dist_point_to_segment(wp.x(), wp.y(), a.x(), a.y(), b.x(), b.y())
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

    def _snap_or_raw(self, wp: QPointF) -> QPointF:
        return self._hover_snap if self._hover_snap is not None else wp

    def _apply_ortho(self, a: QPointF, b: QPointF) -> QPointF:
        dx = b.x() - a.x()
        dy = b.y() - a.y()
        if abs(dx) >= abs(dy):
            return QPointF(a.x() + dx, a.y())
        else:
            return QPointF(a.x(), a.y() + dy)

    def _reset_measure(self):
        self._pt_a = None
        self._pt_b = None
        self._live_b = None
        self._base_seg_index = None
        self._meas_mm = 0.0
        self.measurementChanged.emit(0.0)

    def _update_measure(self, live: bool = False):
        if self._mode == self.MODE_DISTANCE:
            a = self._pt_a
            b = self._pt_b if self._pt_b is not None else (self._live_b if live else None)
            if a is not None and b is not None:
                dx = b.x() - a.x()
                dy = b.y() - a.y()
                self._meas_mm = float(hypot(dx, dy))
                self.measurementChanged.emit(self._meas_mm)
            else:
                self._meas_mm = 0.0
                self.measurementChanged.emit(0.0)
        else:
            if self._base_seg_index is not None:
                a_seg, b_seg = self._segments[self._base_seg_index]
                p = self._pt_b if self._pt_b is not None else (self._live_b if live else None)
                if p is not None:
                    d, t = _dist_point_to_segment(p.x(), p.y(), a_seg.x(), a_seg.y(), b_seg.x(), b_seg.y())
                    self._meas_mm = float(d)
                    self.measurementChanged.emit(self._meas_mm)
                    return
            self._meas_mm = 0.0
            self.measurementChanged.emit(0.0)

    # ---------------- Rendering ----------------
    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#ffffff"))
        p.setRenderHint(QPainter.Antialiasing, True)

        if not self._segments or not self._bounds:
            self._draw_hint_text(p, "Carica un DXF (mouse: pan=centrale, zoom=rotellina | R/E=rotazione | A=allinea | P=perpendicolare | Dx=reset misura)")
            return

        # segmenti
        seg_pen = QPen(QColor("#000000"))
        seg_pen.setWidthF(1.2)
        p.setPen(seg_pen)
        for (a, b) in self._segments:
            va = self._world_to_view(a)
            vb = self._world_to_view(b)
            p.drawLine(va, vb)

        # evidenzia segmento hover
        if self._hover_seg_index is not None and 0 <= self._hover_seg_index < len(self._segments):
            a, b = self._segments[self._hover_seg_index]
            va = self._world_to_view(a)
            vb = self._world_to_view(b)
            p.setPen(QPen(QColor("#ff9800"), 2))
            p.drawLine(va, vb)

        # snap marker singolo
        if self._hover_snap is not None:
            p.setPen(QPen(QColor("#1976d2"), 2))
            v = self._world_to_view(self._hover_snap)
            p.drawEllipse(v, 5, 5)

        # misura
        if self._mode == self.MODE_DISTANCE:
            self._draw_distance_measure(p)
        else:
            self._draw_perp_measure(p)

        # overlay modalità
        self._draw_overlay_mode(p)

    def _draw_distance_measure(self, p: QPainter):
        if self._pt_a is None and self._live_b is None:
            return
        pa = self._world_to_view(self._pt_a) if self._pt_a is not None else None
        pb_world = self._pt_b if self._pt_b is not None else self._live_b
        if pa is None:
            return
        p.setPen(QPen(QColor("#00c853"), 2))
        p.drawEllipse(pa, 4, 4)
        if pb_world is not None:
            pb = self._world_to_view(pb_world)
            p.drawLine(pa, pb)
            p.drawEllipse(pb, 4, 4)
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

        pnt = self._pt_b if self._pt_b is not None else self._live_b
        if pnt is None:
            return

        d, t = _dist_point_to_segment(pnt.x(), pnt.y(), a.x(), a.y(), b.x(), b.y())
        projx = a.x() + t * (b.x() - a.x())
        projy = a.y() + t * (b.y() - a.y())
        proj = QPointF(projx, projy)

        v_point = self._world_to_view(pnt)
        v_proj = self._world_to_view(proj)

        p.setPen(QPen(QColor("#00c853"), 2))
        p.drawLine(v_point, v_proj)
        p.drawEllipse(v_point, 4, 4)
        p.drawEllipse(v_proj, 4, 4)
        mid = QPointF((v_point.x() + v_proj.x()) / 2.0, (v_point.y() + v_proj.y()) / 2.0)
        self._draw_measure_text(p, mid, float(d))

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
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 220))
        p.drawRect(int(x), int(y), int(w), int(h))
        p.setPen(QPen(QColor("#000000")))
        p.drawText(int(x) + 4, int(y) + h - fm.descent() - 2, txt)

    def _draw_overlay_mode(self, p: QPainter):
        mode_txt = "Perpendicolare (P)" if self._mode == self.MODE_PERP else "Distanza (P=Perp)"
        sub = "Shift=orto | R/E=rotazione | A=allinea | Dx=reset"
        font = QFont()
        font.setPointSize(9)
        p.setFont(font)
        fm = QFontMetrics(font)
        txt_w = fm.horizontalAdvance(mode_txt)
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
        p.drawText(x + pad, y + pad + fm.ascent(), mode_txt)
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
