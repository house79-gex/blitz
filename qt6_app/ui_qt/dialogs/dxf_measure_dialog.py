from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt
from ui_qt.widgets.dxf_viewer import DxfViewerWidget

class DxfMeasureDialog(QDialog):
    def __init__(self, parent=None, path: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Misura spessore da DXF")
        self._val = 0.0

        lay = QVBoxLayout(self)

        self.viewer = DxfViewerWidget(self)
        if path:
            try:
                self.viewer.load_dxf(path)
            except Exception as e:
                pass
        lay.addWidget(self.viewer, 1)

        row = QHBoxLayout()
        self.lbl = QLabel("Spessore: — mm")
        row.addWidget(self.lbl); row.addStretch(1)
        self.btn_cancel = QPushButton("Annulla")
        self.btn_ok = QPushButton("Usa misura")
        self.btn_ok.setEnabled(False)
        row.addWidget(self.btn_cancel); row.addWidget(self.btn_ok)
        lay.addLayout(row)

        self.viewer.measurementChanged.connect(self._on_meas)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self._accept)

        self.resize(900, 600)

    def _on_meas(self, v: float):
        self._val = float(v or 0.0)
        if self._val > 0:
            self.lbl.setText(f"Spessore: {self._val:.2f} mm")
            self.btn_ok.setEnabled(True)
        else:
            self.lbl.setText("Spessore: — mm")
            self.btn_ok.setEnabled(False)

    def _accept(self):
        self.accept()

    def result_thickness_mm(self) -> float:
        return float(self._val or 0.0)
