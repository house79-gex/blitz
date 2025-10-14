from __future__ import annotations
from typing import Optional, Dict, Any, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QGridLayout, QHBoxLayout, QLabel,
    QComboBox, QLineEdit, QPushButton
)


class ProfileSaveDialog(QDialog):
    """
    Finestra modale semplice per salvare/modificare un profilo:
    - Seleziona un profilo esistente o digita un nome nuovo.
    - Spessore precompilabile (es. dall'ultima quota dal CAD).
    - Pulsante "Applica" salva senza chiudere. "Chiudi" per uscire.
    """
    def __init__(self, profiles_store, parent=None, default_name: str = "", default_thickness: float = 0.0):
        super().__init__(parent)
        self.setWindowTitle("Salva/Modifica profilo")
        self.setModal(True)
        self.profiles_store = profiles_store

        root = QVBoxLayout(self)
        form = QGridLayout()
        row = 0

        form.addWidget(QLabel("Profilo esistente:"), row, 0)
        self.cmb_existing = QComboBox()
        self._names = self._load_names()
        self.cmb_existing.addItem("— Nuovo —")
        for n in sorted(self._names):
            self.cmb_existing.addItem(n)
        form.addWidget(self.cmb_existing, row, 1)
        row += 1

        form.addWidget(QLabel("Nome profilo:"), row, 0)
        self.edit_name = QLineEdit()
        form.addWidget(self.edit_name, row, 1)
        row += 1

        form.addWidget(QLabel("Spessore (mm):"), row, 0)
        self.edit_th = QLineEdit()
        self.edit_th.setPlaceholderText("0.0")
        form.addWidget(self.edit_th, row, 1)
        row += 1

        root.addLayout(form)

        # Pulsanti
        btns = QHBoxLayout()
        self.btn_apply = QPushButton("Applica")
        self.btn_close = QPushButton("Chiudi")
        btns.addWidget(self.btn_apply)
        btns.addWidget(self.btn_close)
        btns.addStretch(1)
        root.addLayout(btns)

        # Wiring
        self.cmb_existing.currentTextChanged.connect(self._on_existing_changed)
        self.btn_apply.clicked.connect(self._do_apply)
        self.btn_close.clicked.connect(self.accept)

        # Precompila
        if default_name:
            self.edit_name.setText(default_name)
            idx = self.cmb_existing.findText(default_name)
            if idx >= 0:
                self.cmb_existing.setCurrentIndex(idx)
        self.edit_th.setText(f"{float(default_thickness):.3f}".rstrip("0").rstrip("."))

    def _load_names(self) -> List[str]:
        names: List[str] = []
        try:
            rows = self.profiles_store.list_profiles()
            for r in rows:
                n = str(r.get("name") or "").strip()
                if n:
                    names.append(n)
        except Exception:
            pass
        return names

    def _on_existing_changed(self, text: str):
        name = (text or "").strip()
        if name == "— Nuovo —" or not name:
            return
        # Precarica spessore del profilo selezionato
        try:
            rows = self.profiles_store.list_profiles()
            for r in rows:
                if str(r.get("name") or "").strip() == name:
                    th = float(r.get("thickness") or 0.0)
                    self.edit_name.setText(name)
                    self.edit_th.setText(f"{th:.3f}".rstrip("0").rstrip("."))
                    break
        except Exception:
            pass

    def _do_apply(self):
        name = (self.edit_name.text() or "").strip()
        if not name:
            return
        try:
            th = float((self.edit_th.text() or "0").replace(",", "."))
        except Exception:
            th = 0.0
        try:
            self.profiles_store.upsert_profile(name, th)
        except Exception:
            pass
