"""
Out of Quota Handler - 2-Step Sequence for Short Pieces
File: qt6_app/ui_qt/logic/modes/out_of_quota_handler.py
Date: 2025-12-16
Author: house79-gex

Handler for "Out of Quota" mode extracted from semi_auto_page.py.

2-Step Sequence:
1. Heading: Mobile head DX @ 45° at minimum position (zero_homing_mm)
   - Blades: Left inhibited, Right enabled
   - Morse: Both locked
2. Final: Fixed head SX cuts at target + offset_battuta
   - Blades: Left enabled, Right inhibited
   - Morse: Left released, Right locked
"""
from dataclasses import dataclass
from typing import Optional, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class OutOfQuotaConfig:
    """
    Configuration for out of quota mode.
    
    All values should come from settings, NOT hardcoded!
    """
    zero_homing_mm: float = 250.0  # From settings: machine_zero_homing_mm
    offset_battuta_mm: float = 120.0  # From settings: machine_offset_battuta_mm
    heading_angle_deg: float = 45.0  # Standard heading angle for mobile head DX
    
    @classmethod
    def from_settings(cls, settings: dict) -> "OutOfQuotaConfig":
        """Load configuration from settings dict."""
        return cls(
            zero_homing_mm=float(settings.get("machine_zero_homing_mm", 250.0)),
            offset_battuta_mm=float(settings.get("machine_offset_battuta_mm", 120.0)),
            heading_angle_deg=45.0  # Fixed standard value
        )


@dataclass
class OutOfQuotaSequence:
    """
    2-step sequence for out of quota mode.
    
    Step 1 - Heading:
    - Mobile head DX @ 45° at minimum position (zero_homing_mm)
    - Blades: Left inhibited, Right enabled
    - Morse: Both locked
    
    Step 2 - Final:
    - Fixed head SX cuts at target + offset_battuta
    - Blades: Left enabled, Right inhibited
    - Morse: Left released, Right locked
    """
    enabled: bool
    target_length_mm: float
    angle_sx: float
    angle_dx: float
    
    # Step 1: Heading
    heading_position: float  # Position for mobile head DX (= zero_homing_mm)
    heading_angle: float  # Angle for mobile head DX (typically 45°)
    heading_blade_left_inhibit: bool = True  # ❌ Left blade inhibited
    heading_blade_right_enable: bool = True  # ✅ Right blade enabled
    heading_morse_left_lock: bool = True  # ✅ Left morse locked
    heading_morse_right_lock: bool = True  # ✅ Right morse locked
    
    # Step 2: Final
    final_position: float  # Position for fixed head SX (= target + offset_battuta)
    final_angle_sx: float  # Angle for fixed head SX (user requested)
    final_angle_dx: float  # Angle for mobile head DX (user requested)
    final_blade_left_enable: bool = True  # ✅ Left blade enabled
    final_blade_right_inhibit: bool = True  # ❌ Right blade inhibited
    final_morse_left_release: bool = True  # ❌ Left morse released
    final_morse_right_lock: bool = True  # ✅ Right morse locked
    
    current_step: int = 0  # 0=idle, 1=heading, 2=final, 3=complete


