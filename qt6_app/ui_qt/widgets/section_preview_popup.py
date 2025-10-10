from __future__ import annotations
from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget
from PySide6.QtCore import Qt, QRect
from ui_qt.widgets.section_preview import SectionPreviewWidget


class SectionPreviewPopup(QDialog):
    def __init__(self, parent=None, title: str = "Sezione profilo"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(self.windowFlags() | Qt.Tool)  # finestra leggera
        lay = QVBoxLayout(self); lay.setContentsMargins(4, 4, 4, 4)
        self.preview = SectionPreviewWidget(self)
        lay.addWidget(self.preview, 1)
        # dimensione ridotta del ~30% rispetto a 420x300
        self.resize(294, 210)

    def load_path(self, path: str):
        try:
            self.preview.load_dxf(path)
        except Exception:
            self.preview.clear()

    def show_top_left_of(self, widget: QWidget, margin: int = 12):
        if not widget:
            self.show()
            return
        g = widget.frameGeometry()
        x = g.left() + margin
        y = g.top() + margin
        self.setGeometry(QRect(x, y, self.width(), self.height()))
        self.show()
