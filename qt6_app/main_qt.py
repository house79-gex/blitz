import sys
import logging
import traceback
from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QStatusBar, QSizePolicy
)
from PySide6.QtCore import Qt

# Tema/stili
try:
    from ui_qt.theme import apply_global_stylesheet
except Exception:
    apply_global_stylesheet = lambda app: None  # fallback no-op

# Stack che non impone minime eccessive e wrapper che ignora min-size
from ui_qt.widgets.min_stack import MinimalStacked
from ui_qt.widgets.size_ignorer import SizeIgnorer


def _setup_logging():
    """
    Inizializza logging su stderr e su file (utente).
    Log file: %USERPROFILE%/blitz/logs/blitz.log (Windows) o ~/blitz/logs/blitz.log
    """
    try:
        from pathlib import Path
        log_dir = Path.home() / "blitz" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "blitz.log"
    except Exception:
        log_file = None

    logger = logging.getLogger("blitz")
    logger.setLevel(logging.INFO)

    # Evita duplicati se richiamato più volte
    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    if log_file is not None:
        try:
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setLevel(logging.INFO)
            fh.setFormatter(fmt)
            logger.addHandler(fh)
        except Exception:
            # Se fallisce il file, continuiamo solo con stderr
            pass

    # Hook globale per eccezioni non gestite
    def _global_excepthook(exctype, value, tb):
        try:
            logger.error("Uncaught exception", exc_info=(exctype, value, tb))
        except Exception:
            pass
        # Stampa comunque lo stack su stderr per debugging immediato
        try:
            traceback.print_exception(exctype, value, tb, file=sys.stderr)
        except Exception:
            pass

    sys.excepthook = _global_excepthook
    return logger


