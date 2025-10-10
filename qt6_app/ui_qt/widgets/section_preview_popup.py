from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Qt, QRect
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QToolButton, QLabel, QWidget

from ui_qt.widgets.section_preview import SectionPreviewWidget


class SectionPreviewPopup(QDialog):
    """
    Popup leggero per anteprima sezione con controlli di vista:
    - Rotazione ±5°
    - Allineamento verticale al segmento più lungo
    - Posizionamento comodo rispetto a un widget (show_top_left_of)
    Dimensioni: ridotte ~30% (294x210) rispetto a 420x300 come richiesto.
    """
    def __init__(self, parent: Optional[QWidget] = None, title: str = "Sezione profilo"):
        super().__init__(parent)
        self.setWindowTitle(title)
        # Finestra "tool" che resta sopra l'app senza occupare la taskbar
        self.setWindowFlags(self.windowFlags() | Qt.Tool)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        # Toolbar
        tb = QHBoxLayout()
        tb.setSpacing(6)

        self.btn_rot_left = QToolButton(self)
        self.btn_rot_left.setText("⟲ 5°")
        self.btn_rot_right = QToolButton(self)
        self.btn_rot_right.setText("⟳ 5°")
        self.btn_align_vert = QToolButton(self)
        self.btn_align_vert.setText("Allinea verticale")
        self.lbl_hint = QLabel("Rotazione/Allineamento", self)
        self.lbl_hint.setStyleSheet("color:#444;")

        tb.addWidget(self.btn_rot_left)
        tb.addWidget(self.btn_rot_right)
        tb.addWidget(self.btn_align_vert)
        tb.addStretch(1)
        tb.addWidget(self.lbl_hint)

        root.addLayout(tb)

        # Viewer
        self.preview = SectionPreviewWidget(self)
        root.addWidget(self.preview, 1)

        # Connessioni
        self.btn_rot_left.clicked.connect(lambda: self.preview.rotate_by(-5.0))
        self.btn_rot_right.clicked.connect(lambda: self.preview.rotate_by(+5.0))
        self.btn_align_vert.clicked.connect(self.preview.align_vertical_longest)

        # Dimensioni ridotte (circa -30% di 420x300)
        self.resize(294, 210)

        # Memorizza ultimo path (facoltativo)
        self._last_path: Optional[str] = None

    def load_path(self, path: str):
        self._last_path = path
        self.preview.load_dxf(path)

    def show_top_left_of(self, widget: Optional[QWidget], margin: int = 12):
        """
        Posiziona il popup nell'angolo in alto-sinistra del widget dato (es. frame grafico),
        con un margine specificato. Se il widget non è fornito, mostra semplicemente il popup.
        """
        if not widget:
            self.show()
            return
        # Calcola in coordinate schermo la geometria target
        g = widget.frameGeometry()
        x = g.left() + margin
        y = g.top() + margin
        self.setGeometry(QRect(x, y, self.width(), self.height()))
        self.show()
