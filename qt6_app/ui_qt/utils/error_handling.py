"""
Error handling utilities for Blitz CNC.

Provides:
- Context managers for operation error handling
- Decorators for function error handling
- Validation helpers
- Error recovery strategies
"""

from contextlib import contextmanager
from functools import wraps
import logging
from typing import Optional, Callable, Any

logger = logging.getLogger(__name__)


@contextmanager
def handle_errors(
    operation_name: str,
    show_user: bool = True,
    critical: bool = False,
    default_return: Any = None
):
    """
    Context manager for consistent error handling.
    
    Usage:
        with handle_errors("Caricamento profili", show_user=True):
            profiles = load_profiles()
            process_profiles(profiles)
    
    Args:
        operation_name: Human-readable operation description
        show_user: Show error message to user
        critical: Mark error as critical (show in critical log)
        default_return: Value to return on error (if used in assignment)
    """
    try:
        yield
    except Exception as e:
        # Log error with context
        log_method = logger.critical if critical else logger.error
        log_method(
            f"Error in {operation_name}: {e}",
            exc_info=True,
            extra={'extra_data': {
                'operation': operation_name,
                'critical': critical
            }}
        )
        
        # Show user notification if requested
        if show_user:
            _show_error_dialog(operation_name, e, critical)


def safe_operation(
    operation_name: str,
    show_user: bool = True,
    default_return: Any = None,
    reraise: bool = False
):
    """
    Decorator for safe operation execution.
    
    Usage:
        @safe_operation("Salvataggio configurazione", show_user=True)
        def save_config(config):
            with open('config.json', 'w') as f:
                json.dump(config, f)
    
    Args:
        operation_name: Human-readable operation description
        show_user: Show error to user on failure
        default_return: Value to return on error
        reraise: Re-raise exception after logging
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(
                    f"Error in {operation_name} ({func.__name__}): {e}",
                    exc_info=True
                )
                
                if show_user:
                    _show_error_dialog(operation_name, e)
                
                if reraise:
                    raise
                
                return default_return
        
        return wrapper
    return decorator


def _show_error_dialog(operation: str, exception: Exception, critical: bool = False):
    """Show error dialog to user"""
    try:
        from qt6_app.ui_qt.widgets.toast import Toast
        
        # Try toast first (non-blocking)
        Toast.show(
            f"Errore: {operation}\n{str(exception)[:100]}",
            "error" if not critical else "critical",
            duration=5000 if not critical else 10000
        )
    except Exception:
        # Fallback to message box
        try:
            from PySide6.QtWidgets import QMessageBox
            
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical if critical else QMessageBox.Warning)
            msg.setWindowTitle("Errore" if not critical else "Errore Critico")
            msg.setText(f"Errore durante: {operation}")
            msg.setInformativeText(str(exception))
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec()
        except Exception:
            # If both fail, just log it
            logger.error(f"Could not show error dialog: {operation} - {exception}")


class ErrorRecovery:
    """Error recovery strategies"""
    
    @staticmethod
    def retry_operation(
        func: Callable,
        max_retries: int = 3,
        delay_seconds: float = 1.0,
        backoff_factor: float = 2.0
    ) -> Optional[Any]:
        """
        Retry operation with exponential backoff.
        
        Args:
            func: Function to retry
            max_retries: Maximum retry attempts
            delay_seconds: Initial delay between retries
            backoff_factor: Delay multiplier for each retry
        
        Returns:
            Function result or None on failure
        """
        import time
        
        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = delay_seconds * (backoff_factor ** attempt)
                    logger.warning(
                        f"Operation failed (attempt {attempt + 1}/{max_retries}), "
                        f"retrying in {wait_time:.1f}s: {e}"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        f"Operation failed after {max_retries} attempts: {e}",
                        exc_info=True
                    )
                    return None
