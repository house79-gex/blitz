"""
Ultra Short Handler - 3-Step Sequence for Very Short Pieces
File: qt6_app/ui_qt/logic/modes/ultra_short_handler.py
Date: 2025-12-16
Author: house79-gex

Handler for "Ultra Short" mode for pieces <= (zero_homing - offset_battuta).

Key Difference from Extra Long:
- Extra Long: Heading DX → Final SX (measurement INSIDE mobile blade)
- Ultra Short: Heading SX → Final DX (measurement OUTSIDE mobile blade) - INVERTED!

3-Step Sequence:
1. Heading: Fixed head SX cuts at zero_homing + safety_margin
   - Blades: Left enabled, Right inhibited
   - Morse: Both locked
2. Retract: Mobile head DX retracts by offset = piece_length + offset_battuta
   - Morse: Left locked, Right released (DX pulls material)
3. Final: Mobile head DX cuts at heading_position - offset
   - Blades: Left inhibited, Right enabled
   - Morse: Left released, Right locked
"""
from dataclasses import dataclass
from typing import Optional, Any, Dict, Callable
import logging

logger = logging.getLogger(__name__)


@dataclass
class UltraShortConfig:
    """
    Configuration for ultra short mode.
    
    All values should come from settings, NOT hardcoded!
    """
    zero_homing_mm: float = 250.0  # From settings: machine_zero_homing_mm
    offset_battuta_mm: float = 120.0  # From settings: machine_offset_battuta_mm
    safety_margin_mm: float = 50.0  # Safety margin for heading position
    
    @classmethod
    def from_settings(cls, settings: dict) -> "UltraShortConfig":
        """Load configuration from settings dict."""
        return cls(
            zero_homing_mm=float(settings.get("machine_zero_homing_mm", 250.0)),
            offset_battuta_mm=float(settings.get("machine_offset_battuta_mm", 120.0)),
            safety_margin_mm=50.0  # Fixed standard value
        )
    
    @property
    def ultra_short_threshold(self) -> float:
        """Calculate ultra short threshold."""
        return self.zero_homing_mm - self.offset_battuta_mm


@dataclass
class UltraShortSequence:
    """
    3-step sequence for ultra short mode.
    
    Step 1 - Heading:
    - Fixed head SX cuts at zero_homing + safety_margin
    - Blades: Left enabled, Right inhibited
    - Morse: Both locked
    
    Step 2 - Retract:
    - Mobile head DX retracts by offset = piece_length + offset_battuta
    - Morse: Left locked, Right released (DX pulls material)
    
    Step 3 - Final:
    - Mobile head DX cuts at heading_position - offset
    - Blades: Left inhibited, Right enabled
    - Morse: Left released, Right locked
    
    Measurement: OUTSIDE mobile blade DX
    """
    # Required fields (no defaults)
    enabled: bool
    target_length_mm: float
    angle_sx: float
    angle_dx: float
    heading_position: float  # zero_homing + safety_margin
    heading_angle_sx: float  # Angle for fixed head SX
    retract_offset: float  # Offset = piece_length + offset_battuta
    final_position: float  # heading_position - retract_offset
    final_angle_dx: float  # Angle for mobile head DX
    
    # Optional fields with defaults (Step 1: Heading)
    heading_blade_left_enable: bool = True  # ✅ Left blade enabled
    heading_blade_right_inhibit: bool = True  # ❌ Right blade inhibited
    heading_morse_left_lock: bool = True  # ✅ Left morse locked
    heading_morse_right_lock: bool = True  # ✅ Right morse locked
    
    # Optional fields with defaults (Step 2: Retract)
    retract_morse_left_lock: bool = True  # ✅ Left morse locked
    retract_morse_right_release: bool = True  # ❌ Right morse released
    
    # Optional fields with defaults (Step 3: Final)
    final_blade_left_inhibit: bool = True  # ❌ Left blade inhibited
    final_blade_right_enable: bool = True  # ✅ Right blade enabled
    final_morse_left_release: bool = True  # ❌ Left morse released
    final_morse_right_lock: bool = True  # ✅ Right morse locked
    
    # Optional fields with defaults (Tracking)
    measurement_outside: bool = True  # Measurement OUTSIDE mobile blade DX
    current_step: int = 0  # 0=idle, 1=heading, 2=retract, 3=final, 4=complete


