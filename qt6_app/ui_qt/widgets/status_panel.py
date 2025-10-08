from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QLabel, QFrame
from PySide6.QtCore import Qt

# Palette
OK = "#2ecc71"
WARN = "#f39c12"
ERR = "#e74c3c"
INFO = "#2980b9"
TEXT = "#2c3e50"
MUTED = "#7f8c8d"
CARD_BG = "#f7f9fb"
BORDER = "#dfe6e9"

def _pill(text: str, color: str, bold: bool = True) -> QLabel:
    lbl = QLabel(text)
    # Riduci leggermente dimensioni e padding per maggiore compattezza
    lb = "font-weight:800;" if bold else "font-weight:700;"
    lbl.setStyleSheet(
        f"{lb} font-size: 11pt; color:white; background:{color}; border-radius:10px; padding:2px 6px;"
    )
    lbl.setAlignment(Qt.AlignCenter)
    return lbl

class StatusPanel(QWidget):
    """
    Pannello stato compatto:
    - EMG (rosso/verde)
    - HOMED (verde/giallo)
    - FRENO (BLOCCATO=verde / SBLOCCATO=arancio)
    - FRIZIONE (INSERITA=verde / DISINSERITA=arancio)
    - QUOTA (mm) se disponibile
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
        title_lbl.setStyleSheet("font-weight: 800; font-size: 11.5pt; color: #34495e;")
        root.addWidget(title_lbl, 0, alignment=Qt.AlignLeft)

        card = QFrame()
        card.setStyleSheet(f"QFrame{{background:{CARD_BG}; border:1px solid {BORDER}; border-radius:10px;}}")
        root.addWidget(card, 1)

        grid = QGridLayout(card)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        def add_row(r, name, value_widget):
            name_lbl = QLabel(name)
            name_lbl.setStyleSheet("font-weight:600; font-size: 11pt; color:#2c3e50;")
            grid.addWidget(name_lbl, r, 0, alignment=Qt.AlignLeft)
            grid.addWidget(value_widget, r, 1, alignment=Qt.AlignRight)

        self.w_emg = _pill("-", MUTED)
        self.w_homed = _pill("-", MUTED)
        self.w_brake = _pill("-", MUTED)
        self.w_clutch = _pill("-", MUTED)
        self.w_enc = QLabel("—")
        self.w_enc.setStyleSheet("font-weight:700; font-size: 11pt; color:#2980b9;")

        add_row(0, "EMG", self.w_emg)
        add_row(1, "HOMED", self.w_homed)
        add_row(2, "FRENO", self.w_brake)
        add_row(3, "FRIZIONE", self.w_clutch)
        add_row(4, "QUOTA", self.w_enc)

        root.addStretch(1)

    # Helpers
    def _b(self, *names, default=False):
        for n in names:
            if hasattr(self.m, n):
                try:
                    return bool(getattr(self.m, n))
                except Exception:
                    pass
        return default

    def _n(self, *names):
        for n in names:
            if hasattr(self.m, n):
                try:
                    return float(getattr(self.m, n))
                except Exception:
                    pass
        return None

    def refresh(self):
        emg = self._b("emergency_active", "emg_active", "is_emg", "in_emergency")
        self.w_emg.setText("ATTIVA" if emg else "OK")
        self.w_emg.setStyleSheet(
            f"font-weight:800; font-size: 11pt; color:white; background:{ERR if emg else OK}; border-radius:10px; padding:2px 6px;"
        )

        # Include machine_homed tra gli alias supportati
        homed = self._b("machine_homed", "is_homed", "homed", "is_zeroed", "zeroed", "azzerata", "home_done")
        self.w_homed.setText("HOMED" if homed else "NO")
        self.w_homed.setStyleSheet(
            f"font-weight:800; font-size: 11pt; color:white; background:{OK if homed else WARN}; border-radius:10px; padding:2px 6px;"
        )

        brake = self._b("brake_active", "brake_on", "freno_attivo", "freno_bloccato")
        self.w_brake.setText("BLOCCATO" if brake else "SBLOCCATO")
        self.w_brake.setStyleSheet(
            f"font-weight:800; font-size: 11pt; color:white; background:{OK if brake else WARN}; border-radius:10px; padding:2px 6px;"
        )

        clutch = self._b("clutch_active", "clutch_on", "frizione_inserita", default=True)
        self.w_clutch.setText("INSERITA" if clutch else "DISINSERITA")
        self.w_clutch.setStyleSheet(
            f"font-weight:800; font-size: 11pt; color:white; background:{OK if clutch else WARN}; border-radius:10px; padding:2px 6px;"
        )

        enc = self._n("encoder_position", "position_current", "pos_mm", "quota_mm")
        if enc is not None:
            self.w_enc.setText(f"{enc:.2f} mm")
            self.w_enc.setStyleSheet("font-weight:700; font-size: 11pt; color:#2980b9;")
        else:
            self.w_enc.setText("—")
            self.w_enc.setStyleSheet("color:#7f8c8d; font-weight:600; font-size: 11pt;")
