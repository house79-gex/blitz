"""
Bluetooth Low Energy service for ESP32 digital caliper.

Protocol:
- Service UUID: 0x181A (Environmental Sensing)
- Measurement Characteristic: 0x2A58 (Float32, mm)
- Command Characteristic: 0x2A59 (Uint8, commands)

Dependencies:
    pip install bleak

Usage:
    caliper = BluetoothCaliperQt()
    caliper.set_measurement_callback(lambda mm: print(f"Received: {mm}mm"))
    
    devices = caliper.scan_devices_sync()
    if devices:
        caliper.connect_sync(devices[0]['address'])
"""

from typing import Optional, Callable, List, Dict, Any, TYPE_CHECKING
import asyncio
import struct
import logging

if TYPE_CHECKING:
    from bleak import BleakClient, BleakScanner

try:
    from bleak import BleakClient, BleakScanner
    HAS_BLEAK = True
except ImportError:
    HAS_BLEAK = False

logger = logging.getLogger("bluetooth_caliper")

# BLE UUIDs (Standard Environmental Sensing Service)
CALIPER_SERVICE_UUID = "0000181a-0000-1000-8000-00805f9b34fb"
CALIPER_MEASURE_CHAR_UUID = "00002a58-0000-1000-8000-00805f9b34fb"
CALIPER_COMMAND_CHAR_UUID = "00002a59-0000-1000-8000-00805f9b34fb"

# Command codes
CMD_IDLE = 0x00
CMD_GO = 0x01
CMD_CLEAR = 0x02


class BluetoothCaliper:
    """
    Async Bluetooth Low Energy caliper interface.
    
    For Qt integration, use BluetoothCaliperQt wrapper.
    """
    
    def __init__(self):
        self.client: Optional[BleakClient] = None
        self.connected = False
        self.on_measurement_received: Optional[Callable[[float], None]] = None
        self.on_go_command: Optional[Callable[[], None]] = None
        self.on_connection_lost: Optional[Callable[[], None]] = None
        self._device_address: Optional[str] = None
    
    async def scan_devices(self, timeout: float = 5.0) -> List[Dict[str, str]]:
        """
        Scan for BLE devices.
        
        Args:
            timeout: Scan timeout in seconds
        
        Returns:
            List of devices: [{"name": "ESP32_CALIBRO", "address": "AA:BB:CC:..."}]
        """
        if not HAS_BLEAK:
            logger.error("Bleak library not installed. Run: pip install bleak")
            return []
        
        try:
            logger.info(f"Scanning for BLE devices (timeout={timeout}s)...")
            devices = await BleakScanner.discover(timeout=timeout)
            
            result = []
            for d in devices:
                # Filter devices: look for "CALIBRO" or "ESP32" in name
                if d.name and any(keyword in d.name.upper() for keyword in ["CALIBRO", "ESP32", "CALIPER"]):
                    result.append({
                        "name": d.name,
                        "address": d.address,
                        "rssi": getattr(d, 'rssi', None)
                    })
                    logger.info(f"Found caliper device: {d.name} ({d.address})")
            
            if not result:
                logger.warning("No caliper devices found")
            
            return result
        
        except Exception as e:
            logger.error(f"Error scanning devices: {e}")
            return []
    
    async def connect(self, address: str) -> bool:
        """
        Connect to caliper device.
        
        Args:
            address: BLE MAC address (e.g., "AA:BB:CC:DD:EE:FF")
        
        Returns:
            True if connected successfully
        """
        if not HAS_BLEAK:
            logger.error("Bleak library not installed")
            return False
        
        try:
            logger.info(f"Connecting to {address}...")
            
            self.client = BleakClient(
                address,
                disconnected_callback=self._on_disconnect
            )
            
            await self.client.connect(timeout=10.0)
            
            if not self.client.is_connected:
                logger.error("Connection failed")
                return False
            
            # Enable notifications for measurements
            try:
                await self.client.start_notify(
                    CALIPER_MEASURE_CHAR_UUID,
                    self._handle_measurement
                )
                logger.info("Measurement notifications enabled")
            except Exception as e:
                logger.warning(f"Could not enable measurement notifications: {e}")
            
            # Enable notifications for commands (optional)
            try:
                await self.client.start_notify(
                    CALIPER_COMMAND_CHAR_UUID,
                    self._handle_command
                )
                logger.info("Command notifications enabled")
            except Exception as e:
                logger.debug(f"Command characteristic not available: {e}")
            
            self.connected = True
            self._device_address = address
            logger.info(f"✅ Connected to caliper: {address}")
            return True
        
        except Exception as e:
            logger.error(f"Connection error: {e}")
            self.connected = False
            return False
    
    async def disconnect(self):
        """Disconnect from caliper."""
        if self.client and self.connected:
            try:
                await self.client.disconnect()
                logger.info("Disconnected from caliper")
            except Exception as e:
                logger.error(f"Error disconnecting: {e}")
            finally:
                self.connected = False
                self._device_address = None
    
    def _handle_measurement(self, sender, data: bytearray):
        """
        Handle measurement notification from caliper.
        
        Data format: Float32 (4 bytes, big-endian) in millimeters
        """
        try:
            if len(data) != 4:
                logger.warning(f"Invalid measurement data length: {len(data)} bytes")
                return
            
            # Parse float32 (big-endian)
            measurement_mm = struct.unpack('>f', data)[0]
            
            logger.info(f"📏 Measurement received: {measurement_mm:.2f}mm")
            
            # Callback to application
            if self.on_measurement_received:
                self.on_measurement_received(measurement_mm)
        
        except Exception as e:
            logger.error(f"Error parsing measurement: {e}")
    
    def _handle_command(self, sender, data: bytearray):
        """
        Handle command notification from caliper.
        
        Data format: Uint8 (1 byte)
        - 0x01: GO command (trigger movement)
        - 0x02: CLEAR command
        """
        try:
            if len(data) < 1:
                return
            
            cmd = data[0]
            
            if cmd == CMD_GO:
                logger.info("▶️ GO command received from caliper")
                if self.on_go_command:
                    self.on_go_command()
            
            elif cmd == CMD_CLEAR:
                logger.info("🗑️ CLEAR command received from caliper")
                # Could add on_clear_command callback if needed
        
        except Exception as e:
            logger.error(f"Error parsing command: {e}")
    
    def _on_disconnect(self, client):
        """Callback when connection is lost."""
        logger.warning("⚠️ Connection lost to caliper")
        self.connected = False
        self._device_address = None
        
        if self.on_connection_lost:
            self.on_connection_lost()
    
    def is_connected(self) -> bool:
        """Check if currently connected."""
        return self.connected and self.client and self.client.is_connected


