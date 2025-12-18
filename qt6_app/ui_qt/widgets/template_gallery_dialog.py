"""
Template gallery dialog for browsing and selecting templates.
"""
from __future__ import annotations
from typing import Optional, Dict, Any
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                               QPushButton, QListWidget, QListWidgetItem,
                               QTextEdit, QDialogButtonBox, QWidget, QFrame)
from PySide6.QtCore import Qt, Signal

from ..services.label_template_manager import LabelTemplateManager


class TemplateGalleryDialog(QDialog):
    """Dialog for browsing and selecting label templates."""
    
    template_selected = Signal(dict)  # Emitted when template is selected
    
    def __init__(self, template_manager: LabelTemplateManager, parent=None):
        super().__init__(parent)
        self.template_manager = template_manager
        self.selected_template: Optional[Dict[str, Any]] = None
        
        self.setWindowTitle("Galleria Template")
        self.setMinimumSize(700, 500)
        self._build()
        self._load_templates()
    
    def _build(self):
        """Build the dialog UI."""
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel("Scegli un Template")
        title.setStyleSheet("font-size: 18px; font-weight: bold; padding: 10px;")
        layout.addWidget(title)
        
        # Content area
        content = QHBoxLayout()
        
        # Left: Template list
        list_container = QVBoxLayout()
        
        list_label = QLabel("Template Disponibili")
        list_label.setStyleSheet("font-weight: bold;")
        list_container.addWidget(list_label)
        
        self.template_list = QListWidget()
        self.template_list.setStyleSheet("""
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #eee;
            }
            QListWidget::item:selected {
                background-color: #e8f4f8;
                color: black;
            }
            QListWidget::item:hover {
                background-color: #f0f8ff;
            }
        """)
        self.template_list.currentItemChanged.connect(self._on_template_selected)
        list_container.addWidget(self.template_list)
        
        content.addLayout(list_container, 1)
        
        # Right: Template preview/info
        preview_container = QVBoxLayout()
        
        preview_label = QLabel("Anteprima")
        preview_label.setStyleSheet("font-weight: bold;")
        preview_container.addWidget(preview_label)
        
        # Preview frame
        self.preview_frame = QFrame()
        self.preview_frame.setFrameStyle(QFrame.Box | QFrame.Sunken)
        self.preview_frame.setMinimumSize(300, 200)
        self.preview_frame.setStyleSheet("background-color: white;")
        preview_container.addWidget(self.preview_frame)
        
        # Info area
        info_label = QLabel("Informazioni")
        info_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        preview_container.addWidget(info_label)
        
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setMaximumHeight(150)
        self.info_text.setStyleSheet("""
            QTextEdit {
                background-color: #f9f9f9;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        preview_container.addWidget(self.info_text)
        
        content.addLayout(preview_container, 1)
        
        layout.addLayout(content)
        
        # Buttons
        button_box = QDialogButtonBox()
        
        # Custom buttons
        self.load_btn = QPushButton("📂 Carica Template")
        self.load_btn.setEnabled(False)
        self.load_btn.clicked.connect(self._on_load_clicked)
        button_box.addButton(self.load_btn, QDialogButtonBox.AcceptRole)
        
        cancel_btn = QPushButton("Annulla")
        cancel_btn.clicked.connect(self.reject)
        button_box.addButton(cancel_btn, QDialogButtonBox.RejectRole)
        
        layout.addWidget(button_box)
    
    def _load_templates(self):
        """Load templates into list."""
        templates = self.template_manager.list_templates()
        
        for template_info in templates:
            item = QListWidgetItem()
            
            # Create display text
            name = template_info.get("name", "Unknown")
            element_count = template_info.get("element_count", 0)
            
            text = f"<b>{name}</b><br>"
            text += f"<small>{element_count} elementi</small>"
            
            item.setText(text)
            item.setData(Qt.UserRole, template_info)
            
            # Add icon based on template type
            if name == "Standard":
                item.setText("⭐ " + name)
            elif name == "Minimal":
                item.setText("📋 " + name)
            elif name == "Barcode_Focus":
                item.setText("📊 " + name)
            elif name == "Empty":
                item.setText("⬜ " + name)
            else:
                item.setText("📄 " + name)
            
            self.template_list.addItem(item)
        
        # Select first item by default
        if self.template_list.count() > 0:
            self.template_list.setCurrentRow(0)
    
    def _on_template_selected(self, current: QListWidgetItem, previous: QListWidgetItem):
        """Handle template selection."""
        if not current:
            self.load_btn.setEnabled(False)
            self.info_text.clear()
            return
        
        template_info = current.data(Qt.UserRole)
        
        # Update info text
        info_html = f"<h3>{template_info.get('name', 'Unknown')}</h3>"
        info_html += f"<p>{template_info.get('description', 'Nessuna descrizione')}</p>"
        info_html += f"<p><b>Dimensioni:</b> {template_info.get('label_width', 0)} x {template_info.get('label_height', 0)} mm</p>"
        info_html += f"<p><b>Elementi:</b> {template_info.get('element_count', 0)}</p>"
        
        updated = template_info.get('updated_at', '')
        if updated:
            info_html += f"<p><small><i>Aggiornato: {updated[:10]}</i></small></p>"
        
        self.info_text.setHtml(info_html)
        
        self.load_btn.setEnabled(True)
    
    def _on_load_clicked(self):
        """Handle load button click."""
        current_item = self.template_list.currentItem()
        if not current_item:
            return
        
        template_info = current_item.data(Qt.UserRole)
        template_name = template_info.get("name")
        
        # Load full template
        template = self.template_manager.load_template(template_name)
        
        if template:
            self.selected_template = template
            self.template_selected.emit(template)
            self.accept()
    
    def get_selected_template(self) -> Optional[Dict[str, Any]]:
        """Get the selected template."""
        return self.selected_template


class TemplateManagerDialog(QDialog):
    """Dialog for managing templates (save, delete, duplicate)."""
    
    def __init__(self, template_manager: LabelTemplateManager, parent=None):
        super().__init__(parent)
        self.template_manager = template_manager
        
        self.setWindowTitle("Gestione Template")
        self.setMinimumSize(600, 400)
        self._build()
        self._load_templates()
    
    def _build(self):
        """Build the dialog UI."""
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel("Gestione Template")
        title.setStyleSheet("font-size: 18px; font-weight: bold; padding: 10px;")
        layout.addWidget(title)
        
        # Template list
        self.template_list = QListWidget()
        self.template_list.currentItemChanged.connect(self._on_template_selected)
        layout.addWidget(self.template_list)
        
        # Action buttons
        actions_layout = QHBoxLayout()
        
        self.duplicate_btn = QPushButton("📋 Duplica")
        self.duplicate_btn.setEnabled(False)
        self.duplicate_btn.clicked.connect(self._on_duplicate_clicked)
        actions_layout.addWidget(self.duplicate_btn)
        
        self.delete_btn = QPushButton("🗑️ Elimina")
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        actions_layout.addWidget(self.delete_btn)
        
        actions_layout.addStretch()
        
        layout.addLayout(actions_layout)
        
        # Close button
        close_btn = QPushButton("Chiudi")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
    
    def _load_templates(self):
        """Load templates into list."""
        self.template_list.clear()
        templates = self.template_manager.list_templates()
        
        for template_info in templates:
            item = QListWidgetItem()
            name = template_info.get("name", "Unknown")
            item.setText(name)
            item.setData(Qt.UserRole, template_info)
            self.template_list.addItem(item)
    
    def _on_template_selected(self, current: QListWidgetItem, previous: QListWidgetItem):
        """Handle template selection."""
        enabled = current is not None
        self.duplicate_btn.setEnabled(enabled)
        
        # Allow deletion except for default templates
        if current:
            template_info = current.data(Qt.UserRole)
            name = template_info.get("name", "")
            is_default = name in ["Standard", "Minimal", "Barcode_Focus", "Empty"]
            self.delete_btn.setEnabled(not is_default)
        else:
            self.delete_btn.setEnabled(False)
    
    def _on_duplicate_clicked(self):
        """Handle duplicate button click."""
        current_item = self.template_list.currentItem()
        if not current_item:
            return
        
        template_info = current_item.data(Qt.UserRole)
        src_name = template_info.get("name")
        
        # Generate new name
        new_name = f"{src_name}_copia"
        counter = 1
        while self.template_manager.load_template(new_name):
            new_name = f"{src_name}_copia_{counter}"
            counter += 1
        
        # Duplicate
        if self.template_manager.duplicate_template(src_name, new_name):
            self._load_templates()
    
    def _on_delete_clicked(self):
        """Handle delete button click."""
        current_item = self.template_list.currentItem()
        if not current_item:
            return
        
        template_info = current_item.data(Qt.UserRole)
        name = template_info.get("name")
        
        # Confirm deletion
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self,
            "Conferma Eliminazione",
            f"Sei sicuro di voler eliminare il template '{name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            if self.template_manager.delete_template(name):
                self._load_templates()
