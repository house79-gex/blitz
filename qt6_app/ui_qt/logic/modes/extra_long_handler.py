"""
Extra Long Handler - Wrapper for Existing ultra_long_mode.py
File: qt6_app/ui_qt/logic/modes/extra_long_handler.py
Date: 2025-12-16
Author: house79-gex

Wrapper handler for "Extra Long" mode that uses the existing ultra_long_mode.py
implementation with dynamic parameters from configuration.

This module provides a consistent interface while delegating to the existing
calculate_ultra_long_sequence function.
"""
from dataclasses import dataclass
from typing import Optional, Any
import logging
from ..ultra_long_mode import (
    UltraLongConfig as BaseUltraLongConfig,
    UltraLongSequence,
    calculate_ultra_long_sequence
)

logger = logging.getLogger(__name__)


@dataclass
class ExtraLongConfig:
    """
    Wrapper configuration for extra long mode with dynamic parameters.
    
    All values should come from settings, NOT hardcoded!
    """
    max_travel_mm: float  # From settings: machine_max_travel_mm
    stock_length_mm: float  # From settings: stock_length_mm
    safe_head_mm: float = 2000.0  # Safe position for heading cut
    min_offset_mm: float = 500.0  # Minimum offset for safety
    
    @classmethod
    def from_settings(cls, settings: dict) -> "ExtraLongConfig":
        """Load configuration from settings dict."""
        return cls(
            max_travel_mm=float(settings.get("machine_max_travel_mm", 4000.0)),
            stock_length_mm=float(settings.get("stock_length_mm", 6500.0)),
            safe_head_mm=2000.0,  # Fixed standard value
            min_offset_mm=500.0  # Fixed standard value
        )
    
    def to_base_config(self) -> BaseUltraLongConfig:
        """
        Convert to base UltraLongConfig for ultra_long_mode.py.
        
        Returns:
            BaseUltraLongConfig instance compatible with existing code
        """
        return BaseUltraLongConfig(
            max_travel_mm=self.max_travel_mm,
            stock_length_mm=self.stock_length_mm,
            safe_head_mm=self.safe_head_mm,
            min_offset_mm=self.min_offset_mm
        )


