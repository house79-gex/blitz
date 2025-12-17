"""
Metro Digitale Manager - Singleton

Manages global BLE connection to Metro Digitale ESP32-S3 digital caliper.
Routes measurements to Semi-Auto or Automatico pages based on mode field in JSON payload.

Protocol:
- Service UUID: 12345678-1234-1234-1234-123456789abc
- TX Characteristic: 12345678-1234-1234-1234-123456789abd (Metro → App)
- RX Characteristic: 12345678-1234-1234-1234-123456789abe (App → Metro)
- Device Name: "Metro-Digitale"

JSON Payload Format:
{
    "type": "fermavetro",
    "misura_mm": 1250.5,
    "auto_start": true,
    "mode": "semi_auto"  // "semi_auto" | "automatico"
}
"""

from PySide6.QtCore import QObject, Signal, QTimer
from typing import Optional, Dict, Any, List
import logging
import json

try:
    from bleak import BleakClient, BleakScanner
    HAS_BLEAK = True
except ImportError:
    HAS_BLEAK = False
    BleakClient = None
    BleakScanner = None

logger = logging.getLogger("metro_digitale_manager")

# Metro Digitale BLE Protocol
SERVICE_UUID = "12345678-1234-1234-1234-123456789abc"
CHAR_TX_UUID = "12345678-1234-1234-1234-123456789abd"  # Metro → App
CHAR_RX_UUID = "12345678-1234-1234-1234-123456789abe"  # App → Metro
DEVICE_NAME_FILTER = "Metro-Digitale"


