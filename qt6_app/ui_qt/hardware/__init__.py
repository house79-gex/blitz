"""
Hardware abstraction layer for BLITZ CNC control system.

This package provides hardware drivers for the motion control stack:
- MD25HVDriver: Cytron MD25HV motor driver control
- EncoderReader8ALZARD: ELTRA encoder reader via 8AL-ZARD optocoupler
- MotionController: PID-based closed-loop motion control
"""

from .md25hv_driver import MD25HVDriver
from .encoder_reader_8alzard import EncoderReader8ALZARD
from .motion_controller import MotionController

__all__ = [
    "MD25HVDriver",
    "EncoderReader8ALZARD",
    "MotionController",
]
