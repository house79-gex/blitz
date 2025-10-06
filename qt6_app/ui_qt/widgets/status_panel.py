from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt
from ui_qt.theme import THEME

class StatusPanel(QFrame):
    """
    Pannello stato riutilizzabile: EMERGENZA, HOMED, FRENO, MOVIMENTO, FRIZIONE, QUOTA (encoder)
    Parità con ui/shared/status_panel.py (Tk).
    """
    def __init__(self, machine_state=None, title="STATO", parent=None):
        super().__init__(parent)
        self.setObjectName("StatusPanel")
        self.machine = machine_state
        self._build(title)

    def _build(self, title):
        self.setProperty("role", "panel")
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        title_w = QLabel(title)
        title_w.setStyleSheet("font-weight: 700;")
        root.addWidget(title_w)

        self.leds = {}
        leds_col = QVBoxLayout()
        leds_col.setSpacing(3)
        for label in ["EMERGENZA", "HOMED", "FRENO", "MOVIMENTO", "FRIZIONE"]:
            leds_col.addLayout(self._make_led_row(label))
        root.addLayout(leds_col)

        self.lbl_encoder = QLabel("QUOTA: -")
        self.lbl_encoder.setStyleSheet("font-family: Consolas, monospace; font-weight: 700;")
        root.addWidget(self.lbl_encoder)

        self.setStyleSheet(
            """
            QFrame#StatusPanel {
                background: %s;
                border: 1px solid %s;
                border-radius: 6px;
            }
            """ % (THEME.CARD_BG, THEME.OUTLINE)
        )

    def _make_led_row(self, label):
        row = QHBoxLayout()
        row.setSpacing(8)
        lab = QLabel(label)
        dot = QLabel("●")
        dot.setStyleSheet("font-size: 16px; color: #7f8c8d;")
        row.addWidget(lab)
        row.addStretch(1)
        row.addWidget(dot)
        self.leds[label] = dot
        return row

    def refresh(self):
        m = self.machine
        if not m:
            self._set_led("EMERGENZA", "#7f8c8d")
            self._set_led("HOMED", "#7f8c8d")
            self._set_led("FRENO", "#f1c40f")
            self._set_led("MOVIMENTO", "#7f8c8d")
            self._set_led("FRIZIONE", "#f1c40f")
            self.lbl_encoder.setText("QUOTA: -")
            return

        # EMERGENZA: rosso se attiva, grigio altrimenti
        self._set_led("EMERGENZA", THEME.ERR if getattr(m, "emergency_active", False) else "#7f8c8d")
        # HOMED: verde se homed, grigio altrimenti
        self._set_led("HOMED", THEME.OK if getattr(m, "machine_homed", False) else "#7f8c8d")
        # FRENO: verde=bloccato, giallo=sbloccato
        self._set_led("FRENO", THEME.OK if getattr(m, "brake_active", False) else "#f1c40f")
        # MOVIMENTO: viola se in movimento, grigio altrimenti
        self._set_led("MOVIMENTO", THEME.ACCENT_2 if getattr(m, "positioning_active", False) else "#7f8c8d")
        # FRIZIONE: verde=inserita, giallo=disinserita
        self._set_led("FRIZIONE", THEME.OK if getattr(m, "clutch_active", False) else "#f1c40f")
        # QUOTA
        pos = getattr(m, "encoder_position", None)
        try:
            self.lbl_encoder.setText(f"QUOTA: {float(pos):.1f} mm" if pos is not None else "QUOTA: -")
        except Exception:
            self.lbl_encoder.setText("QUOTA: -")

    def _set_led(self, name, color):
        if name in self.leds:
            self.leds[name].setStyleSheet(f"font-size:16px; color: {color};")

