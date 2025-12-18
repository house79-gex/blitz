"""
Label canvas widget with drag & drop WYSIWYG editing.
"""
from __future__ import annotations
from typing import List, Optional, Tuple
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF, Signal, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QBrush, QMouseEvent, QPaintEvent

from .label_element import LabelElement, deserialize_element


class LabelCanvas(QWidget):
    """WYSIWYG canvas for label editing."""
    
    element_selected = Signal(object)  # Emitted when element is selected
    element_modified = Signal()  # Emitted when element is modified
    
    def __init__(self, width_mm: float = 62, height_mm: float = 100, parent=None):
        super().__init__(parent)
        
        self.label_width_mm = width_mm
        self.label_height_mm = height_mm
        
        # Canvas settings
        self.grid_size = 5  # 5mm grid
        self.snap_threshold = 2  # 2mm snap threshold
        self.show_grid = True
        self.show_guides = True
        self.scale = 3.0  # pixels per mm (zoom level)
        
        # Elements
        self.elements: List[LabelElement] = []
        self.selected_element: Optional[LabelElement] = None
        
        # Drag state
        self._dragging = False
        self._drag_start: Optional[QPointF] = None
        self._element_start_pos: Optional[Tuple[float, float]] = None
        
        # Resize state
        self._resizing = False
        self._resize_handle: Optional[str] = None  # "se", "sw", "ne", "nw"
        
        # Alignment guides
        self._alignment_guides: List[Tuple[str, float]] = []  # List of ("vertical"|"horizontal", position)
        
        self.setMinimumSize(int(width_mm * self.scale), int(height_mm * self.scale))
        self.setMouseTracking(True)
    
    def add_element(self, element: LabelElement):
        """Add element to canvas."""
        self.elements.append(element)
        element.z_index = len(self.elements)
        self.element_modified.emit()
        self.update()
    
    def remove_element(self, element: LabelElement):
        """Remove element from canvas."""
        if element in self.elements:
            self.elements.remove(element)
            if self.selected_element == element:
                self.selected_element = None
                self.element_selected.emit(None)
            self.element_modified.emit()
            self.update()
    
    def clear_elements(self):
        """Remove all elements."""
        self.elements.clear()
        self.selected_element = None
        self.element_selected.emit(None)
        self.element_modified.emit()
        self.update()
    
    def load_elements(self, elements_data: List[dict]):
        """Load elements from serialized data."""
        self.elements.clear()
        for data in elements_data:
            element = deserialize_element(data)
            if element:
                self.elements.append(element)
        self.element_modified.emit()
        self.update()
    
    def get_serialized_elements(self) -> List[dict]:
        """Get serialized elements."""
        return [elem.serialize() for elem in self.elements]
    
    def paintEvent(self, event: QPaintEvent):
        """Paint the canvas."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw background
        painter.fillRect(self.rect(), QColor("#ffffff"))
        
        # Draw grid if enabled
        if self.show_grid:
            self._draw_grid(painter)
        
        # Draw label boundary
        painter.setPen(QPen(QColor("#cccccc"), 2))
        painter.drawRect(0, 0, int(self.label_width_mm * self.scale), 
                        int(self.label_height_mm * self.scale))
        
        # Draw alignment guides
        if self.show_guides and self._alignment_guides:
            self._draw_alignment_guides(painter)
        
        # Draw elements (sorted by z-index)
        sorted_elements = sorted(self.elements, key=lambda e: e.z_index)
        for element in sorted_elements:
            element.paint(painter, self.scale)
        
        # Draw selection handles
        if self.selected_element:
            self._draw_selection_handles(painter)
    
    def _draw_grid(self, painter: QPainter):
        """Draw grid lines."""
        painter.setPen(QPen(QColor("#eeeeee"), 1))
        
        # Vertical lines
        x = self.grid_size * self.scale
        while x < self.label_width_mm * self.scale:
            painter.drawLine(int(x), 0, int(x), int(self.label_height_mm * self.scale))
            x += self.grid_size * self.scale
        
        # Horizontal lines
        y = self.grid_size * self.scale
        while y < self.label_height_mm * self.scale:
            painter.drawLine(0, int(y), int(self.label_width_mm * self.scale), int(y))
            y += self.grid_size * self.scale
    
    def _draw_alignment_guides(self, painter: QPainter):
        """Draw alignment guides."""
        painter.setPen(QPen(QColor("#ff6600"), 1, Qt.DashLine))
        
        for guide_type, position in self._alignment_guides:
            if guide_type == "vertical":
                x = int(position * self.scale)
                painter.drawLine(x, 0, x, int(self.label_height_mm * self.scale))
            else:  # horizontal
                y = int(position * self.scale)
                painter.drawLine(0, y, int(self.label_width_mm * self.scale), y)
    
    def _draw_selection_handles(self, painter: QPainter):
        """Draw resize handles for selected element."""
        elem = self.selected_element
        if not elem:
            return
        
        # Draw selection border
        painter.setPen(QPen(QColor("#0066cc"), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(elem.x * self.scale, elem.y * self.scale,
                               elem.width * self.scale, elem.height * self.scale))
        
        # Draw resize handles
        handle_size = 8
        painter.setBrush(QBrush(QColor("#0066cc")))
        
        # Corner handles
        corners = [
            (elem.x * self.scale, elem.y * self.scale),  # NW
            ((elem.x + elem.width) * self.scale, elem.y * self.scale),  # NE
            (elem.x * self.scale, (elem.y + elem.height) * self.scale),  # SW
            ((elem.x + elem.width) * self.scale, (elem.y + elem.height) * self.scale),  # SE
        ]
        
        for x, y in corners:
            painter.drawRect(int(x - handle_size/2), int(y - handle_size/2), 
                           handle_size, handle_size)
    
    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press."""
        if event.button() != Qt.LeftButton:
            return
        
        pos_mm = self._screen_to_mm(event.position())
        
        # Check if clicking on resize handle
        if self.selected_element:
            handle = self._get_resize_handle(pos_mm)
            if handle:
                self._resizing = True
                self._resize_handle = handle
                return
        
        # Check if clicking on element
        clicked_element = self._get_element_at(pos_mm)
        
        if clicked_element:
            # Select and start drag
            if self.selected_element != clicked_element:
                if self.selected_element:
                    self.selected_element.selected = False
                self.selected_element = clicked_element
                self.selected_element.selected = True
                self.element_selected.emit(self.selected_element)
            
            self._dragging = True
            self._drag_start = pos_mm
            self._element_start_pos = (clicked_element.x, clicked_element.y)
        else:
            # Deselect
            if self.selected_element:
                self.selected_element.selected = False
                self.selected_element = None
                self.element_selected.emit(None)
        
        self.update()
    
    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move."""
        pos_mm = self._screen_to_mm(event.position())
        
        if self._resizing and self.selected_element:
            self._handle_resize(pos_mm)
        elif self._dragging and self.selected_element and self._drag_start:
            # Calculate delta
            dx = pos_mm.x() - self._drag_start.x()
            dy = pos_mm.y() - self._drag_start.y()
            
            # Move element
            new_x = self._element_start_pos[0] + dx
            new_y = self._element_start_pos[1] + dy
            
            # Apply snap to grid
            if self.show_grid:
                new_x, new_y = self._snap_to_grid(new_x, new_y)
            
            self.selected_element.move_to(new_x, new_y)
            
            # Update alignment guides
            if self.show_guides:
                self._alignment_guides = self._find_alignment_guides(self.selected_element)
            
            self.update()
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse release."""
        if event.button() == Qt.LeftButton:
            if self._dragging or self._resizing:
                self.element_modified.emit()
            
            self._dragging = False
            self._resizing = False
            self._drag_start = None
            self._element_start_pos = None
            self._resize_handle = None
            self._alignment_guides.clear()
            self.update()
    
    def _screen_to_mm(self, pos: QPointF) -> QPointF:
        """Convert screen coordinates to mm."""
        return QPointF(pos.x() / self.scale, pos.y() / self.scale)
    
    def _get_element_at(self, pos_mm: QPointF) -> Optional[LabelElement]:
        """Get element at position (top-most first)."""
        # Check in reverse z-index order
        sorted_elements = sorted(self.elements, key=lambda e: e.z_index, reverse=True)
        for element in sorted_elements:
            if element.contains_point(pos_mm.x(), pos_mm.y()):
                return element
        return None
    
    def _get_resize_handle(self, pos_mm: QPointF) -> Optional[str]:
        """Get resize handle at position."""
        if not self.selected_element:
            return None
        
        elem = self.selected_element
        threshold = 5 / self.scale  # 5 pixels in mm
        
        # Check corners
        corners = {
            "nw": (elem.x, elem.y),
            "ne": (elem.x + elem.width, elem.y),
            "sw": (elem.x, elem.y + elem.height),
            "se": (elem.x + elem.width, elem.y + elem.height),
        }
        
        for handle, (x, y) in corners.items():
            if abs(pos_mm.x() - x) < threshold and abs(pos_mm.y() - y) < threshold:
                return handle
        
        return None
    
    def _handle_resize(self, pos_mm: QPointF):
        """Handle element resize."""
        if not self.selected_element or not self._resize_handle:
            return
        
        elem = self.selected_element
        handle = self._resize_handle
        
        if handle == "se":
            # Bottom-right corner
            new_width = pos_mm.x() - elem.x
            new_height = pos_mm.y() - elem.y
            elem.resize(new_width, new_height)
        elif handle == "sw":
            # Bottom-left corner
            new_width = (elem.x + elem.width) - pos_mm.x()
            new_height = pos_mm.y() - elem.y
            elem.x = pos_mm.x()
            elem.resize(new_width, new_height)
        elif handle == "ne":
            # Top-right corner
            new_width = pos_mm.x() - elem.x
            new_height = (elem.y + elem.height) - pos_mm.y()
            elem.y = pos_mm.y()
            elem.resize(new_width, new_height)
        elif handle == "nw":
            # Top-left corner
            new_width = (elem.x + elem.width) - pos_mm.x()
            new_height = (elem.y + elem.height) - pos_mm.y()
            elem.x = pos_mm.x()
            elem.y = pos_mm.y()
            elem.resize(new_width, new_height)
        
        self.update()
    
    def _snap_to_grid(self, x: float, y: float) -> Tuple[float, float]:
        """Snap coordinates to grid."""
        x = round(x / self.grid_size) * self.grid_size
        y = round(y / self.grid_size) * self.grid_size
        return x, y
    
    def _find_alignment_guides(self, dragged_element: LabelElement) -> List[Tuple[str, float]]:
        """Find alignment guides for dragged element."""
        guides = []
        
        for elem in self.elements:
            if elem == dragged_element:
                continue
            
            # Check vertical alignment (left edges)
            if abs(dragged_element.x - elem.x) < self.snap_threshold:
                guides.append(("vertical", elem.x))
                dragged_element.x = elem.x
            
            # Check vertical alignment (right edges)
            elif abs((dragged_element.x + dragged_element.width) - (elem.x + elem.width)) < self.snap_threshold:
                guides.append(("vertical", elem.x + elem.width))
            
            # Check horizontal alignment (top edges)
            if abs(dragged_element.y - elem.y) < self.snap_threshold:
                guides.append(("horizontal", elem.y))
                dragged_element.y = elem.y
            
            # Check horizontal alignment (bottom edges)
            elif abs((dragged_element.y + dragged_element.height) - (elem.y + elem.height)) < self.snap_threshold:
                guides.append(("horizontal", elem.y + elem.height))
        
        return guides
    
    def zoom_in(self):
        """Increase zoom level."""
        self.scale = min(self.scale * 1.2, 10.0)
        self.setMinimumSize(int(self.label_width_mm * self.scale), 
                          int(self.label_height_mm * self.scale))
        self.update()
    
    def zoom_out(self):
        """Decrease zoom level."""
        self.scale = max(self.scale / 1.2, 1.0)
        self.setMinimumSize(int(self.label_width_mm * self.scale), 
                          int(self.label_height_mm * self.scale))
        self.update()
    
    def toggle_grid(self):
        """Toggle grid visibility."""
        self.show_grid = not self.show_grid
        self.update()
    
    def toggle_guides(self):
        """Toggle alignment guides."""
        self.show_guides = not self.show_guides
        self.update()