class ExtraLongHandler:
    """
    Handler for extra long mode (3-step) - wrapper for ultra_long_mode.py.
    
    This handler provides a consistent interface while delegating to the existing
    ultra_long_mode implementation for backward compatibility.
    
    3-Step Sequence (from ultra_long_mode.py):
    1. Heading: Mobile head DX cuts at safe_head_mm
    2. Retract: Mobile head DX retracts by offset = piece_length - max_travel
    3. Final: Fixed head SX cuts at max_travel_mm
    
    Measurement: INSIDE mobile blade DX
    """
    
    def __init__(self, machine_io: Any, config: Optional[ExtraLongConfig] = None):
        """
        Initialize handler.
        
        Args:
            machine_io: Machine I/O adapter for controlling machine
            config: Configuration (uses defaults if None)
        """
        self.mio = machine_io
        self.config = config or ExtraLongConfig(
            max_travel_mm=4000.0,
            stock_length_mm=6500.0
        )
        self.sequence: Optional[UltraLongSequence] = None
        logger.info(
            f"ExtraLongHandler initialized: "
            f"max_travel={self.config.max_travel_mm:.0f}mm, "
            f"stock={self.config.stock_length_mm:.0f}mm"
        )
    
    def start_sequence(
        self,
        target_length_mm: float,
        angle_sx: float,
        angle_dx: float
    ) -> bool:
        """
        Start extra long cutting sequence.
        
        Args:
            target_length_mm: Target piece length
            angle_sx: Angle for fixed head SX
            angle_dx: Angle for mobile head DX
        
        Returns:
            True if sequence started successfully, False otherwise
        """
        # Use existing calculate_ultra_long_sequence from ultra_long_mode.py
        base_config = self.config.to_base_config()
        
        self.sequence = calculate_ultra_long_sequence(
            target_length_mm=target_length_mm,
            angle_sx=angle_sx,
            angle_dx=angle_dx,
            config=base_config
        )
        
        if not self.sequence:
            logger.error(
                f"Failed to create extra long sequence for {target_length_mm:.1f}mm. "
                f"Check if piece length is valid."
            )
            return False
        
        logger.info(f"Extra Long sequence started:")
        logger.info(f"  Target length: {target_length_mm:.1f}mm")
        logger.info(f"  Step 1 - Heading: Mobile DX @ {self.sequence.pos_head_cut_dx:.0f}mm, {angle_dx:.1f}°")
        logger.info(f"  Step 2 - Retract: DX by {self.sequence.offset_mm:.0f}mm")
        logger.info(f"  Step 3 - Final: Fixed SX @ {self.sequence.pos_final_cut_dx:.0f}mm, {angle_sx:.1f}°")
        logger.info(f"  Measurement: INSIDE mobile blade DX")
        
        return True
    
    def execute_step_1(self) -> bool:
        """
        Execute Step 1: Heading with mobile head DX.
        
        Actions:
        1. Set blade inhibits: Left=True, Right=False (Right blade DX enabled)
        2. Set morse: Both locked
        3. Move to heading position (pos_head_cut_dx)
        4. Lock brake
        
        Returns:
            True if step executed successfully
        """
        if not self.sequence or not self.sequence.enabled:
            logger.error("No active sequence")
            return False
        
        if self.sequence.current_step != 0:
            logger.warning(f"Step 1 called but current_step={self.sequence.current_step}")
        
        logger.info("Executing Extra Long Step 1: Heading with mobile head DX")
        
        # Set blade inhibits (Right blade enabled for DX heading)
        if hasattr(self.mio, "set_blade_inhibits"):
            self.mio.set_blade_inhibits(
                left=self.sequence.blade_left_inhibit,
                right=not self.sequence.blade_right_enable
            )
        else:
            logger.warning("Machine I/O does not support set_blade_inhibits")
        
        # Set morse (both locked)
        if hasattr(self.mio, "set_morse"):
            self.mio.set_morse(
                left_locked=self.sequence.presser_left_lock,
                right_locked=self.sequence.presser_right_lock
            )
        else:
            logger.warning("Machine I/O does not support set_morse")
        
        # Move to heading position
        if hasattr(self.mio, "command_move"):
            success = self.mio.command_move(
                length_mm=self.sequence.pos_head_cut_dx,
                angle_sx=self.sequence.angle_final_cut_sx,  # Keep SX angle
                angle_dx=self.sequence.angle_head_cut_dx,
                profile="default",
                element="extra_long_heading"
            )
            if not success:
                logger.error("Failed to start heading movement")
                return False
        else:
            logger.warning("Machine I/O does not support command_move")
        
        # Lock brake
        if hasattr(self.mio, "command_lock_brake"):
            self.mio.command_lock_brake()
        
        self.sequence.current_step = 1
        logger.info("Step 1 (Heading) completed")
        return True
    
    def execute_step_2(self) -> bool:
        """
        Execute Step 2: Retract mobile head DX.
        
        Actions:
        1. Set morse: Left locked, Right released (DX pulls material)
        2. Move DX back by offset_mm
        
        Returns:
            True if step executed successfully
        """
        if not self.sequence or not self.sequence.enabled:
            logger.error("No active sequence")
            return False
        
        if self.sequence.current_step != 1:
            logger.warning(f"Step 2 called but current_step={self.sequence.current_step}")
        
        logger.info("Executing Extra Long Step 2: Retract mobile head DX")
        
        # Set morse (left locked, right released)
        if hasattr(self.mio, "set_morse"):
            self.mio.set_morse(
                left_locked=self.sequence.presser_left_lock_step2,
                right_locked=not self.sequence.presser_right_release_step2
            )
        else:
            logger.warning("Machine I/O does not support set_morse")
        
        # Move to position after retract
        if hasattr(self.mio, "command_move"):
            success = self.mio.command_move(
                length_mm=self.sequence.pos_after_retract_dx,
                angle_sx=self.sequence.angle_final_cut_sx,
                angle_dx=self.sequence.angle_head_cut_dx,
                profile="default",
                element="extra_long_retract"
            )
            if not success:
                logger.error("Failed to start retract movement")
                return False
        else:
            logger.warning("Machine I/O does not support command_move")
        
        self.sequence.current_step = 2
        logger.info(f"Step 2 (Retract) completed: moved to {self.sequence.pos_after_retract_dx:.1f}mm")
        return True
    
    def execute_step_3(self) -> bool:
        """
        Execute Step 3: Final cut with fixed head SX.
        
        Actions:
        1. Set blade inhibits: Left=False, Right=True (Left blade SX enabled)
        2. Set morse: Right locked first, then left released (non-simultaneous)
        3. Move to final position (pos_final_cut_dx)
        
        Returns:
            True if step executed successfully
        """
        if not self.sequence or not self.sequence.enabled:
            logger.error("No active sequence")
            return False
        
        if self.sequence.current_step != 2:
            logger.warning(f"Step 3 called but current_step={self.sequence.current_step}")
        
        logger.info("Executing Extra Long Step 3: Final cut with fixed head SX")
        
        # Set blade inhibits (Left blade enabled for SX final cut)
        if hasattr(self.mio, "set_blade_inhibits"):
            self.mio.set_blade_inhibits(
                left=not self.sequence.blade_left_enable,
                right=self.sequence.blade_right_inhibit_step3
            )
        else:
            logger.warning("Machine I/O does not support set_blade_inhibits")
        
        # Set morse: Right locked first
        if hasattr(self.mio, "set_morse"):
            self.mio.set_morse(
                left_locked=True,  # Keep left locked initially
                right_locked=self.sequence.presser_right_lock_step3
            )
        else:
            logger.warning("Machine I/O does not support set_morse")
        
        # Brief delay before releasing left
        import time
        time.sleep(0.1)
        
        # Now release left
        if hasattr(self.mio, "set_morse"):
            self.mio.set_morse(
                left_locked=not self.sequence.presser_left_release_step3,
                right_locked=self.sequence.presser_right_lock_step3
            )
        
        # Move to final position
        if hasattr(self.mio, "command_move"):
            success = self.mio.command_move(
                length_mm=self.sequence.pos_final_cut_dx,
                angle_sx=self.sequence.angle_final_cut_sx,
                angle_dx=self.sequence.angle_head_cut_dx,
                profile="default",
                element="extra_long_final"
            )
            if not success:
                logger.error("Failed to start final movement")
                return False
        else:
            logger.warning("Machine I/O does not support command_move")
        
        self.sequence.current_step = 3
        logger.info("Step 3 (Final Cut) completed")
        return True
    
    def get_current_step(self) -> int:
        """
        Get current step number.
        
        Returns:
            0=idle, 1=heading, 2=retract, 3=final, 4=complete
        """
        if self.sequence:
            return self.sequence.current_step
        return 0
    
    def reset(self):
        """Reset handler to initial state."""
        logger.info("Resetting Extra Long handler")
        self.sequence = None
    
    def get_step_description(self) -> str:
        """Get description of current step."""
        if not self.sequence:
            return "No active sequence"
        
        from ..ultra_long_mode import get_step_description
        return get_step_description(self.sequence)


__all__ = ["ExtraLongHandler", "ExtraLongConfig"]
