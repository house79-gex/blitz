"""
Optimization Results Widget - Display optimization results
File: qt6_app/ui_qt/widgets/optimization_results_widget.py
"""

from typing import Dict, Any
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QScrollArea, QFrame, QPushButton
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont


class OptimizationResultsWidget(QWidget):
    """Widget to display optimization results."""
    
    export_pdf_clicked = Signal()
    export_excel_clicked = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.results = None
        self._build_ui()
    
    def _build_ui(self):
        """Build the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Title
        title = QLabel("RISULTATI OTTIMIZZAZIONE")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Scroll area for results
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.StyledPanel)
        
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        scroll.setWidget(self.content_widget)
        layout.addWidget(scroll, 1)
        
        # Export buttons
        export_layout = QHBoxLayout()
        
        btn_pdf = QPushButton("📄 Esporta PDF")
        btn_pdf.clicked.connect(self.export_pdf_clicked.emit)
        export_layout.addWidget(btn_pdf)
        
        btn_excel = QPushButton("📊 Esporta Excel")
        btn_excel.clicked.connect(self.export_excel_clicked.emit)
        export_layout.addWidget(btn_excel)
        
        layout.addLayout(export_layout)
        
        # Initially hide (show when results available)
        self.hide()
    
    def display_results(self, results: Dict[str, Any]):
        """
        Display optimization results.
        
        Args:
            results: Dictionary with optimization results
        """
        self.results = results
        
        # Clear previous content
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Success message
        success_label = QLabel("✓ Ottimizzazione completata con successo")
        success_font = QFont()
        success_font.setBold(True)
        success_label.setFont(success_font)
        success_label.setStyleSheet("color: green; padding: 10px;")
        self.content_layout.addWidget(success_label)
        
        # Statistics
        stats_frame = QFrame()
        stats_frame.setFrameShape(QFrame.Shape.StyledPanel)
        stats_layout = QVBoxLayout(stats_frame)
        
        stats_title = QLabel("Statistiche:")
        stats_title_font = QFont()
        stats_title_font.setBold(True)
        stats_title.setFont(stats_title_font)
        stats_layout.addWidget(stats_title)
        
        bars_used = results.get('bars_used', 0)
        total_waste = results.get('total_waste', 0)
        efficiency = results.get('efficiency', 0)
        
        stats_layout.addWidget(QLabel(f"• Barre utilizzate:  {bars_used}"))
        stats_layout.addWidget(QLabel(f"• Sfrido totale:     {total_waste:.1f} mm"))
        stats_layout.addWidget(QLabel(f"• Efficienza:        {efficiency:.1f}%"))
        
        self.content_layout.addWidget(stats_frame)
        
        # Cutting plan
        plan_title = QLabel("Piano di Taglio:")
        plan_title_font = QFont()
        plan_title_font.setBold(True)
        plan_title.setFont(plan_title_font)
        self.content_layout.addWidget(plan_title)
        
        bars = results.get('bars', [])
        stock_length = results.get('stock_length', 6500)
        
        for bar_idx, bar in enumerate(bars, 1):
            bar_frame = self._create_bar_frame(bar_idx, bar, stock_length)
            self.content_layout.addWidget(bar_frame)
        
        # Show the widget
        self.show()
    
    def _create_bar_frame(self, bar_idx: int, bar: Dict[str, Any], stock_length: float) -> QFrame:
        """Create a frame for a single bar."""
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setStyleSheet("QFrame { background-color: #f5f5f5; border: 1px solid #ccc; border-radius: 4px; }")
        
        layout = QVBoxLayout(frame)
        
        # Bar title
        title = QLabel(f"Barra {bar_idx} ({stock_length} mm):")
        title_font = QFont()
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        
        # Pieces
        pieces = bar.get('pieces', [])
        for piece in pieces:
            length = piece.get('length', 0)
            label = piece.get('label', '')
            
            text = f"├─ {length:.1f} mm"
            if label:
                text += f"  [{label}]"
            
            piece_label = QLabel(text)
            piece_label.setStyleSheet("padding-left: 10px;")
            layout.addWidget(piece_label)
        
        # Waste
        waste = bar.get('waste', 0)
        waste_label = QLabel(f"└─ Sfrido: {waste:.1f} mm")
        waste_label.setStyleSheet("padding-left: 10px; font-style: italic; color: #666;")
        layout.addWidget(waste_label)
        
        return frame
    
    def clear_results(self):
        """Clear displayed results."""
        self.results = None
        
        # Clear content
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self.hide()
