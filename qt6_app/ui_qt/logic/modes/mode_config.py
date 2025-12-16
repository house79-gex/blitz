"""
Mode Configuration with Dynamic Hardware Parameters
File: qt6_app/ui_qt/logic/modes/mode_config.py
Date: 2025-12-16
Author: house79-gex

CRITICAL: All values read from settings, NOT hardcoded!

Hardware parameters (from Utility → Configuration → Hardware):
- machine_zero_homing_mm: Homing zero position (measured)
- machine_offset_battuta_mm: Physical stop distance (measured)
- machine_max_travel_mm: Max usable stroke (tested)

Operational parameters:
- stock_length_mm: Current bar stock length

Calculated parameters (automatic):
- ultra_short_threshold = zero - offset_battuta
"""
from dataclasses import dataclass
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class ModeRange:
    """Range definition for a cutting mode."""
    min_mm: float
    max_mm: float
    name: str
    color: str
    requires_confirmation: bool = False
    
    def contains(self, length_mm: float) -> bool:
        """Check if length falls within this range."""
        return self.min_mm <= length_mm <= self.max_mm
    
    def __repr__(self) -> str:
        return f"ModeRange({self.name}: {self.min_mm:.0f}-{self.max_mm:.0f}mm, color={self.color})"


@dataclass
class ModeConfig:
    """
    Configuration for cutting modes with dynamic hardware parameters.
    
    CRITICAL: All values read from settings, NOT hardcoded!
    
    Hardware parameters (from Utility → Configuration → Hardware):
    - machine_zero_homing_mm: Homing zero position (measured)
    - machine_offset_battuta_mm: Physical stop distance (measured)
    - machine_max_travel_mm: Max usable stroke (tested)
    
    Operational parameters:
    - stock_length_mm: Current bar stock length
    
    Calculated parameters (automatic):
    - ultra_short_threshold = zero - offset_battuta
    """
    machine_zero_homing_mm: float
    machine_offset_battuta_mm: float
    machine_max_travel_mm: float
    stock_length_mm: float
    
    def __post_init__(self):
        """Validate configuration parameters."""
        if self.machine_zero_homing_mm <= 0:
            logger.error(f"Invalid machine_zero_homing_mm: {self.machine_zero_homing_mm}")
            raise ValueError("machine_zero_homing_mm must be > 0")
        
        if self.machine_offset_battuta_mm <= 0:
            logger.error(f"Invalid machine_offset_battuta_mm: {self.machine_offset_battuta_mm}")
            raise ValueError("machine_offset_battuta_mm must be > 0")
        
        if self.machine_offset_battuta_mm >= self.machine_zero_homing_mm:
            logger.error(
                f"Invalid config: offset_battuta ({self.machine_offset_battuta_mm}) "
                f">= zero_homing ({self.machine_zero_homing_mm})"
            )
            raise ValueError("machine_offset_battuta_mm must be < machine_zero_homing_mm")
        
        if self.machine_max_travel_mm <= self.machine_zero_homing_mm:
            logger.error(
                f"Invalid config: max_travel ({self.machine_max_travel_mm}) "
                f"<= zero_homing ({self.machine_zero_homing_mm})"
            )
            raise ValueError("machine_max_travel_mm must be > machine_zero_homing_mm")
        
        if self.stock_length_mm <= self.machine_max_travel_mm:
            logger.warning(
                f"Stock length ({self.stock_length_mm}) <= max_travel ({self.machine_max_travel_mm}). "
                f"Extra long mode will never trigger."
            )
        
        logger.info(f"ModeConfig initialized:")
        logger.info(f"  Zero homing: {self.machine_zero_homing_mm:.0f}mm")
        logger.info(f"  Offset battuta: {self.machine_offset_battuta_mm:.0f}mm")
        logger.info(f"  Max travel: {self.machine_max_travel_mm:.0f}mm")
        logger.info(f"  Stock length: {self.stock_length_mm:.0f}mm")
        logger.info(f"  Ultra short threshold: {self.ultra_short_threshold:.0f}mm")
    
    @property
    def ultra_short_threshold(self) -> float:
        """
        Auto-calculated threshold for ultra short mode.
        
        When piece length <= this threshold, ultra short mode is required.
        
        Formula: zero_homing - offset_battuta
        Example: 250mm - 120mm = 130mm
        """
        return self.machine_zero_homing_mm - self.machine_offset_battuta_mm
    
    @classmethod
    def from_settings(cls, settings: Dict[str, Any]) -> "ModeConfig":
        """
        Load configuration from settings dict.
        
        Args:
            settings: Settings dictionary from read_settings()
        
        Returns:
            ModeConfig instance with parameters from settings
        """
        return cls(
            machine_zero_homing_mm=float(settings.get("machine_zero_homing_mm", 250.0)),
            machine_offset_battuta_mm=float(settings.get("machine_offset_battuta_mm", 120.0)),
            machine_max_travel_mm=float(settings.get("machine_max_travel_mm", 4000.0)),
            stock_length_mm=float(settings.get("stock_length_mm", 6500.0)),
        )
    
    def to_settings_dict(self) -> Dict[str, float]:
        """
        Convert configuration to settings dict for saving.
        
        Returns:
            Dictionary with settings keys and values
        """
        return {
            "machine_zero_homing_mm": self.machine_zero_homing_mm,
            "machine_offset_battuta_mm": self.machine_offset_battuta_mm,
            "machine_max_travel_mm": self.machine_max_travel_mm,
            "stock_length_mm": self.stock_length_mm,
        }
    
    def get_range_ultra_short(self) -> ModeRange:
        """
        Get range definition for ultra short mode.
        
        Range: 0 to ultra_short_threshold (exclusive)
        Color: Yellow (🟡)
        Requires confirmation: Yes
        """
        return ModeRange(
            min_mm=0.0,
            max_mm=self.ultra_short_threshold,
            name="ultra_short",
            color="yellow",
            requires_confirmation=True
        )
    
    def get_range_out_of_quota(self) -> ModeRange:
        """
        Get range definition for out of quota mode.
        
        Range: ultra_short_threshold to machine_zero_homing_mm (exclusive)
        Color: Red (🔴)
        Requires confirmation: Yes
        """
        return ModeRange(
            min_mm=self.ultra_short_threshold,
            max_mm=self.machine_zero_homing_mm,
            name="out_of_quota",
            color="red",
            requires_confirmation=True
        )
    
    def get_range_normal(self) -> ModeRange:
        """
        Get range definition for normal mode.
        
        Range: machine_zero_homing_mm to machine_max_travel_mm (inclusive)
        Color: Green (🟢)
        Requires confirmation: No
        """
        return ModeRange(
            min_mm=self.machine_zero_homing_mm,
            max_mm=self.machine_max_travel_mm,
            name="normal",
            color="green",
            requires_confirmation=False
        )
    
    def get_range_extra_long(self) -> ModeRange:
        """
        Get range definition for extra long mode.
        
        Range: machine_max_travel_mm to stock_length_mm (inclusive)
        Color: Blue (🔵)
        Requires confirmation: Yes
        """
        return ModeRange(
            min_mm=self.machine_max_travel_mm,
            max_mm=self.stock_length_mm,
            name="extra_long",
            color="blue",
            requires_confirmation=True
        )


__all__ = ["ModeConfig", "ModeRange"]
