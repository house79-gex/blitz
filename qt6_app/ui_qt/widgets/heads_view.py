from PySide6.QtWidgets import QFrame
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPolygonF
from PySide6.QtCore import Qt, QPointF

class HeadsView(QFrame):
    """
    - Scala 0..max; min pos reale = min_distance (es. 250 mm)
    - Linea teste alzata; grafica centrata nel frame
    - Testa SX a 0; DX mobile (>=min_distance)
    - Inclinazioni verso l'esterno (SX oraria, DX antioraria)
    - Carter “mezzo esagono” ancorato al segmento; gradi dentro il carter
    - Safe area orizzontale con pad per evitare tagli a 45°
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

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        w = self.width()
        h = self.height()

        # Carter dimensioni (+50%)
        seg_len = 120
        seg_thick = 6
        pivot_r = 7
        body_w = 54
        body_h = 129
        bevel  = 15

        # Offset perimetrali e safe area ai lati per evitare tagli
        edge_pad = 16
        head_pad = body_w + 20  # più ampio per sicurezza a 45°
        left_margin = edge_pad + head_pad
        right_margin = edge_pad + head_pad

        base_y = h - 64
        heads_y = base_y - 26 - 50
        usable_w = max(50, w - left_margin - right_margin)

        # Dati macchina
        min_mm = float(getattr(self.machine, "min_distance", 250.0))
        max_mm = float(getattr(self.machine, "max_cut_length", 4000.0))
        pos_mm = float(getattr(self.machine, "position_current", min_mm))
        pos_mm = max(min_mm, min(max_mm, pos_mm))
        ang_sx = max(0.0, min(45.0, float(getattr(self.machine, "left_head_angle", 0.0) or 0.0)))
        ang_dx = max(0.0, min(45.0, float(getattr(self.machine, "right_head_angle", 0.0) or 0.0)))

        # Scala 0..max
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

        p.setPen(QPen(QColor("#9fb3c7")))
        p.drawText(int(left_margin), int(heads_y - 48), f"0–{int(max_mm)} mm (min pos. {int(min_mm)})")

        # Linea teste sopra scala
        p.setPen(QPen(QColor("#4a6076"), 1))
        p.drawLine(int(left_margin), int(heads_y), int(left_margin + usable_w), int(heads_y))

        # Pivot SX (0) e DX (pos attuale)
        x_sx = x_at(0.0)
        x_dx = x_at(pos_mm)

        def draw_head(x: float, angle_deg: float, outward_left: bool, color: str):
            # pivot
            p.setBrush(QBrush(QColor(color))); p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(x, heads_y), pivot_r, pivot_r)

            p.save()
            p.translate(x, heads_y)
            p.rotate(-angle_deg if outward_left else +angle_deg)

            # Poligono carter “mezzo esagono”
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

            # Lama (segmento interno)
            pen = QPen(QColor(color)); pen.setWidth(seg_thick)
            p.setPen(pen)
            p.drawLine(0, 0, 0, -seg_len)

            # Gradi all'interno carter
            p.setPen(QPen(QColor("#ecf0f1")))
            text_x = -body_w/2 + 6 if outward_left else 6
            text_y = -body_h/2 + 6
            p.drawText(int(text_x), int(text_y), f"{angle_deg:.0f}°")

            p.restore()

        # Disegno teste
        draw_head(x_sx, ang_sx, outward_left=True,  color="#2980b9")  # SX
        draw_head(x_dx, ang_dx, outward_left=False, color="#9b59b6")  # DX
