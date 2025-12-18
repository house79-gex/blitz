"""
Base classes for label elements in the WYSIWYG editor.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from PySide6.QtGui import QPainter, QFont, QColor, QPixmap, QPen, QBrush
from PySide6.QtCore import QRectF, Qt


class LabelElement(ABC):
    """Base class for all label elements."""
    
    def __init__(self, x: float = 0, y: float = 0, width: float = 100, height: float = 20):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.rotation = 0
        self.z_index = 0
        self.selected = False
        
    @abstractmethod
    def paint(self, painter: QPainter, scale: float = 1.0):
        """Paint the element on the canvas."""
        pass
    
    @abstractmethod
    def serialize(self) -> Dict[str, Any]:
        """Serialize element to dictionary."""
        pass
    
    @classmethod
    @abstractmethod
    def deserialize(cls, data: Dict[str, Any]) -> LabelElement:
        """Deserialize element from dictionary."""
        pass
    
    def get_bounds(self) -> QRectF:
        """Get element bounding rectangle."""
        return QRectF(self.x, self.y, self.width, self.height)
    
    def contains_point(self, x: float, y: float) -> bool:
        """Check if point is inside element."""
        return self.get_bounds().contains(x, y)
    
    def move_to(self, x: float, y: float):
        """Move element to position."""
        self.x = x
        self.y = y
    
    def resize(self, width: float, height: float):
        """Resize element."""
        self.width = max(10, width)
        self.height = max(10, height)


class TextElement(LabelElement):
    """Static text element."""
    
    def __init__(self, text: str = "Text", font_family: str = "Arial", font_size: int = 12, **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.font_family = font_family
        self.font_size = font_size
        self.bold = False
        self.italic = False
        self.color = "#000000"
        
    def paint(self, painter: QPainter, scale: float = 1.0):
        font = QFont(self.font_family, int(self.font_size * scale))
        font.setBold(self.bold)
        font.setItalic(self.italic)
        painter.setFont(font)
        
        if self.selected:
            painter.setPen(QPen(QColor("#0066cc"), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(self.x * scale, self.y * scale, 
                                   self.width * scale, self.height * scale))
        
        painter.setPen(QColor(self.color))
        painter.drawText(QRectF(self.x * scale, self.y * scale, 
                               self.width * scale, self.height * scale), 
                        Qt.AlignLeft | Qt.AlignVCenter, self.text)
    
    def serialize(self) -> Dict[str, Any]:
        return {
            "type": "text",
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "rotation": self.rotation,
            "z_index": self.z_index,
            "text": self.text,
            "font_family": self.font_family,
            "font_size": self.font_size,
            "bold": self.bold,
            "italic": self.italic,
            "color": self.color
        }
    
    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> TextElement:
        elem = cls(
            text=data.get("text", "Text"),
            font_family=data.get("font_family", "Arial"),
            font_size=data.get("font_size", 12),
            x=data.get("x", 0),
            y=data.get("y", 0),
            width=data.get("width", 100),
            height=data.get("height", 20)
        )
        elem.rotation = data.get("rotation", 0)
        elem.z_index = data.get("z_index", 0)
        elem.bold = data.get("bold", False)
        elem.italic = data.get("italic", False)
        elem.color = data.get("color", "#000000")
        return elem


class FieldElement(LabelElement):
    """Dynamic data field element."""
    
    SOURCES = [
        "length", "profile_name", "angle_left", "angle_right",
        "order_id", "piece_id", "operator_name", "date", "time",
        "material", "quantity"
    ]
    
    def __init__(self, source: str = "length", format_string: str = "{}", 
                 font_family: str = "Arial", font_size: int = 12, **kwargs):
        super().__init__(**kwargs)
        self.source = source
        self.format_string = format_string
        self.font_family = font_family
        self.font_size = font_size
        self.bold = False
        self.italic = False
        self.color = "#000000"
        
    def paint(self, painter: QPainter, scale: float = 1.0):
        font = QFont(self.font_family, int(self.font_size * scale))
        font.setBold(self.bold)
        font.setItalic(self.italic)
        painter.setFont(font)
        
        if self.selected:
            painter.setPen(QPen(QColor("#0066cc"), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(self.x * scale, self.y * scale, 
                                   self.width * scale, self.height * scale))
        
        # Show preview with placeholder
        preview_text = self.format_string.format("1234")
        painter.setPen(QColor(self.color))
        painter.drawText(QRectF(self.x * scale, self.y * scale, 
                               self.width * scale, self.height * scale),
                        Qt.AlignLeft | Qt.AlignVCenter, preview_text)
        
        # Show source label
        painter.setPen(QColor("#666666"))
        small_font = QFont(self.font_family, int(8 * scale))
        painter.setFont(small_font)
        painter.drawText(QRectF(self.x * scale, (self.y - 10) * scale, 
                               self.width * scale, 10 * scale),
                        Qt.AlignLeft | Qt.AlignBottom, f"{{{{ {self.source} }}}}")
    
    def serialize(self) -> Dict[str, Any]:
        return {
            "type": "field",
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "rotation": self.rotation,
            "z_index": self.z_index,
            "source": self.source,
            "format_string": self.format_string,
            "font_family": self.font_family,
            "font_size": self.font_size,
            "bold": self.bold,
            "italic": self.italic,
            "color": self.color
        }
    
    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> FieldElement:
        elem = cls(
            source=data.get("source", "length"),
            format_string=data.get("format_string", "{}"),
            font_family=data.get("font_family", "Arial"),
            font_size=data.get("font_size", 12),
            x=data.get("x", 0),
            y=data.get("y", 0),
            width=data.get("width", 100),
            height=data.get("height", 20)
        )
        elem.rotation = data.get("rotation", 0)
        elem.z_index = data.get("z_index", 0)
        elem.bold = data.get("bold", False)
        elem.italic = data.get("italic", False)
        elem.color = data.get("color", "#000000")
        return elem


class BarcodeElement(LabelElement):
    """Barcode element."""
    
    BARCODE_TYPES = ["code128", "qr", "ean13", "code39"]
    
    def __init__(self, source: str = "order_id", barcode_type: str = "code128", **kwargs):
        kwargs.setdefault('width', 90)
        kwargs.setdefault('height', 30)
        super().__init__(**kwargs)
        self.source = source
        self.barcode_type = barcode_type
        
    def paint(self, painter: QPainter, scale: float = 1.0):
        if self.selected:
            painter.setPen(QPen(QColor("#0066cc"), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(self.x * scale, self.y * scale, 
                                   self.width * scale, self.height * scale))
        
        # Draw placeholder barcode representation
        painter.setPen(QPen(QColor("#000000"), 1))
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.drawRect(QRectF(self.x * scale, self.y * scale, 
                               self.width * scale, self.height * scale))
        
        # Draw simple bars to represent barcode
        bar_width = (self.width * scale) / 20
        for i in range(20):
            if i % 3 != 0:  # Simple pattern
                painter.fillRect(QRectF(self.x * scale + i * bar_width, self.y * scale,
                                       bar_width, self.height * scale), QColor("#000000"))
        
        # Show source label
        painter.setPen(QColor("#666666"))
        small_font = QFont("Arial", int(8 * scale))
        painter.setFont(small_font)
        painter.drawText(QRectF(self.x * scale, (self.y - 10) * scale, 
                               self.width * scale, 10 * scale),
                        Qt.AlignCenter, f"[{self.barcode_type}: {self.source}]")
    
    def serialize(self) -> Dict[str, Any]:
        return {
            "type": "barcode",
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "rotation": self.rotation,
            "z_index": self.z_index,
            "source": self.source,
            "barcode_type": self.barcode_type
        }
    
    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> BarcodeElement:
        elem = cls(
            source=data.get("source", "order_id"),
            barcode_type=data.get("barcode_type", "code128"),
            x=data.get("x", 0),
            y=data.get("y", 0),
            width=data.get("width", 90),
            height=data.get("height", 30)
        )
        elem.rotation = data.get("rotation", 0)
        elem.z_index = data.get("z_index", 0)
        return elem


class ImageElement(LabelElement):
    """Image/logo element."""
    
    def __init__(self, image_path: str = "", **kwargs):
        kwargs.setdefault('width', 50)
        kwargs.setdefault('height', 30)
        super().__init__(**kwargs)
        self.image_path = image_path
        self._pixmap: Optional[QPixmap] = None
        
    def paint(self, painter: QPainter, scale: float = 1.0):
        if self.selected:
            painter.setPen(QPen(QColor("#0066cc"), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(self.x * scale, self.y * scale, 
                                   self.width * scale, self.height * scale))
        
        # Draw placeholder or actual image
        painter.setPen(QPen(QColor("#cccccc"), 1))
        painter.setBrush(QBrush(QColor("#f0f0f0")))
        painter.drawRect(QRectF(self.x * scale, self.y * scale, 
                               self.width * scale, self.height * scale))
        
        # Show "IMG" text if no image loaded
        painter.setPen(QColor("#999999"))
        painter.setFont(QFont("Arial", int(10 * scale)))
        painter.drawText(QRectF(self.x * scale, self.y * scale, 
                               self.width * scale, self.height * scale),
                        Qt.AlignCenter, "IMG")
    
    def serialize(self) -> Dict[str, Any]:
        return {
            "type": "image",
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "rotation": self.rotation,
            "z_index": self.z_index,
            "image_path": self.image_path
        }
    
    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> ImageElement:
        elem = cls(
            image_path=data.get("image_path", ""),
            x=data.get("x", 0),
            y=data.get("y", 0),
            width=data.get("width", 50),
            height=data.get("height", 30)
        )
        elem.rotation = data.get("rotation", 0)
        elem.z_index = data.get("z_index", 0)
        return elem


class LineElement(LabelElement):
    """Line separator element."""
    
    def __init__(self, thickness: int = 1, **kwargs):
        kwargs.setdefault('width', 100)
        kwargs.setdefault('height', 1)
        super().__init__(**kwargs)
        self.thickness = thickness
        self.color = "#000000"
        
    def paint(self, painter: QPainter, scale: float = 1.0):
        if self.selected:
            painter.setPen(QPen(QColor("#0066cc"), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(self.x * scale, self.y * scale, 
                                   self.width * scale, self.thickness * scale + 4))
        
        painter.setPen(QPen(QColor(self.color), self.thickness * scale))
        painter.drawLine(int(self.x * scale), int(self.y * scale), 
                        int((self.x + self.width) * scale), int(self.y * scale))
    
    def serialize(self) -> Dict[str, Any]:
        return {
            "type": "line",
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "rotation": self.rotation,
            "z_index": self.z_index,
            "thickness": self.thickness,
            "color": self.color
        }
    
    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> LineElement:
        elem = cls(
            thickness=data.get("thickness", 1),
            x=data.get("x", 0),
            y=data.get("y", 0),
            width=data.get("width", 100),
            height=data.get("height", 1)
        )
        elem.rotation = data.get("rotation", 0)
        elem.z_index = data.get("z_index", 0)
        elem.color = data.get("color", "#000000")
        return elem


class ShapeElement(LabelElement):
    """Rectangle/circle shape element."""
    
    SHAPE_TYPES = ["rectangle", "circle"]
    
    def __init__(self, shape_type: str = "rectangle", **kwargs):
        kwargs.setdefault('width', 50)
        kwargs.setdefault('height', 30)
        super().__init__(**kwargs)
        self.shape_type = shape_type
        self.fill_color = "#ffffff"
        self.border_color = "#000000"
        self.border_width = 1
        
    def paint(self, painter: QPainter, scale: float = 1.0):
        painter.setPen(QPen(QColor(self.border_color), self.border_width * scale))
        painter.setBrush(QBrush(QColor(self.fill_color)))
        
        rect = QRectF(self.x * scale, self.y * scale, 
                     self.width * scale, self.height * scale)
        
        if self.shape_type == "circle":
            painter.drawEllipse(rect)
        else:
            painter.drawRect(rect)
        
        if self.selected:
            painter.setPen(QPen(QColor("#0066cc"), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect)
    
    def serialize(self) -> Dict[str, Any]:
        return {
            "type": "shape",
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "rotation": self.rotation,
            "z_index": self.z_index,
            "shape_type": self.shape_type,
            "fill_color": self.fill_color,
            "border_color": self.border_color,
            "border_width": self.border_width
        }
    
    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> ShapeElement:
        elem = cls(
            shape_type=data.get("shape_type", "rectangle"),
            x=data.get("x", 0),
            y=data.get("y", 0),
            width=data.get("width", 50),
            height=data.get("height", 30)
        )
        elem.rotation = data.get("rotation", 0)
        elem.z_index = data.get("z_index", 0)
        elem.fill_color = data.get("fill_color", "#ffffff")
        elem.border_color = data.get("border_color", "#000000")
        elem.border_width = data.get("border_width", 1)
        return elem


def deserialize_element(data: Dict[str, Any]) -> Optional[LabelElement]:
    """Factory function to deserialize any element type."""
    element_type = data.get("type")
    
    if element_type == "text":
        return TextElement.deserialize(data)
    elif element_type == "field":
        return FieldElement.deserialize(data)
    elif element_type == "barcode":
        return BarcodeElement.deserialize(data)
    elif element_type == "image":
        return ImageElement.deserialize(data)
    elif element_type == "line":
        return LineElement.deserialize(data)
    elif element_type == "shape":
        return ShapeElement.deserialize(data)
    
    return None
