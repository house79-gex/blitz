import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QStackedWidget, QVBoxLayout
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtCore import Qt
from ui_qt.theme import THEME, apply_global_stylesheet

# Pagine: saranno aggiunte progressivamente; per ora, creiamo placeholder sicuri
try:
    from ui_qt.pages.home_page import HomePage
except Exception:
    class HomePage(QWidget):
        def __init__(self, appwin):
            super().__init__()
            from PySide6.QtWidgets import QLabel, QVBoxLayout
            lay = QVBoxLayout(self)
            lay.addWidget(QLabel("Home (placeholder)"))
        def on_show(self):
            pass

# Preferisci usare il MachineState reale (stessa API della versione Tk)
try:
    from ui.shared.machine_state import MachineState
except Exception:
    MachineState = None

class DummyMachineState:
    def __init__(self):
        self.machine_homed = False
        self.emergency_active = False
        self.work_queue = []
    def rebuild_work_queue(self):
        pass

class MainWindow(QMainWindow):
    def __init__(self, machine_state):
        super().__init__()
        self.setWindowTitle("BLITZ 3 - Qt6")
        self.resize(1600, 960)

        self.machine = machine_state
        self.stack = QStackedWidget()
        self.pages = {}

        # Registra le pagine minime
        self.pages["home"] = HomePage(self)
        for p in self.pages.values():
            self.stack.addWidget(p)

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.addWidget(self.stack)
        lay.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(container)

        self._bind_hotkeys()
        self.show_page("home")

    def show_page(self, key: str):
        w = self.pages.get(key)
        if not w:
            return
        # Parità con Tk: disabilita input TESTA di default, normalizza se esci da Manuale
        try:
            if hasattr(self.machine, "set_head_button_input_enabled"):
                self.machine.set_head_button_input_enabled(False)
            if key != "manuale" and hasattr(self.machine, "normalize_after_manual"):
                self.machine.normalize_after_manual()
        except Exception:
            pass
        self.stack.setCurrentWidget(w)
        if hasattr(w, "on_show"):
            w.on_show()

    def _bind_hotkeys(self):
        # F9/F10/F11 come in Tk (simulate head button / emergency toggle / cut pulse)
        QShortcut(QKeySequence("F9"), self, activated=self._simulate_head_button)
        QShortcut(QKeySequence("Shift+F9"), self, activated=self._simulate_head_button)
        QShortcut(QKeySequence("Ctrl+F9"), self, activated=self._simulate_head_button)

        QShortcut(QKeySequence("F10"), self, activated=self._simulate_emergency_toggle)
        QShortcut(QKeySequence("Shift+F10"), self, activated=self._simulate_emergency_toggle)
        QShortcut(QKeySequence("Ctrl+F10"), self, activated=self._simulate_emergency_toggle)

        QShortcut(QKeySequence("F11"), self, activated=self._simulate_cut_pulse)

    def _simulate_head_button(self):
        try:
            if hasattr(self.machine, "simulate_head_button"):
                self.machine.simulate_head_button()
            elif hasattr(self.machine, "set_head_button_input_enabled"):
                self.machine.set_head_button_input_enabled(True)
        except Exception:
            pass

    def _simulate_emergency_toggle(self):
        try:
            if hasattr(self.machine, "toggle_emergency"):
                self.machine.toggle_emergency()
            elif hasattr(self.machine, "clear_emergency"):
                if getattr(self.machine, "emergency_active", False) and hasattr(self.machine, "clear_emergency"):
                    self.machine.clear_emergency()
        except Exception:
            pass

    def _simulate_cut_pulse(self):
        try:
            if hasattr(self.machine, "simulate_cut_pulse"):
                self.machine.simulate_cut_pulse()
            elif hasattr(self.machine, "decrement_current_remaining"):
                self.machine.decrement_current_remaining()
        except Exception:
            pass

def main():
    app = QApplication(sys.argv)
    apply_global_stylesheet(app)

    if MachineState is not None:
        machine_state = MachineState()
    else:
        machine_state = DummyMachineState()

    win = MainWindow(machine_state)
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()