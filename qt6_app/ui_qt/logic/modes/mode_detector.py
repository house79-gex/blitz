"""
Mode Detector - Dynamic Mode Detection from Piece Length
File: qt6_app/ui_qt/logic/modes/mode_detector.py
Date: 2025-12-16
Author: house79-gex

Detects appropriate cutting mode from piece length using DYNAMIC thresholds
calculated from hardware configuration.
"""
from dataclasses import dataclass
from typing import Optional
import logging
from .mode_config import ModeConfig, ModeRange

logger = logging.getLogger(__name__)


@dataclass
class ModeInfo:
    """Mode detection result."""
    mode_name: str  # "ultra_short" | "out_of_quota" | "normal" | "extra_long" | "invalid"
    mode_range: Optional[ModeRange]
    is_valid: bool
    error_message: str = ""
    warning_message: str = ""
    
    def __repr__(self) -> str:
        if self.is_valid:
            return f"ModeInfo({self.mode_name}, valid, range={self.mode_range})"
        else:
            return f"ModeInfo(invalid, error={self.error_message})"


class ModeDetector:
    """Detects appropriate mode from piece length using dynamic configuration."""
    
    def __init__(self, config: ModeConfig):
        """
        Initialize detector with configuration.
        
        Args:
            config: ModeConfig with dynamic hardware parameters
        """
        self.config = config
        logger.info(f"ModeDetector initialized with config: "
                   f"ultra_short <= {config.ultra_short_threshold:.0f}mm, "
                   f"out_of_quota < {config.machine_zero_homing_mm:.0f}mm, "
                   f"normal <= {config.machine_max_travel_mm:.0f}mm, "
                   f"extra_long <= {config.stock_length_mm:.0f}mm")
    
    def detect(self, piece_length_mm: float) -> ModeInfo:
        """
        Detect mode from piece length using DYNAMIC thresholds.
        
        Mode ranges (calculated from config):
        - Ultra Short: 0 < length <= ultra_short_threshold (e.g., <= 130mm)
        - Out of Quota: ultra_short_threshold < length < zero_homing (e.g., 130-250mm)
        - Normal: zero_homing <= length <= max_travel (e.g., 250-4000mm)
        - Extra Long: max_travel < length <= stock_length (e.g., 4000-6500mm)
        
        Args:
            piece_length_mm: Requested piece length in millimeters
        
        Returns:
            ModeInfo with detection result and appropriate range
        """
        # Validate piece length
        if piece_length_mm <= 0:
            logger.error(f"Invalid piece length: {piece_length_mm:.2f}mm (must be > 0)")
            return ModeInfo(
                mode_name="invalid",
                mode_range=None,
                is_valid=False,
                error_message=f"Lunghezza pezzo invalida: {piece_length_mm:.2f}mm (deve essere > 0)"
            )
        
        if piece_length_mm > self.config.stock_length_mm:
            logger.error(
                f"Piece length {piece_length_mm:.2f}mm exceeds stock length "
                f"{self.config.stock_length_mm:.0f}mm"
            )
            return ModeInfo(
                mode_name="invalid",
                mode_range=None,
                is_valid=False,
                error_message=(
                    f"Lunghezza pezzo {piece_length_mm:.1f}mm supera la lunghezza stock "
                    f"{self.config.stock_length_mm:.0f}mm"
                )
            )
        
        # Detect mode based on dynamic thresholds
        if piece_length_mm <= self.config.ultra_short_threshold:
            # Ultra short mode
            mode_range = self.config.get_range_ultra_short()
            logger.info(
                f"Detected ULTRA SHORT mode for {piece_length_mm:.1f}mm "
                f"(<= {self.config.ultra_short_threshold:.0f}mm)"
            )
            return ModeInfo(
                mode_name="ultra_short",
                mode_range=mode_range,
                is_valid=True,
                warning_message=(
                    f"⚠️ MODALITÀ ULTRA CORTA\n\n"
                    f"Pezzo: {piece_length_mm:.1f}mm <= {self.config.ultra_short_threshold:.0f}mm\n\n"
                    f"Sequenza 3 passi:\n"
                    f"1. Intestatura con testa FISSA SX\n"
                    f"2. Arretramento testa MOBILE DX\n"
                    f"3. Taglio finale con testa MOBILE DX\n\n"
                    f"Misura ESTERNA lama mobile DX."
                )
            )
        
        elif piece_length_mm < self.config.machine_zero_homing_mm:
            # Out of quota mode
            mode_range = self.config.get_range_out_of_quota()
            logger.info(
                f"Detected OUT OF QUOTA mode for {piece_length_mm:.1f}mm "
                f"(< {self.config.machine_zero_homing_mm:.0f}mm)"
            )
            return ModeInfo(
                mode_name="out_of_quota",
                mode_range=mode_range,
                is_valid=True,
                warning_message=(
                    f"⚠️ MODALITÀ FUORI QUOTA\n\n"
                    f"Pezzo: {piece_length_mm:.1f}mm < {self.config.machine_zero_homing_mm:.0f}mm\n\n"
                    f"Sequenza 2 passi:\n"
                    f"1. Intestatura: Testa mobile DX @ 45° alla minima\n"
                    f"2. Taglio finale: Testa fissa SX alla quota + offset battuta\n\n"
                    f"Posizione finale: {piece_length_mm + self.config.machine_offset_battuta_mm:.1f}mm"
                )
            )
        
        elif piece_length_mm <= self.config.machine_max_travel_mm:
            # Normal mode
            mode_range = self.config.get_range_normal()
            logger.info(
                f"Detected NORMAL mode for {piece_length_mm:.1f}mm "
                f"(<= {self.config.machine_max_travel_mm:.0f}mm)"
            )
            return ModeInfo(
                mode_name="normal",
                mode_range=mode_range,
                is_valid=True,
                warning_message=""  # No warning for normal mode
            )
        
        else:
            # Extra long mode
            mode_range = self.config.get_range_extra_long()
            logger.info(
                f"Detected EXTRA LONG mode for {piece_length_mm:.1f}mm "
                f"(> {self.config.machine_max_travel_mm:.0f}mm)"
            )
            return ModeInfo(
                mode_name="extra_long",
                mode_range=mode_range,
                is_valid=True,
                warning_message=(
                    f"⚠️ MODALITÀ EXTRA LUNGA\n\n"
                    f"Pezzo: {piece_length_mm:.1f}mm > {self.config.machine_max_travel_mm:.0f}mm\n\n"
                    f"Sequenza 3 passi:\n"
                    f"1. Intestatura con testa MOBILE DX\n"
                    f"2. Arretramento testa MOBILE DX\n"
                    f"3. Taglio finale con testa FISSA SX\n\n"
                    f"Misura INTERNA lama mobile DX."
                )
            )
    
    def get_mode_display_name(self, mode_name: str) -> str:
        """
        Get human-readable display name for mode.
        
        Args:
            mode_name: Mode name ("ultra_short", "out_of_quota", "normal", "extra_long")
        
        Returns:
            Display name in Italian
        """
        mode_names = {
            "ultra_short": "Ultra Corta",
            "out_of_quota": "Fuori Quota",
            "normal": "Normale",
            "extra_long": "Extra Lunga",
            "invalid": "Invalida"
        }
        return mode_names.get(mode_name, mode_name.replace("_", " ").title())


__all__ = ["ModeDetector", "ModeInfo"]
