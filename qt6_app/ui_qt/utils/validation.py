"""
Input validation framework for Blitz CNC.

Provides validators for:
- Length values
- Angle values
- File paths
- Configuration values
"""

from typing import Optional, List, Callable
from dataclasses import dataclass
import logging
import re

logger = logging.getLogger(__name__)


@dataclass
class ValidationError:
    """Validation error details"""
    field: str
    message: str
    code: str
    severity: str = "error"  # error, warning, info


class ValidationResult:
    """Result of validation operation"""
    
    def __init__(self):
        self.errors: List[ValidationError] = []
        self.warnings: List[ValidationError] = []
    
    @property
    def is_valid(self) -> bool:
        """Check if validation passed (no errors)"""
        return len(self.errors) == 0
    
    def add_error(self, field: str, message: str, code: str):
        """Add error to result"""
        self.errors.append(ValidationError(field, message, code, "error"))
    
    def add_warning(self, field: str, message: str, code: str):
        """Add warning to result"""
        self.warnings.append(ValidationError(field, message, code, "warning"))
    
    def get_error_messages(self) -> List[str]:
        """Get list of error messages"""
        return [e.message for e in self.errors]


class Validator:
    """Input validation helpers"""
    
    @staticmethod
    def validate_length(
        value: float,
        min_mm: float = 0.0,
        max_mm: float = 10000.0,
        field_name: str = "length"
    ) -> ValidationResult:
        """
        Validate length value.
        
        Args:
            value: Length in mm
            min_mm: Minimum allowed length
            max_mm: Maximum allowed length
            field_name: Field name for error messages
        
        Returns:
            ValidationResult with errors if any
        """
        result = ValidationResult()
        
        if value < min_mm:
            result.add_error(
                field_name,
                f"{field_name} minima: {min_mm}mm (attuale: {value}mm)",
                "LENGTH_TOO_SHORT"
            )
        
        if value > max_mm:
            result.add_error(
                field_name,
                f"{field_name} massima: {max_mm}mm (attuale: {value}mm)",
                "LENGTH_TOO_LONG"
            )
        
        return result
    
    @staticmethod
    def validate_angle(
        value: int,
        valid_angles: List[int] = [0, 15, 22, 30, 45, 90],
        field_name: str = "angle"
    ) -> ValidationResult:
        """Validate angle value"""
        result = ValidationResult()
        
        if value not in valid_angles:
            result.add_error(
                field_name,
                f"Angolo non valido. Valori ammessi: {', '.join(map(str, valid_angles))}",
                "INVALID_ANGLE"
            )
        
        return result
    
    @staticmethod
    def validate_file_path(
        path: str,
        must_exist: bool = False,
        extensions: Optional[List[str]] = None,
        field_name: str = "file_path"
    ) -> ValidationResult:
        """Validate file path"""
        from pathlib import Path
        
        result = ValidationResult()
        path_obj = Path(path)
        
        if must_exist and not path_obj.exists():
            result.add_error(
                field_name,
                f"File non trovato: {path}",
                "FILE_NOT_FOUND"
            )
        
        if extensions and path_obj.suffix.lower() not in extensions:
            result.add_error(
                field_name,
                f"Estensione non valida. Estensioni ammesse: {', '.join(extensions)}",
                "INVALID_EXTENSION"
            )
        
        return result
