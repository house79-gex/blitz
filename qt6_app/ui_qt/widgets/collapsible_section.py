"""
Collapsible Section Widget
File: qt6_app/ui_qt/widgets/collapsible_section.py

Provides a collapsible container with smooth animation for grouping UI elements.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QFrame, QSizePolicy
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Signal
from PySide6.QtGui import QFont

# Qt's maximum widget size constant
QWIDGETSIZE_MAX = 16777215


class CollapsibleSection(QWidget):
    """
    Collapsible section widget with smooth animation.
    
    Features:
    - Click header to expand/collapse
    - Smooth animated transitions
    - Visual indicator (▼/▶ arrow)
    - Preserves content when collapsed
    
    Signals:
        toggled(bool): Emitted when section is expanded (True) or collapsed (False)
    """
    
    toggled = Signal(bool)  # True = expanded, False = collapsed
    
    def __init__(self, title: str, parent=None, start_collapsed: bool = False):
        """
        Initialize collapsible section.
        
        Args:
            title: Section title text
            parent: Parent widget
            start_collapsed: If True, section starts collapsed
        """
        super().__init__(parent)
        self._is_collapsed = start_collapsed
        self._title = title
        
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Header button (clickable)
        self.header = QPushButton()
        self.header.setCheckable(True)
        self.header.setChecked(not start_collapsed)
        self.header.clicked.connect(self._toggle)
        self._update_header_text()
        
        # Style the header
        self.header.setStyleSheet("""
            QPushButton {
                background: #34495e;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 12px;
                text-align: left;
                font-weight: 600;
                font-size: 11pt;
            }
            QPushButton:hover {
                background: #415a77;
            }
            QPushButton:pressed {
                background: #2c3e50;
            }
        """)
        
        main_layout.addWidget(self.header)
        
        # Content container
        self.content_container = QFrame()
        self.content_container.setFrameShape(QFrame.Shape.StyledPanel)
        self.content_container.setStyleSheet("""
            QFrame {
                border: 1px solid #3b4b5a;
                border-radius: 6px;
                background: #ecf0f3;
                margin-top: 2px;
            }
        """)
        
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(8, 8, 8, 8)
        self.content_layout.setSpacing(6)
        
        main_layout.addWidget(self.content_container)
        
        # Animation for collapse/expand
        self.animation = QPropertyAnimation(self.content_container, b"maximumHeight")
        self.animation.setDuration(250)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        
        # Set initial state
        if start_collapsed:
            self.content_container.setMaximumHeight(0)
            self.content_container.setVisible(False)
        else:
            # Let it expand naturally
            self.content_container.setMaximumHeight(QWIDGETSIZE_MAX)
    
    def _update_header_text(self):
        """Update header text with arrow indicator."""
        arrow = "▼" if not self._is_collapsed else "▶"
        self.header.setText(f"{arrow} {self._title}")
    
    def _toggle(self):
        """Toggle collapse state."""
        if self._is_collapsed:
            self.expand()
        else:
            self.collapse()
    
    def collapse(self):
        """Collapse the section with animation."""
        if self._is_collapsed:
            return
        
        self._is_collapsed = True
        self._update_header_text()
        self.header.setChecked(False)
        
        # Get current height before animation
        current_height = self.content_container.height()
        
        # Animate to 0 height
        self.animation.setStartValue(current_height)
        self.animation.setEndValue(0)
        self.animation.finished.connect(self._on_collapse_finished)
        self.animation.start()
        
        self.toggled.emit(False)
    
    def _on_collapse_finished(self):
        """Called when collapse animation finishes."""
        self.content_container.setVisible(False)
        try:
            self.animation.finished.disconnect(self._on_collapse_finished)
        except (TypeError, RuntimeError):
            # TypeError: signal already disconnected
            # RuntimeError: wrapped C/C++ object has been deleted
            pass
    
    def expand(self):
        """Expand the section with animation."""
        if not self._is_collapsed:
            return
        
        self._is_collapsed = False
        self._update_header_text()
        self.header.setChecked(True)
        
        # Make visible before animation
        self.content_container.setVisible(True)
        
        # Calculate target height
        self.content_container.setMaximumHeight(QWIDGETSIZE_MAX)
        target_height = self.content_container.sizeHint().height()
        
        # Animate from 0 to target height
        self.animation.setStartValue(0)
        self.animation.setEndValue(target_height)
        self.animation.finished.connect(self._on_expand_finished)
        self.animation.start()
        
        self.toggled.emit(True)
    
    def _on_expand_finished(self):
        """Called when expand animation finishes."""
        # Remove height constraint so content can resize naturally
        self.content_container.setMaximumHeight(QWIDGETSIZE_MAX)
        try:
            self.animation.finished.disconnect(self._on_expand_finished)
        except (TypeError, RuntimeError):
            # TypeError: signal already disconnected
            # RuntimeError: wrapped C/C++ object has been deleted
            pass
    
    def add_content(self, widget: QWidget):
        """
        Add a widget to the content area.
        
        Args:
            widget: Widget to add to content
        """
        self.content_layout.addWidget(widget)
    
    def add_content_layout(self, layout):
        """
        Add a layout to the content area.
        
        Args:
            layout: Layout to add to content
        """
        self.content_layout.addLayout(layout)
    
    def is_collapsed(self) -> bool:
        """Check if section is currently collapsed."""
        return self._is_collapsed
    
    def set_collapsed(self, collapsed: bool):
        """
        Set collapse state without animation.
        
        Args:
            collapsed: True to collapse, False to expand
        """
        if collapsed:
            if not self._is_collapsed:
                self._is_collapsed = True
                self._update_header_text()
                self.header.setChecked(False)
                self.content_container.setMaximumHeight(0)
                self.content_container.setVisible(False)
        else:
            if self._is_collapsed:
                self._is_collapsed = False
                self._update_header_text()
                self.header.setChecked(True)
                self.content_container.setMaximumHeight(QWIDGETSIZE_MAX)
                self.content_container.setVisible(True)
