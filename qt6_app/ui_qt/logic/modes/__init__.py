"""
Modes Package - Modular Mode System with Dynamic Hardware Configuration
File: qt6_app/ui_qt/logic/modes/__init__.py
Date: 2025-12-16
Author: house79-gex

This package provides a modular system for handling special cutting modes
(Out of Quota, Ultra Short, Extra Long) with dynamic hardware configuration.

All machine parameters are read from settings (configured via Utility → Configuration),
eliminating hardcoded values.

Usage Example:
    ```python
    from ui_qt.utils.settings import read_settings
    from ui_qt.logic.modes import ModeConfig, ModeDetector, OutOfQuotaHandler
    
    # Load configuration from settings (NO hardcoded values!)
    settings = read_settings()
    config = ModeConfig.from_settings(settings)
    
    # Detect mode
    detector = ModeDetector(config)
    info = detector.detect(180.0)  # Example: 180mm piece
    
    if not info.is_valid:
        print(info.error_message)
    elif info.mode_name == "out_of_quota":
        # Show confirmation dialog
        print(info.warning_message)
        
        # Execute handler
        handler = OutOfQuotaHandler(machine_io, config)
        handler.start_sequence(180.0, angle_sx=90.0, angle_dx=90.0)
    ```

Modules:
    - mode_config: Configuration with dynamic parameters from settings
    - mode_detector: Mode detection from piece length
    - morse_strategy: Morse (clamp) configurations per mode/step
    - offset_calculator: Offset calculations for special modes
    - out_of_quota_handler: Out of Quota handler (2-step sequence)
    - ultra_short_handler: Ultra Short handler (3-step, inverted heads)
    - extra_long_handler: Extra Long handler (wrapper for ultra_long_mode.py)
"""

from .mode_config import ModeConfig, ModeRange
from .mode_detector import ModeDetector, ModeInfo
from .morse_strategy import MorseStrategy
from .offset_calculator import OffsetCalculator, OffsetResult
from .out_of_quota_handler import (
    OutOfQuotaHandler,
    OutOfQuotaConfig,
    OutOfQuotaSequence
)
from .ultra_short_handler import (
    UltraShortHandler,
    UltraShortConfig,
    UltraShortSequence
)
from .extra_long_handler import (
    ExtraLongHandler,
    ExtraLongConfig
)

__all__ = [
    # Configuration
    "ModeConfig",
    "ModeRange",
    
    # Detection
    "ModeDetector",
    "ModeInfo",
    
    # Strategies
    "MorseStrategy",
    
    # Calculators
    "OffsetCalculator",
    "OffsetResult",
    
    # Out of Quota
    "OutOfQuotaHandler",
    "OutOfQuotaConfig",
    "OutOfQuotaSequence",
    
    # Ultra Short
    "UltraShortHandler",
    "UltraShortConfig",
    "UltraShortSequence",
    
    # Extra Long
    "ExtraLongHandler",
    "ExtraLongConfig",
]
