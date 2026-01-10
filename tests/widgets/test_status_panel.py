"""Unit tests for StatusPanel widget."""

import pytest
from qt6_app.ui_qt.widgets.status_panel import StatusPanel


def test_status_panel_initialization(qapp, mock_machine):
    """Test status panel creates without errors."""
    panel = StatusPanel(mock_machine)
    
    assert panel is not None
    assert panel.w_emg is not None
    assert panel.w_homed is not None
    assert panel.w_brake is not None
    assert panel.w_clutch is not None


def test_status_panel_refresh_emergency(qapp, mock_machine):
    """Test emergency state display."""
    panel = StatusPanel(mock_machine)
    
    # Set emergency
    mock_machine.emergency_active = True
    panel.refresh()
    
    # Check pill shows emergency
    assert "ATTIVA" in panel.w_emg.text().upper() or "EMERGENZA" in panel.w_emg.text().upper()


def test_status_panel_refresh_homed(qapp, mock_machine):
    """Test homed state display."""
    panel = StatusPanel(mock_machine)
    
    # Set homed
    mock_machine.homed = True
    mock_machine.machine_homed = True
    panel.refresh()
    
    # Check pill shows homed
    text = panel.w_homed.text().upper()
    assert "HOMED" in text or "SÌ" in text


def test_status_panel_refresh_brake(qapp, mock_machine):
    """Test brake state display."""
    panel = StatusPanel(mock_machine)
    
    # Brake active
    mock_machine.brake_active = True
    panel.refresh()
    assert "BLOCC" in panel.w_brake.text().upper()
    
    # Brake released
    mock_machine.brake_active = False
    panel.refresh()
    assert "SBLOCC" in panel.w_brake.text().upper()


def test_status_panel_refresh_clutch(qapp, mock_machine):
    """Test clutch state display."""
    panel = StatusPanel(mock_machine)
    
    # Clutch active
    mock_machine.clutch_active = True
    panel.refresh()
    assert "INSERITA" in panel.w_clutch.text().upper()
    
    # Clutch released
    mock_machine.clutch_active = False
    panel.refresh()
    assert "DISINSERITA" in panel.w_clutch.text().upper()


def test_status_panel_refresh_all_states(qapp, mock_machine):
    """Test all possible state combinations."""
    panel = StatusPanel(mock_machine)
    
    # Emergency + not homed
    mock_machine.emergency_active = True
    mock_machine.homed = False
    mock_machine.machine_homed = False
    panel.refresh()
    assert panel.w_emg.text() != "-"
    assert "ATTIVA" in panel.w_emg.text().upper()
    
    # OK + homed
    mock_machine.emergency_active = False
    mock_machine.homed = True
    mock_machine.machine_homed = True
    panel.refresh()
    assert panel.w_homed.text() != "-"
    assert "HOMED" in panel.w_homed.text().upper() or "OK" in panel.w_homed.text().upper()


def test_status_panel_with_get_state(qapp, mock_machine):
    """Test status panel with get_state() method."""
    panel = StatusPanel(mock_machine)
    
    # Update state via get_state
    mock_machine.emergency_active = False
    mock_machine.homed = True
    mock_machine.brake_active = False
    
    panel.refresh()
    
    # Verify state is read correctly
    assert "OK" in panel.w_emg.text().upper()
    assert "HOMED" in panel.w_homed.text().upper()
    assert "SBLOCC" in panel.w_brake.text().upper()


def test_status_panel_morse_state(qapp, mock_machine):
    """Test morse lock state display."""
    panel = StatusPanel(mock_machine)
    
    # Lock left morse
    mock_machine.left_morse_locked = True
    mock_machine.right_morse_locked = False
    panel.refresh()
    
    assert "BLOCC" in panel.w_morse_sx.text().upper()
    assert "SBLOCC" in panel.w_morse_dx.text().upper()
