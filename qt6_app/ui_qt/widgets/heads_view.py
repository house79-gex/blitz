from PySide6.QtWidgets import QFrame
from PySide6.QtGui import QPainter, QColor, QPen, QBrush
from PySide6.QtCore import Qt, QRectF

class HeadsView(QFrame):
    """
    Visualizzazione semplificata di due teste con inclinazione 0-45°.
    Legge left_head_angle e right_head_angle da machine.
    """
    def __init__(self, machine, parent=None):
        super().__init__(parent)
        self.machine = machine
        self.setMinimumHeight(180)
        self.setMinimumWidth(380)
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)

    def refresh(self):
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        w = self.width()
        h = self.height()
        cx1 = w * 0.25
        cx2 = w * 0.75
        cy  = h * 0.55
        rw, rh = 120, 28

        p.setPen(QPen(QColor("#3b4b5a"), 2))
        p.drawLine(10, int(cy), w-10, int(cy))

        def draw_head(cx, angle_deg, color="#2980b9"):
            try:
                a = float(angle_deg or 0.0)
            except Exception:
                a = 0.0
            a = max(0.0, min(45.0, a))
            p.save()
            p.translate(cx, cy)
            p.rotate(-a)
            p.setBrush(QBrush(QColor(color)))
            p.setPen(QPen(QColor("#1b2836"), 1))
            rect = QRectF(-rw/2, -rh/2, rw, rh)
            p.drawRoundedRect(rect, 6, 6)
            p.setBrush(QBrush(QColor("#e67e22")))
            p.drawEllipse(QRectF(rw/2 - 6, -6, 12, 12))
            p.restore()

        a1 = getattr(self.machine, "left_head_angle", 0.0)
        a2 = getattr(self.machine, "right_head_angle", 0.0)
        draw_head(cx1, a1, "#2980b9")
        draw_head(cx2, a2, "#9b59b6")

        p.setPen(QPen(QColor("#ecf0f1")))
        try:
            p.drawText(int(cx1 - 40), int(cy + 40), f"SX: {float(a1):.1f}°")
        except Exception:
            p.drawText(int(cx1 - 40), int(cy + 40), "SX: —")
        try:
            p.drawText(int(cx2 - 40), int(cy + 40), f"DX: {float(a2):.1f}°")
        except Exception:
            p.drawText(int(cx2 - 40), int(cy + 40), "DX: —")
        p.end()
