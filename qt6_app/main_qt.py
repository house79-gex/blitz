import sys
from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QStackedWidget, QStatusBar
)

# Tema/stili
try:
    from ui_qt.theme import apply_global_stylesheet
except Exception:
    apply_global_stylesheet = lambda app: None  # fallback no-op


# --- Fallback DummyMachineState (usato solo se la reale non è importabile) ---
class DummyMachineState:
    def __init__(self):
        self.machine_homed = False
        self.emergency_active = False
        self.brake_active = False
        self.clutch_active = True
        self.positioning_active = False
        self.min_distance = 250.0
        self.max_cut_length = 4000.0
        self.position_current = self.min_distance
        self.left_head_angle = 0.0
        self.right_head_angle = 0.0
        self.count_active_on_closed = True
        self.invert_left_switch = False
        self.invert_right_switch = False
        self.cut_pulse_debounce_ms = 120
        self.cut_pulse_group_ms = 500
        self.semi_auto_target_pieces = 0
        self.semi_auto_count_done = 0
        self.work_queue = []
        self.current_work_idx = None

    def set_active_mode(self, mode: str):  # compat
        pass

    def normalize_after_manual(self):  # compat
        self.clutch_active = True

    def set_head_button_input_enabled(self, enabled: bool):  # compat
        pass

    # API esplicite per coerenza con l’UI
    def set_brake(self, active: bool) -> bool:
        if self.emergency_active or self.positioning_active:
            return False
        if active and not self.machine_homed:
            return False
        self.brake_active = bool(active)
        return True

    def set_clutch(self, active: bool) -> bool:
        if self.emergency_active or self.positioning_active:
            return False
        self.clutch_active = bool(active)
        return True

    # Simulazione homing: porta a minima, imposta homed=True, freno OFF, frizione ON
    def do_homing(self, callback=None):
        import time, threading

        def seq():
            if self.emergency_active:
                if callback:
                    callback(success=False, msg="EMERGENZA")
                return
            if self.machine_homed:
                if callback:
                    callback(success=True, msg="GIÀ HOMED")
                return
            time.sleep(1.0)
            self.position_current = self.min_distance
            self.brake_active = False
            self.clutch_active = True
            self.machine_homed = True
            if callback:
                callback(success=True, msg="HOMING OK")

        threading.Thread(target=seq, daemon=True).start()

    def move_to_length_and_angles(self, length_mm: float, ang_sx: float, ang_dx: float, done_cb=None):
        # simulazione posizionamento
        self.brake_active = False
        self.positioning_active = True
        self.left_head_angle = float(ang_sx)
        self.right_head_angle = float(ang_dx)
        from threading import Thread
        import time

        def run():
            time.sleep(0.8)
            self.positioning_active = False
            self.brake_active = True
            if done_cb:
                done_cb(True, "OK")

        Thread(target=run, daemon=True).start()

    def reset(self):
        self.machine_homed = False
        self.emergency_active = False
        self.brake_active = False
        self.clutch_active = True
        self.positioning_active = False
        self.position_current = self.min_distance
        self.left_head_angle = 0.0
        self.right_head_angle = 0.0
        self.semi_auto_target_pieces = 0
        self.semi_auto_count_done = 0
        self.work_queue.clear()
        self.current_work_idx = None


# --- Toast minimale su status bar ---
class _Toast:
    def __init__(self, win: QMainWindow):
        self._win = win

    def show(self, msg: str, level: str = "info", ms: int = 2000):
        try:
            self._win.statusBar().showMessage(msg, ms)
        except Exception:
            pass


# --- MainWindow con stack e navigazione ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BLITZ 3")
        self.resize(1280, 800)

        # Status bar per messaggi/toast
        self.setStatusBar(QStatusBar())
        self.toast = _Toast(self)

        # Istanza MachineState reale, se disponibile; altrimenti Dummy
        self.machine = self._make_machine()

        # Stack pagine
        self.stack = QStackedWidget(self)
        self.setCentralWidget(self.stack)
        self._pages: dict[str, tuple[object, int]] = {}

        # Registra pagine (Home è obbligatoria; le altre best-effort)
        from ui_qt.pages.home_page import HomePage
        self.add_page("home", HomePage(self))

        # Import "tolleranti" per le altre, così l'app parte comunque
        self._try_add_page("manuale", "ui_qt.pages.manuale_page", "ManualePage")
        self._try_add_page("automatico", "ui_qt.pages.automatico_page", "AutomaticoPage")
        self._try_add_page("semi", "ui_qt.pages.semi_auto_page", "SemiAutoPage")
        self._try_add_page("tipologie", "ui_qt.pages.tipologie_page", "TipologiePage")
        self._try_add_page("quotevani", "ui_qt.pages.quotevani_page", "QuoteVaniPage")
        self._try_add_page("utility", "ui_qt.pages.utility_page", "UtilityPage")

        # Navigazione iniziale
        self.show_page("home")

        # Espone nav compatibile (alcuni callback cercano appwin.nav.go_home)
        class _Nav:
            def __init__(nav_self, mw: "MainWindow"):
                nav_self._mw = mw

            def go_home(nav_self):
                nav_self._mw.show_page("home")

        self.nav = _Nav(self)

    def _make_machine(self):
        try:
            # MachineState reale con logica completa (do_homing, toggle_brake, ecc.)
            from ui.shared.machine_state import MachineState as RealMachineState
            return RealMachineState()
        except Exception:
            return DummyMachineState()

    def add_page(self, key: str, widget):
        idx = self.stack.addWidget(widget)
        self._pages[key] = (widget, idx)

    def _try_add_page(self, key: str, mod_name: str, cls_name: str):
        try:
            import importlib
            mod = importlib.import_module(mod_name)
            cls = getattr(mod, cls_name)
            self.add_page(key, cls(self))
        except Exception:
            # la pagina è facoltativa: se manca, l’app continua a funzionare
            pass

    def show_page(self, key: str):
        rec = self._pages.get(key)
        if not rec:
            if hasattr(self, "toast"):
                self.toast.show(f"Pagina '{key}' non disponibile", "warn", 2000)
            return
        widget, idx = rec
        self.stack.setCurrentIndex(idx)
        # callback pagina
        if hasattr(widget, "on_show") and callable(getattr(widget, "on_show")):
            try:
                widget.on_show()
            except Exception:
                pass

    # Alias di navigazione per compatibilità
    def go_home(self): self.show_page("home")
    def show_home(self): self.show_page("home")
    def navigate_home(self): self.show_page("home")
    def home(self): self.show_page("home")

    # Reset “globale” (usato dai fallback dell’Header)
    def reset_current_page(self):
        # se la macchina espone reset(), usala
        if hasattr(self.machine, "reset") and callable(getattr(self.machine, "reset")):
            try:
                self.machine.reset()
                self.toast.show("Reset eseguito", "ok", 1500)
            except Exception:
                pass

    def reset_all(self):
        self.reset_current_page()
        self.show_page("home")


def main():
    app = QApplication(sys.argv)
    try:
        apply_global_stylesheet(app)
    except Exception:
        pass
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
