"""
Setup wizard for first-time label editor configuration.
"""
from __future__ import annotations
from typing import Optional
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                               QPushButton, QStackedWidget, QWidget, QRadioButton,
                               QButtonGroup, QTextEdit, QComboBox)
from PySide6.QtCore import Qt, Signal


class LabelEditorWizard(QDialog):
    """Wizard for initial label editor setup."""
    
    template_selected = Signal(str)  # Emitted when setup is complete
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_template = "Standard"
        
        self.setWindowTitle("Configurazione Editor Etichette")
        self.setMinimumSize(600, 500)
        self.setModal(True)
        
        self._build()
    
    def _build(self):
        """Build the wizard UI."""
        layout = QVBoxLayout(self)
        
        # Title area
        title_container = QWidget()
        title_container.setStyleSheet("background-color: #0066cc; color: white;")
        title_layout = QVBoxLayout(title_container)
        
        title = QLabel("🎓 Benvenuto nell'Editor Etichette")
        title.setStyleSheet("font-size: 20px; font-weight: bold; padding: 10px;")
        title_layout.addWidget(title)
        
        subtitle = QLabel("Configuriamo insieme il tuo editor")
        subtitle.setStyleSheet("font-size: 14px; padding: 0 10px 10px 10px;")
        title_layout.addWidget(subtitle)
        
        layout.addWidget(title_container)
        
        # Steps container
        self.steps = QStackedWidget()
        
        # Step 1: Welcome
        step1 = self._create_step1()
        self.steps.addWidget(step1)
        
        # Step 2: Label size
        step2 = self._create_step2()
        self.steps.addWidget(step2)
        
        # Step 3: Template selection
        step3 = self._create_step3()
        self.steps.addWidget(step3)
        
        # Step 4: Completion
        step4 = self._create_step4()
        self.steps.addWidget(step4)
        
        layout.addWidget(self.steps)
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        
        self.back_btn = QPushButton("⬅️ Indietro")
        self.back_btn.clicked.connect(self._go_back)
        self.back_btn.setEnabled(False)
        nav_layout.addWidget(self.back_btn)
        
        nav_layout.addStretch()
        
        self.skip_btn = QPushButton("Salta Wizard")
        self.skip_btn.clicked.connect(self._skip_wizard)
        nav_layout.addWidget(self.skip_btn)
        
        self.next_btn = QPushButton("Avanti ➡️")
        self.next_btn.clicked.connect(self._go_next)
        nav_layout.addWidget(self.next_btn)
        
        layout.addLayout(nav_layout)
    
    def _create_step1(self) -> QWidget:
        """Create welcome step."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignCenter)
        
        icon = QLabel("🎨")
        icon.setStyleSheet("font-size: 72px;")
        icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon)
        
        title = QLabel("Editor WYSIWYG")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-top: 20px;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        desc = QTextEdit()
        desc.setReadOnly(True)
        desc.setMaximumHeight(200)
        desc.setHtml("""
            <html>
            <body style="font-family: Arial; font-size: 14px; text-align: center;">
                <h3>Caratteristiche dell'editor:</h3>
                <ul style="text-align: left; margin-left: 50px;">
                    <li>🖱️ Drag & Drop per posizionare elementi</li>
                    <li>📐 Griglia e guide di allineamento</li>
                    <li>↶↷ Undo/Redo per annullare modifiche</li>
                    <li>📚 Template predefiniti</li>
                    <li>🎨 Anteprima in tempo reale</li>
                    <li>💾 Salva i tuoi template personalizzati</li>
                </ul>
                <p><b>Iniziamo la configurazione!</b></p>
            </body>
            </html>
        """)
        layout.addWidget(desc)
        
        layout.addStretch()
        
        return widget
    
    def _create_step2(self) -> QWidget:
        """Create label size selection step."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        title = QLabel("📏 Dimensioni Etichetta")
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)
        
        desc = QLabel("Seleziona le dimensioni dell'etichetta:")
        layout.addWidget(desc)
        
        # Size options
        self.size_group = QButtonGroup()
        
        sizes = [
            ("62 x 100 mm (Standard Brother DK)", "62x100", True),
            ("29 x 90 mm (Piccola)", "29x90", False),
            ("62 x 29 mm (Larga)", "62x29", False),
        ]
        
        for label, value, default in sizes:
            radio = QRadioButton(label)
            radio.setProperty("value", value)
            if default:
                radio.setChecked(True)
            self.size_group.addButton(radio)
            layout.addWidget(radio)
        
        layout.addStretch()
        
        info = QLabel("💡 Puoi modificare le dimensioni in seguito")
        info.setStyleSheet("color: #666; font-size: 12px; font-style: italic;")
        layout.addWidget(info)
        
        return widget
    
    def _create_step3(self) -> QWidget:
        """Create template selection step."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        title = QLabel("📚 Template Iniziale")
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)
        
        desc = QLabel("Scegli un template di partenza:")
        layout.addWidget(desc)
        
        # Template options
        self.template_group = QButtonGroup()
        
        templates = [
            ("⭐ Standard", "Standard", "Profilo + Lunghezza + Barcode", True),
            ("📋 Minimal", "Minimal", "Solo lunghezza in grande", False),
            ("📊 Barcode Focus", "Barcode_Focus", "Enfasi sul barcode", False),
            ("⬜ Vuoto", "Empty", "Inizia da zero", False),
        ]
        
        for icon_label, value, desc_text, default in templates:
            container = QWidget()
            container_layout = QVBoxLayout(container)
            container_layout.setContentsMargins(10, 10, 10, 10)
            
            radio = QRadioButton(icon_label)
            radio.setProperty("value", value)
            radio.setStyleSheet("font-weight: bold; font-size: 14px;")
            if default:
                radio.setChecked(True)
                self.selected_template = value
            
            radio.toggled.connect(lambda checked, v=value: self._on_template_changed(v, checked))
            self.template_group.addButton(radio)
            container_layout.addWidget(radio)
            
            desc_label = QLabel(desc_text)
            desc_label.setStyleSheet("color: #666; margin-left: 25px;")
            container_layout.addWidget(desc_label)
            
            container.setStyleSheet("""
                QWidget {
                    background-color: #f5f5f5;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                }
            """)
            
            layout.addWidget(container)
        
        layout.addStretch()
        
        return widget
    
    def _create_step4(self) -> QWidget:
        """Create completion step."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignCenter)
        
        icon = QLabel("✓")
        icon.setStyleSheet("font-size: 72px; color: green;")
        icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon)
        
        title = QLabel("Configurazione Completata!")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-top: 20px;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        desc = QLabel("L'editor è pronto all'uso.")
        desc.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc)
        
        tips = QTextEdit()
        tips.setReadOnly(True)
        tips.setMaximumHeight(200)
        tips.setHtml("""
            <html>
            <body style="font-family: Arial; font-size: 13px;">
                <h4>💡 Primi passi:</h4>
                <ol>
                    <li>Aggiungi elementi dalla barra laterale sinistra</li>
                    <li>Trascina e ridimensiona gli elementi sul canvas</li>
                    <li>Modifica le proprietà nel pannello destro</li>
                    <li>Salva il tuo template per riutilizzarlo</li>
                </ol>
                <p><b>Buon lavoro! 🎉</b></p>
            </body>
            </html>
        """)
        layout.addWidget(tips)
        
        layout.addStretch()
        
        return widget
    
    def _on_template_changed(self, value: str, checked: bool):
        """Handle template selection change."""
        if checked:
            self.selected_template = value
    
    def _go_back(self):
        """Go to previous step."""
        current = self.steps.currentIndex()
        if current > 0:
            self.steps.setCurrentIndex(current - 1)
            self._update_nav_buttons()
    
    def _go_next(self):
        """Go to next step."""
        current = self.steps.currentIndex()
        
        if current < self.steps.count() - 1:
            self.steps.setCurrentIndex(current + 1)
            self._update_nav_buttons()
        else:
            # Last step - finish
            self.template_selected.emit(self.selected_template)
            self.accept()
    
    def _update_nav_buttons(self):
        """Update navigation button states."""
        current = self.steps.currentIndex()
        
        self.back_btn.setEnabled(current > 0)
        
        if current == self.steps.count() - 1:
            self.next_btn.setText("✓ Inizia")
            self.skip_btn.setVisible(False)
        else:
            self.next_btn.setText("Avanti ➡️")
            self.skip_btn.setVisible(True)
    
    def _skip_wizard(self):
        """Skip wizard and use default."""
        self.selected_template = "Standard"
        self.template_selected.emit(self.selected_template)
        self.accept()
    
    def get_selected_template(self) -> str:
        """Get selected template name."""
        return self.selected_template
