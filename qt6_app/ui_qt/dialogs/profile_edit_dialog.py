from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton
from PySide6.QtCore import Qt

class ProfileEditDialog(QDialog):
    def __init__(self, parent=None, default_name="", default_thickness=0.0):
        super().__init__(parent)
        self.setWindowTitle("Salva profilo")
        self.result_name = None
        self.result_thickness = None

        lay = QVBoxLayout(self)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Nome profilo:"))
        self.edit_name = QLineEdit()
        self.edit_name.setText(str(default_name or ""))
        row1.addWidget(self.edit_name, 1)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Spessore (mm):"))
        self.edit_th = QLineEdit()
        self.edit_th.setText(str(default_thickness or 0.0))
        row2.addWidget(self.edit_th, 1)
        lay.addLayout(row2)

        btns = QHBoxLayout()
        self.btn_ok = QPushButton("OK")
        self.btn_cancel = QPushButton("Annulla")
        self.btn_ok.clicked.connect(self._accept)
        self.btn_cancel.clicked.connect(self.reject)
        btns.addWidget(self.btn_cancel)
        btns.addStretch(1)
        btns.addWidget(self.btn_ok)
        lay.addLayout(btns)

        self.setMinimumWidth(320)

    def _accept(self):
        name = (self.edit_name.text() or "").strip()
        try:
            th = float((self.edit_th.text() or "0").replace(",", "."))
        except Exception:
            th = 0.0
        if not name:
            return
        self.result_name = name
        self.result_thickness = th
        self.accept()
