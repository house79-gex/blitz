from PySide6.QtWidgets import QFrame
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont
from PySide6.QtCore import Qt, QRectF, QPointF

class HeadsView(QFrame):
    """
    Visualizzazione teste:
    - Scala quotata 250..4000 mm
    - Testa SX: fissa a min_distance (pivot alla base), inclinazione 0-45° verso sinistra
    - Testa DX: mobile su position_current (pivot alla base), inclinazione 0-45° verso destra
    - Il pallino (pivot) rappresenta l'interno lame => quota di posizionamento
    """
    def __init__(self, machine, parent=None):
        super().__init__(parent)
        self.machine = machine
        self.setMinimumHeight(260)
        self.setMinimumWidth(620)
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
        left_margin = 70
        right_margin = 24
        top_margin = 10
        base_y = h - 60  # linea scala
        usable_w = max(50, w - left_margin - right_margin)

        # Dati macchina
        min_mm = float(getattr(self.machine, "min_distance", 250.0))
        max_mm = float(getattr(self.machine, "max_cut_length", 4000.0))
        pos_mm = float(getattr(self.machine, "position_current", min_mm))
        pos_mm = max(min_mm, min(max_mm, pos_mm))
        ang_sx = float(getattr(self.machine, "left_head_angle", 0.0) or 0.0)
        ang_dx = float(getattr(self.machine, "right_head_angle", 0.0) or 0.0)
        ang_sx = max(0.0, min(45.0, ang_sx))
        ang_dx = max(0.0, min(45.0, ang_dx))

        # Mapper mm -> x pixel
        def x_at(mm: float) -> float:
            if max_mm <= min_mm:
                return left_margin
            f = (mm - min_mm) / (max_mm - min_mm)
            return left_margin + f * usable_w

        # Disegno scala
        p.setPen(QPen(QColor("#3b4b5a"), 2))
        p.drawLine(int(left_margin), int(base_y), int(left_margin + usable_w), int(base_y))

        # Tacche e label principali
        p.setPen(QPen(QColor("#5c738a"), 1))
        font = QFont()
        font.setPointSizeF(max(8.0, self.font().pointSizeF() - 1))
        p.setFont(font)

        ticks = [min_mm, 1000, 2000, 3000, max_mm]
        ticks = sorted(set([t for t in ticks if min_mm <= t <= max_mm]))
        for t in ticks:
            x = x_at(t)
            p.drawLine(int(x), int(base_y), int(x), int(base_y - 12))
            label = f"{int(t)}"
            tw = p.fontMetrics().horizontalAdvance(label)
            p.drawText(int(x - tw/2), int(base_y - 16), label)

        # Etichetta range
        rng = f"{int(min_mm)}–{int(max_mm)} mm"
        p.setPen(QPen(QColor("#9fb3c7")))
        p.drawText(int(left_margin), int(top_margin + 4), rng)

        # Parametri grafici teste
        seg_len = 110
        seg_thick = 6
        pivot_r = 7

        def draw_head_segment(x: float, angle_deg: float, tilt_left: bool, color: str):
            # pivot base (pallino = fulcro)
            p.setBrush(QBrush(QColor(color)))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(x, base_y), pivot_r, pivot_r)

            # segmento lama dal pivot verso l'alto
            p.save()
            p.translate(x, base_y)
            rot = angle_deg if tilt_left else -angle_deg  # + = CCW (sinistra)
            p.rotate(rot)
            # linea verticale che sale (direzione -Y)
            pen = QPen(QColor(color))
            pen.setWidth(seg_thick)
            p.setPen(pen)
            p.drawLine(0, 0, 0, -seg_len)
            p.restore()

        # Testa SX: fissa a min_mm, inclinazione a sinistra
        x_sx = x_at(min_mm)
        draw_head_segment(x_sx, ang_sx, tilt_left=True, color="#2980b9")

        # Testa DX: mobile sulla quota attuale (om-ing a 250)
        x_dx = x_at(pos_mm)
        draw_head_segment(x_dx, ang_dx, tilt_left=False, color="#9b59b6")

        # Etichette
        p.setPen(QPen(QColor("#ecf0f1")))
        p.drawText(int(x_sx - 40), int(base_y + 20), f"SX: {ang_sx:.1f}°")
        p.drawText(int(x_dx - 40), int(base_y + 20), f"DX: {ang_dx:.1f}° ({int(pos_mm)} mm)")

        p.end()
