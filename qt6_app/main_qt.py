"""
MainWindow aggiornato:
- Usa MachineAdapter + SimulationMachine (o RealMachine con flag --real).
- Nessun DummyMachine: la simulazione fa homing a 250 mm con homing_in_progress.
- StatusPanel resta compatibile (legge dal raw). Pagine usano l'adapter.
"""

import sys
import logging
import traceback
from typing import Optional

from PySide6.QtWidgets import QApplication, QMainWindow, QStatusBar, QSizePolicy
from PySide6.QtCore import Qt

# Tema/stili
try:
    from ui_qt.theme import apply_global_stylesheet
except Exception:
    apply_global_stylesheet = lambda app: None  # no-op

# Stack che non impone minime in alto
from ui_qt.widgets.min_stack import MinimalStacked
from ui_qt.widgets.size_ignorer import SizeIgnorer

# Adapter + macchine
try:
    from ui_qt.machine.machine_adapter import MachineAdapter
    from ui_qt.machine.simulation_machine import SimulationMachine
    from ui_qt.machine.real_machine import RealMachine
except Exception:
    MachineAdapter = None
    SimulationMachine = None
    RealMachine = None


def _setup_logging():
    try:
        from pathlib import Path
        log_dir = Path.home() / "blitz" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "blitz.log"
    except Exception:
        log_file = None

    logger = logging.getLogger("blitz")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
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
                pass

        def _global_excepthook(exctype, value, tb):
            try:
                logger.error("Uncaught exception", exc_info=(exctype, value, tb))
            except Exception:
                pass
            try:
                traceback.print_exception(exctype, value, tb, file=sys.stderr)
            except Exception:
                pass

        sys.excepthook = _global_excepthook
    return logger


class _Toast:
    def __init__(self, win: QMainWindow):
        self._win = win
    def show(self, msg: str, level: str = "info", ms: int = 2000):
        try:
            self._win.statusBar().showMessage(msg, ms)
        except Exception:
            pass


class MainWindow(QMainWindow):
    def __init__(self, simulation: bool = True):
        super().__init__()
        self.setWindowTitle("BLITZ 3")
        self.setStatusBar(QStatusBar())
        self.toast = _Toast(self)

        self.machine, self.machine_adapter = self._make_machine(simulation)

        # Stack centrale
        self.stack = MinimalStacked(self)
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.stack.setMinimumSize(0, 0)
        self.setCentralWidget(self.stack)
        self._pages: dict[str, tuple[object, int, object]] = {}

        # Pagine
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

    def _make_machine(self, simulation: bool):
        logger = logging.getLogger("blitz")
        if not simulation and RealMachine and MachineAdapter:
            try:
                raw = RealMachine()
                logger.info("Macchina reale avviata.")
                return raw, MachineAdapter(raw)
            except Exception as e:
                logger.warning(f"RealMachine non disponibile, fallback a SimulationMachine: {e}")

        if SimulationMachine and MachineAdapter:
            raw = SimulationMachine()
            logger.info("Avvio SimulationMachine.")
            return raw, MachineAdapter(raw)

        # Fallback di emergenza (non dovrebbe servire)
        class _Fallback:
            min_distance = 250.0
            max_cut_length = 4000.0
            machine_homed = False
            homing_in_progress = False
            encoder_position = 250.0
            def get_position(self): return self.encoder_position
            def is_positioning_active(self): return False
            def tick(self): pass
            def get_state(self): return {"homed": self.machine_homed, "position_mm": self.encoder_position}
            def close(self): pass
            def do_homing(self, callback=None):
                import threading, time
                def seq():
                    self.homing_in_progress = True
                    time.sleep(0.6)
                    self.encoder_position = self.min_distance
                    self.machine_homed = True
                    self.homing_in_progress = False
                    if callback: callback(success=True, msg="HOMING OK")
                threading.Thread(target=seq, daemon=True).start()
        raw = _Fallback()
        class _Adapter:
            def __init__(self, r): self._r = r
            def get_position(self): return self._r.get_position()
            def is_positioning_active(self): return self._r.is_positioning_active()
            def tick(self): self._r.tick()
            def get_state(self): return self._r.get_state()
            def close(self): self._r.close()
            def command_move(self, *a, **k): return False
            def command_lock_brake(self): return True
            def command_release_brake(self): return True
            def command_set_head_angles(self, sx, dx): return True
            def command_set_pressers(self, l, r): return True
            def command_set_blade_inhibit(self, left=None, right=None): return True
            def command_sim_cut_pulse(self): pass
            def command_sim_start_pulse(self): pass
            def command_sim_dx_blade_out(self, on): pass
        logger.info("Avvio Fallback machine.")
        return raw, _Adapter(raw)

    def add_page(self, key: str, widget):
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
            logger.exception(f"Errore caricando pagina '{key}' ({mod_name}.{cls_name}): {e}")
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
        if hasattr(page, "on_show") and callable(getattr(page, "on_show")):
            try:
                page.on_show()
            except Exception:
                logger.exception(f"Errore in on_show() della pagina '{key}'")
                try:
                    self.toast.show(f"Errore on_show in '{key}' (vedi log)", "warn", 3000)
                except Exception:
                    pass

    # Alias navigazione
    def go_home(self): self.show_page("home")
    def show_home(self): self.show_page("home")
    def navigate_home(self): self.show_page("home")
    def home(self): self.show_page("home")

    def reset_current_page(self):
        logger = logging.getLogger("blitz")
        raw = self.machine
        if hasattr(raw, "reset") and callable(getattr(raw, "reset")):
            try:
                raw.reset()
                self.toast.show("Reset eseguito", "ok", 1500)
                logger.info("Reset macchina eseguito")
            except Exception:
                logger.exception("Errore durante reset macchina")

    def reset_all(self):
        self.reset_current_page()
        self.show_page("home")


def main():
    _setup_logging()
    logger = logging.getLogger("blitz")
    logger.info("Avvio BLITZ 3")

    # Flag --real per tentare la macchina reale
    simulation = True
    for a in sys.argv[1:]:
        if a.strip().lower() in ("--real", "--hardware", "--hw"):
            simulation = False

    app = QApplication(sys.argv)
    try:
        apply_global_stylesheet(app)
    except Exception as e:
        logging.getLogger("blitz").warning(f"apply_global_stylesheet fallita: {e}")

    win = MainWindow(simulation=simulation)
    win.showMaximized()
    rc = app.exec()
    logging.getLogger("blitz").info(f"Chiusura BLITZ 3 (exit code {rc})")
    try:
        win.machine_adapter.close()
    except Exception:
        pass
    sys.exit(rc)


if __name__ == "__main__":
    main()
