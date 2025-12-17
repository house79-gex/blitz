"""
Reusable Bluetooth Caliper connection widget.

Can be embedded in:
- Semi-Auto page (direct measurement input)
- Automatico page (batch measurement collection)
- Standalone page (measurement list)

Signals:
- measurement_received(float): Emitted when measurement arrives
- go_command_received(): Emitted when GO button pressed on caliper
- connected(): Emitted when connection established
- disconnected(): Emitted when connection lost
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QComboBox, QFrame
)
from PySide6.QtCore import Signal, QTimer, Qt
import logging

from ui_qt.services.bluetooth_caliper import BluetoothCaliperQt, check_bleak_available

logger = logging.getLogger("caliper_widget")


class CaliperWidget(QWidget):
    """
    Bluetooth caliper connection widget.
    
    Features:
    - Device scanning
    - Connection/disconnection
    - Status indicator
    - Signal emission for measurements/commands
    
    Signals:
        measurement_received(float): mm value received
        go_command_received(): GO command received
        connected(): Connection established
        disconnected(): Connection lost
    """
    
    measurement_received = Signal(float)
    go_command_received = Signal()
    connected = Signal()
    disconnected = Signal()
    
    def __init__(self, parent=None, compact=False):
        """
        Args:
            parent: Parent widget
            compact: If True, use compact layout (fewer labels)
        """
        super().__init__(parent)
        self.compact = compact
        
        # Check Bleak availability
        if not check_bleak_available():
            logger.error("Bleak library not installed - caliper will not work")
        
        self.caliper = BluetoothCaliperQt()
        self.caliper.set_measurement_callback(self._on_measurement)
        self.caliper.set_go_callback(self._on_go)
        self.caliper.set_connection_lost_callback(self._on_connection_lost)
        
        self._build()
    
    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)
        
        # Status indicator
        self.lbl_status = QLabel("⚪ Disconnesso")
        self.lbl_status.setStyleSheet("font-weight: 600; padding: 4px 8px;")
        layout.addWidget(self.lbl_status)
        
        # Device selector
        self.combo_devices = QComboBox()
        self.combo_devices.setMinimumWidth(220)
        self.combo_devices.setPlaceholderText("Seleziona dispositivo...")
        layout.addWidget(self.combo_devices)
        
        # Scan button
        self.btn_scan = QPushButton("🔍 Cerca")
        self.btn_scan.setToolTip("Cerca calibri Bluetooth nelle vicinanze")
        self.btn_scan.clicked.connect(self._scan_devices)
        self.btn_scan.setStyleSheet("""
            QPushButton {
                background: #3498db;
                color: white;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: 600;
            }
            QPushButton:hover { background: #2980b9; }
            QPushButton:disabled { background: #7f8c8d; }
        """)
        layout.addWidget(self.btn_scan)
        
        # Connect button
        self.btn_connect = QPushButton("🔌 Connetti")
        self.btn_connect.setToolTip("Connetti al calibro selezionato")
        self.btn_connect.clicked.connect(self._connect)
        self.btn_connect.setEnabled(False)
        self.btn_connect.setStyleSheet("""
            QPushButton {
                background: #27ae60;
                color: white;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: 600;
            }
            QPushButton:hover { background: #229954; }
            QPushButton:disabled { background: #7f8c8d; }
        """)
        layout.addWidget(self.btn_connect)
        
        # Disconnect button
        self.btn_disconnect = QPushButton("❌ Disconnetti")
        self.btn_disconnect.setToolTip("Disconnetti dal calibro")
        self.btn_disconnect.clicked.connect(self._disconnect)
        self.btn_disconnect.setEnabled(False)
        self.btn_disconnect.setStyleSheet("""
            QPushButton {
                background: #e74c3c;
                color: white;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: 600;
            }
            QPushButton:hover { background: #c0392b; }
            QPushButton:disabled { background: #7f8c8d; }
        """)
        layout.addWidget(self.btn_disconnect)
        
        if not self.compact:
            layout.addStretch()
    
    def _scan_devices(self):
        """Scan for BLE caliper devices."""
        if not check_bleak_available():
            self.lbl_status.setText("❌ Bleak not installed")
            logger.error("Cannot scan: Bleak library not installed")
            return
        
        self.btn_scan.setEnabled(False)
        self.btn_scan.setText("⏳ Scanning...")
        self.lbl_status.setText("🔍 Scanning...")
        self.combo_devices.clear()
        
        # Run scan in next event loop iteration (non-blocking UI)
        QTimer.singleShot(100, self._do_scan)
    
    def _do_scan(self):
        """Execute actual scan (blocking call)."""
        try:
            devices = self.caliper.scan_devices_sync(timeout=5.0)
            
            self.combo_devices.clear()
            
            if devices:
                for d in devices:
                    display_text = f"{d['name']} ({d['address']})"
                    self.combo_devices.addItem(display_text, d['address'])
                
                self.lbl_status.setText(f"🔍 Trovati {len(devices)} dispositivi")
                self.btn_connect.setEnabled(True)
                logger.info(f"Found {len(devices)} caliper devices")
            else:
                self.lbl_status.setText("⚠️ Nessun calibro trovato")
                self.btn_connect.setEnabled(False)
                logger.warning("No caliper devices found")
        
        except Exception as e:
            logger.error(f"Scan error: {e}")
            self.lbl_status.setText(f"❌ Errore scan")
        
        finally:
            self.btn_scan.setEnabled(True)
            self.btn_scan.setText("🔍 Cerca")
    
    def _connect(self):
        """Connect to selected device."""
        if self.combo_devices.currentIndex() < 0:
            return
        
        address = self.combo_devices.currentData()
        device_name = self.combo_devices.currentText()
        
        self.btn_connect.setEnabled(False)
        self.btn_scan.setEnabled(False)
        self.lbl_status.setText("⏳ Connessione...")
        
        # Run connection in next event loop iteration
        QTimer.singleShot(100, lambda: self._do_connect(address, device_name))
    
    def _do_connect(self, address: str, device_name: str):
        """Execute actual connection (blocking call)."""
        try:
            success = self.caliper.connect_sync(address)
            
            if success:
                self.lbl_status.setText(f"🟢 Connesso")
                self.btn_connect.setEnabled(False)
                self.btn_disconnect.setEnabled(True)
                self.combo_devices.setEnabled(False)
                self.connected.emit()
                logger.info(f"Connected to {device_name}")
            else:
                self.lbl_status.setText("❌ Connessione fallita")
                self.btn_connect.setEnabled(True)
                self.btn_scan.setEnabled(True)
                logger.error("Connection failed")
        
        except Exception as e:
            logger.error(f"Connection error: {e}")
            self.lbl_status.setText("❌ Errore connessione")
            self.btn_connect.setEnabled(True)
            self.btn_scan.setEnabled(True)
    
    def _disconnect(self):
        """Disconnect from caliper."""
        try:
            self.caliper.disconnect_sync()
            self._on_connection_lost()
        except Exception as e:
            logger.error(f"Disconnect error: {e}")
    
    def _on_measurement(self, value_mm: float):
        """Callback when measurement received."""
        logger.info(f"Measurement received: {value_mm:.2f}mm")
        self.measurement_received.emit(value_mm)
    
    def _on_go(self):
        """Callback when GO command received."""
        logger.info("GO command received")
        self.go_command_received.emit()
    
    def _on_connection_lost(self):
        """Callback when connection is lost."""
        self.lbl_status.setText("⚪ Disconnesso")
        self.btn_connect.setEnabled(False)
        self.btn_disconnect.setEnabled(False)
        self.btn_scan.setEnabled(True)
        self.combo_devices.setEnabled(True)
        self.disconnected.emit()
        logger.warning("Connection lost")
    
    def is_connected(self) -> bool:
        """Check if currently connected."""
        return self.caliper.is_connected()
    
    def get_device_address(self) -> str:
        """Get connected device address."""
        addr = self.caliper.get_device_address()
        return addr if addr else ""
