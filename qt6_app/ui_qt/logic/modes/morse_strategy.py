"""
Morse (Clamp) Strategy - Configurations per Mode/Step
File: qt6_app/ui_qt/logic/modes/morse_strategy.py
Date: 2025-12-16
Author: house79-gex

Static morse (clamp/presser) configurations for each cutting mode and step.
"""
from typing import Dict
import logging

logger = logging.getLogger(__name__)


class MorseStrategy:
    """
    Static morse (clamp/presser) configurations for each mode and step.
    
    Morse states:
    - locked (True): Clamp is locked, holding the material
    - released (False): Clamp is released, material can move
    
    Configuration dict keys:
    - left_locked: Left clamp state (bool)
    - right_locked: Right clamp state (bool)
    """
    
    @staticmethod
    def normal() -> Dict[str, bool]:
        """
        Normal mode morse configuration.
        
        Both clamps released for standard cutting.
        
        Returns:
            {"left_locked": False, "right_locked": False}
        """
        return {
            "left_locked": False,
            "right_locked": False
        }
    
    @staticmethod
    def out_of_quota_heading() -> Dict[str, bool]:
        """
        Out of Quota - Step 1: Heading (Intestatura).
        
        Both clamps locked to hold material for heading cut with mobile head DX @ 45°.
        
        Returns:
            {"left_locked": True, "right_locked": True}
        """
        return {
            "left_locked": True,
            "right_locked": True
        }
    
    @staticmethod
    def out_of_quota_final() -> Dict[str, bool]:
        """
        Out of Quota - Step 2: Final cut.
        
        Left clamp released, right clamp locked.
        Fixed head SX cuts at target + offset_battuta.
        
        Returns:
            {"left_locked": False, "right_locked": True}
        """
        return {
            "left_locked": False,
            "right_locked": True
        }
    
    @staticmethod
    def ultra_short_heading() -> Dict[str, bool]:
        """
        Ultra Short - Step 1: Heading (Intestatura).
        
        Both clamps locked to hold material for heading cut with fixed head SX.
        
        Returns:
            {"left_locked": True, "right_locked": True}
        """
        return {
            "left_locked": True,
            "right_locked": True
        }
    
    @staticmethod
    def ultra_short_retract() -> Dict[str, bool]:
        """
        Ultra Short - Step 2: Retract.
        
        Left clamp locked, right clamp released.
        Mobile head DX retracts pulling material with right clamp.
        
        Returns:
            {"left_locked": True, "right_locked": False}
        """
        return {
            "left_locked": True,
            "right_locked": False
        }
    
    @staticmethod
    def ultra_short_final() -> Dict[str, bool]:
        """
        Ultra Short - Step 3: Final cut.
        
        Left clamp released, right clamp locked.
        Mobile head DX cuts at final position.
        
        Returns:
            {"left_locked": False, "right_locked": True}
        """
        return {
            "left_locked": False,
            "right_locked": True
        }
    
    @staticmethod
    def extra_long_heading() -> Dict[str, bool]:
        """
        Extra Long - Step 1: Heading (Intestatura).
        
        Both clamps locked to hold material for heading cut with mobile head DX.
        
        Returns:
            {"left_locked": True, "right_locked": True}
        """
        return {
            "left_locked": True,
            "right_locked": True
        }
    
    @staticmethod
    def extra_long_retract() -> Dict[str, bool]:
        """
        Extra Long - Step 2: Retract.
        
        Left clamp locked, right clamp released.
        Mobile head DX retracts pulling material with right clamp.
        
        Returns:
            {"left_locked": True, "right_locked": False}
        """
        return {
            "left_locked": True,
            "right_locked": False
        }
    
    @staticmethod
    def extra_long_final() -> Dict[str, bool]:
        """
        Extra Long - Step 3: Final cut.
        
        Left clamp released, right clamp locked.
        Fixed head SX cuts at final position.
        
        Returns:
            {"left_locked": False, "right_locked": True}
        """
        return {
            "left_locked": False,
            "right_locked": True
        }
    
    @staticmethod
    def get_config(mode: str, step: str) -> Dict[str, bool]:
        """
        Get morse configuration for a specific mode and step.
        
        Args:
            mode: Mode name ("normal", "out_of_quota", "ultra_short", "extra_long")
            step: Step name ("heading", "retract", "final")
        
        Returns:
            Morse configuration dict
        
        Raises:
            ValueError: If mode/step combination is invalid
        """
        mode = mode.lower()
        step = step.lower()
        
        if mode == "normal":
            return MorseStrategy.normal()
        
        elif mode == "out_of_quota":
            if step == "heading":
                return MorseStrategy.out_of_quota_heading()
            elif step == "final":
                return MorseStrategy.out_of_quota_final()
            else:
                raise ValueError(f"Invalid step '{step}' for mode 'out_of_quota'. Valid: heading, final")
        
        elif mode == "ultra_short":
            if step == "heading":
                return MorseStrategy.ultra_short_heading()
            elif step == "retract":
                return MorseStrategy.ultra_short_retract()
            elif step == "final":
                return MorseStrategy.ultra_short_final()
            else:
                raise ValueError(f"Invalid step '{step}' for mode 'ultra_short'. Valid: heading, retract, final")
        
        elif mode == "extra_long":
            if step == "heading":
                return MorseStrategy.extra_long_heading()
            elif step == "retract":
                return MorseStrategy.extra_long_retract()
            elif step == "final":
                return MorseStrategy.extra_long_final()
            else:
                raise ValueError(f"Invalid step '{step}' for mode 'extra_long'. Valid: heading, retract, final")
        
        else:
            raise ValueError(f"Invalid mode '{mode}'. Valid: normal, out_of_quota, ultra_short, extra_long")


__all__ = ["MorseStrategy"]
