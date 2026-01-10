"""
Pytest configuration and shared fixtures.

Provides:
- Qt Application fixture (session-scoped)
- Mock machine objects
- Temporary directories
- Test data generators
"""

import pytest
import sys
import tempfile
import shutil
from pathlib import Path
from PySide6.QtWidgets import QApplication

@pytest.fixture(scope='session')
def qapp():
    """
    Qt Application fixture (session-scoped).
    
    Creates a single QApplication instance for all tests.
    Required for any test that uses Qt widgets.
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app
    # Note: Don't quit app in tests, causes crashes

@pytest.fixture
def mock_machine():
    """Mock machine for testing UI without hardware."""
    from tests.mocks.mock_machine import MockMachine
    machine = MockMachine()
    yield machine
    machine.cleanup()

@pytest.fixture
def mock_machine_adapter():
    """Mock machine adapter."""
    from tests.mocks.mock_machine import MockMachineAdapter
    return MockMachineAdapter()

@pytest.fixture
def temp_dir():
    """Temporary directory for test files."""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)

@pytest.fixture
def sample_cutlist():
    """Sample cutlist for testing optimizer."""
    return [
        {'length': 1000, 'angle_sx': 45, 'angle_dx': 45, 'qty': 5},
        {'length': 1500, 'angle_sx': 90, 'angle_dx': 90, 'qty': 3},
        {'length': 800, 'angle_sx': 45, 'angle_dx': 90, 'qty': 2},
        {'length': 2000, 'angle_sx': 90, 'angle_dx': 45, 'qty': 1},
    ]

@pytest.fixture
def sample_profile():
    """Sample profile data for testing."""
    return {
        'name': 'Test Profile',
        'width_mm': 50,
        'height_mm': 30,
        'thickness_mm': 2.0,
        'material': 'Alluminio 6063',
        'dxf_path': None
    }

@pytest.fixture
def sample_mode_config():
    """Sample mode configuration for testing."""
    from qt6_app.ui_qt.logic.modes.mode_config import ModeConfig
    return ModeConfig(
        machine_zero_homing_mm=250.0,
        machine_offset_battuta_mm=120.0,
        machine_max_travel_mm=4000.0,
        stock_length_mm=6500.0
    )
