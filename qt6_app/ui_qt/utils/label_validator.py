"""
Validation utilities for label elements.
"""
from __future__ import annotations
from typing import List, Tuple, Optional
from .label_element import LabelElement, TextElement, FieldElement, BarcodeElement


class ValidationResult:
    """Result of element validation."""
    
    def __init__(self, valid: bool = True, message: str = "", level: str = "info"):
        self.valid = valid
        self.message = message
        self.level = level  # "info", "warning", "error"


class LabelValidator:
    """Validates label elements for common issues."""
    
    def __init__(self, canvas_width: float, canvas_height: float):
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        
    def validate_element(self, element: LabelElement) -> List[ValidationResult]:
        """
        Validate a single element.
        
        Args:
            element: Element to validate
            
        Returns:
            List of validation results
        """
        results = []
        
        # Check bounds
        if element.x < 0 or element.y < 0:
            results.append(ValidationResult(
                valid=False,
                message="Elemento fuori margini (posizione negativa)",
                level="error"
            ))
        
        if element.x + element.width > self.canvas_width:
            results.append(ValidationResult(
                valid=False,
                message="Elemento esce dal margine destro",
                level="error"
            ))
        
        if element.y + element.height > self.canvas_height:
            results.append(ValidationResult(
                valid=False,
                message="Elemento esce dal margine inferiore",
                level="error"
            ))
        
        # Check text elements
        if isinstance(element, TextElement):
            if element.font_size < 6:
                results.append(ValidationResult(
                    valid=False,
                    message="Font troppo piccolo (< 6pt)",
                    level="warning"
                ))
            elif element.font_size < 8:
                results.append(ValidationResult(
                    valid=True,
                    message="Font molto piccolo, potrebbe non essere leggibile",
                    level="warning"
                ))
            
            if not element.text or element.text.strip() == "":
                results.append(ValidationResult(
                    valid=False,
                    message="Testo vuoto",
                    level="warning"
                ))
        
        # Check field elements
        if isinstance(element, FieldElement):
            if not element.source:
                results.append(ValidationResult(
                    valid=False,
                    message="Sorgente dati non configurata",
                    level="error"
                ))
            
            if element.font_size < 6:
                results.append(ValidationResult(
                    valid=False,
                    message="Font troppo piccolo (< 6pt)",
                    level="warning"
                ))
        
        # Check barcode elements
        if isinstance(element, BarcodeElement):
            if not element.source:
                results.append(ValidationResult(
                    valid=False,
                    message="Sorgente dati barcode non configurata",
                    level="error"
                ))
            
            if element.width < 30 or element.height < 15:
                results.append(ValidationResult(
                    valid=False,
                    message="Barcode troppo piccolo",
                    level="warning"
                ))
        
        # If no issues found
        if not results:
            results.append(ValidationResult(
                valid=True,
                message="Elemento valido",
                level="info"
            ))
        
        return results
    
    def validate_all(self, elements: List[LabelElement]) -> List[Tuple[LabelElement, List[ValidationResult]]]:
        """
        Validate all elements.
        
        Args:
            elements: List of elements to validate
            
        Returns:
            List of tuples (element, validation_results)
        """
        results = []
        
        for element in elements:
            validation = self.validate_element(element)
            results.append((element, validation))
        
        # Check for overlaps (warning only)
        for i, elem1 in enumerate(elements):
            for elem2 in elements[i+1:]:
                if self._check_overlap(elem1, elem2):
                    results.append((elem1, [ValidationResult(
                        valid=True,
                        message="Elemento sovrapposto ad un altro",
                        level="warning"
                    )]))
                    break
        
        return results
    
    def _check_overlap(self, elem1: LabelElement, elem2: LabelElement) -> bool:
        """Check if two elements overlap."""
        return not (elem1.x + elem1.width < elem2.x or
                   elem2.x + elem2.width < elem1.x or
                   elem1.y + elem1.height < elem2.y or
                   elem2.y + elem2.height < elem1.y)
    
    def get_summary(self, elements: List[LabelElement]) -> Tuple[int, int, int]:
        """
        Get validation summary.
        
        Args:
            elements: List of elements to validate
            
        Returns:
            Tuple of (error_count, warning_count, info_count)
        """
        errors = 0
        warnings = 0
        infos = 0
        
        for element in elements:
            results = self.validate_element(element)
            for result in results:
                if result.level == "error":
                    errors += 1
                elif result.level == "warning":
                    warnings += 1
                else:
                    infos += 1
        
        return errors, warnings, infos
