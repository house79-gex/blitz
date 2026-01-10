"""
Unit tests for input validation framework.
"""

import pytest
from pathlib import Path
import tempfile
from qt6_app.ui_qt.utils.validation import (
    ValidationError,
    ValidationResult,
    Validator
)


def test_validation_error_creation():
    """Test ValidationError dataclass creation."""
    error = ValidationError(
        field="test_field",
        message="Test message",
        code="TEST_CODE",
        severity="error"
    )
    
    assert error.field == "test_field"
    assert error.message == "Test message"
    assert error.code == "TEST_CODE"
    assert error.severity == "error"


def test_validation_result_is_valid_empty():
    """Test ValidationResult.is_valid with no errors."""
    result = ValidationResult()
    assert result.is_valid


def test_validation_result_is_valid_with_errors():
    """Test ValidationResult.is_valid with errors."""
    result = ValidationResult()
    result.add_error("field", "Error message", "ERROR_CODE")
    
    assert not result.is_valid


def test_validation_result_is_valid_with_warnings_only():
    """Test ValidationResult.is_valid with warnings only (should be valid)."""
    result = ValidationResult()
    result.add_warning("field", "Warning message", "WARNING_CODE")
    
    assert result.is_valid


def test_validation_result_add_error():
    """Test ValidationResult.add_error method."""
    result = ValidationResult()
    result.add_error("test_field", "Test error", "ERROR_CODE")
    
    assert len(result.errors) == 1
    assert result.errors[0].field == "test_field"
    assert result.errors[0].message == "Test error"
    assert result.errors[0].code == "ERROR_CODE"
    assert result.errors[0].severity == "error"


def test_validation_result_add_warning():
    """Test ValidationResult.add_warning method."""
    result = ValidationResult()
    result.add_warning("test_field", "Test warning", "WARNING_CODE")
    
    assert len(result.warnings) == 1
    assert result.warnings[0].field == "test_field"
    assert result.warnings[0].message == "Test warning"
    assert result.warnings[0].code == "WARNING_CODE"
    assert result.warnings[0].severity == "warning"


def test_validation_result_get_error_messages():
    """Test ValidationResult.get_error_messages method."""
    result = ValidationResult()
    result.add_error("field1", "Error 1", "CODE1")
    result.add_error("field2", "Error 2", "CODE2")
    
    messages = result.get_error_messages()
    
    assert len(messages) == 2
    assert "Error 1" in messages
    assert "Error 2" in messages


def test_validator_validate_length_valid():
    """Test Validator.validate_length with valid value."""
    result = Validator.validate_length(
        value=500.0,
        min_mm=0.0,
        max_mm=1000.0,
        field_name="test_length"
    )
    
    assert result.is_valid
    assert len(result.errors) == 0


def test_validator_validate_length_too_short():
    """Test Validator.validate_length with value too short."""
    result = Validator.validate_length(
        value=50.0,
        min_mm=100.0,
        max_mm=1000.0,
        field_name="test_length"
    )
    
    assert not result.is_valid
    assert len(result.errors) == 1
    assert result.errors[0].code == "LENGTH_TOO_SHORT"
    assert "50.0mm" in result.errors[0].message


def test_validator_validate_length_too_long():
    """Test Validator.validate_length with value too long."""
    result = Validator.validate_length(
        value=1500.0,
        min_mm=0.0,
        max_mm=1000.0,
        field_name="test_length"
    )
    
    assert not result.is_valid
    assert len(result.errors) == 1
    assert result.errors[0].code == "LENGTH_TOO_LONG"
    assert "1500.0mm" in result.errors[0].message


def test_validator_validate_length_at_boundaries():
    """Test Validator.validate_length at min/max boundaries."""
    # At minimum
    result_min = Validator.validate_length(value=100.0, min_mm=100.0, max_mm=1000.0)
    assert result_min.is_valid
    
    # At maximum
    result_max = Validator.validate_length(value=1000.0, min_mm=100.0, max_mm=1000.0)
    assert result_max.is_valid


