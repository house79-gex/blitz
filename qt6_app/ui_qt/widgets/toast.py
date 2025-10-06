from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout

class Toast(QWidget):
    def __init__(self, parent, message, bg, fg, duration_ms=2500):
        super().__init__(parent, flags=Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setObjectName("Toast")
        self.message = message
        self.bg = bg
        self.fg = fg
        self.duration_ms = duration_ms

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(message)
        self.label.setStyleSheet(f"background:{bg}; color:{fg}; padding:10px 16px; font-weight:700; border-radius:6px;")
        lay.addWidget(self.label)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.close)

    def show_at(self, x, y):
        self.adjustSize()
        self.move(x, y)
        self.show()
        self.timer.start(self.duration_ms)

class ToastManager:
    def __init__(self, parent_window: QWidget):
        self.parent = parent_window
        self.toasts: list[Toast] = []

    def show(self, message, level="info", duration=2500):
        colors = {
            "info": ("#3498db", "white"),
            "ok": ("#27ae60", "white"),
            "warn": ("#e67e22", "white"),
            "error": ("#c0392b", "white"),
        }
        bg, fg = colors.get(level, colors["info"])

        # Base position: top-right inside the window
        geo = self.parent.geometry()
        x_base = geo.x() + geo.width() - 30
        y_base = geo.y() + 70

        # Stack existing toasts
        offset_y = 0
        for t in self.toasts:
            if t.isVisible():
                t.adjustSize()
                offset_y += t.height() + 8

        toast = Toast(self.parent, message, bg, fg, duration)
        self.toasts.append(toast)

        toast.adjustSize()
        x = x_base - toast.width()
        y = y_base + offset_y
        toast.show_at(x, y)

        # Cleanup after close
        def on_closed():
            if toast in self.toasts:
                self.toasts.remove(toast)
            # Repack remaining
            offset = 0
            for t in self.toasts:
                if t.isVisible():
                    t.adjustSize()
                    tx = x_base - t.width()
                    ty = y_base + offset
                    t.move(tx, ty)
                    offset += t.height() + 8
        toast.destroyed.connect(on_closed)
