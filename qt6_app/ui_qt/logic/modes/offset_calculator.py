"""
Offset Calculator - Position Calculations for Special Modes
File: qt6_app/ui_qt/logic/modes/offset_calculator.py
Date: 2025-12-16
Author: house79-gex

Offset calculations for special cutting modes using dynamic parameters from configuration.
"""
from dataclasses import dataclass
from typing import Dict
import logging

logger = logging.getLogger(__name__)


@dataclass
class OffsetResult:
    """Result of offset calculation."""
    heading_position: float
    final_position: float
    offset: float
    
    def __repr__(self) -> str:
        return (
            f"OffsetResult(heading={self.heading_position:.1f}mm, "
            f"final={self.final_position:.1f}mm, offset={self.offset:.1f}mm)"
        )


class OffsetCalculator:
    """Calculator for position offsets in special cutting modes."""
    
    @staticmethod
    def calculate_out_of_quota(
        piece_length_mm: float,
        zero_homing_mm: float,
        offset_battuta_mm: float
    ) -> OffsetResult:
        """
        Calculate positions for out of quota mode.
        
        Out of Quota sequence (2 steps):
        1. Heading: Mobile head DX @ 45° at minimum position (zero_homing_mm)
        2. Final: Fixed head SX cuts at piece_length + offset_battuta_mm
        
        Args:
            piece_length_mm: Target piece length
            zero_homing_mm: Machine zero/homing position (from config)
            offset_battuta_mm: Physical stop distance (from config)
        
        Returns:
            OffsetResult with heading and final positions
        
        Example:
            piece_length = 180mm
            zero_homing = 250mm
            offset_battuta = 120mm
            
            heading_position = 250mm (minimum position)
            final_position = 180mm + 120mm = 300mm
            offset = 120mm
        """
        heading_position = zero_homing_mm
        final_position = piece_length_mm + offset_battuta_mm
        offset = offset_battuta_mm
        
        logger.info(
            f"Out of Quota calculation: piece={piece_length_mm:.1f}mm, "
            f"heading={heading_position:.1f}mm, final={final_position:.1f}mm"
        )
        
        return OffsetResult(
            heading_position=heading_position,
            final_position=final_position,
            offset=offset
        )
    
    @staticmethod
    def calculate_ultra_short(
        piece_length_mm: float,
        zero_homing_mm: float,
        offset_battuta_mm: float,
        safety_margin_mm: float = 50.0
    ) -> Dict[str, float]:
        """
        Calculate positions for ultra short mode (3-step).
        
        Ultra Short sequence (3 steps):
        1. Heading: Fixed head SX cuts at zero_homing + safety_margin
        2. Retract: Mobile head DX retracts by offset = piece_length + offset_battuta
        3. Final: Mobile head DX cuts at heading_position - offset
        
        Measurement is OUTSIDE the mobile blade DX.
        
        Args:
            piece_length_mm: Target piece length
            zero_homing_mm: Machine zero/homing position (from config)
            offset_battuta_mm: Physical stop distance (from config)
            safety_margin_mm: Safety margin for heading position (default: 50mm)
        
        Returns:
            Dict with positions:
            - heading_position: Position for heading cut
            - retract_offset: Distance to retract
            - final_position: Final cutting position
            - measurement_outside: True (measurement outside mobile blade)
        
        Example:
            piece_length = 100mm
            zero_homing = 250mm
            offset_battuta = 120mm
            safety_margin = 50mm
            
            heading_position = 250mm + 50mm = 300mm
            retract_offset = 100mm + 120mm = 220mm
            final_position = 300mm - 220mm = 80mm
        """
        heading_position = zero_homing_mm + safety_margin_mm
        retract_offset = piece_length_mm + offset_battuta_mm
        final_position = heading_position - retract_offset
        
        # Validate final position
        if final_position < 0:
            logger.error(
                f"Invalid ultra short calculation: final_position={final_position:.1f}mm < 0. "
                f"Piece too long for ultra short mode."
            )
            raise ValueError(
                f"Pezzo troppo lungo per modalità ultra corta: "
                f"posizione finale {final_position:.1f}mm < 0"
            )
        
        logger.info(
            f"Ultra Short calculation: piece={piece_length_mm:.1f}mm, "
            f"heading={heading_position:.1f}mm, retract_offset={retract_offset:.1f}mm, "
            f"final={final_position:.1f}mm"
        )
        
        return {
            "heading_position": heading_position,
            "retract_offset": retract_offset,
            "final_position": final_position,
            "measurement_outside": True  # Measurement OUTSIDE mobile blade DX
        }
    
    @staticmethod
    def calculate_extra_long(
        piece_length_mm: float,
        max_travel_mm: float,
        safe_head_mm: float = 2000.0,
        min_offset_mm: float = 500.0
    ) -> Dict[str, float]:
        """
        Calculate positions for extra long mode (3-step).
        
        Extra Long sequence (3 steps):
        1. Heading: Mobile head DX cuts at safe_head_mm
        2. Retract: Mobile head DX retracts by offset = piece_length - max_travel
        3. Final: Fixed head SX cuts at max_travel_mm
        
        Measurement is INSIDE the mobile blade DX.
        
        Args:
            piece_length_mm: Target piece length
            max_travel_mm: Maximum machine travel (from config)
            safe_head_mm: Safe position for heading cut (default: 2000mm)
            min_offset_mm: Minimum offset for safety (default: 500mm)
        
        Returns:
            Dict with positions:
            - heading_position: Position for heading cut
            - retract_offset: Distance to retract
            - final_position: Final cutting position
            - after_retract_position: Position after retract
            - measurement_inside: True (measurement inside mobile blade)
        
        Example:
            piece_length = 5000mm
            max_travel = 4000mm
            safe_head = 2000mm
            
            retract_offset = 5000mm - 4000mm = 1000mm
            heading_position = 2000mm
            after_retract = 2000mm - 1000mm = 1000mm
            final_position = 4000mm
        """
        offset = piece_length_mm - max_travel_mm
        
        if offset < min_offset_mm:
            logger.error(
                f"Extra long offset {offset:.1f}mm < minimum {min_offset_mm:.1f}mm. "
                f"Use normal mode instead."
            )
            raise ValueError(
                f"Offset {offset:.1f}mm troppo piccolo. Usa modalità normale."
            )
        
        heading_position = safe_head_mm
        after_retract_position = heading_position - offset
        final_position = max_travel_mm
        
        # Validate after retract position
        if after_retract_position < 250:  # Typical machine zero
            logger.error(
                f"Extra long: after_retract_position={after_retract_position:.1f}mm < 250mm (zero). "
                f"Piece too long or safe_head_mm too small."
            )
            raise ValueError(
                f"Arretramento porta a {after_retract_position:.1f}mm < 250mm (zero macchina)"
            )
        
        logger.info(
            f"Extra Long calculation: piece={piece_length_mm:.1f}mm, "
            f"heading={heading_position:.1f}mm, retract_offset={offset:.1f}mm, "
            f"after_retract={after_retract_position:.1f}mm, final={final_position:.1f}mm"
        )
        
        return {
            "heading_position": heading_position,
            "retract_offset": offset,
            "final_position": final_position,
            "after_retract_position": after_retract_position,
            "measurement_inside": True  # Measurement INSIDE mobile blade DX
        }


__all__ = ["OffsetCalculator", "OffsetResult"]
