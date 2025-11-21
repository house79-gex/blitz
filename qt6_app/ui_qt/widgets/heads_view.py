from PySide6.QtWidgets import QFrame
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPolygonF
from PySide6.QtCore import Qt, QPointF
import math

class HeadsView(QFrame):
    """
    Vista grafica teste:
    - Ora compatibile con MachineAdapter (get_position / get_state).
    - Fallback su attributi legacy (position_current / encoder_position).
    """

    def __init__(self, machine, parent=None):
        super().__init__(parent)
        self.machine = machine
        self.setMinimumHeight(360)
        self.setMinimumWidth(560)
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)

    def refresh(self):
        self.update()

    # --- Helpers nuova logica ---
    def _get_position_mm(self):
        # Adapter style
        if hasattr(self.machine, "get_position") and callable(getattr(self.machine, "get_position")):
            try:
                v = self.machine.get_position()
                if v is not None:
                    return float(v)
            except Exception:
                pass
        # Legacy attributes
        for name in ("encoder_position", "position_current"):
            if hasattr(self.machine, name):
                try:
                    return float(getattr(self.machine, name))
                except Exception:
                    pass
        return float(getattr(self.machine, "min_distance", 250.0))

    def _get_angle(self, left=True):
        # Adapter state
        if hasattr(self.machine, "get_state") and callable(getattr(self.machine, "get_state")):
            try:
                st = self.machine.get_state()
                ha = st.get("head_angles") or {}
                return float(ha.get("sx" if left else "dx", 0.0))
            except Exception:
                pass
        # Legacy attribute
        attr = "left_head_angle" if left else "right_head_angle"
        try:
            return float(getattr(self.machine, attr, 0.0) or 0.0)
        except Exception:
            return 0.0

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w = self.width()
        h = self.height()

        # Dimensioni carter/segmento
        seg_len   = 120
        seg_thick = 6
        pivot_r   = 7
        body_w    = 54
        body_h    = 129
        bevel     = 15

        # Dati macchina (compat)
        min_mm = float(getattr(self.machine, "min_distance", 250.0))
        max_mm = float(getattr(self.machine, "max_cut_length", 4000.0))
        pos_mm = self._get_position_mm()
        pos_mm = max(min_mm, min(max_mm, pos_mm))
        ang_sx = max(0.0, min(45.0, self._get_angle(left=True)))
        ang_dx = max(0.0, min(45.0, self._get_angle(left=False)))

        # Safe area per 45°
        max_theta = math.radians(45.0)
        pad_x = int(body_w * math.cos(max_theta) + body_h * math.sin(max_theta)) + pivot_r + 8
        edge_pad = 16
        left_margin  = edge_pad + pad_x
        right_margin = edge_pad + pad_x

        heads_to_scale_gap = 76
        block_h = body_h + heads_to_scale_gap
        center_y = h / 2.0
        heads_y = int(center_y - (block_h / 2.0) + body_h)   # pivot base
        base_y  = heads_y + heads_to_scale_gap               # linea scala

        usable_w = max(50, w - left_margin - right_margin)
        scale_min, scale_max = 0.0, max_mm

        def x_at(mm: float) -> float:
            if scale_max <= scale_min:
                return left_margin
            f = (mm - scale_min) / (scale_max - scale_min)
            return left_margin + f * usable_w

        # Scala base
        p.setPen(QPen(QColor("#3b4b5a"), 2))
        p.drawLine(int(left_margin), int(base_y), int(left_margin + usable_w), int(base_y))

        # Tacche
        p.setPen(QPen(QColor("#5c738a"), 1))
        font = QFont(); font.setPointSizeF(max(8.0, self.font().pointSizeF() - 1))
        p.setFont(font)
        for t in (0, 1000, 2000, 3000, int(max_mm)):
            x = x_at(t)
            p.drawLine(int(x), int(base_y), int(x), int(base_y - 12))
            label = f"{int(t)}"
            tw = p.fontMetrics().horizontalAdvance(label)
            p.drawText(int(x - tw/2), int(base_y - 16), label)

        # Linea teste
        p.setPen(QPen(QColor("#4a6076"), 1))
        p.drawLine(int(left_margin), int(heads_y), int(left_margin + usable_w), int(heads_y))

        # Pivot SX (0) e DX (posizione)
        x_sx = x_at(0.0)
        x_dx = x_at(pos_mm)

        def draw_head(x: float, angle_deg: float, outward_left: bool, color: str):
            p.setBrush(QBrush(QColor(color))); p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(x, heads_y), pivot_r, pivot_r)

            p.save()
            p.translate(x, heads_y)
            p.rotate(-angle_deg if outward_left else +angle_deg)

            if outward_left:
                pts = [
                    QPointF(0, 0),
                    QPointF(-(body_w - bevel), 0),
                    QPointF(-body_w, -bevel),
                    QPointF(-body_w, -(body_h - bevel)),
                    QPointF(-(body_w - bevel), -body_h),
                    QPointF(0, -body_h),
                ]
            else:
                pts = [
                    QPointF(0, 0),
                    QPointF(body_w - bevel, 0),
                    QPointF(body_w, -bevel),
                    QPointF(body_w, -(body_h - bevel)),
                    QPointF(body_w - bevel, -body_h),
                    QPointF(0, -body_h),
                ]
            poly = QPolygonF(pts)
            p.setBrush(QBrush(QColor("#34495e")))
            p.setPen(QPen(QColor("#95a5a6"), 1))
            p.drawPolygon(poly)

            pen = QPen(QColor(color)); pen.setWidth(seg_thick)
            p.setPen(pen)
            p.drawLine(0, 0, 0, -seg_len)

            p.setPen(QPen(QColor("#ecf0f1")))
            text_x = -body_w/2 + 6 if outward_left else 6
            text_y = -body_h/2 + 6
            p.drawText(int(text_x), int(text_y), f"{angle_deg:.1f}°")

            p.restore()

        # Disegno teste
        draw_head(x_sx, ang_sx, outward_left=True,  color="#2980b9")
        draw_head(x_dx, ang_dx, outward_left=False, color="#9b59b6")
