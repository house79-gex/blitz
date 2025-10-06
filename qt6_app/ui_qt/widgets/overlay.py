from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout

class CenterMessageOverlay(QWidget):
    """
    Overlay centrale come in Tk.
    """
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setStyleSheet("background: rgba(0,0,0,0.25);")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setAlignment(Qt.AlignCenter)
        self.label = QLabel("")
        self.label.setStyleSheet("background:#1e272e; color:white; padding:14px 20px; border-radius:8px; font-weight:700;")
        lay.addWidget(self.label)
        self.hide()

    def show_message(self, text: str, duration_ms: int = 1800):
        self.label.setText(text)
        self.resize(self.parentWidget().size())
        self.move(self.parentWidget().pos())
        self.show()
        QTimer.singleShot(duration_ms, self.hide)