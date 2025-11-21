from __future__ import annotations
from typing import Any, Dict
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QGridLayout
from PySide6.QtCore import Qt

OK = "#27ae60"
WARN = "#f39c12"
ERR = "#c0392b"
MUTED = "#95a5a6"
BORDER = "#3b4b5a"
CARD_BG = "#ecf0f3"

def _pill(text: str, bg: str) -> QLabel:
    w = QLabel(text)
    w.setAlignment(Qt.AlignCenter)
    w.setStyleSheet(
        f"font-weight:800; font-size: 11pt; color:white; background:{bg}; "
        "border-radius:10px; padding:2px 6px;"
    )
    return w

class StatusPanel(QWidget):
    """
    Pannello stato compatto (versione estesa):
    - EMG
    - HOMED
    - FRENO
    - FRIZIONE
    - TESTA SX/DX (inibizione lama)
    - PRESSORE SX/DX (left_presser_locked / right_presser_locked)
    Supporta sia oggetto 'raw' con attributi legacy sia adapter con get_state().
    """
    def __init__(self, machine_state: Any, title="STATO", parent=None):
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
        card.setStyleSheet(
            f"QFrame{{background:{CARD_BG}; border:1px solid {BORDER}; border-radius:10px;}}"
        )
        root.addWidget(card, 1)

        grid = QGridLayout(card)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        def add_row(r, name, w):
            lbl = QLabel(name)
            lbl.setStyleSheet("font-weight:600; font-size:11pt; color:#2c3e50;")
            grid.addWidget(lbl, r, 0, alignment=Qt.AlignLeft)
            grid.addWidget(w, r, 1, alignment=Qt.AlignRight)

        self.w_emg = _pill("-", MUTED)
        self.w_homed = _pill("-", MUTED)
        self.w_brake = _pill("-", MUTED)
        self.w_clutch = _pill("-", MUTED)
        self.w_head_sx = _pill("-", MUTED)
        self.w_head_dx = _pill("-", MUTED)
        self.w_press_sx = _pill("-", MUTED)
        self.w_press_dx = _pill("-", MUTED)

        add_row(0, "EMG", self.w_emg)
        add_row(1, "HOMED", self.w_homed)
        add_row(2, "FRENO", self.w_brake)
        add_row(3, "FRIZIONE", self.w_clutch)
        add_row(4, "TESTA SX", self.w_head_sx)
        add_row(5, "TESTA DX", self.w_head_dx)
        add_row(6, "PRESS. SX", self.w_press_sx)
        add_row(7, "PRESS. DX", self.w_press_dx)

        root.addStretch(1)

    # Legacy fallback
    def _legacy_attr(self, *names, default=False) -> bool:
        for n in names:
            if hasattr(self.m, n):
                try:
                    return bool(getattr(self.m, n))
                except Exception:
                    pass
        return bool(default)

    def _state_bool(self, state: Dict[str, Any], *keys, default=False) -> bool:
        for k in keys:
            if k in state:
                try:
                    return bool(state[k])
                except Exception:
                    pass
        return bool(default)

    def refresh(self):
        state = None
        if hasattr(self.m, "get_state") and callable(getattr(self.m, "get_state")):
            try:
                st = self.m.get_state()
                if isinstance(st, dict):
                    state = st
            except Exception:
                state = None

        if state:
            emg    = self._state_bool(state, "emergency_active")
            homed  = self._state_bool(state, "homed", "machine_homed")
            brake  = self._state_bool(state, "brake_active")
            clutch = self._state_bool(state, "clutch_active", default=True)
            inh_sx = self._state_bool(state, "left_blade_inhibit")
            inh_dx = self._state_bool(state, "right_blade_inhibit")
            # Pressori possono essere sia diretti sia dentro 'pressers'
            press_sx = self._state_bool(state, "left_presser_locked")
            press_dx = self._state_bool(state, "right_presser_locked")
            if not press_sx and "pressers" in state and isinstance(state["pressers"], dict):
                press_sx = bool(state["pressers"].get("left", False))
            if not press_dx and "pressers" in state and isinstance(state["pressers"], dict):
                press_dx = bool(state["pressers"].get("right", False))
        else:
            emg    = self._legacy_attr("emergency_active", "emg_active", "is_emg", "in_emergency")
            homed  = self._legacy_attr("machine_homed", "homed", "is_homed", "home_done", "azzerata")
            brake  = self._legacy_attr("brake_active", "brake_on", "freno_bloccato")
            clutch = self._legacy_attr("clutch_active", "clutch_on", "frizione_inserita", default=True)
            inh_sx = self._legacy_attr("left_blade_inhibit", "lama_sx_inibita", "sx_inhibit")
            inh_dx = self._legacy_attr("right_blade_inhibit", "lama_dx_inibita", "dx_inhibit")
            press_sx = self._legacy_attr("left_presser_locked")
            press_dx = self._legacy_attr("right_presser_locked")

        # EMG
        self.w_emg.setText("ATTIVA" if emg else "OK")
        self.w_emg.setStyleSheet(self._style(emg, err_on=True))

        # HOMED
        self.w_homed.setText("HOMED" if homed else "NO")
        self.w_homed.setStyleSheet(self._style(homed))

        # FRENO
        self.w_brake.setText("BLOCCATO" if brake else "SBLOCCATO")
        self.w_brake.setStyleSheet(self._style(brake))

        # FRIZIONE
        self.w_clutch.setText("INSERITA" if clutch else "DISINSERITA")
        self.w_clutch.setStyleSheet(self._style(clutch))

        # TESTA SX/DX (inibizione -> DISABILITATA)
        self.w_head_sx.setText("ABILITATA" if not inh_sx else "DISABILITATA")
        self.w_head_sx.setStyleSheet(self._style(not inh_sx))
        self.w_head_dx.setText("ABILITATA" if not inh_dx else "DISABILITATA")
        self.w_head_dx.setStyleSheet(self._style(not inh_dx))

        # PRESSORI
        self.w_press_sx.setText("BLOCCATO" if press_sx else "SBLOCCATO")
        self.w_press_sx.setStyleSheet(self._style(press_sx))
        self.w_press_dx.setText("BLOCCATO" if press_dx else "SBLOCCATO")
        self.w_press_dx.setStyleSheet(self._style(press_dx))

    @staticmethod
    def _style(active: bool, err_on: bool = False) -> str:
        if err_on:
            return (
                f"font-weight:800; font-size:11pt; color:white; background:{ERR if active else OK}; "
                "border-radius:10px; padding:2px 6px;"
            )
        return (
            f"font-weight:800; font-size:11pt; color:white; background:{OK if active else WARN}; "
            "border-radius:10px; padding:2px 6px;"
        )
