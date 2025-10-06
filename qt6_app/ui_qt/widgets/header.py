from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QFrame
from PySide6.QtCore import Qt
from ui_qt.theme import THEME

class Header(QFrame):
    """
    Header con titolo + azioni comuni:
    - Home: ritorna alla pagina Home
    - AZZERA: clear emergency (se attiva) + homing
    Compatibile con chiamata Header(appwin, title).
    """
    def __init__(self, appwin, title: str, show_home: bool = True, show_reset: bool = True):
        super().__init__(appwin)
        self.appwin = appwin
        self.setObjectName("Header")
        self.setStyleSheet(f"""
            QFrame#Header {{
                background: {THEME.PANEL_BG};
                border-bottom: 1px solid {THEME.OUTLINE};
            }}
            QLabel#HeaderTitle {{
                font-size: 18px;
                font-weight: 800;
            }}
            QPushButton#HdrBtn {{
                padding: 6px 10px;
                border: 1px solid {THEME.OUTLINE};
                border-radius: 6px;
                background: {THEME.TILE_BG};
            }}
            QPushButton#HdrBtn:hover {{
                border-color: {THEME.ACCENT};
            }}
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        self.lbl = QLabel(title)
        self.lbl.setObjectName("HeaderTitle")
        lay.addWidget(self.lbl, 0, alignment=Qt.AlignVCenter | Qt.AlignLeft)
        lay.addStretch(1)

        if show_home:
            btn_home = QPushButton("Home")
            btn_home.setObjectName("HdrBtn")
            btn_home.clicked.connect(lambda: self.appwin.show_page("home"))
            lay.addWidget(btn_home)

        if show_reset:
            self.btn_reset = QPushButton("AZZERA")
            self.btn_reset.setObjectName("HdrBtn")
            self.btn_reset.clicked.connect(self._do_reset)
            lay.addWidget(self.btn_reset)

    def _do_reset(self):
        try:
            m = self.appwin.machine

            # Se emergenza attiva, prova a cancellarla
            if getattr(m, "emergency_active", False) and hasattr(m, "clear_emergency"):
                m.clear_emergency()

            # Avvia homing
            if hasattr(m, "do_homing"):
                # disabilita il bottone durante la sequenza
                try:
                    self.btn_reset.setEnabled(False)
                except Exception:
                    pass

                def cb(success: bool, msg: str):
                    # feedback utente
                    try:
                        if hasattr(self.appwin, "toast") and self.appwin.toast:
                            self.appwin.toast.show(f"AZZERA: {msg}", "ok" if success else "warn", 2500)
                    except Exception:
                        pass
                    # riabilita bottone
                    try:
                        self.btn_reset.setEnabled(True)
                    except Exception:
                        pass

                m.do_homing(callback=cb)
            else:
                # Fallback: imposta stati minimi per sbloccare i test
                setattr(m, "machine_homed", True)
                setattr(m, "brake_active", False)
                setattr(m, "clutch_active", True)
                if hasattr(self.appwin, "toast") and self.appwin.toast:
                    self.appwin.toast.show("AZZERA: modalità fallback (homed).", "warn", 2500)
        except Exception:
            # In ogni caso riabilita il bottone
            try:
                self.btn_reset.setEnabled(True)
            except Exception:
                pass
