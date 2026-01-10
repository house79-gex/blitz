"""
Mock machine objects for testing without hardware.

Provides realistic simulation of machine behavior for UI tests.
"""

import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class MockMachine:
    """
    Mock machine for testing.
    
    Simulates machine state and behavior without hardware.
    """
    
    def __init__(self):
        # State
        self.emergency_active = False
        self.homed = False
        self.machine_homed = False  # Alias for compatibility
        self.brake_active = True
        self.clutch_active = True
        self.encoder_position = 250.0
        self._positioning_active = False
        self._positioning_callback = None
        
        # Morse/heads
        self.left_morse_locked = False
        self.right_morse_locked = False
        self.left_blade_inhibit = False
        self.right_blade_inhibit = False
        
        # Angles
        self.left_head_angle = 90
        self.right_head_angle = 90
        
        logger.info("MockMachine initialized")
    
    def get_position(self) -> Optional[float]:
        """Get current position in mm."""
        return self.encoder_position
    
    def is_positioning_active(self) -> bool:
        """Check if positioning is active."""
        return self._positioning_active
    
    def move_to(self, position_mm: float, callback=None):
        """Simulate movement to position."""
        logger.info(f"MockMachine: Moving to {position_mm}mm")
        self.encoder_position = position_mm
        self._positioning_active = True
        self._positioning_callback = callback
        
        # Simulate instant completion (for testing)
        self._positioning_active = False
        if callback:
            callback()
    
    def command_move(self, length_mm: float, ang_sx: float = 0.0, ang_dx: float = 0.0,
                     profile: str = "", element: str = "") -> bool:
        """Simulate move command."""
        logger.info(f"MockMachine: command_move to {length_mm}mm")
        self.encoder_position = length_mm
        self.left_head_angle = ang_sx
        self.right_head_angle = ang_dx
        return True
    
    def do_homing(self, callback=None):
        """Simulate homing sequence."""
        logger.info("MockMachine: Homing")
        self.encoder_position = 250.0
        self.homed = True
        self.machine_homed = True
        if callback:
            callback()
    
    def reset(self):
        """Reset machine state."""
        logger.info("MockMachine: Reset")
        self.emergency_active = False
        self.brake_active = True
        self.clutch_active = True
        self._positioning_active = False
    
    def get_state(self) -> Dict[str, Any]:
        """Get machine state dict."""
        return {
            'emergency_active': self.emergency_active,
            'homed': self.homed,
            'machine_homed': self.machine_homed,
            'brake_active': self.brake_active,
            'clutch_active': self.clutch_active,
            'position_mm': self.encoder_position,
            'positioning_active': self._positioning_active,
            'left_morse_locked': self.left_morse_locked,
            'right_morse_locked': self.right_morse_locked,
            'left_blade_inhibit': self.left_blade_inhibit,
            'right_blade_inhibit': self.right_blade_inhibit,
        }
    
    def tick(self):
        """Tick simulation (called periodically)."""
        pass
    
    def close(self):
        """Cleanup."""
        pass
    
    def cleanup(self):
        """Alias for close."""
        self.close()


class MockMachineAdapter:
    """Mock machine adapter."""
    
    def __init__(self):
        self._machine = MockMachine()
    
    def get_position(self):
        return self._machine.get_position()
    
    def is_positioning_active(self):
        return self._machine.is_positioning_active()
    
    def get_state(self):
        return self._machine.get_state()
    
    def command_move(self, position_mm: float, callback=None):
        self._machine.move_to(position_mm, callback)
        return True
    
    def command_lock_brake(self):
        self._machine.brake_active = True
        return True
    
    def command_release_brake(self):
        self._machine.brake_active = False
        return True
    
    def command_set_clutch(self, active: bool):
        self._machine.clutch_active = active
        return True
    
    def command_set_head_angles(self, sx: int, dx: int):
        self._machine.left_head_angle = sx
        self._machine.right_head_angle = dx
        return True
    
    def command_set_morse(self, left: bool, right: bool):
        self._machine.left_morse_locked = left
        self._machine.right_morse_locked = right
        return True
    
    def do_homing(self, callback=None):
        self._machine.do_homing(callback)
    
    def reset_machine(self):
        self._machine.reset()
