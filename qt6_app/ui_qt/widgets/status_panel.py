from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QWidget
from PySide6.QtCore import Qt
from ui_qt.theme import THEME

def _color(name, default):
    try:
        return getattr(THEME, name)
    except Exception:
        return default

class StatusPanel(QFrame):
    """
    Pannello stato:
    - LED/controlli raggruppati in alto
    - Quota (encoder) allineata in basso del frame
    - Fallback colori per massima visibilità
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

        # Top area: titolo + LED
        top_area = QVBoxLayout()
        top_area.setSpacing(6)

        title_w = QLabel(title)
        title_w.setStyleSheet("font-weight: 700;")
        top_area.addWidget(title_w)

        self.leds = {}
        leds_col = QVBoxLayout()
        leds_col.setSpacing(3)
        for label in ["EMERGENZA", "HOMED", "FRENO", "MOVIMENTO", "FRIZIONE"]:
            leds_col.addLayout(self._make_led_row(label))
        top_area.addLayout(leds_col)

        root.addLayout(top_area, 0)

        # Spacer per spingere la quota in basso
        root.addStretch(1)

        # Bottom area: quota encoder (ancorata in basso)
        self.lbl_encoder = QLabel("QUOTA: -")
        self.lbl_encoder.setStyleSheet("font-family: Consolas, monospace; font-weight: 700;")
        root.addWidget(self.lbl_encoder, 0, alignment=Qt.AlignBottom)

        # Stile
        try:
            bg = THEME.CARD_BG; outline = THEME.OUTLINE
        except Exception:
            bg = "#1f2a33"; outline = "#3b4b5a"
        self.setStyleSheet(
            f"""
            QFrame#StatusPanel {{
                background: {bg};
                border: 1px solid {outline};
                border-radius: 6px;
            }}
            """
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
        ok_col   = _color("OK", "#2ecc71")
        err_col  = _color("ERR", "#e74c3c")
        warn_col = _color("WARN", "#f1c40f")
        acc2_col = _color("ACCENT_2", "#9b59b6")

        if not m:
            self._set_led("EMERGENZA", "#7f8c8d")
            self._set_led("HOMED", "#7f8c8d")
            self._set_led("FRENO", warn_col)
            self._set_led("MOVIMENTO", "#7f8c8d")
            self._set_led("FRIZIONE", warn_col)
            self.lbl_encoder.setText("QUOTA: -")
            return

        self._set_led("EMERGENZA", err_col if getattr(m, "emergency_active", False) else "#7f8c8d")
        self._set_led("HOMED", ok_col if getattr(m, "machine_homed", False) else "#7f8c8d")
        self._set_led("FRENO", ok_col if getattr(m, "brake_active", False) else warn_col)
        self._set_led("MOVIMENTO", acc2_col if getattr(m, "positioning_active", False) else "#7f8c8d")
        self._set_led("FRIZIONE", ok_col if getattr(m, "clutch_active", False) else warn_col)

        pos = getattr(m, "encoder_position", None)
        if pos is None:
            pos = getattr(m, "position_current", None)
        try:
            self.lbl_encoder.setText(f"QUOTA: {float(pos):.1f} mm" if pos is not None else "QUOTA: -")
        except Exception:
            self.lbl_encoder.setText("QUOTA: -")

    def _set_led(self, name, color):
        if name in self.leds:
            self.leds[name].setStyleSheet(f"font-size:16px; color: {color};")
