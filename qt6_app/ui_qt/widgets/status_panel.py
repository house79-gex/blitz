from __future__ import annotations
from typing import Optional
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QGridLayout
from PySide6.QtCore import Qt

# Palette
OK = "#27ae60"
WARN = "#f39c12"
ERR = "#c0392b"
MUTED = "#95a5a6"
BORDER = "#3b4b5a"
CARD_BG = "#ecf0f3"

def _pill(text: str, bg: str) -> QLabel:
    w = QLabel(text)
    w.setAlignment(Qt.AlignCenter)
    w.setStyleSheet(f"font-weight:800; font-size: 11pt; color:white; background:{bg}; border-radius:10px; padding:2px 6px;")
    return w


class StatusPanel(QWidget):
    """
    Pannello stato compatto:
    - EMG (rosso/verde)
    - HOMED (verde/giallo)
    - FRENO (BLOCCATO=verde / SBLOCCATO=arancio)
    - FRIZIONE (INSERITA=verde / DISINSERITA=arancio)
    - TESTA SX/DX (ABILITATA/DISABILITATA) in base a inibizione lama

    Nota: QUOTA e PRESSORI rimossi su richiesta.
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
        self.w_head_sx = _pill("-", MUTED)
        self.w_head_dx = _pill("-", MUTED)

        add_row(0, "EMG", self.w_emg)
        add_row(1, "HOMED", self.w_homed)
        add_row(2, "FRENO", self.w_brake)
        add_row(3, "FRIZIONE", self.w_clutch)
        add_row(4, "TESTA SX", self.w_head_sx)
        add_row(5, "TESTA DX", self.w_head_dx)

        root.addStretch(1)

    def _b(self, *names, default=False):
        for n in names:
            if hasattr(self.m, n):
                try:
                    return bool(getattr(self.m, n))
                except Exception:
                    pass
        return default

    def refresh(self):
        emg = self._b("emergency_active", "emg_active", "is_emg", "in_emergency")
        self.w_emg.setText("ATTIVA" if emg else "OK")
        self.w_emg.setStyleSheet(
            f"font-weight:800; font-size: 11pt; color:white; background:{ERR if emg else OK}; border-radius:10px; padding:2px 6px;"
        )

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

        inh_sx = self._b("left_blade_inhibit", "lama_sx_inibita", "sx_inhibit", default=False)
        inh_dx = self._b("right_blade_inhibit", "lama_dx_inibita", "dx_inhibit", default=False)

        self.w_head_sx.setText("ABILITATA" if not inh_sx else "DISABILITATA")
        self.w_head_sx.setStyleSheet(
            f"font-weight:800; font-size: 11pt; color:white; background:{OK if not inh_sx else WARN}; border-radius:10px; padding:2px 6px;"
        )
        self.w_head_dx.setText("ABILITATA" if not inh_dx else "DISABILITATA")
        self.w_head_dx.setStyleSheet(
            f"font-weight:800; font-size: 11pt; color:white; background:{OK if not inh_dx else WARN}; border-radius:10px; padding:2px 6px;"
        )
