from __future__ import annotations
from PySide6.QtWidgets import QDialog, QVBoxLayout
from PySide6.QtCore import Qt, QRect
from ui_qt.widgets.section_preview import SectionPreviewWidget

class SectionPreviewPopup(QDialog):
    def __init__(self, parent=None, title: str = "Sezione profilo"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(self.windowFlags() | Qt.Tool)  # finestra leggera, sopra l'app
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        lay = QVBoxLayout(self); lay.setContentsMargins(4, 4, 4, 4)
        self.preview = SectionPreviewWidget(self)
        lay.addWidget(self.preview, 1)
        self.resize(420, 300)

    def load_path(self, path: str):
        try:
            self.preview.load_dxf(path)
        except Exception:
            self.preview.clear()

    def show_top_right_of(self, widget, margin: int = 16):
        if not widget:
            self.show(); return
        g = widget.frameGeometry()
        x = g.right() - self.width() - margin
        y = g.top() + margin
        self.setGeometry(QRect(x, y, self.width(), self.height()))
        self.show()
