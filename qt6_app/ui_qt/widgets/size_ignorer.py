from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import QSize

class SizeIgnorer(QWidget):
    """
    Wrapper che ignora i minimum size del contenuto.
    Serve per impedire che le pagine impongano minime oltre lo schermo.
    """
    def __init__(self, child: QWidget, parent: QWidget | None = None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(child)

    def minimumSizeHint(self) -> QSize:
        return QSize(0, 0)

    def sizeHint(self) -> QSize:
        return QSize(640, 480)
