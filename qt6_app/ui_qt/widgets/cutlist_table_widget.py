"""
Cutlist Table Widget - Editable table for cutlist management
File: qt6_app/ui_qt/widgets/cutlist_table_widget.py
"""

from typing import List, Dict, Any, Tuple
from PySide6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QHeaderView, 
    QAbstractItemView, QMenu
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush


class CutlistTableWidget(QTableWidget):
    """
    Editable table for cutlist management.
    
    Signals:
        data_changed: Emitted when table data changes
        validation_error(str): Emitted on validation errors
    """
    
    data_changed = Signal()
    validation_error = Signal(str)
    
    def __init__(self, parent=None, stock_length: float = 6500.0):
        super().__init__(parent)
        self.stock_length = stock_length
        self._setup_columns()
        self._setup_behavior()
    
    def _setup_columns(self):
        """Setup table columns."""
        self.setColumnCount(4)
        self.setHorizontalHeaderLabels(['#', 'Lunghezza (mm)', 'Quantità', 'Etichetta'])
        
        # Column widths
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        
        self.setColumnWidth(0, 50)
        
        # Row header
        self.verticalHeader().setVisible(False)
    
    def _setup_behavior(self):
        """Setup table behavior."""
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setAlternatingRowColors(True)
        
        # Connect signals
        self.itemChanged.connect(self._on_item_changed)
    
    def set_stock_length(self, stock_length: float):
        """Update stock length for validation."""
        self.stock_length = stock_length
        self._validate_all_rows()
    
    def add_piece(self, length: float = 0, quantity: int = 1, label: str = ""):
        """Add a piece to the list."""
        row = self.rowCount()
        self.insertRow(row)
        
        # Row number (non-editable)
        item_num = QTableWidgetItem(str(row + 1))
        item_num.setFlags(item_num.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item_num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row, 0, item_num)
        
        # Length
        item_len = QTableWidgetItem(str(length))
        item_len.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setItem(row, 1, item_len)
        
        # Quantity
        item_qty = QTableWidgetItem(str(quantity))
        item_qty.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row, 2, item_qty)
        
        # Label
        item_label = QTableWidgetItem(label)
        self.setItem(row, 3, item_label)
        
        self._validate_row(row)
        self.data_changed.emit()
    
    def remove_selected_rows(self):
        """Remove selected rows."""
        selected_rows = sorted(set(item.row() for item in self.selectedItems()), reverse=True)
        
        for row in selected_rows:
            self.removeRow(row)
        
        # Update row numbers
        self._update_row_numbers()
        self.data_changed.emit()
    
    def duplicate_selected_row(self):
        """Duplicate the selected row."""
        selected = self.selectedItems()
        if not selected:
            return
        
        row = selected[0].row()
        
        try:
            length = float(self.item(row, 1).text())
            quantity = int(self.item(row, 2).text())
            label = self.item(row, 3).text()
            self.add_piece(length, quantity, label)
        except Exception:
            pass
    
    def _update_row_numbers(self):
        """Update row numbers after deletion."""
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item:
                item.setText(str(row + 1))
    
    def get_cutlist(self) -> List[Dict[str, Any]]:
        """Export current table data."""
        pieces = []
        
        for row in range(self.rowCount()):
            try:
                length = float(self.item(row, 1).text())
                quantity = int(self.item(row, 2).text())
                label = self.item(row, 3).text()
                
                if length > 0 and quantity > 0:
                    pieces.append({
                        'length': length,
                        'quantity': quantity,
                        'label': label
                    })
            except Exception:
                continue
        
        return pieces
    
    def load_cutlist(self, pieces: List[Dict[str, Any]]):
        """Load cutlist data into table."""
        self.setRowCount(0)
        
        for piece in pieces:
            self.add_piece(
                length=piece.get('length', 0),
                quantity=piece.get('quantity', 1),
                label=piece.get('label', '')
            )
    
    def clear_all(self):
        """Clear all rows."""
        self.setRowCount(0)
        self.data_changed.emit()
    
    def validate(self) -> Tuple[bool, List[str]]:
        """
        Validate all rows.
        
        Returns:
            (is_valid, errors) tuple
        """
        errors = []
        
        for row in range(self.rowCount()):
            try:
                length = float(self.item(row, 1).text())
                quantity = int(self.item(row, 2).text())
                
                if length <= 0:
                    errors.append(f"Riga {row + 1}: Lunghezza deve essere > 0")
                elif length > self.stock_length:
                    errors.append(f"Riga {row + 1}: Lunghezza supera stock disponibile ({self.stock_length} mm)")
                
                if quantity < 1:
                    errors.append(f"Riga {row + 1}: Quantità deve essere >= 1")
                    
            except ValueError:
                errors.append(f"Riga {row + 1}: Valore non valido")
        
        return len(errors) == 0, errors
    
    def _validate_row(self, row: int):
        """Validate a single row and apply visual feedback."""
        try:
            length_item = self.item(row, 1)
            qty_item = self.item(row, 2)
            
            if not length_item or not qty_item:
                return
            
            try:
                length = float(length_item.text())
                quantity = int(qty_item.text())
            except ValueError:
                self._set_cell_error(length_item, "Valore non valido")
                return
            
            # Validate length
            if length <= 0:
                self._set_cell_error(length_item, "Lunghezza deve essere > 0")
            elif length > self.stock_length:
                self._set_cell_warning(length_item, f"Lunghezza supera stock ({self.stock_length} mm)")
            else:
                self._clear_cell_style(length_item)
            
            # Validate quantity
            if quantity < 1:
                self._set_cell_error(qty_item, "Quantità deve essere >= 1")
            else:
                self._clear_cell_style(qty_item)
                
        except Exception:
            pass
    
    def _validate_all_rows(self):
        """Validate all rows."""
        for row in range(self.rowCount()):
            self._validate_row(row)
    
    def _set_cell_error(self, item: QTableWidgetItem, tooltip: str):
        """Set error styling on cell."""
        item.setBackground(QBrush(QColor(255, 200, 200)))
        item.setToolTip(f"⚠️ {tooltip}")
    
    def _set_cell_warning(self, item: QTableWidgetItem, tooltip: str):
        """Set warning styling on cell."""
        item.setBackground(QBrush(QColor(255, 230, 200)))
        item.setToolTip(f"⚠️ {tooltip}")
    
    def _clear_cell_style(self, item: QTableWidgetItem):
        """Clear cell styling."""
        item.setBackground(QBrush(QColor(255, 255, 255)))
        item.setToolTip("")
    
    def _on_item_changed(self, item: QTableWidgetItem):
        """Handle item changes."""
        if item.column() == 0:
            return  # Row number column
        
        self._validate_row(item.row())
        self.data_changed.emit()
    
    def get_totals(self) -> Dict[str, Any]:
        """Get totals (pieces count, linear meters)."""
        total_pieces = 0
        total_length = 0.0
        
        for row in range(self.rowCount()):
            try:
                length = float(self.item(row, 1).text())
                quantity = int(self.item(row, 2).text())
                
                total_pieces += quantity
                total_length += length * quantity
                
            except Exception:
                continue
        
        return {
            'total_pieces': total_pieces,
            'total_length_mm': total_length,
            'total_length_m': total_length / 1000.0
        }
    
    def keyPressEvent(self, event):
        """Handle keyboard shortcuts."""
        if event.key() == Qt.Key.Key_Delete:
            self.remove_selected_rows()
        elif event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_D:
            self.duplicate_selected_row()
        else:
            super().keyPressEvent(event)
