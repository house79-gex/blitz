from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Qt, QRect, QTimer
from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget
from ui_qt.widgets.section_preview import SectionPreviewWidget


class SectionPreviewPopup(QDialog):
    """
    Popup anteprima sezione:
    - Dimensionabile alla bbox (ridotto).
    - Temporaneo: auto-chiusura dopo N ms.
    - Posizionamento in alto-sinistra di un widget di riferimento.
    """
    def __init__(self, parent: Optional[QWidget] = None, title: str = "Sezione profilo"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(self.windowFlags() | Qt.Tool)  # finestra leggera
        lay = QVBoxLayout(self); lay.setContentsMargins(4, 4, 4, 4)
        self.preview = SectionPreviewWidget(self)
        lay.addWidget(self.preview, 1)
        self._auto_close_timer: Optional[QTimer] = None
        self.resize(220, 150)

    def load_path(self, path: str):
        try:
            self.preview.load_dxf(path)
        except Exception:
            self.preview.clear()

    def show_top_left_of(self, widget: QWidget, margin: int = 12, auto_hide_ms: int = 0):
        if widget:
            g = widget.frameGeometry()
            x = g.left() + margin
            y = g.top() + margin
            self.setGeometry(QRect(x, y, self.width(), self.height()))
        self.show()
        if auto_hide_ms and auto_hide_ms > 0:
            if self._auto_close_timer is None:
                self._auto_close_timer = QTimer(self)
                self._auto_close_timer.setSingleShot(True)
                self._auto_close_timer.timeout.connect(self._on_auto_close)
            self._auto_close_timer.start(int(auto_hide_ms))

    def _on_auto_close(self):
        try:
            self.close()
        except Exception:
            pass
