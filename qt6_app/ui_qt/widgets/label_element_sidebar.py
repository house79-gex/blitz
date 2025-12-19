"""
Element toolbox sidebar for label editor.
"""
from __future__ import annotations
import logging
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QPushButton, 
                               QScrollArea, QFrame, QSizePolicy)
from PySide6.QtCore import Qt, Signal

from .label_element import (TextElement, FieldElement, BarcodeElement, 
                            ImageElement, LineElement, ShapeElement)

logger = logging.getLogger(__name__)


class LabelElementSidebar(QWidget):
    """Sidebar with draggable element tools."""
    
    element_requested = Signal(object)  # Emitted when user wants to add element
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.typologies_store = None
        try:
            from ui_qt.services.typologies_store import TypologiesStore
            self.typologies_store = TypologiesStore()
        except Exception as e:
            logger.warning(f"Could not load TypologiesStore: {e}")
        
        self._build()
        self._load_elements_from_typologies()
    
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
        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setSpacing(8)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        
        # Add standard element buttons
        self._add_element_button(self.container_layout, "📝 Testo", "text", 
                                "Aggiungi testo statico")
        self._add_element_button(self.container_layout, "🔢 Campo Dati", "field",
                                "Aggiungi campo dinamico")
        self._add_element_button(self.container_layout, "📊 Barcode", "barcode",
                                "Aggiungi barcode/QR")
        self._add_element_button(self.container_layout, "🖼️ Immagine", "image",
                                "Aggiungi logo/immagine")
        self._add_element_button(self.container_layout, "➖ Linea", "line",
                                "Aggiungi linea separatore")
        self._add_element_button(self.container_layout, "⬜ Forma", "shape",
                                "Aggiungi rettangolo/cerchio")
        
        # Add stretch after standard elements
        self.container_layout.addStretch()
        
        scroll.setWidget(self.container)
        layout.addWidget(scroll)
        
        self.setMaximumWidth(200)
        self.setStyleSheet("""
            QWidget {
                background-color: #f5f5f5;
            }
        """)
    
    def _load_elements_from_typologies(self):
        """Carica elementi dinamicamente da tipologie."""
        if not self.typologies_store:
            return
        
        try:
            # Insert separator before typologies if we have any
            separator = QLabel("─ Tipologie ─")
            separator.setStyleSheet("color: #999; font-size: 10px; padding: 5px;")
            separator.setAlignment(Qt.AlignCenter)
            # Insert before stretch
            self.container_layout.insertWidget(self.container_layout.count() - 1, separator)
            
            typologies = self.typologies_store.list_typologies()
            element_names_added = set()
            
            for typo in typologies:
                try:
                    typo_full = self.typologies_store.get_typology_full(typo["id"])
                    if not typo_full:
                        continue
                    
                    components = typo_full.get("componenti", [])
                    for comp in components:
                        element_name = comp.get("nome", "").strip()
                        if element_name and element_name not in element_names_added:
                            # Add element button for this component
                            self._add_typology_element_button(
                                self.container_layout,
                                f"🏷️ {element_name}",
                                element_name,
                                f"Elemento da tipologia: {typo.get('name', '')}"
                            )
                            element_names_added.add(element_name)
                except Exception as e:
                    logger.error(f"Error loading typology {typo.get('id')}: {e}")
                    
        except Exception as e:
            logger.error(f"Error loading elements from typologies: {e}")
    
    def _add_typology_element_button(self, layout: QVBoxLayout, label: str, 
                                    element_name: str, tooltip: str):
        """Add a typology element button to the sidebar."""
        btn = QPushButton(label)
        btn.setToolTip(tooltip)
        btn.setMinimumHeight(35)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #fff9e6;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 6px;
                text-align: left;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #fff4cc;
                border-color: #ff9900;
            }
            QPushButton:pressed {
                background-color: #ffe599;
            }
        """)
        
        btn.clicked.connect(lambda: self._on_typology_element_clicked(element_name))
        # Insert before stretch
        layout.insertWidget(layout.count() - 1, btn)
    
    def _on_typology_element_clicked(self, element_name: str):
        """Handle typology element button click."""
        # Create a text element with the component name
        element = TextElement(text=element_name, x=10, y=10)
        self.element_requested.emit(element)
    
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
