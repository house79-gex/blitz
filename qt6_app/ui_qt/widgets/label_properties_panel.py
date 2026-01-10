"""
Properties panel for editing selected element.
"""
from __future__ import annotations
import logging
from typing import Optional
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QLineEdit, 
                               QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox,
                               QFormLayout, QScrollArea, QPushButton, QColorDialog,
                               QHBoxLayout)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from .label_element import (LabelElement, TextElement, FieldElement, 
                            BarcodeElement, ImageElement, LineElement, ShapeElement)

logger = logging.getLogger(__name__)


class LabelPropertiesPanel(QWidget):
    """Properties editor for selected label element."""
    
    property_changed = Signal()  # Emitted when property is modified
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_element: Optional[LabelElement] = None
        self._updating = False  # Flag to prevent recursive updates
        self._build()
    
    def _build(self):
        """Build the properties panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # Title
        self.title_label = QLabel("Proprietà")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self.title_label)
        
        # Scroll area for properties
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        
        # Container for properties
        self.props_container = QWidget()
        self.props_layout = QFormLayout(self.props_container)
        self.props_layout.setSpacing(8)
        
        scroll.setWidget(self.props_container)
        layout.addWidget(scroll)
        
        # Delete button
        self.delete_btn = QPushButton("🗑️ Elimina Elemento")
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
        """)
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        layout.addWidget(self.delete_btn)
        
        self.setMaximumWidth(250)
        self.setStyleSheet("""
            QWidget {
                background-color: #f5f5f5;
            }
        """)
        
        self._show_empty_state()
    
    def set_element(self, element: Optional[LabelElement]):
        """Set the element to edit."""
        self.current_element = element
        self._updating = True  # Block signals during update
        self._rebuild_properties()
        self._updating = False  # Re-enable signals
    
    def _rebuild_properties(self):
        """Rebuild properties form for current element."""
        # Clear existing properties
        while self.props_layout.count():
            item = self.props_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if not self.current_element:
            self._show_empty_state()
            self.delete_btn.setEnabled(False)
            return
        
        self.delete_btn.setEnabled(True)
        
        # Common properties
        self._add_position_properties()
        self._add_size_properties()
        
        # Element-specific properties
        if isinstance(self.current_element, TextElement):
            self._add_text_properties()
        elif isinstance(self.current_element, FieldElement):
            self._add_field_properties()
        elif isinstance(self.current_element, BarcodeElement):
            self._add_barcode_properties()
        elif isinstance(self.current_element, ImageElement):
            self._add_image_properties()
        elif isinstance(self.current_element, LineElement):
            self._add_line_properties()
        elif isinstance(self.current_element, ShapeElement):
            self._add_shape_properties()
    
    def _show_empty_state(self):
        """Show empty state message."""
        label = QLabel("Nessun elemento selezionato")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: #999; padding: 20px;")
        self.props_layout.addRow(label)
    
    def _add_position_properties(self):
        """Add position properties."""
        elem = self.current_element
        
        # X position
        x_spin = QDoubleSpinBox()
        x_spin.setRange(0, 1000)
        x_spin.setValue(elem.x)
        x_spin.setSuffix(" mm")
        x_spin.valueChanged.connect(lambda v: self._update_property("x", v))
        self.props_layout.addRow("Posizione X:", x_spin)
        
        # Y position
        y_spin = QDoubleSpinBox()
        y_spin.setRange(0, 1000)
        y_spin.setValue(elem.y)
        y_spin.setSuffix(" mm")
        y_spin.valueChanged.connect(lambda v: self._update_property("y", v))
        self.props_layout.addRow("Posizione Y:", y_spin)
    
    def _add_size_properties(self):
        """Add size properties."""
        elem = self.current_element
        
        # Width
        width_spin = QDoubleSpinBox()
        width_spin.setRange(1, 1000)
        width_spin.setValue(elem.width)
        width_spin.setSuffix(" mm")
        width_spin.valueChanged.connect(lambda v: self._update_property("width", v))
        self.props_layout.addRow("Larghezza:", width_spin)
        
        # Height
        height_spin = QDoubleSpinBox()
        height_spin.setRange(1, 1000)
        height_spin.setValue(elem.height)
        height_spin.setSuffix(" mm")
        height_spin.valueChanged.connect(lambda v: self._update_property("height", v))
        self.props_layout.addRow("Altezza:", height_spin)
    
    def _add_text_properties(self):
        """Add text element properties."""
        elem: TextElement = self.current_element
        
        # Text content
        text_edit = QLineEdit(elem.text)
        text_edit.textChanged.connect(lambda v: self._update_property("text", v))
        self.props_layout.addRow("Testo:", text_edit)
        
        # Font family
        font_combo = QComboBox()
        font_combo.addItems(["Arial", "Helvetica", "Times New Roman", "Courier"])
        font_combo.setCurrentText(elem.font_family)
        font_combo.currentTextChanged.connect(lambda v: self._update_property("font_family", v))
        self.props_layout.addRow("Font:", font_combo)
        
        # Font size
        size_spin = QSpinBox()
        size_spin.setRange(6, 72)
        size_spin.setValue(elem.font_size)
        size_spin.valueChanged.connect(lambda v: self._update_property("font_size", v))
        self.props_layout.addRow("Dimensione:", size_spin)
        
        # Bold
        bold_check = QCheckBox()
        bold_check.setChecked(elem.bold)
        bold_check.toggled.connect(lambda v: self._update_property("bold", v))
        self.props_layout.addRow("Grassetto:", bold_check)
        
        # Italic
        italic_check = QCheckBox()
        italic_check.setChecked(elem.italic)
        italic_check.toggled.connect(lambda v: self._update_property("italic", v))
        self.props_layout.addRow("Corsivo:", italic_check)
    
    def _add_field_properties(self):
        """Add field element properties."""
        elem: FieldElement = self.current_element
        
        # Data source
        source_combo = QComboBox()
        source_combo.addItems(FieldElement.SOURCES)
        source_combo.setCurrentText(elem.source)
        source_combo.currentTextChanged.connect(lambda v: self._update_property("source", v))
        self.props_layout.addRow("Sorgente:", source_combo)
        
        # Format string
        format_edit = QLineEdit(elem.format_string)
        format_edit.textChanged.connect(lambda v: self._update_property("format_string", v))
        self.props_layout.addRow("Formato:", format_edit)
        
        # Font properties (same as text)
        font_combo = QComboBox()
        font_combo.addItems(["Arial", "Helvetica", "Times New Roman", "Courier"])
        font_combo.setCurrentText(elem.font_family)
        font_combo.currentTextChanged.connect(lambda v: self._update_property("font_family", v))
        self.props_layout.addRow("Font:", font_combo)
        
        size_spin = QSpinBox()
        size_spin.setRange(6, 72)
        size_spin.setValue(elem.font_size)
        size_spin.valueChanged.connect(lambda v: self._update_property("font_size", v))
        self.props_layout.addRow("Dimensione:", size_spin)
    
    def _add_barcode_properties(self):
        """Add barcode element properties."""
        elem: BarcodeElement = self.current_element
        
        # Data source
        source_combo = QComboBox()
        source_combo.addItems(FieldElement.SOURCES)
        source_combo.setCurrentText(elem.source)
        source_combo.currentTextChanged.connect(lambda v: self._update_property("source", v))
        self.props_layout.addRow("Sorgente:", source_combo)
        
        # Barcode type
        type_combo = QComboBox()
        type_combo.addItems(BarcodeElement.BARCODE_TYPES)
        type_combo.setCurrentText(elem.barcode_type)
        type_combo.currentTextChanged.connect(lambda v: self._update_property("barcode_type", v))
        self.props_layout.addRow("Tipo:", type_combo)
    
    def _add_image_properties(self):
        """Add image element properties."""
        elem: ImageElement = self.current_element
        
        # Image path
        path_edit = QLineEdit(elem.image_path)
        path_edit.textChanged.connect(lambda v: self._update_property("image_path", v))
        self.props_layout.addRow("Percorso:", path_edit)
        
        # Browse button
        browse_btn = QPushButton("Sfoglia...")
        # TODO: Add file dialog
        self.props_layout.addRow("", browse_btn)
    
    def _add_line_properties(self):
        """Add line element properties."""
        elem: LineElement = self.current_element
        
        # Thickness
        thickness_spin = QSpinBox()
        thickness_spin.setRange(1, 10)
        thickness_spin.setValue(elem.thickness)
        thickness_spin.valueChanged.connect(lambda v: self._update_property("thickness", v))
        self.props_layout.addRow("Spessore:", thickness_spin)
    
    def _add_shape_properties(self):
        """Add shape element properties."""
        elem: ShapeElement = self.current_element
        
        # Shape type
        type_combo = QComboBox()
        type_combo.addItems(ShapeElement.SHAPE_TYPES)
        type_combo.setCurrentText(elem.shape_type)
        type_combo.currentTextChanged.connect(lambda v: self._update_property("shape_type", v))
        self.props_layout.addRow("Tipo:", type_combo)
        
        # Border width
        border_spin = QSpinBox()
        border_spin.setRange(0, 10)
        border_spin.setValue(elem.border_width)
        border_spin.valueChanged.connect(lambda v: self._update_property("border_width", v))
        self.props_layout.addRow("Bordo:", border_spin)
    
    def _update_property(self, prop_name: str, value):
        """Update element property."""
        if self._updating or not self.current_element:
            return
        
        # Apply property to element
        try:
            setattr(self.current_element, prop_name, value)
            self.property_changed.emit()
        except Exception as e:
            logger.error(f"Error setting property {prop_name}: {e}")
    
    def _on_delete_clicked(self):
        """Handle delete button click."""
        # This will be handled by the parent editor
        pass