class BluetoothCaliperQt:
    """
    Qt-friendly wrapper for BluetoothCaliper.
    
    Provides synchronous methods that can be called from Qt main thread.
    Async operations run in separate event loop.
    
    Usage:
        caliper = BluetoothCaliperQt()
        caliper.set_measurement_callback(self._on_measurement)
        
        devices = caliper.scan_devices_sync()
        if devices:
            success = caliper.connect_sync(devices[0]['address'])
    """
    
    def __init__(self):
        self.caliper = BluetoothCaliper()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
    
    def scan_devices_sync(self, timeout: float = 5.0) -> List[Dict[str, str]]:
        """
        Synchronous device scan (blocking).
        
        Note: Uses asyncio.run() which creates a new event loop separate from Qt's.
        This is safe because the operation is blocking and completes before returning.
        Called via QTimer.singleShot() to avoid blocking the Qt main thread.
        
        Returns:
            List of devices found
        """
        if not HAS_BLEAK:
            logger.error("Bleak not installed. Install with: pip install bleak")
            return []
        
        try:
            # asyncio.run() creates a new event loop, separate from Qt's event loop
            return asyncio.run(self.caliper.scan_devices(timeout))
        except Exception as e:
            logger.error(f"Scan error: {e}")
            return []
    
    def connect_sync(self, address: str) -> bool:
        """
        Synchronous connection (blocking).
        
        Note: Uses asyncio.run() which creates a new event loop separate from Qt's.
        This is safe because the operation is blocking and completes before returning.
        Called via QTimer.singleShot() to avoid blocking the Qt main thread.
        
        Args:
            address: BLE MAC address
        
        Returns:
            True if connected
        """
        if not HAS_BLEAK:
            return False
        
        try:
            # asyncio.run() creates a new event loop, separate from Qt's event loop
            return asyncio.run(self.caliper.connect(address))
        except Exception as e:
            logger.error(f"Connect error: {e}")
            return False
    
    def disconnect_sync(self):
        """
        Synchronous disconnection (blocking).
        
        Note: Uses asyncio.run() which creates a new event loop separate from Qt's.
        """
        if self.caliper.is_connected():
            try:
                # asyncio.run() creates a new event loop, separate from Qt's event loop
                asyncio.run(self.caliper.disconnect())
            except Exception as e:
                logger.error(f"Disconnect error: {e}")
    
    def set_measurement_callback(self, callback: Callable[[float], None]):
        """
        Set callback for measurement reception.
        
        Args:
            callback: Function taking float (mm) as parameter
        """
        self.caliper.on_measurement_received = callback
    
    def set_go_callback(self, callback: Callable[[], None]):
        """
        Set callback for GO command reception.
        
        Args:
            callback: Function with no parameters
        """
        self.caliper.on_go_command = callback
    
    def set_connection_lost_callback(self, callback: Callable[[], None]):
        """
        Set callback for connection lost event.
        
        Args:
            callback: Function with no parameters
        """
        self.caliper.on_connection_lost = callback
    
    def is_connected(self) -> bool:
        """Check if connected."""
        return self.caliper.is_connected()
    
    def get_device_address(self) -> Optional[str]:
        """Get connected device address."""
        return self.caliper._device_address


# Check if Bleak is available
def check_bleak_available() -> bool:
    """Check if Bleak library is installed."""
    return HAS_BLEAK


def get_install_instructions() -> str:
    """Get installation instructions for Bleak."""
    return """
Bluetooth Caliper requires the 'bleak' library.

Install with:
    pip install bleak

Or add to requirements.txt:
    bleak>=0.21.0
"""
