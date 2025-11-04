from __future__ import annotations
from typing import Optional

from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextEdit, QHBoxLayout, QPushButton
from PySide6.QtCore import Qt


class LogViewerDialog(QDialog):
    """
    Finestra separata per il registro (nascondibile).
    """
    def __init__(self, parent, title: str = "Registro"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(False)
        self.resize(720, 420)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.addWidget(QLabel("Registro eventi"))
        self.txt = QTextEdit()
        self.txt.setReadOnly(True)
        root.addWidget(self.txt, 1)
        btns = QHBoxLayout()
        btn_clear = QPushButton("Pulisci"); btn_clear.clicked.connect(self.txt.clear)
        btn_close = QPushButton("Chiudi"); btn_close.clicked.connect(self.close)
        btns.addStretch(1); btns.addWidget(btn_clear); btns.addWidget(btn_close)
        root.addLayout(btns)

    def append(self, s: str):
        try:
            self.txt.append(s)
        except Exception:
            pass
