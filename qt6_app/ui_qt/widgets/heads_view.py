from PySide6.QtWidgets import QFrame
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont
from PySide6.QtCore import Qt, QRectF, QPointF

class HeadsView(QFrame):
    """
    Visualizzazione teste:
    - Scala quotata 250..4000 mm (linea base)
    - Linea teste sopra la scala per evitare accavallamenti
    - Testa SX: fissa a 0 mm (pivot separato, a sinistra della scala)
    - Testa DX: mobile su position_current (min 250 mm) mappata sulla scala
    - Le teste si inclinano verso l’esterno (SX ruota in senso orario, DX in senso antiorario)
    - Il pallino alla base è il fulcro (interno lame = quota di posizionamento)
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
        left_margin = 80
        right_margin = 24
        top_margin = 10
        base_y = h - 60                  # linea scala (250..4000)
        heads_y = base_y - 24            # linea teste (sopra la scala)
        usable_w = max(50, w - left_margin - right_margin)

        # Dati macchina
        min_mm = float(getattr(self.machine, "min_distance", 250.0))  # 250
        max_mm = float(getattr(self.machine, "max_cut_length", 4000.0))
        pos_mm = float(getattr(self.machine, "position_current", min_mm))
        pos_mm = max(min_mm, min(max_mm, pos_mm))
        ang_sx = float(getattr(self.machine, "left_head_angle", 0.0) or 0.0)
        ang_dx = float(getattr(self.machine, "right_head_angle", 0.0) or 0.0)
        ang_sx = max(0.0, min(45.0, ang_sx))
        ang_dx = max(0.0, min(45.0, ang_dx))

        # Mapper mm -> x pixel (scala 250..4000)
        def x_at(mm: float) -> float:
            if max_mm <= min_mm:
                return left_margin
            f = (mm - min_mm) / (max_mm - min_mm)
            return left_margin + f * usable_w

        # ----- Disegna scala base -----
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

        # ----- Linea teste (sopra scala) -----
        p.setPen(QPen(QColor("#4a6076"), 1))
        p.drawLine(int(left_margin), int(heads_y), int(left_margin + usable_w), int(heads_y))

        # Parametri grafici segmenti/teste
        seg_len = 110
        seg_thick = 6
        pivot_r = 7

        # Posizione pivot SX: 0 mm (fuori dalla scala a sinistra)
        zero_gap_px = 28  # distanza visiva tra 0 e inizio scala (250)
        x_sx = left_margin - zero_gap_px

        # Posizione pivot DX: quota attuale mappata su scala
        x_dx = x_at(pos_mm)

        def draw_head_segment(x: float, angle_deg: float, outward_left: bool, color: str):
            # pivot (pallino) sulla linea teste
            p.setBrush(QBrush(QColor(color)))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(x, heads_y), pivot_r, pivot_r)

            # segmento lama dal pivot verso l'alto
            p.save()
            p.translate(x, heads_y)
            # Le teste si inclinano verso l'ESTERNO:
            # - SX: ruota in senso orario (negativo)
            # - DX: ruota in senso antiorario (positivo)
            rot = -angle_deg if outward_left else +angle_deg
            p.rotate(rot)
            pen = QPen(QColor(color))
            pen.setWidth(seg_thick)
            p.setPen(pen)
            p.drawLine(0, 0, 0, -seg_len)
            p.restore()

        # Disegno teste
        draw_head_segment(x_sx, ang_sx, outward_left=True,  color="#2980b9")  # SX
        draw_head_segment(x_dx, ang_dx, outward_left=False, color="#9b59b6")  # DX

        # Etichette
        p.setPen(QPen(QColor("#ecf0f1")))
        p.drawText(int(x_sx - 40), int(heads_y + 22), f"SX: {ang_sx:.1f}° (0)")
        p.drawText(int(x_dx - 40), int(heads_y + 22), f"DX: {ang_dx:.1f}° ({int(pos_mm)} mm)")

        p.end()
