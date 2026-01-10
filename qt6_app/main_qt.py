#!/usr/bin/env python3
"""
BLITZ CNC - Main Application Entry Point

Qt6-based control software for dual-head CNC saw. 
"""

import sys
import os
from pathlib import Path

# ========== CRITICAL FIX: Add project root to Python path ==========
# This ensures qt6_app module is importable regardless of execution directory
project_root = Path(__file__).parent.parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
print(f"[STARTUP] Project root:  {project_root}")
# ====================================================================

import logging
from typing import Optional, Dict, Any, Tuple

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QStackedWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QFrame, QSizePolicy, QMessageBox
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QIcon

# Application imports
try:
    from qt6_app.ui_qt.utils.logger import setup_logging
except ImportError:
    # Fallback if logger module not available
    def setup_logging(log_dir=None, level=logging.INFO):
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

try:
    from qt6_app.ui_qt.utils.settings import read_settings, write_settings
except ImportError:
    def read_settings():
        return {}
    def write_settings(settings):
        pass

from qt6_app.ui_qt.widgets.size_ignorer import SizeIgnorer
from qt6_app.ui_qt.widgets.toast import Toast

# Logger
logger = logging.getLogger("blitz")

# Configuration
USE_SIMULATION = os.environ.get('SIMULATION', '1') == '1'  # Default to simulation
APP_VERSION = "1.0.0"