def test_validator_validate_angle_valid():
    """Test Validator.validate_angle with valid angle."""
    result = Validator.validate_angle(
        value=45,
        valid_angles=[0, 15, 22, 30, 45, 90],
        field_name="test_angle"
    )
    
    assert result.is_valid
    assert len(result.errors) == 0


def test_validator_validate_angle_invalid():
    """Test Validator.validate_angle with invalid angle."""
    result = Validator.validate_angle(
        value=60,
        valid_angles=[0, 15, 22, 30, 45, 90],
        field_name="test_angle"
    )
    
    assert not result.is_valid
    assert len(result.errors) == 1
    assert result.errors[0].code == "INVALID_ANGLE"
    assert "60" not in result.errors[0].message or "non valido" in result.errors[0].message


def test_validator_validate_angle_default_angles():
    """Test Validator.validate_angle with default angles."""
    # Test all default angles are valid
    default_angles = [0, 15, 22, 30, 45, 90]
    
    for angle in default_angles:
        result = Validator.validate_angle(value=angle)
        assert result.is_valid, f"Angle {angle} should be valid"


def test_validator_validate_file_path_exists():
    """Test Validator.validate_file_path with existing file."""
    with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as tmp:
        tmp_path = tmp.name
        tmp.write(b"test content")
    
    try:
        result = Validator.validate_file_path(
            path=tmp_path,
            must_exist=True,
            field_name="test_file"
        )
        
        assert result.is_valid
        assert len(result.errors) == 0
    finally:
        Path(tmp_path).unlink()


def test_validator_validate_file_path_not_exists():
    """Test Validator.validate_file_path with non-existing file."""
    result = Validator.validate_file_path(
        path="/nonexistent/file.txt",
        must_exist=True,
        field_name="test_file"
    )
    
    assert not result.is_valid
    assert len(result.errors) == 1
    assert result.errors[0].code == "FILE_NOT_FOUND"


def test_validator_validate_file_path_valid_extension():
    """Test Validator.validate_file_path with valid extension."""
    result = Validator.validate_file_path(
        path="/some/path/file.csv",
        extensions=['.csv', '.xlsx'],
        field_name="test_file"
    )
    
    assert result.is_valid


def test_validator_validate_file_path_invalid_extension():
    """Test Validator.validate_file_path with invalid extension."""
    result = Validator.validate_file_path(
        path="/some/path/file.txt",
        extensions=['.csv', '.xlsx'],
        field_name="test_file"
    )
    
    assert not result.is_valid
    assert len(result.errors) == 1
    assert result.errors[0].code == "INVALID_EXTENSION"


def test_validator_validate_file_path_case_insensitive_extension():
    """Test Validator.validate_file_path is case insensitive for extensions."""
    result = Validator.validate_file_path(
        path="/some/path/FILE.CSV",
        extensions=['.csv', '.xlsx'],
        field_name="test_file"
    )
    
    assert result.is_valid


def test_validator_validate_file_path_multiple_errors():
    """Test Validator.validate_file_path can have multiple errors."""
    result = Validator.validate_file_path(
        path="/nonexistent/file.txt",
        must_exist=True,
        extensions=['.csv', '.xlsx'],
        field_name="test_file"
    )
    
    assert not result.is_valid
    assert len(result.errors) == 2  # File not found + invalid extension


def test_validation_result_multiple_errors_and_warnings():
    """Test ValidationResult with multiple errors and warnings."""
    result = ValidationResult()
    result.add_error("field1", "Error 1", "ERROR1")
    result.add_error("field2", "Error 2", "ERROR2")
    result.add_warning("field3", "Warning 1", "WARN1")
    result.add_warning("field4", "Warning 2", "WARN2")
    
    assert not result.is_valid
    assert len(result.errors) == 2
    assert len(result.warnings) == 2
    
    messages = result.get_error_messages()
    assert len(messages) == 2
    assert "Error 1" in messages
    assert "Error 2" in messages
