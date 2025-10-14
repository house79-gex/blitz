from __future__ import annotations
from typing import List, Tuple, Optional, Iterable, Dict, Any, Set
from dataclasses import dataclass
from math import hypot, atan2, degrees, radians, sin, cos
from pathlib import Path
import os
import shutil
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
    - Import DWG: conversione automatica DWG→DXF via ODA/Teigha File Converter (se configurato o in $ODA_CONVERTER)
    - Snap: endpoint, midpoint, intersezione
    - Misure: distanza (G), perpendicolare (P), angolare (O)
    - Quota allineata (D): crea entità di quota con linee di estensione, linea di quota, frecce e testo
    - Rotazione vista (R/E) ±5°, Allinea verticale (A)
    - Stato vista salvabile (scala/rotazione/pan)
    Mouse: rotellina = zoom, centrale = pan, sinistro = interazione strumento
    """
    measurementChanged = Signal(float)      # misura live
    dimensionCommitted = Signal(float)      # valore quota allineata creata
    viewStateChanged = Signal(dict)

    TOOL_DISTANCE = 1
    TOOL_PERP = 2
    TOOL_ANGLE = 3
    TOOL_DIM_ALIGNED = 4
    TOOL_MOVE = 5
    TOOL_ROTATE = 6
    TOOL_TRIM = 7
    TOOL_EXTEND = 8

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setMouseTracking(True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)

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
        self._segments: List[CadSegment] = []  # per snap/intersezioni/trim/extend
        self._intersections: List[QPointF] = []
        self._all_items: List[QGraphicsItem] = []

        # Snap
        self._snap_radius_px = 12
        self._hover_snap_item: Optional[QGraphicsEllipseItem] = None
        self._hover_snap_point: Optional[QPointF] = None

        # Strumenti misure/edit
        self._tool = self.TOOL_DISTANCE
        self._shift_down = False
        self._pt_a: Optional[QPointF] = None
        self._pt_b: Optional[QPointF] = None
        self._base_seg: Optional[CadSegment] = None
        self._live_line_item: Optional[QGraphicsLineItem] = None
        self._live_extra_item: Optional[QGraphicsItem] = None
        self._live_text: Optional[QGraphicsSimpleTextItem] = None
        self._measure_value = 0.0

        # Penne
        self._pen_entity = QPen(QColor("#000000"), 0)   # hairline
        self._pen_highlight = QPen(QColor("#ff9800"), 0)
        self._pen_measure = QPen(QColor("#00c853"), 0)
        self._pen_construction = QPen(QColor("#1976d2"), 0)

        # Ultima quota (per “imposta spessore = quota”)
        self._last_dimension_value = 0.0

        # Percorso ODA/Teigha Converter opzionale
        self._oda_converter_path: Optional[str] = None

    # ------------------------ Import files (DXF/DWG) ------------------------
    def set_oda_converter_path(self, path: Optional[str]):
        """Imposta il percorso all'eseguibile ODA/Teigha File Converter (facoltativo)."""
        self._oda_converter_path = path

    def load_file(self, path: str):
        """Carica DXF o DWG. Per DWG tenta conversione automatica a DXF."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(path)
        ext = p.suffix.lower()
        if ext == ".dwg":
            dxf_path = self._convert_dwg_to_dxf(p)
            self.load_dxf(str(dxf_path))
        else:
            self.load_dxf(str(p))

    def _convert_dwg_to_dxf(self, dwg_path: Path) -> Path:
        """
        Converte un DWG in DXF usando ODA/Teigha File Converter.
        - Cerca percorso in self._oda_converter_path o variabile d’ambiente ODA_CONVERTER.
        - Output: DXF ASCII 2018 in cartella temporanea.
        """
        exe = self._resolve_oda_converter()
        if exe is None:
            raise RuntimeError("Converter ODA/Teigha non trovato. Imposta il percorso o la variabile d'ambiente ODA_CONVERTER.")
        # ODAFileConverter richiede directory input/output e file mask
        tmp_out = Path(tempfile.mkdtemp(prefix="dwg2dxf_"))
        in_dir = dwg_path.parent
        mask = dwg_path.name
        # Sintassi (tipica): ODAFileConverter <in_dir> <out_dir> 2018 2018 ascii -y <mask>
        cmd = [exe, str(in_dir), str(tmp_out), "2018", "2018", "ascii", "-y", mask]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as e:
            raise RuntimeError(f"Conversione DWG→DXF fallita: {e}")
        out_dxf = tmp_out / (dwg_path.stem + ".dxf")
        if not out_dxf.exists():
            # Alcune versioni non rispettano il case del mask: fallback cerca qualsiasi .dxf generato
            candidates = list(tmp_out.glob("*.dxf"))
            if not candidates:
                raise RuntimeError("DXF non generato dal converter ODA.")
            out_dxf = candidates[0]
        return out_dxf

    def _resolve_oda_converter(self) -> Optional[str]:
        """
        Risolve il percorso dell'eseguibile del converter ODA/Teigha.
        Accetta:
        - valore impostato via set_oda_converter_path
        - variabile d’ambiente ODA_CONVERTER (può essere directory o path eseguibile)
        Restituisce path eseguibile o None.
        """
        candidates: List[str] = []
        if self._oda_converter_path:
            candidates.append(self._oda_converter_path)
        env = os.environ.get("ODA_CONVERTER") or os.environ.get("TEIGHA_CONVERTER")
        if env:
            candidates.append(env)
        # Normalizza: se è directory, cerca eseguibile tipico
        exe_names = ["ODAFileConverter", "TeighaFileConverter", "ODAFileConverter.exe", "TeighaFileConverter.exe"]
        for c in candidates:
            cpath = Path(c)
            if cpath.is_file() and os.access(c, os.X_OK):
                return str(cpath)
            if cpath.is_dir():
                for name in exe_names:
                    cand = cpath / name
                    if cand.exists() and os.access(cand, os.X_OK):
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
        self._reset_measure_overlay()
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

        def add_path_from_points(points: List[QPointF], selectable: bool = False):
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
            # segment registry
            for i in range(len(points)-1):
                a = points[i]; b = points[i+1]
                line_item = QGraphicsLineItem(a.x(), a.y(), b.x(), b.y())
                line_item.setPen(self._pen_entity)
                line_item.setVisible(False)
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
                path = ezpath.from_entity(entity, segments=0)  # autodensità
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
                    pts = list(entity.approximate(480))
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

        # LINE
        for e in msp.query("LINE"):
            try:
                pts_w = to_wcs_pts(e, [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)])
                if len(pts_w) >= 2:
                    add_line(pts_w[0], pts_w[1])
            except Exception:
                pass

        # 3DFACE / TRACE / SOLID -> spigoli
        for e in msp.query("3DFACE"):
            try:
                vs = [e.dxf.vtx0, e.dxf.vtx1, e.dxf.vtx2, e.dxf.vtx3]
                pts = [(v.x, v.y) for v in vs if v is not None]
                pts_w = to_wcs_pts(e, pts)
                if len(pts_w) >= 3:
                    add_path_from_points(pts_w + [pts_w[0]])
            except Exception:
                pass
        for e in msp.query("TRACE"):
            add_virtual(e)
        for e in msp.query("SOLID"):
            add_virtual(e)

        # LWPOLYLINE / POLYLINE (bulge e 3D polyline)
        for e in msp.query("LWPOLYLINE"):
            add_virtual(e)
        for e in msp.query("POLYLINE"):
            add_virtual(e)

        # Curve
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

        # HATCH boundaries
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
                                pts = list(edge.approximate(480))
                                pts_w = to_wcs_pts(h, pts)
                                add_path_from_points(pts_w)
                        except Exception:
                            pass
            except Exception:
                pass

        # Blocchi
        for ins in msp.query("INSERT"):
            add_virtual(ins)

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

    # ---------------- Quota allineata (D) ----------------
    def _create_aligned_dimension(self, a: QPointF, b: QPointF, offset: float = 15.0):
        """
        Crea una quota allineata tra i punti a e b.
        offset è la distanza della linea di quota dalle linee di estensione (in unità scena = mm DXF).
        """
        # Direzione AB e normale
        vx, vy = b.x()-a.x(), b.y()-a.y()
        L = max(1e-9, hypot(vx, vy))
        nx, ny = -vy / L, vx / L  # normale a sinistra
        # Punti proiettati sulla linea di quota
        qa = QPointF(a.x() + nx*offset, a.y() + ny*offset)
        qb = QPointF(b.x() + nx*offset, b.y() + ny*offset)

        dim_pen = QPen(QColor("#1e88e5"), 0)
        # Linee di estensione
        ext1 = QGraphicsLineItem(a.x(), a.y(), qa.x(), qa.y())
        ext1.setPen(dim_pen); ext1.setZValue(8e6); self.scene.addItem(ext1)
        ext2 = QGraphicsLineItem(b.x(), b.y(), qb.x(), qb.y())
        ext2.setPen(dim_pen); ext2.setZValue(8e6); self.scene.addItem(ext2)
        # Linea di quota
        dim_line = QGraphicsLineItem(qa.x(), qa.y(), qb.x(), qb.y())
        dim_line.setPen(dim_pen); dim_line.setZValue(8e6); self.scene.addItem(dim_line)
        # Frecce (triangolini semplici)
        def arrow_at(p: QPointF, dirx: float, diry: float, size: float = 5.0):
            # base vettoriale: direzione linea (verso interno)
            tx, ty = dirx / L, diry / L
            # ortogonale per base
            ox, oy = -ty, tx
            p1 = QPointF(p.x(), p.y())
            p2 = QPointF(p.x() - tx*size + ox*size*0.6, p.y() - ty*size + oy*size*0.6)
            p3 = QPointF(p.x() - tx*size - ox*size*0.6, p.y() - ty*size - oy*size*0.6)
            path = QPainterPath(p1); path.lineTo(p2); path.lineTo(p3); path.closeSubpath()
            tri = QGraphicsPathItem(path); tri.setPen(dim_pen); tri.setBrush(QColor("#1e88e5")); tri.setZValue(8e6)
            self.scene.addItem(tri)
        arrow_at(qa, vx, vy)
        arrow_at(qb, -vx, -vy)
        # Testo
        val = hypot(vx, vy)
        txt = QGraphicsSimpleTextItem(f"{val:.2f} mm")
        font = QFont(); font.setBold(True)
        txt.setFont(font); txt.setBrush(QColor("#000"))
        txt.setZValue(8e6)
        mid = QPointF((qa.x()+qb.x())/2.0, (qa.y()+qb.y())/2.0)
        txt.setPos(mid)
        self.scene.addItem(txt)

        self._last_dimension_value = float(val)
        self.dimensionCommitted.emit(self._last_dimension_value)

    def last_dimension_value(self) -> float:
        return float(self._last_dimension_value)

    # ---------------- Edit base (placeholders per future) ----------------
    def _selected_line_items(self) -> List[QGraphicsLineItem]:
        return [it for it in self.scene.selectedItems() if isinstance(it, QGraphicsLineItem)]

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
            if self._tool in (self.TOOL_DISTANCE, self.TOOL_PERP, self.TOOL_ANGLE, self.TOOL_DIM_ALIGNED):
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
                            self._pt_a = QPointF(s.a)
                            self._pt_b = QPointF(s.b)
                    else:
                        s = self._nearest_segment(pos_scene)
                        if s:
                            self._update_angle_overlay(self._pt_a, self._pt_b, s.a, s.b, pos_scene)
                elif self._tool == self.TOOL_DIM_ALIGNED:
                    if self._pt_a is None:
                        self._pt_a = self._snap_or_raw(pos_scene)
                    else:
                        self._pt_b = self._snap_or_raw(pos_scene)
                        # Crea quota allineata e resetta overlay
                        self._create_aligned_dimension(self._pt_a, self._pt_b, offset=15.0 / max(self._scale_factor, 1e-6))
                        self._reset_measure_overlay()
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
            if s:
                self._update_angle_overlay(self._pt_a, self._pt_b, s.a, s.b, pos_scene)
        elif self._tool == self.TOOL_DIM_ALIGNED and self._pt_a is not None and self._pt_b is None:
            # anteprima distanza (stessa di distanza lineare)
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
            self._tool = self.TOOL_DISTANCE; self._reset_measure_overlay(); e.accept(); return

        # Tools
        if k == Qt.Key_G: self._tool = self.TOOL_DISTANCE; self._reset_measure_overlay(); e.accept(); return
        if k == Qt.Key_P: self._tool = self.TOOL_PERP; self._reset_measure_overlay(); e.accept(); return
        if k == Qt.Key_O: self._tool = self.TOOL_ANGLE; self._reset_measure_overlay(); e.accept(); return
        if k == Qt.Key_D: self._tool = self.TOOL_DIM_ALIGNED; self._reset_measure_overlay(); e.accept(); return

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
    def set_tool_distance(self): self._tool = self.TOOL_DISTANCE; self._reset_measure_overlay()
    def set_tool_perpendicular(self): self._tool = self.TOOL_PERP; self._reset_measure_overlay()
    def set_tool_angle(self): self._tool = self.TOOL_ANGLE; self._reset_measure_overlay()
    def set_tool_dim_aligned(self): self._tool = self.TOOL_DIM_ALIGNED; self._reset_measure_overlay()

    def last_measure_value(self) -> float: return float(self._measure_value)
    def last_dimension_value(self) -> float: return float(self._last_dimension_value)

    def save_view_state(self) -> Dict[str, Any]:
        t: QTransform = self.transform()
        return {
            "rotation_deg": float(self._rotation_deg),
            "scale": float(self._scale_factor),
            "dx": float(t.dx()), "dy": float(t.dy()),
        }

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
