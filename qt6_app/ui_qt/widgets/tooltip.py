from PySide6.QtCore import QObject, QEvent, QTimer, QPoint
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QToolTip

class Tooltip(QObject):
    """
    Tooltip minimale con delay e follow del mouse (parità con Tk tooltip).
    Usa QToolTip e un event filter per mostrare/sparire.
    """
    def __init__(self, widget, text: str, delay_ms: int = 350, offset=(18, 20)):
        super().__init__(widget)
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self.offset = offset
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._show)
        self.widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.widget:
            if event.type() == QEvent.Enter:
                self._timer.start(self.delay_ms)
            elif event.type() in (QEvent.Leave, QEvent.MouseButtonPress):
                self._timer.stop()
                QToolTip.hideText()
            elif event.type() == QEvent.MouseMove:
                if QToolTip.isVisible():
                    self._reposition()
        return super().eventFilter(obj, event)

    def _show(self):
        if not self.text:
            return
        pos = self._calc_pos()
        QToolTip.showText(pos, self.text, self.widget)

    def _reposition(self):
        pos = self._calc_pos()
        # In Qt non c'è API per muovere un tooltip già mostrato;
        # richiamiamo showText con stessa stringa per aggiornare posizione
        QToolTip.showText(pos, self.text, self.widget)

    def _calc_pos(self):
        cur = QCursor.pos()
        ox, oy = self.offset
        return QPoint(cur.x() + ox, cur.y() + oy)