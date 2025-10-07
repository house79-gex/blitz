from PySide6.QtWidgets import QFrame
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPolygonF
from PySide6.QtCore import Qt, QRectF, QPointF

class HeadsView(QFrame):
    """
    Visualizzazione teste:
    - Scala 0..max (linea base); min posizionamento reale = min_distance (es. 250 mm)
    - Linea teste sopra la scala (alzata di +50 px per evitare accavallamenti)
    - Testa SX: fissa a 0 mm (pivot a sinistra su scala)
    - Testa DX: mobile su position_current (vincolo min_distance)
    - Inclinazione verso l'esterno (SX oraria, DX antioraria)
    - Carter: “mezzo esagono” con lato interno coincidente con il segmento (lama)
    - All’interno del carter è mostrato l’angolo in gradi; nessuna etichetta esterna
    """
    def __init__(self, machine, parent=None):
        super().__init__(parent)
        self.machine = machine
        # Più alta per carter ingranditi (+50%)
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

        # Margini e dimensioni scala
        left_margin = 80
        right_margin = 24
        top_margin = 6
        base_y = h - 64                  # linea scala (0..max)
        heads_y = base_y - 26 - 50       # linea teste (sopra la scala, +50 px)
        usable_w = max(50, w - left_margin - right_margin)

        # Dati macchina
        min_mm = float(getattr(self.machine, "min_distance", 250.0))   # vincolo reale (es. 250)
        max_mm = float(getattr(self.machine, "max_cut_length", 4000.0))
        pos_mm = float(getattr(self.machine, "position_current", min_mm))
        pos_mm = max(min_mm, min(max_mm, pos_mm))
        ang_sx = float(getattr(self.machine, "left_head_angle", 0.0) or 0.0)
        ang_dx = float(getattr(self.machine, "right_head_angle", 0.0) or 0.0)
        ang_sx = max(0.0, min(45.0, ang_sx))
        ang_dx = max(0.0, min(45.0, ang_dx))

        # Mapper mm -> x pixel (scala 0..max)
        scale_min = 0.0
        scale_max = max_mm
        def x_at(mm: float) -> float:
            if scale_max <= scale_min:
                return left_margin
            f = (mm - scale_min) / (scale_max - scale_min)
            return left_margin + f * usable_w

        # ----- Scala base 0..max -----
        p.setPen(QPen(QColor("#3b4b5a"), 2))
        p.drawLine(int(left_margin), int(base_y), int(left_margin + usable_w), int(base_y))

        # Tacche e label
        p.setPen(QPen(QColor("#5c738a"), 1))
        font = QFont()
        font.setPointSizeF(max(8.0, self.font().pointSizeF() - 1))
        p.setFont(font)
        ticks = [0, 1000, 2000, 3000, int(max_mm)]
        ticks = sorted(set([t for t in ticks if scale_min <= t <= scale_max]))
        for t in ticks:
            x = x_at(t)
            p.drawLine(int(x), int(base_y), int(x), int(base_y - 12))
            label = f"{int(t)}"
            tw = p.fontMetrics().horizontalAdvance(label)
            p.drawText(int(x - tw/2), int(base_y - 16), label)

        p.setPen(QPen(QColor("#9fb3c7")))
        p.drawText(int(left_margin), int(top_margin + 4), f"0–{int(max_mm)} mm (min pos. {int(min_mm)})")

        # ----- Linea teste (sopra scala) -----
        p.setPen(QPen(QColor("#4a6076"), 1))
        p.drawLine(int(left_margin), int(heads_y), int(left_margin + usable_w), int(heads_y))

        # Parametri grafici segmenti e carter (+50%)
        seg_len = 120
        seg_thick = 6
        pivot_r = 7
        body_w = 54
        body_h = 129
        bevel  = 15

        # Pivot SX e DX
        x_sx = x_at(0.0)        # SX a 0 mm
        x_dx = x_at(pos_mm)     # DX a quota attuale (>= min_mm)

        def draw_head(x: float, angle_deg: float, outward_left: bool, color: str):
            # pivot (pallino) sulla linea teste
            p.setBrush(QBrush(QColor(color)))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(x, heads_y), pivot_r, pivot_r)

            p.save()
            p.translate(x, heads_y)
            rot = -angle_deg if outward_left else +angle_deg  # SX oraria (esterna), DX antioraria (esterna)
            p.rotate(rot)

            # Carter “mezzo esagono”, lato interno coincidente con il segmento (x=0)
            if outward_left:
                pts = [
                    QPointF(0, 0),                             # inner-bottom
                    QPointF(-(body_w - bevel), 0),             # bottom edge
                    QPointF(-body_w, -bevel),                  # lower bevel 45°
                    QPointF(-body_w, -(body_h - bevel)),       # outer side
                    QPointF(-(body_w - bevel), -body_h),       # upper bevel 45°
                    QPointF(0, -body_h),                       # inner-top
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

            # Lama (segmento) sul lato interno
            pen = QPen(QColor(color))
            pen.setWidth(seg_thick)
            p.setPen(pen)
            p.drawLine(0, 0, 0, -seg_len)

            # Gradi all'interno del carter (centrati circa a metà)
            p.setPen(QPen(QColor("#ecf0f1")))
            text_x = -body_w/2 + 6 if outward_left else 6
            text_y = -body_h/2 + 6
            p.drawText(int(text_x), int(text_y), f"{angle_deg:.0f}°")

            p.restore()

        # Disegno teste
        draw_head(x_sx, ang_sx, outward_left=True,  color="#2980b9")  # SX
        draw_head(x_dx, ang_dx, outward_left=False, color="#9b59b6")  # DX
