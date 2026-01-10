# Production-Grade Error Handling & Logging System

## Overview

This implementation provides a robust, production-ready system for error handling, logging, and input validation for the Blitz CNC application.

## Features

### 1. Structured Logging System (`logger.py`)
- **Dual output formats**: Human-readable console + structured JSON files
- **Rotating file handlers**: 10MB main log, 5MB error log with automatic rotation
- **Separate error log**: All ERROR and CRITICAL messages in dedicated file
- **Exception tracking**: Full traceback capture with context
- **Extra data support**: Add custom fields to log entries

### 2. Error Handling Utilities (`error_handling.py`)
- **Context manager**: `handle_errors()` for consistent error handling
- **Decorator**: `@safe_operation()` for function-level error handling
- **Retry mechanism**: `ErrorRecovery.retry_operation()` with exponential backoff
- **User notifications**: Automatic error display via Toast or QMessageBox

### 3. Input Validation Framework (`validation.py`)
- **Length validation**: Min/max bounds with clear error messages
- **Angle validation**: Configurable valid angle list
- **File path validation**: Existence and extension checks
- **Structured results**: Separate errors and warnings with validation codes

## Installation

No additional dependencies required beyond the standard requirements.txt.

## Quick Start

### Setup Logging

```python
# In your main application entry point (main_qt.py)
from ui_qt.utils.logger import setup_logging, get_logger

# Setup logging system (called once at startup)
log_dir = setup_logging()

# Get logger for your module
logger = get_logger(__name__)
logger.info("Application started")
```

### Error Handling with Context Manager

```python
from ui_qt.utils.error_handling import handle_errors

def load_configuration():
    with handle_errors("Caricamento configurazione", show_user=True):
        config = read_config_file()
        validate_config(config)
        return config
```

### Error Handling with Decorator

```python
from ui_qt.utils.error_handling import safe_operation

@safe_operation("Salvataggio dati", show_user=True, default_return=False)
def save_data(data):
    with open('data.json', 'w') as f:
        json.dump(data, f)
    return True
```

### Input Validation

```python
from ui_qt.utils.validation import Validator

def validate_cut_parameters(length_mm, angle):
    # Validate length
    length_result = Validator.validate_length(
        length_mm,
        min_mm=250.0,
        max_mm=4000.0,
        field_name="lunghezza"
    )
    
    if not length_result.is_valid:
        error_messages = '\n'.join(length_result.get_error_messages())
        show_error_to_user(error_messages)
        return False
    
    # Validate angle
    angle_result = Validator.validate_angle(
        angle,
        valid_angles=[0, 15, 22, 30, 45, 90],
        field_name="angolo"
    )
    
    if not angle_result.is_valid:
        error_messages = '\n'.join(angle_result.get_error_messages())
        show_error_to_user(error_messages)
        return False
    
    return True
```

### Retry Mechanism

```python
from ui_qt.utils.error_handling import ErrorRecovery

def connect_to_hardware():
    def _connect():
        # Your connection logic
        return establish_connection()
    
    result = ErrorRecovery.retry_operation(
        _connect,
        max_retries=3,
        delay_seconds=1.0,
        backoff_factor=2.0
    )
    
    return result is not None
```

## Log Files

Logs are stored in `~/.blitz/logs/`:
- `blitz.log`: All logs (DEBUG and above) in JSON format
- `errors.log`: Only ERROR and CRITICAL logs in JSON format

Both files automatically rotate when reaching size limits.

## JSON Log Format

```json
{
  "timestamp": "2026-01-10T19:47:59.380114",
  "level": "ERROR",
  "logger": "module.name",
  "message": "Error message",
  "module": "file.py",
  "function": "function_name",
  "line": 42,
  "thread": "MainThread",
  "exception": {
    "type": "ValueError",
    "message": "Error details",
    "traceback": "Full traceback..."
  },
  "extra": {
    "custom_field": "custom_value"
  }
}
```

## Testing

Comprehensive test suites are included:
- `tests/test_logger.py`: 8 tests for logging system
- `tests/test_error_handling.py`: 14 tests for error handling
- `tests/test_validation.py`: 21 tests for validation framework

Run tests:
```bash
python3 -m pytest tests/test_logger.py -v
python3 -m pytest tests/test_error_handling.py -v
python3 -m pytest tests/test_validation.py -v
```

## Examples

See `examples/error_handling_integration.py` for complete integration examples.

## Best Practices

1. **Always use structured logging**: Get a logger with `get_logger(__name__)` in each module
2. **Wrap risky operations**: Use `handle_errors()` or `@safe_operation()` for operations that might fail
3. **Validate early**: Check inputs before processing with `Validator` methods
4. **Log with context**: Add extra data to logs for better debugging
5. **Don't swallow exceptions**: Use `show_user=True` to notify users of errors
6. **Use retry for transient failures**: Network connections, hardware communication, etc.

## Integration Guidelines

- **Minimal changes**: Only integrate where error handling is weak or missing
- **Backward compatible**: Existing code continues to work
- **Optional usage**: Not required for all code, use where beneficial
- **Clear errors**: All error messages in Italian for user-facing errors

## Acceptance Criteria ✅

### Logging
- ✅ Logs written to ~/.blitz/logs/blitz.log
- ✅ Errors written to ~/.blitz/logs/errors.log
- ✅ Rotating works (10MB limit)
- ✅ JSON structure valid
- ✅ Console output human-readable

### Exception Handling
- ✅ Uncaught exceptions captured
- ✅ Dialog shown to user
- ✅ Exception logged with traceback
- ✅ Application continues to function

### Error Recovery
- ✅ Context manager works in try/except
- ✅ Decorator catches exceptions
- ✅ Retry mechanism functional
- ✅ User notification correct

### Validation
- ✅ Length validation works
- ✅ Angle validation works
- ✅ File path validation works
- ✅ Error messages clear

## Support

For questions or issues, refer to the inline documentation or check the examples directory.