class MetroDigitaleManager(QObject):
    """
    Singleton manager for Metro Digitale BLE connection.
    
    Signals:
        measurement_received(float, str, bool): (mm, mode, auto_start)
        connection_changed(bool): connection status
        error_occurred(str): error message
    """
    
    measurement_received = Signal(float, str, bool)  # (mm, mode, auto_start)
    connection_changed = Signal(bool)
    error_occurred = Signal(str)
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        super().__init__()
        self._initialized = True
        
        if not HAS_BLEAK:
            logger.error("Bleak library not available for Metro Digitale")
            logger.error("Install bleak: pip install bleak")
        
        self.client: Optional[BleakClient] = None
        self._current_page: Optional[str] = None
        self._connected = False
        self._last_device_address: Optional[str] = None
        self._measurement_history: List[Dict[str, Any]] = []
        
        logger.info("MetroDigitaleManager initialized")
    
    def is_available(self) -> bool:
        """Check if metro receiver is available."""
        return HAS_BLEAK
    
    def set_current_page(self, page_name: str):
        """
        Set currently active page.
        
        Args:
            page_name: "semi_auto" | "automatico" | None
        """
        self._current_page = page_name
        logger.info(f"Active page: {page_name}")
    
    def try_auto_reconnect(self):
        """Attempt auto-reconnect to last device."""
        if not self.is_available():
            return
        
        try:
            from ui_qt.utils.settings import read_settings
            settings = read_settings()
        except Exception:
            logger.warning("Could not read settings for auto-reconnect")
            return
        
        if not settings.get("metro_auto_reconnect", True):
            logger.info("Auto-reconnect disabled in settings")
            return
        
        last_address = settings.get("metro_last_device_address")
        if not last_address:
            logger.info("No previous metro device saved")
            return
        
        logger.info(f"Attempting auto-reconnect to {last_address}...")
        
        # Schedule connection attempt (non-blocking)
        QTimer.singleShot(2000, lambda: self._do_auto_reconnect(last_address))
    
    def _do_auto_reconnect(self, address: str):
        """Execute auto-reconnect (called from timer)."""
        try:
            import asyncio
            
            # Check if we're already in an event loop
            try:
                loop = asyncio.get_running_loop()
                # We're in an event loop, use ensure_future
                asyncio.ensure_future(self._connect_async(address))
            except RuntimeError:
                # No event loop, create one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                success = loop.run_until_complete(self._connect_async(address))
                loop.close()
                
                if success:
                    self._connected = True
                    self._last_device_address = address
                    self.connection_changed.emit(True)
                    logger.info("✅ Auto-reconnect successful")
                else:
                    logger.warning("Auto-reconnect failed")
        except Exception as e:
            logger.error(f"Auto-reconnect error: {e}")
    
    async def _scan_async(self, timeout: float = 5.0) -> List[Dict[str, str]]:
        """Async scan for Metro Digitale devices."""
        if not HAS_BLEAK:
            return []
        
        try:
            logger.info(f"Scanning for Metro Digitale devices (timeout={timeout}s)...")
            devices = await BleakScanner.discover(timeout=timeout)
            
            result = []
            for d in devices:
                if d.name and DEVICE_NAME_FILTER in d.name:
                    result.append({
                        "name": d.name,
                        "address": d.address,
                        "rssi": getattr(d, 'rssi', None)
                    })
                    logger.info(f"Found Metro Digitale: {d.name} ({d.address})")
            
            if not result:
                logger.warning("No Metro Digitale devices found")
            
            return result
        
        except Exception as e:
            logger.error(f"Scan error: {e}")
            return []
    
    def scan_devices(self) -> List[Dict[str, str]]:
        """Scan for Metro Digitale devices (blocking)."""
        if not self.is_available():
            return []
        
        try:
            import asyncio
            
            # Check if we're already in an event loop
            try:
                loop = asyncio.get_running_loop()
                # Can't use run_until_complete in running loop
                logger.warning("Cannot scan from within event loop")
                return []
            except RuntimeError:
                # No event loop, create one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                devices = loop.run_until_complete(self._scan_async())
                loop.close()
                return devices
        
        except Exception as e:
            logger.error(f"Scan error: {e}")
            return []
    
    async def _connect_async(self, address: str) -> bool:
        """Async connect to metro device."""
        try:
            logger.info(f"Connecting to {address}...")
            
            self.client = BleakClient(
                address,
                disconnected_callback=self._on_disconnect_callback
            )
            
            await self.client.connect(timeout=10.0)
            
            if not self.client.is_connected:
                logger.error("Connection failed")
                return False
            
            # Enable notifications for TX characteristic (Metro → App)
            await self.client.start_notify(
                CHAR_TX_UUID,
                self._handle_notification
            )
            logger.info("Notifications enabled for Metro TX")
            
            logger.info(f"✅ Connected to Metro Digitale: {address}")
            return True
        
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False
    
    def connect(self, address: str) -> bool:
        """Connect to metro device (blocking)."""
        if not self.is_available():
            return False
        
        try:
            import asyncio
            
            # Check if we're already in an event loop
            try:
                loop = asyncio.get_running_loop()
                # Can't use run_until_complete in running loop
                logger.warning("Cannot connect from within event loop")
                return False
            except RuntimeError:
                # No event loop, create one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                success = loop.run_until_complete(self._connect_async(address))
                loop.close()
                
                if success:
                    self._connected = True
                    self._last_device_address = address
                    
                    # Save for auto-reconnect
                    try:
                        from ui_qt.utils.settings import read_settings, write_settings
                        settings = read_settings()
                        settings["metro_last_device_address"] = address
                        settings["metro_auto_reconnect"] = True
                        write_settings(settings)
                    except Exception as e:
                        logger.warning(f"Could not save metro settings: {e}")
                    
                    self.connection_changed.emit(True)
                    return True
                
                return False
        
        except Exception as e:
            logger.error(f"Connection error: {e}")
            self.error_occurred.emit(f"Errore connessione: {e}")
            return False
    
    async def _disconnect_async(self):
        """Async disconnect from metro."""
        if self.client and self._connected:
            try:
                await self.client.disconnect()
                logger.info("Disconnected from Metro Digitale")
            except Exception as e:
                logger.error(f"Error disconnecting: {e}")
    
    def disconnect(self):
        """Disconnect from metro (blocking)."""
        if not self.is_available() or not self._connected:
            return
        
        try:
            import asyncio
            
            # Check if we're already in an event loop
            try:
                loop = asyncio.get_running_loop()
                # Can't use run_until_complete in running loop
                asyncio.ensure_future(self._disconnect_async())
            except RuntimeError:
                # No event loop, create one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._disconnect_async())
                loop.close()
            
            self._connected = False
            self.connection_changed.emit(False)
        
        except Exception as e:
            logger.error(f"Disconnect error: {e}")
    
    def is_connected(self) -> bool:
        """Check if currently connected."""
        return self._connected
    
    def get_measurement_history(self) -> List[Dict[str, Any]]:
        """Get measurement history (last 10)."""
        return self._measurement_history[-10:]
    
    def _handle_notification(self, sender, data: bytearray):
        """
        Handle notification from Metro Digitale.
        
        Expected JSON format:
        {
            "type": "fermavetro",
            "misura_mm": 1250.5,
            "auto_start": true,
            "mode": "semi_auto"
        }
        """
        try:
            # Decode JSON payload
            json_str = data.decode('utf-8')
            payload = json.loads(json_str)
            
            # Extract fields
            misura_mm = payload.get("misura_mm")
            mode = payload.get("mode", "semi_auto")  # Default semi_auto
            auto_start = payload.get("auto_start", False)
            metro_type = payload.get("type", "unknown")
            
            if misura_mm is None:
                logger.warning("Measurement missing in payload")
                return
            
            logger.info(f"📏 Measurement: {misura_mm:.2f}mm → {mode.upper()} [auto_start={auto_start}] (type={metro_type})")
            
            # Add to history
            from datetime import datetime
            self._measurement_history.append({
                "value": misura_mm,
                "mode": mode,
                "auto_start": auto_start,
                "type": metro_type,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            
            # Keep only last 50 measurements
            if len(self._measurement_history) > 50:
                self._measurement_history = self._measurement_history[-50:]
            
            # Emit signal with routing info
            self.measurement_received.emit(float(misura_mm), mode, auto_start)
        
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from Metro: {e}")
            logger.debug(f"Raw data: {data}")
        except Exception as e:
            logger.error(f"Error processing measurement: {e}")
            self.error_occurred.emit(f"Errore processamento misura: {e}")
    
    def _on_disconnect_callback(self, client):
        """Callback when connection is lost."""
        logger.warning("⚠️ Connection lost to Metro Digitale")
        self._connected = False
        self._last_device_address = None
        self.connection_changed.emit(False)


def get_metro_manager() -> MetroDigitaleManager:
    """Get singleton instance."""
    return MetroDigitaleManager()
