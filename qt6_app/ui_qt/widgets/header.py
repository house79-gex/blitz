from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSizePolicy, QGridLayout
from PySide6.QtCore import Qt

OK = "#2ecc71"
WARN = "#f39c12"
ERR = "#e74c3c"
MUTED = "#7f8c8d"
TEXT = "#2c3e50"
PANEL_BG = "#f7f9fb"
BORDER = "#dfe6e9"

class StatusPanel(QWidget):
    """
    Pannello stato compatto.
    Mostra:
    - EMG (rosso/verde)
    - Homed/Azzerata (verde/giallo)
    - Freno (BLOCCATO/SBLOCCATO con colori evidenti)
    - Frizione (INSERITA/DISINSERITA)
    - Quota (se disponibile)
    """
    def __init__(self, machine_state, title="STATO", parent=None):
        super().__init__(parent)
        self.m = machine_state
        self._build(title)

    def _build(self, title: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        title_lbl = QLabel(title.upper())
        title_lbl.setStyleSheet("font-weight: 800; color: #34495e;")
        root.addWidget(title_lbl, 0, alignment=Qt.AlignLeft)

        card = QFrame()
        card.setStyleSheet(f"QFrame{{background:{PANEL_BG}; border:1px solid {BORDER}; border-radius:10px;}}")
        root.addWidget(card, 1)

        grid = QGridLayout(card)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)

        # Labels
        self._emg = QLabel("-")
        self._homed = QLabel("-")
        self._brake = QLabel("-")
        self._clutch = QLabel("-")
        self._enc = QLabel("-")

        font_l = "font-weight:700; color:#2c3e50;"
        font_v = "font-weight:800;"

        def add_row(r, name, w: QLabel):
            lbl = QLabel(name)
            lbl.setStyleSheet(font_l)
            w.setStyleSheet(font_v)
            grid.addWidget(lbl, r, 0, alignment=Qt.AlignLeft)
            grid.addWidget(w, r, 1, alignment=Qt.AlignRight)

        add_row(0, "EMG", self._emg)
        add_row(1, "HOMED", self._homed)
        add_row(2, "FRENO", self._brake)
        add_row(3, "FRIZIONE", self._clutch)
        add_row(4, "QUOTA", self._enc)

        root.addStretch(1)

    def _bool_attr(self, *names, default=False):
        for n in names:
            if hasattr(self.m, n):
                try:
                    return bool(getattr(self.m, n))
                except Exception:
                    pass
        return default

    def _num_attr(self, *names):
        for n in names:
            if hasattr(self.m, n):
                try:
                    return float(getattr(self.m, n))
                except Exception:
                    pass
        return None

    def refresh(self):
        # EMG
        emg = self._bool_attr("emergency_active", "emg_active", "is_emg", "in_emergency", default=False)
        self._emg.setText("ATTIVA" if emg else "OK")
        self._emg.setStyleSheet(f"font-weight:800; color:{ERR if emg else OK};")

        # Homed/Azzerata
        homed = self._bool_attr("is_homed", "homed", "is_zeroed", "zeroed", "azzerata", default=False)
        self._homed.setText("HOMED" if homed else "NO")
        self._homed.setStyleSheet(f"font-weight:800; color:{OK if homed else WARN};")

        # Freno
        brake = self._bool_attr("brake_active", "freno_attivo", default=False)
        self._brake.setText("BLOCCATO" if brake else "SBLOCCATO")
        self._brake.setStyleSheet(f"font-weight:900; color:{OK if brake else ORANGE};")

        # Frizione
        clutch = self._bool_attr("clutch_active", "frizione_inserita", default=True)
        self._clutch.setText("INSERITA" if clutch else "DISINSERITA")
        self._clutch.setStyleSheet(f"font-weight:900; color:{OK if clutch else ORANGE};")

        # Quota
        enc = self._num_attr("encoder_position", "pos_mm", "quota_mm")
        self._enc.setText(f"{enc:.2f} mm" if enc is not None else "—")
        self._enc.setStyleSheet("font-weight:800; color:#2980b9;" if enc is not None else "color:#7f8c8d;")