class OutOfQuotaHandler:
    """
    Handler for out of quota mode execution.
    
    Manages 2-step sequence for cutting pieces below machine zero position.
    """
    
    def __init__(self, machine_io: Any, config: Optional[OutOfQuotaConfig] = None):
        """
        Initialize handler.
        
        Args:
            machine_io: Machine I/O adapter for controlling machine
            config: Configuration (uses defaults if None)
        """
        self.mio = machine_io
        self.config = config or OutOfQuotaConfig()
        self.sequence: Optional[OutOfQuotaSequence] = None
        logger.info(
            f"OutOfQuotaHandler initialized: "
            f"zero={self.config.zero_homing_mm:.0f}mm, "
            f"offset={self.config.offset_battuta_mm:.0f}mm"
        )
    
    def start_sequence(
        self,
        target_length_mm: float,
        angle_sx: float,
        angle_dx: float
    ) -> bool:
        """
        Start out of quota cutting sequence.
        
        Args:
            target_length_mm: Target piece length (internal measurement)
            angle_sx: Final angle for fixed head SX
            angle_dx: Final angle for mobile head DX
        
        Returns:
            True if sequence started successfully
        """
        # Calculate positions
        heading_position = self.config.zero_homing_mm
        final_position = target_length_mm + self.config.offset_battuta_mm
        
        logger.info(f"Starting Out of Quota sequence:")
        logger.info(f"  Target length: {target_length_mm:.1f}mm")
        logger.info(f"  Heading position: {heading_position:.1f}mm @ {self.config.heading_angle_deg:.1f}°")
        logger.info(f"  Final position: {final_position:.1f}mm (SX @ {angle_sx:.1f}°)")
        
        self.sequence = OutOfQuotaSequence(
            enabled=True,
            target_length_mm=target_length_mm,
            angle_sx=angle_sx,
            angle_dx=angle_dx,
            heading_position=heading_position,
            heading_angle=self.config.heading_angle_deg,
            final_position=final_position,
            final_angle_sx=angle_sx,
            final_angle_dx=angle_dx,
            current_step=0
        )
        
        return True
    
    def execute_step_1(self) -> bool:
        """
        Execute Step 1: Heading with mobile head DX @ 45°.
        
        Actions:
        1. Set blade inhibits: Left=True, Right=False
        2. Set morse: Both locked
        3. Move to heading_position with heading_angle on DX
        4. Lock brake
        
        Returns:
            True if step executed successfully
        """
        if not self.sequence or not self.sequence.enabled:
            logger.error("No active sequence")
            return False
        
        if self.sequence.current_step != 0:
            logger.warning(f"Step 1 called but current_step={self.sequence.current_step}")
        
        logger.info("Executing Out of Quota Step 1: Heading")
        
        # Step 1: Set blade inhibits
        if hasattr(self.mio, "set_blade_inhibits"):
            self.mio.set_blade_inhibits(left=True, right=False)
        else:
            logger.warning("Machine I/O does not support set_blade_inhibits")
        
        # Step 2: Set morse (both locked)
        if hasattr(self.mio, "set_morse"):
            self.mio.set_morse(left_locked=True, right_locked=True)
        else:
            logger.warning("Machine I/O does not support set_morse")
        
        # Step 3: Move to heading position
        if hasattr(self.mio, "command_move"):
            success = self.mio.command_move(
                length_mm=self.sequence.heading_position,
                angle_sx=self.sequence.angle_sx,  # Keep SX angle unchanged
                angle_dx=self.sequence.heading_angle,  # DX @ 45°
                profile="default",
                element="out_of_quota_heading"
            )
            if not success:
                logger.error("Failed to start heading movement")
                return False
        else:
            logger.warning("Machine I/O does not support command_move")
        
        # Step 4: Lock brake (typically done after movement completes)
        if hasattr(self.mio, "command_lock_brake"):
            self.mio.command_lock_brake()
        
        self.sequence.current_step = 1
        logger.info("Step 1 (Heading) completed")
        return True
    
    def execute_step_2(self) -> bool:
        """
        Execute Step 2: Final cut with fixed head SX.
        
        Actions:
        1. Set blade inhibits: Left=False, Right=True
        2. Set morse: Left released, Right locked
        3. Move to final_position with final angles
        
        Returns:
            True if step executed successfully
        """
        if not self.sequence or not self.sequence.enabled:
            logger.error("No active sequence")
            return False
        
        if self.sequence.current_step != 1:
            logger.warning(f"Step 2 called but current_step={self.sequence.current_step}")
        
        logger.info("Executing Out of Quota Step 2: Final Cut")
        
        # Step 1: Set blade inhibits
        if hasattr(self.mio, "set_blade_inhibits"):
            self.mio.set_blade_inhibits(left=False, right=True)
        else:
            logger.warning("Machine I/O does not support set_blade_inhibits")
        
        # Step 2: Set morse (left released, right locked)
        if hasattr(self.mio, "set_morse"):
            self.mio.set_morse(left_locked=False, right_locked=True)
        else:
            logger.warning("Machine I/O does not support set_morse")
        
        # Step 3: Move to final position
        if hasattr(self.mio, "command_move"):
            success = self.mio.command_move(
                length_mm=self.sequence.final_position,
                angle_sx=self.sequence.final_angle_sx,
                angle_dx=self.sequence.final_angle_dx,
                profile="default",
                element="out_of_quota_final"
            )
            if not success:
                logger.error("Failed to start final movement")
                return False
        else:
            logger.warning("Machine I/O does not support command_move")
        
        self.sequence.current_step = 2
        logger.info("Step 2 (Final Cut) completed")
        return True
    
    def get_current_step(self) -> int:
        """
        Get current step number.
        
        Returns:
            0=idle, 1=heading, 2=final, 3=complete
        """
        if self.sequence:
            return self.sequence.current_step
        return 0
    
    def reset(self):
        """Reset handler to initial state."""
        logger.info("Resetting Out of Quota handler")
        self.sequence = None
    
    def get_step_description(self) -> str:
        """Get description of current step."""
        if not self.sequence:
            return "No active sequence"
        
        if self.sequence.current_step == 0:
            return "IDLE - Ready for heading"
        elif self.sequence.current_step == 1:
            return (
                f"STEP 1/2: Heading with mobile head DX @ "
                f"{self.sequence.heading_position:.0f}mm, {self.sequence.heading_angle:.1f}°"
            )
        elif self.sequence.current_step == 2:
            return (
                f"STEP 2/2: Final cut with fixed head SX @ "
                f"{self.sequence.final_position:.0f}mm (piece: {self.sequence.target_length_mm:.1f}mm)"
            )
        else:
            return "Sequence complete"


__all__ = ["OutOfQuotaHandler", "OutOfQuotaConfig", "OutOfQuotaSequence"]