class BlitzMainWindow(QMainWindow):
    """
    Main application window.
    
    Manages: 
    - Page stack
    - Machine instance
    - Global toast notifications
    - Application lifecycle
    """
    
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle(f"BLITZ CNC v{APP_VERSION}")
        self.setMinimumSize(1280, 800)
        
        # Stack for pages
        self.stack = QStackedWidget()
        self.setCentralWidget(self. stack)
        
        # Page registry:  {key: (wrapper, index, page_widget)}
        self._pages: Dict[str, Tuple[QWidget, int, QWidget]] = {}
        
        # Initialize machine
        self. machine = None
        self.machine_adapter = None
        self._init_machine()
        
        # Toast notifications
        self.toast = Toast(self)
        
        # Global exception handler
        sys.excepthook = self._global_exception_handler
        
        # Load pages
        self._load_pages()
        
        # Show home page
        self. show_page("home")
        
        logger.info(f"BLITZ CNC v{APP_VERSION} started (simulation={USE_SIMULATION})")
    
    def _init_machine(self):
        """Initialize machine instance."""
        try:
            if USE_SIMULATION:
                self.machine, self.machine_adapter = self._create_simulation_machine()
                logger.info("Machine initialized:  SIMULATION mode")
            else:
                self.machine, self.machine_adapter = self._create_real_machine()
                logger.info("Machine initialized: REAL HARDWARE mode")
        except Exception as e:
            logger.exception(f"Error initializing machine: {e}")
            # Fallback to simulation
            self.machine, self. machine_adapter = self._create_fallback_machine()
            self.toast.show(f"Machine init failed, using fallback: {e}", "warn", 5000)
    
    def _create_simulation_machine(self):
        """Create simulation machine."""
        try:
            from qt6_app.ui_qt.machine.simulation_machine import SimulationMachine
            from qt6_app.ui_qt.machine.machine_adapter import MachineAdapter
            
            raw = SimulationMachine()
            adapter = MachineAdapter(raw)
            return raw, adapter
        except ImportError as e:
            logger.error(f"Cannot import SimulationMachine: {e}")
            return self._create_fallback_machine()
    
    def _create_real_machine(self):
        """Create real hardware machine."""
        try:
            from qt6_app.ui_qt.machine.real_machine import RealMachine
            from qt6_app.ui_qt. machine.machine_adapter import MachineAdapter
            
            # Load hardware config
            import json
            config_path = Path(__file__).parent. parent / "data" / "hardware_config.json"
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            raw = RealMachine(config)
            adapter = MachineAdapter(raw)
            return raw, adapter
        except Exception as e:
            logger.error(f"Cannot create RealMachine: {e}")
            return self._create_fallback_machine()
    
    def _create_fallback_machine(self):
        """Create minimal fallback machine."""
        logger.warning("Using fallback machine (minimal simulation)")
        
        # Minimal machine mock
        class _FallbackMachine:
            def __init__(self):
                self.emergency_active = False
                self.homed = False
                self.brake_active = True
                self.clutch_active = True
                self._position_mm = 250.0
                self._positioning_active = False
                self. left_morse_locked = False
                self.right_morse_locked = False
                self.left_blade_inhibit = False
                self.right_blade_inhibit = False
                self.testa_sx_angle = 90
                self.testa_dx_angle = 90
            
            def get_position(self):
                return self._position_mm
            
            def is_positioning_active(self):
                return self._positioning_active
            
            def move_to(self, position_mm, callback=None):
                self._position_mm = position_mm
                if callback:
                    callback()
            
            def get_state(self):
                return {
                    'emergency_active': self.emergency_active,
                    'homed':  self.homed,
                    'brake_active': self.brake_active,
                    'clutch_active': self.clutch_active,
                    'position_mm': self._position_mm,
                }
            
            def tick(self):
                pass
            
            def close(self):
                pass
            
            def do_homing(self, callback=None):
                self. homed = True
                self._position_mm = 250.0
                if callback:
                    callback()
            
            def reset(self):
                self.emergency_active = False
                self. brake_active = True
        
        raw = _FallbackMachine()
        
        # Adapter
        class _FallbackAdapter:
            def __init__(self, r):
                self._r = r
            
            def get_position(self):
                return self._r.get_position()
            
            def is_positioning_active(self):
                return self._r.is_positioning_active()
            
            def tick(self):
                self._r.tick()
            
            def get_state(self):
                return self._r.get_state()
            
            def close(self):
                self._r.close()
            
            def command_move(self, position_mm, callback=None):
                self._r.move_to(position_mm, callback)
                return True
            
            def command_lock_brake(self):
                self._r.brake_active = True
                return True
            
            def command_release_brake(self):
                self._r.brake_active = False
                return True
            
            def command_set_clutch(self, active):
                self._r.clutch_active = bool(active)
                return True
            
            def set_mode_context(self, mode, piece_length_mm=0.0, bar_length_mm=6500.0):
                pass
            
            def command_set_head_angles(self, sx, dx):
                self._r.testa_sx_angle = sx
                self._r.testa_dx_angle = dx
                return True
            
            def command_set_morse(self, left, right):
                self._r.left_morse_locked = left
                self._r.right_morse_locked = right
                return True
            
            def command_set_blade_inhibit(self, left=None, right=None):
                if left is not None:
                    self._r.left_blade_inhibit = left
                if right is not None: 
                    self._r.right_blade_inhibit = right
                return True
            
            def command_sim_cut_pulse(self):
                pass
            
            def command_sim_start_pulse(self):
                pass
            
            def command_sim_dx_blade_out(self, on):
                pass
            
            def get_input(self, name):
                return False
            
            def do_homing(self, callback=None):
                self._r.do_homing(callback)
            
            def reset_machine(self):
                self._r.reset()
        
        return raw, _FallbackAdapter(raw)
    
    def _load_pages(self):
        """Load all application pages."""
        # Try to load each page, continue on error
        self._try_add_page("home", "qt6_app. ui_qt.pages.home_page", "HomePage")
        self._try_add_page("semi_auto", "qt6_app.ui_qt.pages.semi_auto_page", "SemiAutoPage")
        self._try_add_page("automatico", "qt6_app. ui_qt.pages.automatico_page", "AutomaticoPage")
        self._try_add_page("manuale", "qt6_app. ui_qt.pages.manuale_page", "ManualePage")
        self._try_add_page("utility", "qt6_app.ui_qt.pages.utility_page", "UtilityPage")
        self._try_add_page("statistics", "qt6_app.ui_qt.pages.statistics_page", "StatisticsPage")
        self._try_add_page("label_editor", "qt6_app.ui_qt.pages.label_editor_page", "LabelEditorPage")
    
    def add_page(self, key: str, widget:  QWidget):
        """Add page to stack."""
        wrapper = SizeIgnorer(widget)
        idx = self.stack.addWidget(wrapper)
        self._pages[key] = (wrapper, idx, widget)
    
    def _try_add_page(self, key: str, mod_name: str, cls_name: str):
        """Try to load and add page, log error on failure."""
        try:
            import importlib
            mod = importlib.import_module(mod_name)
            cls = getattr(mod, cls_name)
            self.add_page(key, cls(self))
            logger.info(f"Page loaded: {key} ({mod_name}. {cls_name})")
        except Exception as e:
            logger.exception(f"Error loading page '{key}' ({mod_name}.{cls_name}): {e}")
            try:
                self. toast.show(f"Errore caricamento pagina '{key}' (vedi log)", "warn", 4000)
            except Exception: 
                pass
    
    def show_page(self, key:  str):
        """Show page by key."""
        rec = self._pages.get(key)
        if not rec:
            try:
                self.toast.show(f"Pagina '{key}' non disponibile", "warn", 2000)
            except Exception: 
                pass
            logger.warning(f"Attempted to open non-existent page: {key}")
            return
        
        wrapper, idx, page = rec
        self.stack.setCurrentIndex(idx)
        
        # Call on_show if available
        if hasattr(page, "on_show") and callable(getattr(page, "on_show")):
            try:
                page.on_show()
            except Exception: 
                logger.exception(f"Error in on_show() for page '{key}'")
                try:
                    self.toast. show(f"Errore on_show '{key}'", "warn", 3000)
                except Exception: 
                    pass
    
    def go_home(self):
        """Navigate to home page."""
        self. show_page("home")
    
    def show_home(self):
        """Alias for go_home."""
        self.show_page("home")
    
    def _global_exception_handler(self, exc_type, exc_value, exc_tb):
        """Global exception handler."""
        import traceback
        
        logger. critical(
            "Uncaught exception",
            exc_info=(exc_type, exc_value, exc_tb)
        )
        
        # Print to console
        print(f"Uncaught exception: {exc_type.__name__}:  {exc_value}")
        traceback.print_tb(exc_tb)
        
        # Show dialog
        try:
            QMessageBox.critical(
                self,
                "Errore Critico",
                f"Si è verificato un errore imprevisto.\n\n"
                f"Tipo: {exc_type.__name__}\n"
                f"Dettagli: {exc_value}\n\n"
                f"L'errore è stato salvato nei log."
            )
        except Exception:
            pass
        
        # Call default handler
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    
    def closeEvent(self, event):
        """Handle window close."""
        logger.info("Application closing")
        
        # Cleanup machine
        try:
            if self.machine_adapter:
                self.machine_adapter.close()
            if self.machine:
                self.machine.close()
        except Exception as e:
            logger. error(f"Error during machine cleanup: {e}")
        
        event.accept()


def main():
    """Application entry point."""
    # Setup logging
    try:
        setup_logging()
    except Exception as e:
        print(f"Warning: Could not setup logging: {e}")
        logging.basicConfig(level=logging.INFO)
    
    logger.info("="*60)
    logger.info(f"BLITZ CNC v{APP_VERSION}")
    logger.info(f"Python {sys.version}")
    logger.info(f"Simulation mode: {USE_SIMULATION}")
    logger.info("="*60)
    
    # Create application
    app = QApplication. instance()
    if app is None:
        app = QApplication(sys.argv)
    
    # Set application properties
    app.setApplicationName("BLITZ CNC")
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("BLITZ")
    
    # Apply theme
    try:
        from qt6_app.ui_qt.theme import apply_theme
        apply_theme(app)
        logger.info("Theme applied")
    except Exception as e:
        logger.warning(f"Could not apply theme: {e}")
    
    # Create main window
    window = BlitzMainWindow()
    window.show()
    
    # Run event loop
    exit_code = app.exec()
    
    logger.info(f"Application exited with code: {exit_code}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
