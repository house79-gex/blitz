"""
Example integration of production-grade error handling and logging.

This file demonstrates how to use the new utilities in your code.
DO NOT modify existing working code unless absolutely necessary.
"""

from qt6_app.ui_qt.utils.logger import get_logger
from qt6_app.ui_qt.utils.error_handling import handle_errors, safe_operation, ErrorRecovery
from qt6_app.ui_qt.utils.validation import Validator

# Get logger for your module
logger = get_logger(__name__)


# Example 1: Using context manager for error handling
def example_load_profiles():
    """Example of loading profiles with error handling."""
    logger.info("Loading profiles...")
    
    with handle_errors("Caricamento profili", show_user=True):
        # Your code that might fail
        profiles = load_profiles_from_disk()
        process_profiles(profiles)
    
    logger.info("Profiles loaded successfully")


# Example 2: Using decorator for safe operations
@safe_operation("Salvataggio configurazione", show_user=True, default_return=False)
def example_save_config(config_data):
    """Example of saving configuration with error handling."""
    logger.info("Saving configuration...")
    
    # Validate first
    if not config_data:
        raise ValueError("Configuration data is empty")
    
    # Save to file
    with open('/path/to/config.json', 'w') as f:
        import json
        json.dump(config_data, f)
    
    return True


# Example 3: Input validation before processing
def example_validate_and_cut(length_mm, angle_sx, angle_dx):
    """Example of validating inputs before cutting."""
    logger.info(f"Validating cut parameters: length={length_mm}, angles=({angle_sx}, {angle_dx})")
    
    # Validate length
    validation = Validator.validate_length(
        length_mm,
        min_mm=250.0,  # Machine minimum
        max_mm=4000.0,  # Machine maximum
        field_name="lunghezza taglio"
    )
    
    if not validation.is_valid:
        error_msg = '\n'.join(validation.get_error_messages())
        logger.warning(f"Validation failed: {error_msg}")
        # Show error to user (via existing UI methods)
        return False
    
    # Validate angles
    for angle, name in [(angle_sx, "sinistro"), (angle_dx, "destro")]:
        angle_validation = Validator.validate_angle(
            angle,
            valid_angles=[0, 15, 22, 30, 45, 90],
            field_name=f"angolo {name}"
        )
        
        if not angle_validation.is_valid:
            error_msg = '\n'.join(angle_validation.get_error_messages())
            logger.warning(f"Angle validation failed: {error_msg}")
            return False
    
    # All validations passed - proceed with cut
    logger.info("All validations passed - proceeding with cut")
    with handle_errors("Esecuzione taglio", show_user=True):
        perform_cut(length_mm, angle_sx, angle_dx)
    
    return True


# Example 4: Retry mechanism for unreliable operations
def example_connect_to_device():
    """Example of connecting to a device with retry."""
    logger.info("Attempting to connect to device...")
    
    def _connect():
        # Your connection logic here
        return connect_to_hardware()
    
    result = ErrorRecovery.retry_operation(
        _connect,
        max_retries=3,
        delay_seconds=1.0,
        backoff_factor=2.0
    )
    
    if result:
        logger.info("Successfully connected to device")
        return True
    else:
        logger.error("Failed to connect after retries")
        return False


# Example 5: Integration in existing semi_auto_page.py pattern
class ExampleSemiAutoIntegration:
    """
    Example showing how to integrate into semi_auto_page.py.
    
    IMPORTANT: This is just a demonstration pattern.
    Only integrate if specifically requested.
    """
    
    def __init__(self):
        self.logger = get_logger(f"{__name__}.SemiAutoPage")
    
    @safe_operation("Avvio ciclo taglio", show_user=True)
    def _on_start(self):
        """Start cutting cycle with error handling."""
        
        # Get values from UI
        length = self.spin_length.value()
        angle_sx = self.combo_sx.currentData()
        angle_dx = self.combo_dx.currentData()
        
        # Validate inputs
        length_validation = Validator.validate_length(
            length,
            min_mm=self._mode_config.ultra_short_threshold,
            max_mm=self._mode_config.machine_max_travel_mm,
            field_name="lunghezza"
        )
        
        if not length_validation.is_valid:
            self._show_warn('\n'.join(length_validation.get_error_messages()))
            return
        
        # Proceed with operation
        with handle_errors("Posizionamento asse", show_user=True):
            self.mio.command_move(length)
        
        with handle_errors("Impostazione angoli", show_user=True):
            self.mio.command_set_head_angles(angle_sx, angle_dx)


# Placeholder functions for demonstration
def load_profiles_from_disk():
    """Placeholder function."""
    return []

def process_profiles(profiles):
    """Placeholder function."""
    pass

def perform_cut(length, angle_sx, angle_dx):
    """Placeholder function."""
    pass

def connect_to_hardware():
    """Placeholder function."""
    return True


if __name__ == "__main__":
    # Quick test of examples
    from qt6_app.ui_qt.utils.logger import setup_logging
    import tempfile
    from pathlib import Path
    
    tmpdir = Path(tempfile.mkdtemp())
    setup_logging(log_dir=tmpdir / 'example_logs')
    
    print("=== Example 1: Load profiles ===")
    example_load_profiles()
    
    print("\n=== Example 2: Save config ===")
    result = example_save_config({"key": "value"})
    print(f"Save result: {result}")
    
    print("\n=== Example 3: Validate and cut ===")
    example_validate_and_cut(500.0, 45, 30)
    example_validate_and_cut(50.0, 45, 30)  # Should fail validation
    
    print("\n=== Example 4: Connect with retry ===")
    example_connect_to_device()
    
    print("\n=== All examples completed ===")
