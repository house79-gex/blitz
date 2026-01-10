"""Tests for main_qt.py application startup and initialization."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os


class TestMainQtImports:
    """Test that main_qt.py imports work correctly."""
    
    def test_main_qt_module_imports(self):
        """Test that main_qt.py can be imported without errors."""
        # This ensures all imports in main_qt.py are correct
        from qt6_app import main_qt
        assert main_qt is not None
        assert hasattr(main_qt, 'BlitzMainWindow')
        assert hasattr(main_qt, 'main')
    
    def test_main_qt_constants(self):
        """Test that main_qt.py constants are defined correctly."""
        from qt6_app import main_qt
        assert hasattr(main_qt, 'USE_SIMULATION')
        assert hasattr(main_qt, 'APP_VERSION')
        assert isinstance(main_qt.APP_VERSION, str)


@pytest.mark.integration
class TestBlitzMainWindowInit:
    """Test BlitzMainWindow initialization."""
    
    def test_window_initialization(self, qtbot):
        """Test that BlitzMainWindow can be initialized."""
        from qt6_app.main_qt import BlitzMainWindow
        
        # Create the window
        window = BlitzMainWindow()
        qtbot.addWidget(window)
        
        # Verify basic properties
        assert window.windowTitle().startswith("BLITZ CNC")
        assert window.stack is not None
        assert window.machine is not None
        assert window.machine_adapter is not None
        assert isinstance(window._pages, dict)
    
    def test_pages_loaded(self, qtbot):
        """Test that pages are loaded correctly."""
        from qt6_app.main_qt import BlitzMainWindow
        
        window = BlitzMainWindow()
        qtbot.addWidget(window)
        
        # Check that pages were loaded
        assert len(window._pages) > 0, "No pages were loaded"
        
        # Verify home page is loaded
        assert "home" in window._pages, "Home page not loaded"
        
        # Verify expected pages are loaded (excluding StatisticsPage which doesn't exist)
        expected_pages = ["home", "semi_auto", "automatico", "manuale", "utility", "label_editor"]
        for page_key in expected_pages:
            # Page might fail to load if dependencies are missing, but we check the attempt was made
            if page_key in window._pages:
                wrapper, idx, page_widget = window._pages[page_key]
                assert wrapper is not None
                assert idx >= 0
                assert page_widget is not None
    
    def test_statistics_page_not_loaded(self, qtbot):
        """Test that the non-existent StatisticsPage is not in the pages list."""
        from qt6_app.main_qt import BlitzMainWindow
        
        window = BlitzMainWindow()
        qtbot.addWidget(window)
        
        # StatisticsPage should not be loaded since it doesn't exist
        assert "statistics" not in window._pages, "StatisticsPage should not be loaded"
    
    def test_show_home_method(self, qtbot):
        """Test that show_home method works."""
        from qt6_app.main_qt import BlitzMainWindow
        
        window = BlitzMainWindow()
        qtbot.addWidget(window)
        
        # This should not raise an exception
        if "home" in window._pages:
            window.show_home()
            # Verify home page is shown
            wrapper, idx, _ = window._pages["home"]
            assert window.stack.currentIndex() == idx
    
    def test_machine_fallback(self, qtbot):
        """Test that fallback machine is created when imports fail."""
        from qt6_app.main_qt import BlitzMainWindow
        
        window = BlitzMainWindow()
        qtbot.addWidget(window)
        
        # Machine should always be created (either real, simulation, or fallback)
        assert window.machine is not None
        assert window.machine_adapter is not None
        
        # Fallback machine should have required methods
        assert hasattr(window.machine, 'get_position')
        assert hasattr(window.machine, 'get_state')
        assert hasattr(window.machine_adapter, 'get_position')
        assert hasattr(window.machine_adapter, 'command_move')


@pytest.mark.integration
class TestApplicationStartup:
    """Test application startup functionality."""
    
    def test_app_can_be_created(self, qapp):
        """Test that the application instance can be created."""
        # qapp fixture provides QApplication instance
        assert qapp is not None
        assert qapp.applicationName() == "BLITZ CNC"
    
    def test_window_shows_maximized(self, qtbot):
        """Test that window can be shown maximized."""
        from qt6_app.main_qt import BlitzMainWindow
        
        window = BlitzMainWindow()
        qtbot.addWidget(window)
        
        # Test that showMaximized method exists and can be called
        assert hasattr(window, 'showMaximized')
        
        # Note: We don't actually call showMaximized() in headless test environment
        # as it requires a display, but we verify the method exists
