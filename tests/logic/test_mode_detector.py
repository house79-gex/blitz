"""Unit tests for mode detection logic."""

import pytest
from qt6_app.ui_qt.logic.modes.mode_detector import ModeDetector
from qt6_app.ui_qt.logic.modes.mode_config import ModeConfig


def test_mode_detector_initialization(sample_mode_config):
    """Test mode detector creates with config."""
    detector = ModeDetector(sample_mode_config)
    assert detector is not None
    assert detector.config == sample_mode_config


def test_mode_detector_normal():
    """Test normal mode detection."""
    config = ModeConfig(
        machine_zero_homing_mm=250.0,
        machine_offset_battuta_mm=120.0,
        machine_max_travel_mm=4000.0,
        stock_length_mm=6500.0
    )
    detector = ModeDetector(config)
    
    mode = detector.detect(length_mm=1000.0)
    
    assert mode.mode_name == "normal"
    assert mode.is_valid
    assert not mode.error_message


def test_mode_detector_ultra_short():
    """Test ultra short mode detection."""
    config = ModeConfig(
        machine_zero_homing_mm=250.0,
        machine_offset_battuta_mm=120.0,
        machine_max_travel_mm=4000.0,
        stock_length_mm=6500.0
    )
    detector = ModeDetector(config)
    
    # 130mm is the threshold (250 - 120)
    mode = detector.detect(length_mm=100.0)
    
    assert mode.mode_name == "ultra_short"
    assert mode.is_valid
    assert mode.warning_message  # Should have warning


def test_mode_detector_out_of_quota():
    """Test out of quota mode detection."""
    config = ModeConfig(
        machine_zero_homing_mm=250.0,
        machine_offset_battuta_mm=120.0,
        machine_max_travel_mm=4000.0,
        stock_length_mm=6500.0
    )
    detector = ModeDetector(config)
    
    # Between 130mm and 250mm is out of quota
    mode = detector.detect(length_mm=200.0)
    
    assert mode.mode_name == "out_of_quota"
    assert mode.is_valid
    assert mode.warning_message


def test_mode_detector_extra_long():
    """Test extra long mode detection."""
    config = ModeConfig(
        machine_zero_homing_mm=250.0,
        machine_offset_battuta_mm=120.0,
        machine_max_travel_mm=4000.0,
        stock_length_mm=6500.0
    )
    detector = ModeDetector(config)
    
    mode = detector.detect(length_mm=4500.0)
    
    assert mode.mode_name == "extra_long"
    assert mode.is_valid
    assert mode.warning_message


def test_mode_detector_invalid_negative():
    """Test invalid negative length."""
    config = ModeConfig(
        machine_zero_homing_mm=250.0,
        machine_offset_battuta_mm=120.0,
        machine_max_travel_mm=4000.0,
        stock_length_mm=6500.0
    )
    detector = ModeDetector(config)
    
    mode = detector.detect(length_mm=-10.0)
    
    assert mode.mode_name == "invalid"
    assert not mode.is_valid
    assert mode.error_message


def test_mode_detector_invalid_too_long():
    """Test invalid length exceeding stock."""
    config = ModeConfig(
        machine_zero_homing_mm=250.0,
        machine_offset_battuta_mm=120.0,
        machine_max_travel_mm=4000.0,
        stock_length_mm=6500.0
    )
    detector = ModeDetector(config)
    
    mode = detector.detect(length_mm=7000.0)
    
    assert mode.mode_name == "invalid"
    assert not mode.is_valid
    assert mode.error_message


def test_mode_detector_boundary_ultra_short():
    """Test boundary at ultra short threshold."""
    config = ModeConfig(
        machine_zero_homing_mm=250.0,
        machine_offset_battuta_mm=120.0,
        machine_max_travel_mm=4000.0,
        stock_length_mm=6500.0
    )
    detector = ModeDetector(config)
    
    # Exactly at threshold (130mm)
    mode = detector.detect(length_mm=130.0)
    
    assert mode.is_valid
    # Should be ultra_short (<=)
    assert mode.mode_name == "ultra_short"


def test_mode_detector_boundary_out_of_quota():
    """Test boundary at zero homing."""
    config = ModeConfig(
        machine_zero_homing_mm=250.0,
        machine_offset_battuta_mm=120.0,
        machine_max_travel_mm=4000.0,
        stock_length_mm=6500.0
    )
    detector = ModeDetector(config)
    
    # Just below zero homing
    mode = detector.detect(length_mm=249.0)
    assert mode.mode_name == "out_of_quota"
    
    # At zero homing
    mode = detector.detect(length_mm=250.0)
    assert mode.mode_name == "normal"


def test_mode_detector_boundary_extra_long():
    """Test boundary at max travel."""
    config = ModeConfig(
        machine_zero_homing_mm=250.0,
        machine_offset_battuta_mm=120.0,
        machine_max_travel_mm=4000.0,
        stock_length_mm=6500.0
    )
    detector = ModeDetector(config)
    
    # At max travel
    mode = detector.detect(length_mm=4000.0)
    assert mode.mode_name == "normal"
    
    # Just over max travel
    mode = detector.detect(length_mm=4001.0)
    assert mode.mode_name == "extra_long"


def test_mode_detector_display_names(sample_mode_config):
    """Test mode display name conversion."""
    detector = ModeDetector(sample_mode_config)
    
    assert "Ultra Corta" in detector.get_mode_display_name("ultra_short")
    assert "Fuori Quota" in detector.get_mode_display_name("out_of_quota")
    assert "Normale" in detector.get_mode_display_name("normal")
    assert "Extra Lunga" in detector.get_mode_display_name("extra_long")