class UltraShortHandler:
    """
    Handler for ultra short mode execution (3-step).
    
    Manages 3-step sequence for cutting very short pieces with inverted head configuration.
    """
    
    def __init__(self, machine_io: Any, config: Optional[UltraShortConfig] = None):
        """
        Initialize handler.
        
        Args:
            machine_io: Machine I/O adapter for controlling machine
            config: Configuration (uses defaults if None)
        """
        self.mio = machine_io
        self.config = config or UltraShortConfig()
        self.sequence: Optional[UltraShortSequence] = None
        self.on_step_complete = None
        logger.info(
            f"UltraShortHandler initialized: "
            f"zero={self.config.zero_homing_mm:.0f}mm, "
            f"offset={self.config.offset_battuta_mm:.0f}mm, "
            f"threshold={self.config.ultra_short_threshold:.0f}mm"
        )
    
    def start_sequence(
        self,
        target_length_mm: float,
        angle_sx: float,
        angle_dx: float,
        on_step_complete=None
    ) -> bool:
        """
        Start ultra short cutting sequence.
        
        Args:
            target_length_mm: Target piece length
            angle_sx: Angle for fixed head SX
            angle_dx: Angle for mobile head DX
            on_step_complete: Optional callback function called after each step completes.
                            Signature: (step_number: int, description: str) -> None
        
        Returns:
            True if sequence started successfully
        """
        self.on_step_complete = on_step_complete
        # Validate length
        if target_length_mm > self.config.ultra_short_threshold:
            logger.error(
                f"Piece length {target_length_mm:.1f}mm > threshold "
                f"{self.config.ultra_short_threshold:.0f}mm. Use different mode."
            )
            return False
        
        # Calculate positions
        heading_position = self.config.zero_homing_mm + self.config.safety_margin_mm
        retract_offset = target_length_mm + self.config.offset_battuta_mm
        final_position = heading_position - retract_offset
        
        # Validate final position
        if final_position < 0:
            logger.error(
                f"Invalid calculation: final_position={final_position:.1f}mm < 0. "
                f"Piece too long for ultra short mode."
            )
            return False
        
        logger.info(f"Starting Ultra Short sequence:")
        logger.info(f"  Target length: {target_length_mm:.1f}mm")
        logger.info(f"  Step 1 - Heading: Fixed SX @ {heading_position:.1f}mm, {angle_sx:.1f}°")
        logger.info(f"  Step 2 - Retract: DX by {retract_offset:.1f}mm")
        logger.info(f"  Step 3 - Final: Mobile DX @ {final_position:.1f}mm, {angle_dx:.1f}°")
        logger.info(f"  Measurement: OUTSIDE mobile blade DX")
        
        self.sequence = UltraShortSequence(
            enabled=True,
            target_length_mm=target_length_mm,
            angle_sx=angle_sx,
            angle_dx=angle_dx,
            heading_position=heading_position,
            heading_angle_sx=angle_sx,
            retract_offset=retract_offset,
            final_position=final_position,
            final_angle_dx=angle_dx,
            current_step=0
        )
        
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
        Execute Step 1: Heading with fixed head SX.
        
        Actions:
        1. Apply angles FIRST
        2. Configure morse (both locked)
        3. Start movement to heading_position
        
        Returns:
            True if step executed successfully
        """
        if not self.sequence or not self.sequence.enabled:
            logger.error("No active sequence")
            return False
        
        if self.sequence.current_step != 0:
            logger.warning(f"Step 1 called but current_step={self.sequence.current_step}")
        
        logger.info("Executing Ultra Short Step 1: Heading with fixed head SX")
        
        try:
            # 1. Apply angles FIRST
            self.mio.command_set_head_angles(
                sx=self.sequence.heading_angle_sx,
                dx=90.0  # Mobile head at 90° for now
            )
            
            # 2. Configure morse for heading
            from ui_qt.logic.modes.morse_strategy import MorseStrategy
            morse_config = MorseStrategy.ultra_short_heading()
            self.mio.command_set_morse(
                morse_config["left_locked"],
                morse_config["right_locked"]
            )
            
            # 3. Start movement
            success = self.mio.command_move(
                self.sequence.heading_position,
                ang_sx=self.sequence.heading_angle_sx,
                ang_dx=90.0
            )
            
            if success:
                self.sequence.current_step = 1
                logger.info(f"Ultra short step 1: heading @ {self.sequence.heading_position:.1f}mm")
            
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
        3. Move DX back by retract_offset
        
        Returns:
            True if step executed successfully
        """
        if not self.sequence or not self.sequence.enabled:
            logger.error("No active sequence")
            return False
        
        if self.sequence.current_step != 1:
            logger.warning(f"Step 2 called but current_step={self.sequence.current_step}")
        
        logger.info("Executing Ultra Short Step 2: Retract mobile head DX")
        
        try:
            # 1. Release brake to allow movement
            self.mio.command_release_brake()
            
            # 2. Configure morse for retract
            from ui_qt.logic.modes.morse_strategy import MorseStrategy
            morse_config = MorseStrategy.ultra_short_retract()
            self.mio.command_set_morse(
                morse_config["left_locked"],
                morse_config["right_locked"]
            )
            
            # 3. Calculate and move to retract position
            after_retract_position = self.sequence.heading_position - self.sequence.retract_offset
            
            success = self.mio.command_move(
                after_retract_position,
                ang_sx=self.sequence.angle_sx,
                ang_dx=90.0
            )
            
            if success:
                self.sequence.current_step = 2
                logger.info(f"Ultra short step 2: retract to {after_retract_position:.1f}mm")
            
            return success
        except Exception as e:
            logger.error(f"Error executing step 2: {e}")
            return False
    
    def execute_step_3(self) -> bool:
        """
        Execute Step 3: Final cut with mobile head DX.
        
        Actions:
        1. Apply angles for final cut
        2. Release brake to allow movement
        3. Configure morse for final cut
        4. Move to final_position for cutting
        
        Returns:
            True if step executed successfully
        """
        if not self.sequence or not self.sequence.enabled:
            logger.error("No active sequence")
            return False
        
        if self.sequence.current_step != 2:
            logger.warning(f"Step 3 called but current_step={self.sequence.current_step}")
        
        logger.info("Executing Ultra Short Step 3: Final cut with mobile head DX")
        
        try:
            # 1. Apply angles for final cut
            self.mio.command_set_head_angles(
                sx=90.0,  # Fixed head not used
                dx=self.sequence.final_angle_dx
            )
            
            # 2. Release brake to allow movement
            self.mio.command_release_brake()
            
            # 3. Configure morse for final cut
            from ui_qt.logic.modes.morse_strategy import MorseStrategy
            morse_config = MorseStrategy.ultra_short_final()
            self.mio.command_set_morse(
                morse_config["left_locked"],
                morse_config["right_locked"]
            )
            
            # 4. Start movement
            success = self.mio.command_move(
                self.sequence.final_position,
                ang_sx=90.0,
                ang_dx=self.sequence.final_angle_dx
            )
            
            if success:
                self.sequence.current_step = 3
                logger.info(f"Ultra short step 3: final @ {self.sequence.final_position:.1f}mm")
            
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
        logger.info("Resetting Ultra Short handler")
        self.sequence = None
    
    def get_step_description(self) -> str:
        """Get description of current step."""
        if not self.sequence:
            return "No active sequence"
        
        if self.sequence.current_step == 0:
            return "IDLE - Ready for heading"
        elif self.sequence.current_step == 1:
            return (
                f"STEP 1/3: Heading with fixed head SX @ "
                f"{self.sequence.heading_position:.0f}mm, {self.sequence.heading_angle_sx:.1f}°"
            )
        elif self.sequence.current_step == 2:
            after_pos = self.sequence.heading_position - self.sequence.retract_offset
            return (
                f"STEP 2/3: Retract mobile head DX by {self.sequence.retract_offset:.0f}mm "
                f"→ {after_pos:.0f}mm"
            )
        elif self.sequence.current_step == 3:
            return (
                f"STEP 3/3: Final cut with mobile head DX @ "
                f"{self.sequence.final_position:.0f}mm (piece: {self.sequence.target_length_mm:.1f}mm)"
            )
        else:
            return "Sequence complete"


__all__ = ["UltraShortHandler", "UltraShortConfig", "UltraShortSequence"]
