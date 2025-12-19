"""
Main label editor page with WYSIWYG interface.
"""
from __future__ import annotations
from typing import Optional
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                               QLabel, QToolBar, QMessageBox, QInputDialog,
                               QSplitter, QFrame, QScrollArea)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut

from ..widgets.header import Header
from ..widgets.label_canvas import LabelCanvas
from ..widgets.label_element_sidebar import LabelElementSidebar
from ..widgets.label_properties_panel import LabelPropertiesPanel
from ..widgets.template_gallery_dialog import TemplateGalleryDialog, TemplateManagerDialog
from ..widgets.label_help_widget import LabelHelpWidget
from ..services.label_template_manager import LabelTemplateManager
from ..utils.label_history import EditorHistory
from ..utils.label_validator import LabelValidator


class LabelEditorPage(QWidget):
    """Main label editor page with WYSIWYG interface."""
    
    def __init__(self, appwin, parent=None):
        super().__init__(parent)
        self.appwin = appwin
        
        # Initialize services
        self.template_manager = LabelTemplateManager()
        self.history = EditorHistory(max_history=50)
        
        # State
        self.current_template_name: Optional[str] = None
        self.unsaved_changes = False
        
        self._build()
        self._setup_shortcuts()
        
        # Load default template
        self._load_template("Standard")
    
    def _build(self):
        """Build the editor UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header = Header(
            self.appwin,
            title="Editor Etichette",
            mode="default",
            on_home=self._go_home,
            show_home=True
        )
        layout.addWidget(header)
        
        # Toolbar
        toolbar = self._create_toolbar()
        layout.addWidget(toolbar)
        
        # Status bar with tooltips
        self.status_bar = QLabel("💡 Trascina elementi dalla sidebar per iniziare")
        self.status_bar.setStyleSheet("""
            QLabel {
                background-color: #fff3cd;
                color: #856404;
                padding: 8px;
                border-top: 1px solid #ffeeba;
            }
        """)
        layout.addWidget(self.status_bar)
        
        # Main content: 3-column layout
        splitter = QSplitter(Qt.Horizontal)
        
        # Left: Element sidebar
        self.sidebar = LabelElementSidebar()
        self.sidebar.element_requested.connect(self._on_element_requested)
        splitter.addWidget(self.sidebar)
        
        # Center: Canvas in scroll area
        canvas_container = QWidget()
        canvas_layout = QVBoxLayout(canvas_container)
        canvas_layout.setContentsMargins(10, 10, 10, 10)
        
        self.canvas = LabelCanvas(width_mm=62, height_mm=100)
        self.canvas.element_selected.connect(self._on_element_selected)
        self.canvas.element_modified.connect(self._on_element_modified)
        
        canvas_scroll = QScrollArea()
        canvas_scroll.setWidget(self.canvas)
        canvas_scroll.setWidgetResizable(True)
        canvas_scroll.setMinimumSize(400, 500)
        canvas_scroll.setStyleSheet("QScrollArea { background-color: #e0e0e0; }")
        
        canvas_layout.addWidget(canvas_scroll)
        
        # Canvas controls
        controls_layout = QHBoxLayout()
        
        zoom_in_btn = QPushButton("🔍+")
        zoom_in_btn.setToolTip("Zoom In")
        zoom_in_btn.clicked.connect(self.canvas.zoom_in)
        controls_layout.addWidget(zoom_in_btn)
        
        zoom_out_btn = QPushButton("🔍-")
        zoom_out_btn.setToolTip("Zoom Out")
        zoom_out_btn.clicked.connect(self.canvas.zoom_out)
        controls_layout.addWidget(zoom_out_btn)
        
        grid_btn = QPushButton("📐 Griglia")
        grid_btn.setCheckable(True)
        grid_btn.setChecked(True)
        grid_btn.clicked.connect(self.canvas.toggle_grid)
        controls_layout.addWidget(grid_btn)
        
        guides_btn = QPushButton("📏 Guide")
        guides_btn.setCheckable(True)
        guides_btn.setChecked(True)
        guides_btn.clicked.connect(self.canvas.toggle_guides)
        controls_layout.addWidget(guides_btn)
        
        controls_layout.addStretch()
        canvas_layout.addLayout(controls_layout)
        
        splitter.addWidget(canvas_container)
        
        # Right: Properties panel and help
        right_panel = QSplitter(Qt.Vertical)
        
        self.properties_panel = LabelPropertiesPanel()
        self.properties_panel.property_changed.connect(self._on_property_changed)
        self.properties_panel.delete_btn.clicked.connect(self._on_delete_element)
        right_panel.addWidget(self.properties_panel)
        
        self.help_widget = LabelHelpWidget()
        right_panel.addWidget(self.help_widget)
        
        splitter.addWidget(right_panel)
        
        # Set splitter proportions
        splitter.setSizes([200, 600, 300])
        
        layout.addWidget(splitter)
        
        # Bottom status
        bottom_bar = QLabel("")
        bottom_bar.setStyleSheet("background-color: #f5f5f5; padding: 5px;")
        layout.addWidget(bottom_bar)
    
    def _create_toolbar(self) -> QToolBar:
        """Create toolbar with editor actions."""
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setStyleSheet("""
            QToolBar {
                background-color: #ffffff;
                border-bottom: 1px solid #ddd;
                padding: 5px;
                spacing: 5px;
            }
            QToolButton {
                padding: 8px;
                margin: 2px;
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: white;
            }
            QToolButton:hover {
                background-color: #e8f4f8;
                border-color: #0066cc;
            }
        """)
        
        # Template actions
        new_btn = QPushButton("📄 Nuovo")
        new_btn.setToolTip("Nuovo template vuoto")
        new_btn.clicked.connect(self._new_template)
        toolbar.addWidget(new_btn)
        
        open_btn = QPushButton("📂 Apri")
        open_btn.setToolTip("Apri template esistente")
        open_btn.clicked.connect(self._open_template)
        toolbar.addWidget(open_btn)
        
        save_btn = QPushButton("💾 Salva")
        save_btn.setToolTip("Salva template")
        save_btn.clicked.connect(self._save_template)
        toolbar.addWidget(save_btn)
        
        save_as_btn = QPushButton("💾 Salva Come...")
        save_as_btn.setToolTip("Salva template con nuovo nome")
        save_as_btn.clicked.connect(self._save_template_as)
        toolbar.addWidget(save_as_btn)
        
        toolbar.addSeparator()
        
        # Edit actions
        self.undo_btn = QPushButton("↶ Annulla")
        self.undo_btn.setToolTip("Annulla (Ctrl+Z)")
        self.undo_btn.setEnabled(False)
        self.undo_btn.clicked.connect(self._undo)
        toolbar.addWidget(self.undo_btn)
        
        self.redo_btn = QPushButton("↷ Ripristina")
        self.redo_btn.setToolTip("Ripristina (Ctrl+Y)")
        self.redo_btn.setEnabled(False)
        self.redo_btn.clicked.connect(self._redo)
        toolbar.addWidget(self.redo_btn)
        
        toolbar.addSeparator()
        
        # Validate
        validate_btn = QPushButton("✓ Valida")
        validate_btn.setToolTip("Valida elementi")
        validate_btn.clicked.connect(self._validate_elements)
        toolbar.addWidget(validate_btn)
        
        # Test print
        test_print_btn = QPushButton("🖨️ Stampa Test")
        test_print_btn.setToolTip("Stampa etichetta di test")
        test_print_btn.clicked.connect(self._test_print)
        toolbar.addWidget(test_print_btn)
        
        toolbar.addSeparator()
        
        # Manage templates
        manage_btn = QPushButton("⚙️ Gestione Template")
        manage_btn.setToolTip("Gestisci template salvati")
        manage_btn.clicked.connect(self._manage_templates)
        toolbar.addWidget(manage_btn)
        
        return toolbar
    
    def _setup_shortcuts(self):
        """Setup keyboard shortcuts."""
        # Undo
        undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        undo_shortcut.activated.connect(self._undo)
        
        # Redo
        redo_shortcut = QShortcut(QKeySequence("Ctrl+Y"), self)
        redo_shortcut.activated.connect(self._redo)
        
        # Save
        save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        save_shortcut.activated.connect(self._save_template)
        
        # Duplicate
        duplicate_shortcut = QShortcut(QKeySequence("Ctrl+D"), self)
        duplicate_shortcut.activated.connect(self._duplicate_selected)
        
        # Delete
        delete_shortcut = QShortcut(QKeySequence("Delete"), self)
        delete_shortcut.activated.connect(self._on_delete_element)
    
    def _on_element_requested(self, element):
        """Handle element addition request."""
        self.canvas.add_element(element)
        self._save_history_state()
        self._update_tooltip()
    
    def _on_element_selected(self, element):
        """Handle element selection."""
        self.properties_panel.set_element(element)
        self._update_tooltip()
    
    def _on_element_modified(self):
        """Handle element modification."""
        self.unsaved_changes = True
        self._save_history_state()
        self.canvas.update()
        self._update_tooltip()
    
    def _on_property_changed(self):
        """Handle property change."""
        self.unsaved_changes = True
        self._save_history_state()
        self.canvas.update()
    
    def _on_delete_element(self):
        """Handle element deletion."""
        if self.canvas.selected_element:
            self.canvas.remove_element(self.canvas.selected_element)
            self._save_history_state()
    
    def _save_history_state(self):
        """Save current state to history."""
        self.history.save_state(self.canvas.elements)
        self.undo_btn.setEnabled(self.history.can_undo())
        self.redo_btn.setEnabled(self.history.can_redo())
    
    def _undo(self):
        """Undo last action."""
        state = self.history.undo()
        if state is not None:
            self.canvas.load_elements(state)
            self.undo_btn.setEnabled(self.history.can_undo())
            self.redo_btn.setEnabled(self.history.can_redo())
    
    def _redo(self):
        """Redo last undone action."""
        state = self.history.redo()
        if state is not None:
            self.canvas.load_elements(state)
            self.undo_btn.setEnabled(self.history.can_undo())
            self.redo_btn.setEnabled(self.history.can_redo())
    
    def _duplicate_selected(self):
        """Duplicate selected element."""
        if self.canvas.selected_element:
            elem = self.canvas.selected_element
            # Create copy
            data = elem.serialize()
            data["x"] += 10  # Offset
            data["y"] += 10
            
            from ..widgets.label_element import deserialize_element
            new_elem = deserialize_element(data)
            if new_elem:
                self.canvas.add_element(new_elem)
                self._save_history_state()
    
    def _new_template(self):
        """Create new empty template."""
        if self.unsaved_changes:
            reply = QMessageBox.question(
                self, "Modifiche non salvate",
                "Ci sono modifiche non salvate. Continuare?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
        
        self.canvas.clear_elements()
        self.current_template_name = None
        self.unsaved_changes = False
        self.history.clear()
        self._save_history_state()
    
    def _open_template(self):
        """Open template from gallery."""
        dialog = TemplateGalleryDialog(self.template_manager, self)
        if dialog.exec():
            template = dialog.get_selected_template()
            if template:
                self._load_template_data(template)
    
    def _load_template(self, name: str):
        """Load template by name."""
        template = self.template_manager.load_template(name)
        if template:
            self._load_template_data(template)
    
    def _load_template_data(self, template: dict):
        """Load template data into canvas."""
        self.canvas.clear_elements()
        
        # Update canvas size if specified
        width = template.get("label_width", 62)
        height = template.get("label_height", 100)
        self.canvas.label_width_mm = width
        self.canvas.label_height_mm = height
        self.canvas.setMinimumSize(int(width * self.canvas.scale), 
                                   int(height * self.canvas.scale))
        
        # Load elements
        elements = template.get("elements", [])
        self.canvas.load_elements(elements)
        
        self.current_template_name = template.get("name")
        self.unsaved_changes = False
        self.history.clear()
        self._save_history_state()
    
    def _save_template(self):
        """Save current template."""
        if not self.current_template_name:
            self._save_template_as()
            return
        
        template_data = {
            "name": self.current_template_name,
            "description": f"Template {self.current_template_name}",
            "label_width": self.canvas.label_width_mm,
            "label_height": self.canvas.label_height_mm,
            "elements": self.canvas.get_serialized_elements()
        }
        
        if self.template_manager.save_template(self.current_template_name, template_data):
            self.unsaved_changes = False
            QMessageBox.information(self, "Salvataggio", "Template salvato con successo!")
    
    def _save_template_as(self):
        """Save template with new name."""
        name, ok = QInputDialog.getText(
            self, "Salva Template",
            "Nome del template:",
            text=self.current_template_name or "Nuovo_Template"
        )
        
        if ok and name:
            template_data = {
                "name": name,
                "description": f"Template {name}",
                "label_width": self.canvas.label_width_mm,
                "label_height": self.canvas.label_height_mm,
                "elements": self.canvas.get_serialized_elements()
            }
            
            if self.template_manager.save_template(name, template_data):
                self.current_template_name = name
                self.unsaved_changes = False
                QMessageBox.information(self, "Salvataggio", "Template salvato con successo!")
    
    def _manage_templates(self):
        """Open template management dialog."""
        dialog = TemplateManagerDialog(self.template_manager, self)
        dialog.exec()
    
    def _validate_elements(self):
        """Validate all elements."""
        validator = LabelValidator(self.canvas.label_width_mm, self.canvas.label_height_mm)
        errors, warnings, infos = validator.get_summary(self.canvas.elements)
        
        msg = f"Validazione completata:\n\n"
        msg += f"✓ Elementi validi: {infos}\n"
        if warnings > 0:
            msg += f"⚠️ Avvisi: {warnings}\n"
        if errors > 0:
            msg += f"❌ Errori: {errors}\n"
        
        if errors > 0 or warnings > 0:
            msg += f"\nControlla il pannello proprietà per i dettagli."
        
        QMessageBox.information(self, "Validazione", msg)
    
    def _test_print(self):
        """Test print with sample data."""
        QMessageBox.information(
            self, "Stampa Test",
            "Funzione di stampa non ancora implementata.\n"
            "Questa funzione stamperà un'etichetta di test con dati di esempio."
        )
    
    def _update_tooltip(self):
        """Update contextual tooltip."""
        if len(self.canvas.elements) == 0:
            self.status_bar.setText("💡 Trascina elementi dalla sidebar per iniziare")
            self.status_bar.setStyleSheet("""
                QLabel {
                    background-color: #d1ecf1;
                    color: #0c5460;
                    padding: 8px;
                    border-top: 1px solid #bee5eb;
                }
            """)
        elif self.canvas.selected_element:
            self.status_bar.setText("💡 Modifica le proprietà nel pannello destro")
            self.status_bar.setStyleSheet("""
                QLabel {
                    background-color: #fff3cd;
                    color: #856404;
                    padding: 8px;
                    border-top: 1px solid #ffeeba;
                }
            """)
        else:
            self.status_bar.setText("✓ Pronto - Clicca su un elemento per modificarlo")
            self.status_bar.setStyleSheet("""
                QLabel {
                    background-color: #d4edda;
                    color: #155724;
                    padding: 8px;
                    border-top: 1px solid #c3e6cb;
                }
            """)
    
    def _go_home(self):
        """Go back to home page."""
        if self.unsaved_changes:
            reply = QMessageBox.question(
                self, "Modifiche non salvate",
                "Ci sono modifiche non salvate. Vuoi tornare alla home?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
        
        self.appwin.go_home()
