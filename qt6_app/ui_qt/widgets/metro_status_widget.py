"""
Metro Digitale Status Widget

Global widget showing Metro Digitale connection status, visible in all pages.
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt
import logging

logger = logging.getLogger("metro_status_widget")


class MetroStatusWidget(QWidget):
    """
    Global metro connection status widget.
    
    Shows:
    - Connection status indicator
    - Quick disconnect button
    - Device name (when connected)
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Import here to avoid circular dependencies
        from ui_qt.services.metro_digitale_manager import get_metro_manager
        self.metro_manager = get_metro_manager()
        
        self._build()
        
        # Connect signals
        if self.metro_manager.is_available():
            self.metro_manager.connection_changed.connect(self._update_status)
            
            # Initial state
            self._update_status(self.metro_manager.is_connected())
        else:
            # Metro not available, show disabled state
            self.lbl_status.setText("📡 ⚫ Metro (N/A)")
            self.lbl_status.setToolTip("Metro Digitale non disponibile (bleak non installato)")
            self.setVisible(False)  # Hide if not available
    
    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)
        
        # Status label
        self.lbl_status = QLabel("📡 ⚪ Metro")
        self.lbl_status.setToolTip("Metro Digitale Bluetooth")
        self.lbl_status.setStyleSheet("font-weight: 600; font-size: 11pt;")
        layout.addWidget(self.lbl_status)
        
        # Disconnect button (visible only when connected)
        self.btn_disconnect = QPushButton("❌")
        self.btn_disconnect.setMaximumWidth(30)
        self.btn_disconnect.setToolTip("Disconnetti Metro Digitale")
        self.btn_disconnect.setVisible(False)
        self.btn_disconnect.clicked.connect(self._on_disconnect)
        self.btn_disconnect.setStyleSheet("""
            QPushButton {
                background: #e74c3c;
                color: white;
                border-radius: 4px;
                font-weight: 700;
            }
            QPushButton:hover { background: #c0392b; }
        """)
        layout.addWidget(self.btn_disconnect)
    
    def _update_status(self, connected: bool):
        """Update status display."""
        if connected:
            self.lbl_status.setText("📡 🟢 Metro")
            self.lbl_status.setToolTip("Metro Digitale connesso")
            self.lbl_status.setStyleSheet("font-weight: 600; font-size: 11pt; color: #27ae60;")
            self.btn_disconnect.setVisible(True)
        else:
            self.lbl_status.setText("📡 ⚪ Metro")
            self.lbl_status.setToolTip("Metro Digitale disconnesso")
            self.lbl_status.setStyleSheet("font-weight: 600; font-size: 11pt; color: #95a5a6;")
            self.btn_disconnect.setVisible(False)
    
    def _on_disconnect(self):
        """Disconnect button clicked."""
        logger.info("Disconnect button clicked")
        self.metro_manager.disconnect()
