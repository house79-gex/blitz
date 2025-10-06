from PySide6.QtWidgets import QFrame
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont
from PySide6.QtCore import Qt, QRectF

class HeadsView(QFrame):
    """
    Visualizzazione teste:
    - Scala quotata 250..4000 mm
    - Testa SX: fissa sullo zero corsa (min_distance), sopra la scala, fulcro in basso, inclinazione 0-45° verso sinistra
    - Testa DX: speculare e mobile lungo la scala (position_current), fulcro in basso, inclinazione 0-45° verso destra
    """
    def __init__(self, machine, parent=None):
        super().__init__(parent)
        self.machine = machine
        self.setMinimumHeight(220)
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
        left_margin = 60
        right_margin = 30
        top_margin = 20
        base_y = h - 50  # linea della scala
        usable_w = max(50, w - left_margin - right_margin)

        # Dati macchina
        min_mm = float(getattr(self.machine, "min_distance", 250.0))
        max_mm = float(getattr(self.machine, "max_cut_length", 4000.0))
        pos_mm = float(getattr(self.machine, "position_current", min_mm))
        pos_mm = max(min_mm, min(max_mm, pos_mm))
        ang_sx = float(getattr(self.machine, "left_head_angle", 0.0) or 0.0)
        ang_dx = float(getattr(self.machine, "right_head_angle", 0.0) or 0.0)
        # Clamp angoli 0..45
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

        # Tacche principali e etichette
        p.setPen(QPen(QColor("#5c738a"), 1))
        font = QFont()
        font.setPointSizeF(max(8.0, self.font().pointSizeF() - 1))
        p.setFont(font)

        ticks = [min_mm, 1000, 2000, 3000, max_mm]
        # Assicura unicità e ordine
        ticks = sorted(set([min_mm, max_mm] + [t for t in ticks if min_mm <= t <= max_mm]))
        for t in ticks:
            x = x_at(t)
            p.drawLine(int(x), int(base_y), int(x), int(base_y - 12))
            label = f"{int(t)}"
            tw = p.fontMetrics().horizontalAdvance(label)
            p.drawText(int(x - tw/2), int(base_y - 16), label)

        # Etichetta range
        rng = f"{int(min_mm)}–{int(max_mm)} mm"
        p.setPen(QPen(QColor("#9fb3c7")))
        p.drawText(int(left_margin), int(top_margin), rng)

        # Parametri grafici teste
        head_w = 26
        head_h = 90

        # Funzione per disegnare una testa con pivot in basso
        def draw_head(x: float, angle_deg: float, color_body: str, tilt_left: bool):
            p.save()
            p.translate(x, base_y)  # pivot in basso, sulla linea scala
            # rotazione: positiva = antioraria (sinistra). Per la destra, ruota in senso orario (negativa).
            rot = angle_deg if tilt_left else -angle_deg
            p.rotate(rot)
            # Corpo: rettangolo che sale dalla linea scala verso l'alto
            p.setBrush(QBrush(QColor(color_body)))
            p.setPen(QPen(QColor("#1b2836"), 1))
            rect = QRectF(-head_w/2, -head_h, head_w, head_h)
            p.drawRoundedRect(rect, 4, 4)
            # Indicatore punta
            p.setBrush(QBrush(QColor("#e67e22")))
            p.drawEllipse(QRectF(-5, -head_h - 8, 10, 10))
            p.restore()

        # Testa SX: fissa al min_mm
        x_sx = x_at(min_mm)
        draw_head(x_sx, ang_sx, "#2980b9", tilt_left=True)

        # Testa DX: mobile su position_current
        x_dx = x_at(pos_mm)
        draw_head(x_dx, ang_dx, "#9b59b6", tilt_left=False)

        # Etichette SX/DX
        p.setPen(QPen(QColor("#ecf0f1")))
        p.drawText(int(x_sx - 40), int(base_y + 18), f"SX: {ang_sx:.1f}°")
        p.drawText(int(x_dx - 40), int(base_y + 18), f"DX: {ang_dx:.1f}°")

        p.end()
