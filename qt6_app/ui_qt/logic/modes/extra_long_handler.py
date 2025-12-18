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
from typing import Optional, Any, Callable
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
        self.on_step_complete = None
        logger.info(
            f"ExtraLongHandler initialized: "
            f"max_travel={self.config.max_travel_mm:.0f}mm, "
            f"stock={self.config.stock_length_mm:.0f}mm"
        )
    
    def start_sequence(
        self,
        target_length_mm: float,
        angle_sx: float,
        angle_dx: float,
        on_step_complete=None
    ) -> bool:
        """
        Start extra long cutting sequence.
        
        Args:
            target_length_mm: Target piece length
            angle_sx: Angle for fixed head SX
            angle_dx: Angle for mobile head DX
            on_step_complete: Optional callback function called after each step completes.
                            Signature: (step_number: int, description: str) -> None
        
        Returns:
            True if sequence started successfully, False otherwise
        """
        self.on_step_complete = on_step_complete
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
    
    def _invoke_step_callback(self, step_number: int, description: str):
        """
        Invoke step completion callback if provided.
        
        Args:
            step_number: Current step number
            description: Step description
        """
        if self.on_step_complete:
            self.on_step_complete(step_number, description)
    
    def execute_step_1(self) -> bool:
        """
        Execute Step 1: Heading with mobile head DX.
        
        Actions:
        1. Apply angles FIRST
        2. Configure morse (both locked)
        3. Start movement to heading position
        
        Returns:
            True if step executed successfully
        """
        if not self.sequence or not self.sequence.enabled:
            logger.error("No active sequence")
            return False
        
        if self.sequence.current_step != 0:
            logger.warning(f"Step 1 called but current_step={self.sequence.current_step}")
        
        logger.info("Executing Extra Long Step 1: Heading with mobile head DX")
        
        try:
            # 1. Apply angles FIRST
            self.mio.command_set_head_angles(
                sx=90.0,  # Fixed head not used yet
                dx=self.sequence.angle_head_cut_dx
            )
            
            # 2. Configure morse for heading
            self.mio.command_set_morse(
                left_locked=self.sequence.presser_left_lock,
                right_locked=self.sequence.presser_right_lock
            )
            
            # 3. Start movement
            success = self.mio.command_move(
                self.sequence.pos_head_cut_dx,
                ang_sx=90.0,
                ang_dx=self.sequence.angle_head_cut_dx
            )
            
            if success:
                self.sequence.current_step = 1
                logger.info(f"Extra long step 1: heading @ {self.sequence.pos_head_cut_dx:.1f}mm")
            
            return success
        except Exception as e:
            logger.error(f"Error executing step 1: {e}")
            return False
    
    def execute_step_2(self) -> bool:
        """
        Execute Step 2: Retract mobile head DX.
        
        Actions:
        1. Release brake to allow movement
        2. Configure morse (left locked, right released)
        3. Move DX back by offset_mm
        
        Returns:
            True if step executed successfully
        """
        if not self.sequence or not self.sequence.enabled:
            logger.error("No active sequence")
            return False
        
        if self.sequence.current_step != 1:
            logger.warning(f"Step 2 called but current_step={self.sequence.current_step}")
        
        logger.info("Executing Extra Long Step 2: Retract mobile head DX")
        
        try:
            # 1. Release brake to allow movement
            self.mio.command_release_brake()
            
            # 2. Configure morse for retract
            self.mio.command_set_morse(
                left_locked=self.sequence.presser_left_lock_step2,
                right_locked=not self.sequence.presser_right_release_step2
            )
            
            # 3. Move to position after retract
            success = self.mio.command_move(
                self.sequence.pos_after_retract_dx,
                ang_sx=90.0,
                ang_dx=self.sequence.angle_head_cut_dx
            )
            
            if success:
                self.sequence.current_step = 2
                logger.info(f"Extra long step 2: retract to {self.sequence.pos_after_retract_dx:.1f}mm")
            
            return success
        except Exception as e:
            logger.error(f"Error executing step 2: {e}")
            return False
    
    def execute_step_3(self) -> bool:
        """
        Execute Step 3: Final cut with fixed head SX.
        
        Actions:
        1. Apply angles for final cut
        2. Release brake to allow movement
        3. Configure morse for final cut
        4. Move to final position
        
        Returns:
            True if step executed successfully
        """
        if not self.sequence or not self.sequence.enabled:
            logger.error("No active sequence")
            return False
        
        if self.sequence.current_step != 2:
            logger.warning(f"Step 3 called but current_step={self.sequence.current_step}")
        
        logger.info("Executing Extra Long Step 3: Final cut with fixed head SX")
        
        try:
            # 1. Apply angles for final cut
            self.mio.command_set_head_angles(
                sx=self.sequence.angle_final_cut_sx,
                dx=90.0  # Mobile head not used
            )
            
            # 2. Release brake to allow movement
            self.mio.command_release_brake()
            
            # 3. Configure morse for final cut
            self.mio.command_set_morse(
                left_locked=not self.sequence.presser_left_release_step3,
                right_locked=self.sequence.presser_right_lock_step3
            )
            
            # 4. Move to final position
            success = self.mio.command_move(
                self.sequence.pos_final_cut_dx,
                ang_sx=self.sequence.angle_final_cut_sx,
                ang_dx=90.0
            )
            
            if success:
                self.sequence.current_step = 3
                logger.info(f"Extra long step 3: final @ {self.sequence.pos_final_cut_dx:.1f}mm")
            
            return success
        except Exception as e:
            logger.error(f"Error executing step 3: {e}")
            return False
    
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
