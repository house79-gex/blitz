"""
Element toolbox sidebar for label editor.
"""
from __future__ import annotations
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QPushButton, 
                               QScrollArea, QFrame, QSizePolicy)
from PySide6.QtCore import Qt, Signal

from .label_element import (TextElement, FieldElement, BarcodeElement, 
                            ImageElement, LineElement, ShapeElement)


class LabelElementSidebar(QWidget):
    """Sidebar with draggable element tools."""
    
    element_requested = Signal(object)  # Emitted when user wants to add element
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()
    
    def _build(self):
        """Build the sidebar UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # Title
        title = QLabel("Elementi")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)
        
        # Scroll area for elements
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        
        # Container for element buttons
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(8)
        container_layout.setContentsMargins(0, 0, 0, 0)
        
        # Add element buttons
        self._add_element_button(container_layout, "📝 Testo", "text", 
                                "Aggiungi testo statico")
        self._add_element_button(container_layout, "🔢 Campo Dati", "field",
                                "Aggiungi campo dinamico")
        self._add_element_button(container_layout, "📊 Barcode", "barcode",
                                "Aggiungi barcode/QR")
        self._add_element_button(container_layout, "🖼️ Immagine", "image",
                                "Aggiungi logo/immagine")
        self._add_element_button(container_layout, "➖ Linea", "line",
                                "Aggiungi linea separatore")
        self._add_element_button(container_layout, "⬜ Forma", "shape",
                                "Aggiungi rettangolo/cerchio")
        
        container_layout.addStretch()
        
        scroll.setWidget(container)
        layout.addWidget(scroll)
        
        self.setMaximumWidth(200)
        self.setStyleSheet("""
            QWidget {
                background-color: #f5f5f5;
            }
        """)
    
    def _add_element_button(self, layout: QVBoxLayout, label: str, 
                           element_type: str, tooltip: str):
        """Add an element button to the sidebar."""
        btn = QPushButton(label)
        btn.setToolTip(tooltip)
        btn.setMinimumHeight(40)
        btn.setStyleSheet("""
            QPushButton {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 8px;
                text-align: left;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #e8f4f8;
                border-color: #0066cc;
            }
            QPushButton:pressed {
                background-color: #d0e8f0;
            }
        """)
        
        btn.clicked.connect(lambda: self._on_element_clicked(element_type))
        layout.addWidget(btn)
    
    def _on_element_clicked(self, element_type: str):
        """Handle element button click."""
        # Create element at default position
        element = None
        
        if element_type == "text":
            element = TextElement(text="Testo", x=10, y=10)
        elif element_type == "field":
            element = FieldElement(source="length", format_string="{} mm", x=10, y=10)
        elif element_type == "barcode":
            element = BarcodeElement(source="order_id", x=10, y=10)
        elif element_type == "image":
            element = ImageElement(x=10, y=10)
        elif element_type == "line":
            element = LineElement(x=10, y=10, width=80)
        elif element_type == "shape":
            element = ShapeElement(x=10, y=10)
        
        if element:
            self.element_requested.emit(element)
