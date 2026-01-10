"""
Unit tests for error handling utilities.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from qt6_app.ui_qt.utils.error_handling import (
    handle_errors,
    safe_operation,
    ErrorRecovery,
    _show_error_dialog
)


def test_handle_errors_context_manager_success():
    """Test handle_errors context manager with successful operation."""
    operation_called = False
    
    with handle_errors("Test operation", show_user=False):
        operation_called = True
        result = 1 + 1
    
    assert operation_called
    assert result == 2


def test_handle_errors_context_manager_catches_exception():
    """Test handle_errors context manager catches exceptions."""
    with patch('qt6_app.ui_qt.utils.error_handling.logger') as mock_logger:
        exception_caught = False
        
        try:
            with handle_errors("Test operation", show_user=False):
                raise ValueError("Test error")
        except ValueError:
            exception_caught = True
        
        # Exception should be caught, not raised
        assert not exception_caught
        
        # Logger should have been called
        assert mock_logger.error.called or mock_logger.critical.called


def test_handle_errors_logs_critical():
    """Test handle_errors logs critical errors."""
    with patch('qt6_app.ui_qt.utils.error_handling.logger') as mock_logger:
        with handle_errors("Test operation", show_user=False, critical=True):
            raise RuntimeError("Critical error")
        
        # Should call critical, not error
        assert mock_logger.critical.called
        call_args = mock_logger.critical.call_args
        assert "Critical error" in str(call_args)


def test_safe_operation_decorator_success():
    """Test safe_operation decorator with successful function."""
    @safe_operation("Test operation", show_user=False)
    def successful_function(x, y):
        return x + y
    
    result = successful_function(5, 3)
    assert result == 8


def test_safe_operation_decorator_catches_exception():
    """Test safe_operation decorator catches exceptions."""
    @safe_operation("Test operation", show_user=False, default_return=None)
    def failing_function():
        raise ValueError("Function failed")
    
    result = failing_function()
    assert result is None


def test_safe_operation_decorator_with_default_return():
    """Test safe_operation decorator returns default value on error."""
    @safe_operation("Test operation", show_user=False, default_return=42)
    def failing_function():
        raise ValueError("Function failed")
    
    result = failing_function()
    assert result == 42


def test_safe_operation_decorator_reraise():
    """Test safe_operation decorator can reraise exceptions."""
    @safe_operation("Test operation", show_user=False, reraise=True)
    def failing_function():
        raise ValueError("Function failed")
    
    with pytest.raises(ValueError, match="Function failed"):
        failing_function()


def test_safe_operation_preserves_function_metadata():
    """Test safe_operation decorator preserves function metadata."""
    @safe_operation("Test operation", show_user=False)
    def documented_function():
        """This is a documented function."""
        return True
    
    assert documented_function.__name__ == "documented_function"
    assert documented_function.__doc__ == "This is a documented function."


def test_error_recovery_retry_success_first_try():
    """Test ErrorRecovery.retry_operation succeeds on first try."""
    call_count = [0]
    
    def operation():
        call_count[0] += 1
        return "success"
    
    result = ErrorRecovery.retry_operation(operation, max_retries=3)
    
    assert result == "success"
    assert call_count[0] == 1


def test_error_recovery_retry_success_after_failures():
    """Test ErrorRecovery.retry_operation succeeds after some failures."""
    call_count = [0]
    
    def operation():
        call_count[0] += 1
        if call_count[0] < 3:
            raise ValueError("Not yet")
        return "success"
    
    with patch('qt6_app.ui_qt.utils.error_handling.logger'):
        result = ErrorRecovery.retry_operation(
            operation, 
            max_retries=3,
            delay_seconds=0.01  # Short delay for testing
        )
    
    assert result == "success"
    assert call_count[0] == 3


def test_error_recovery_retry_exhausts_retries():
    """Test ErrorRecovery.retry_operation returns None after exhausting retries."""
    call_count = [0]
    
    def operation():
        call_count[0] += 1
        raise ValueError("Always fails")
    
    with patch('qt6_app.ui_qt.utils.error_handling.logger'):
        result = ErrorRecovery.retry_operation(
            operation,
            max_retries=3,
            delay_seconds=0.01
        )
    
    assert result is None
    assert call_count[0] == 3


def test_error_recovery_retry_exponential_backoff():
    """Test ErrorRecovery.retry_operation uses exponential backoff."""
    import time
    
    call_times = []
    
    def operation():
        call_times.append(time.time())
        raise ValueError("Always fails")
    
    with patch('qt6_app.ui_qt.utils.error_handling.logger'):
        ErrorRecovery.retry_operation(
            operation,
            max_retries=3,
            delay_seconds=0.1,
            backoff_factor=2.0
        )
    
    # Check that delays increase
    assert len(call_times) == 3
    
    # First to second should be ~0.1s
    # Second to third should be ~0.2s
    if len(call_times) >= 3:
        delay1 = call_times[1] - call_times[0]
        delay2 = call_times[2] - call_times[1]
        
        # Allow some tolerance
        assert 0.05 < delay1 < 0.2
        assert 0.15 < delay2 < 0.4


def test_show_error_dialog_fallback_to_messagebox():
    """Test _show_error_dialog falls back to QMessageBox when Toast fails."""
    with patch('qt6_app.ui_qt.utils.error_handling.QMessageBox') as mock_msgbox:
        # Mock the message box
        mock_msg_instance = MagicMock()
        mock_msgbox.return_value = mock_msg_instance
        
        exception = ValueError("Test error")
        _show_error_dialog("Test operation", exception, critical=False)
        
        # Should have created a message box
        assert mock_msgbox.called
        assert mock_msg_instance.setText.called
        assert mock_msg_instance.exec.called


def test_handle_errors_with_extra_data():
    """Test handle_errors includes extra data in logs."""
    with patch('qt6_app.ui_qt.utils.error_handling.logger') as mock_logger:
        with handle_errors("Test operation", show_user=False):
            raise ValueError("Test error")
        
        # Check that extra data was included
        call_args = mock_logger.error.call_args
        assert call_args is not None
        assert 'extra' in call_args[1]
        assert 'extra_data' in call_args[1]['extra']