# --- Fallback DummyMachineState (sviluppo) con movimento/encoder simulati ---
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
        self.encoder_position = self.position_current
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

    def do_homing(self, callback=None):
        import time, threading
        def seq():
            if self.emergency_active:
                if callback: callback(success=False, msg="EMERGENZA")
                return
            if self.machine_homed:
                if callback: callback(success=True, msg="GIÀ HOMED")
                return
            time.sleep(0.6)
            self.position_current = self.min_distance
            self.encoder_position = self.min_distance
            self.brake_active = False
            self.clutch_active = True
            self.machine_homed = True
            if callback: callback(success=True, msg="HOMING OK")
        threading.Thread(target=seq, daemon=True).start()

    def move_to_length_and_angles(self, length_mm: float, ang_sx: float, ang_dx: float, done_cb=None):
        # Simulazione movimento graduale con encoder live
        import time, threading
        if self.emergency_active or not self.machine_homed:
            if done_cb: done_cb(False, "BLOCCO/NO HOMING")
            return
        self.brake_active = False
        self.positioning_active = True
        self.left_head_angle = float(ang_sx)
        self.right_head_angle = float(ang_dx)
        target = max(self.min_distance, min(float(length_mm), self.max_cut_length))
        start = float(self.position_current)

        def run():
            steps = 80
            dt = 0.02
            for i in range(steps + 1):
                if self.emergency_active or not self.positioning_active:
                    break
                f = i / steps
                self.position_current = start + (target - start) * f
                self.encoder_position = self.position_current
                time.sleep(dt)
            if not self.emergency_active:
                self.position_current = target
                self.encoder_position = target
            self.positioning_active = False
            self.brake_active = True
            if done_cb:
                done_cb(not self.emergency_active, "OK" if not self.emergency_active else "EMG")
        threading.Thread(target=run, daemon=True).start()

    def reset(self):
        self.machine_homed = False
        self.emergency_active = False
        self.brake_active = False
        self.clutch_active = True
        self.positioning_active = False
        self.position_current = self.min_distance
        self.encoder_position = self.position_current
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

        self.setStatusBar(QStatusBar())
        self.toast = _Toast(self)

        self.machine = self._make_machine()

        # Stack che NON impone minime in alto
        self.stack = MinimalStacked(self)
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.stack.setMinimumSize(0, 0)
        self.setCentralWidget(self.stack)
        # mappa: key -> (wrapped_widget, idx, original_page)
        self._pages: dict[str, tuple[object, int, object]] = {}

        from ui_qt.pages.home_page import HomePage
        self.add_page("home", HomePage(self))
        self._try_add_page("manuale", "ui_qt.pages.manuale_page", "ManualePage")
        self._try_add_page("automatico", "ui_qt.pages.automatico_page", "AutomaticoPage")
        self._try_add_page("semi", "ui_qt.pages.semi_auto_page", "SemiAutoPage")
        self._try_add_page("tipologie", "ui_qt.pages.tipologie_page", "TipologiePage")
        self._try_add_page("quotevani", "ui_qt.pages.quotevani_page", "QuoteVaniPage")
        self._try_add_page("utility", "ui_qt.pages.utility_page", "UtilityPage")

        self.show_page("home")

        class _Nav:
            def __init__(nav_self, mw: "MainWindow"):
                nav_self._mw = mw
            def go_home(nav_self):
                nav_self._mw.show_page("home")
        self.nav = _Nav(self)

    def _make_machine(self):
        try:
            from ui.shared.machine_state import MachineState as RealMachineState
            return RealMachineState()
        except Exception as e:
            logging.getLogger("blitz").warning(f"MachineState reale non disponibile, uso Dummy: {e}")
            return DummyMachineState()

    def add_page(self, key: str, widget):
        # Wrappa la pagina in un contenitore che ignora min-size
        wrapper = SizeIgnorer(widget)
        idx = self.stack.addWidget(wrapper)
        self._pages[key] = (wrapper, idx, widget)

    def _try_add_page(self, key: str, mod_name: str, cls_name: str):
        logger = logging.getLogger("blitz")
        try:
            import importlib
            mod = importlib.import_module(mod_name)
            cls = getattr(mod, cls_name)
            self.add_page(key, cls(self))
            logger.info(f"Pagina caricata: {key} ({mod_name}.{cls_name})")
        except Exception as e:
            # Log completo con stacktrace su file e stderr
            logger.exception(f"Errore caricando pagina '{key}' ({mod_name}.{cls_name}): {e}")
            # Messaggio visivo non bloccante
            try:
                self.toast.show(f"Errore pagina '{key}' (vedi log)", "warn", 4000)
            except Exception:
                pass

    def show_page(self, key: str):
        logger = logging.getLogger("blitz")
        rec = self._pages.get(key)
        if not rec:
            try:
                self.toast.show(f"Pagina '{key}' non disponibile", "warn", 2000)
            except Exception:
                pass
            logger.warning(f"Tentativo di aprire pagina non registrata: {key}")
            return
        wrapper, idx, page = rec
        self.stack.setCurrentIndex(idx)
        # callback della pagina originale (non del wrapper)
        if hasattr(page, "on_show") and callable(getattr(page, "on_show")):
            try:
                page.on_show()
            except Exception:
                logger.exception(f"Errore in on_show() della pagina '{key}'")
                try:
                    self.toast.show(f"Errore on_show in '{key}' (vedi log)", "warn", 3000)
                except Exception:
                    pass

    def go_home(self): self.show_page("home")
    def show_home(self): self.show_page("home")
    def navigate_home(self): self.show_page("home")
    def home(self): self.show_page("home")

    def reset_current_page(self):
        logger = logging.getLogger("blitz")
        if hasattr(self.machine, "reset") and callable(getattr(self.machine, "reset")):
            try:
                self.machine.reset()
                self.toast.show("Reset eseguito", "ok", 1500)
                logger.info("Reset macchina eseguito")
            except Exception:
                logger.exception("Errore durante reset macchina")

    def reset_all(self):
        self.reset_current_page()
        self.show_page("home")


def main():
    # Logging prima di creare l'app Qt
    _setup_logging()
    logger = logging.getLogger("blitz")
    logger.info("Avvio BLITZ 3")

    app = QApplication(sys.argv)
    try:
        apply_global_stylesheet(app)
    except Exception as e:
        logging.getLogger("blitz").warning(f"apply_global_stylesheet fallita: {e}")

    win = MainWindow()
    # Apertura massimizzata (nessuna setGeometry manuale)
    win.showMaximized()
    rc = app.exec()
    logging.getLogger("blitz").info(f"Chiusura BLITZ 3 (exit code {rc})")
    sys.exit(rc)


if __name__ == "__main__":
    main()
