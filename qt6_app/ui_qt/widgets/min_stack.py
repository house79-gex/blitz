from PySide6.QtWidgets import QStackedWidget
from PySide6.QtCore import QSize

class MinimalStacked(QStackedWidget):
    """
    QStackedWidget che non propaga i minimumSize dei figli al MainWindow.
    Evita mintrack eccessivi che causano warning QWindowsWindow::setGeometry.
    """
    def minimumSizeHint(self) -> QSize:
        return QSize(0, 0)

    def sizeHint(self) -> QSize:
        return QSize(640, 480)
