import pytest
from qt6_app.ui_qt.services.bluetooth_caliper import BluetoothCaliperQt, check_bleak_available

def test_bleak_check():
    """Test Bleak availability check."""
    # Should return True or False (not crash)
    result = check_bleak_available()
    assert isinstance(result, bool)

def test_caliper_init():
    """Test caliper initialization."""
    caliper = BluetoothCaliperQt()
    assert caliper is not None
    assert not caliper.is_connected()

def test_measurement_callback():
    """Test measurement callback registration."""
    caliper = BluetoothCaliperQt()
    
    received_value = None
    def callback(mm):
        nonlocal received_value
        received_value = mm
    
    caliper.set_measurement_callback(callback)
    
    # Simulate measurement (would come from BLE in real scenario)
    caliper.caliper.on_measurement_received(1250.5)
    
    assert received_value == 1250.5

def test_go_callback():
    """Test GO command callback registration."""
    caliper = BluetoothCaliperQt()
    
    go_received = False
    def callback():
        nonlocal go_received
        go_received = True
    
    caliper.set_go_callback(callback)
    
    # Simulate GO command
    caliper.caliper.on_go_command()
    
    assert go_received

def test_connection_lost_callback():
    """Test connection lost callback registration."""
    caliper = BluetoothCaliperQt()
    
    lost_received = False
    def callback():
        nonlocal lost_received
        lost_received = True
    
    caliper.set_connection_lost_callback(callback)
    
    # Simulate connection lost
    caliper.caliper.on_connection_lost()
    
    assert lost_received

def test_device_address_when_not_connected():
    """Test getting device address when not connected."""
    caliper = BluetoothCaliperQt()
    addr = caliper.get_device_address()
    assert addr is None
