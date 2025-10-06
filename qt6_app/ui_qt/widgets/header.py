from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer
from ui_qt.theme import THEME

class Header(QFrame):
    """
    Header con titolo e banner emergenza (parità con shared.header).
    """
    def __init__(self, appwin, title: str):
        super().__init__()
        self.appwin = appwin
        self.setProperty("role", "header")
        h = QHBoxLayout(self)
        h.setContentsMargins(8, 6, 8, 6)
        h.setSpacing(8)
        self.title_label = QLabel(title)
        self.title_label.setProperty("role", "headerTitle")
        self.emg_label = QLabel("")  # mostrato solo in emergenza
        self.emg_label.setStyleSheet(f"background:{THEME.ERR}; color:white; padding:4px 8px; font-weight:700; border-radius:4px;")
        h.addWidget(self.title_label, 1, Qt.AlignCenter)
        h.addWidget(self.emg_label, 0, Qt.AlignRight)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(200)

    def set_title(self, text: str):
        self.title_label.setText(text)

    def _tick(self):
        m = self.appwin.machine
        if getattr(m, "emergency_active", False):
            self.emg_label.setText("EMERGENZA ATTIVA")
            self.emg_label.show()
        else:
            self.emg_label.hide()