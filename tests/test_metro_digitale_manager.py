"""
Unit tests for Metro Digitale Manager
"""

import pytest
from qt6_app.ui_qt.services.metro_digitale_manager import MetroDigitaleManager, get_metro_manager


def test_metro_manager_singleton():
    """Test singleton pattern."""
    manager1 = get_metro_manager()
    manager2 = get_metro_manager()
    
    assert manager1 is manager2, "MetroDigitaleManager should be a singleton"


def test_metro_manager_initialization():
    """Test manager initialization."""
    manager = get_metro_manager()
    
    assert manager is not None
    assert hasattr(manager, 'measurement_received')
    assert hasattr(manager, 'connection_changed')
    assert hasattr(manager, 'error_occurred')
    assert not manager.is_connected()


def test_metro_manager_availability():
    """Test availability check."""
    manager = get_metro_manager()
    
    # Should return True or False (not crash)
    result = manager.is_available()
    assert isinstance(result, bool)


def test_set_current_page():
    """Test setting current page."""
    manager = get_metro_manager()
    
    # Should not crash
    manager.set_current_page("semi_auto")
    manager.set_current_page("automatico")
    manager.set_current_page(None)


def test_measurement_history():
    """Test measurement history."""
    manager = get_metro_manager()
    
    # Get history (should return list)
    history = manager.get_measurement_history()
    assert isinstance(history, list)


def test_json_payload_parsing():
    """Test JSON payload parsing simulation."""
    manager = get_metro_manager()
    
    # Simulate receiving measurement callback
    received_measurements = []
    
    def callback(mm, mode, auto_start):
        received_measurements.append({
            'mm': mm,
            'mode': mode,
            'auto_start': auto_start
        })
    
    manager.measurement_received.connect(callback)
    
    # Simulate a notification
    import json
    payload = {
        "type": "fermavetro",
        "misura_mm": 1250.5,
        "auto_start": True,
        "mode": "semi_auto"
    }
    
    # Simulate the notification handler
    data = json.dumps(payload).encode('utf-8')
    manager._handle_notification(None, bytearray(data))
    
    # Check if measurement was received
    assert len(received_measurements) == 1
    assert received_measurements[0]['mm'] == 1250.5
    assert received_measurements[0]['mode'] == "semi_auto"
    assert received_measurements[0]['auto_start'] is True


def test_invalid_json_payload():
    """Test handling of invalid JSON payload."""
    manager = get_metro_manager()
    
    # Should not crash on invalid JSON
    invalid_data = b"not valid json"
    try:
        manager._handle_notification(None, bytearray(invalid_data))
    except Exception as e:
        pytest.fail(f"Should handle invalid JSON gracefully: {e}")


def test_connection_status():
    """Test connection status tracking."""
    manager = get_metro_manager()
    
    # Initially not connected
    assert not manager.is_connected()


def test_measurement_history_limit():
    """Test that measurement history is limited."""
    manager = get_metro_manager()
    
    # Add many measurements to history
    import json
    for i in range(100):
        payload = {
            "type": "fermavetro",
            "misura_mm": float(i),
            "auto_start": False,
            "mode": "semi_auto"
        }
        data = json.dumps(payload).encode('utf-8')
        manager._handle_notification(None, bytearray(data))
    
    # History should be limited
    history = manager.get_measurement_history()
    assert len(history) <= 50, "History should be limited to last 50"
