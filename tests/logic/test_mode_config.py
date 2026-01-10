"""Unit tests for mode configuration."""

import pytest
from qt6_app.ui_qt.logic.modes.mode_config import ModeConfig, ModeRange


def test_mode_config_initialization():
    """Test mode config creates with valid parameters."""
    config = ModeConfig(
        machine_zero_homing_mm=250.0,
        machine_offset_battuta_mm=120.0,
        machine_max_travel_mm=4000.0,
        stock_length_mm=6500.0
    )
    
    assert config.machine_zero_homing_mm == 250.0
    assert config.machine_offset_battuta_mm == 120.0
    assert config.machine_max_travel_mm == 4000.0
    assert config.stock_length_mm == 6500.0


def test_mode_config_ultra_short_threshold():
    """Test ultra short threshold calculation."""
    config = ModeConfig(
        machine_zero_homing_mm=250.0,
        machine_offset_battuta_mm=120.0,
        machine_max_travel_mm=4000.0,
        stock_length_mm=6500.0
    )
    
    # Threshold = zero - offset = 250 - 120 = 130
    assert config.ultra_short_threshold == 130.0


def test_mode_config_invalid_zero_homing():
    """Test validation of invalid zero homing."""
    with pytest.raises(ValueError, match="machine_zero_homing_mm must be > 0"):
        ModeConfig(
            machine_zero_homing_mm=0.0,
            machine_offset_battuta_mm=120.0,
            machine_max_travel_mm=4000.0,
            stock_length_mm=6500.0
        )


def test_mode_config_invalid_offset():
    """Test validation of invalid offset."""
    with pytest.raises(ValueError, match="machine_offset_battuta_mm must be > 0"):
        ModeConfig(
            machine_zero_homing_mm=250.0,
            machine_offset_battuta_mm=0.0,
            machine_max_travel_mm=4000.0,
            stock_length_mm=6500.0
        )


def test_mode_config_offset_exceeds_zero():
    """Test validation of offset >= zero."""
    with pytest.raises(ValueError, match="machine_offset_battuta_mm must be <"):
        ModeConfig(
            machine_zero_homing_mm=250.0,
            machine_offset_battuta_mm=300.0,
            machine_max_travel_mm=4000.0,
            stock_length_mm=6500.0
        )


def test_mode_config_invalid_max_travel():
    """Test validation of invalid max travel."""
    with pytest.raises(ValueError, match="machine_max_travel_mm must be >"):
        ModeConfig(
            machine_zero_homing_mm=250.0,
            machine_offset_battuta_mm=120.0,
            machine_max_travel_mm=200.0,
            stock_length_mm=6500.0
        )


def test_mode_config_from_settings():
    """Test loading config from settings dict."""
    settings = {
        "machine_zero_homing_mm": 250.0,
        "machine_offset_battuta_mm": 120.0,
        "machine_max_travel_mm": 4000.0,
        "stock_length_mm": 6500.0,
    }
    
    config = ModeConfig.from_settings(settings)
    
    assert config.machine_zero_homing_mm == 250.0
    assert config.machine_offset_battuta_mm == 120.0
    assert config.machine_max_travel_mm == 4000.0
    assert config.stock_length_mm == 6500.0


def test_mode_config_to_settings_dict():
    """Test converting config to settings dict."""
    config = ModeConfig(
        machine_zero_homing_mm=250.0,
        machine_offset_battuta_mm=120.0,
        machine_max_travel_mm=4000.0,
        stock_length_mm=6500.0
    )
    
    settings = config.to_settings_dict()
    
    assert settings["machine_zero_homing_mm"] == 250.0
    assert settings["machine_offset_battuta_mm"] == 120.0
    assert settings["machine_max_travel_mm"] == 4000.0
    assert settings["stock_length_mm"] == 6500.0


def test_mode_config_get_range_ultra_short():
    """Test getting ultra short range."""
    config = ModeConfig(
        machine_zero_homing_mm=250.0,
        machine_offset_battuta_mm=120.0,
        machine_max_travel_mm=4000.0,
        stock_length_mm=6500.0
    )
    
    range_obj = config.get_range_ultra_short()
    
    assert range_obj.min_mm == 0.0
    assert range_obj.max_mm == 130.0
    assert range_obj.name == "ultra_short"
    assert range_obj.requires_confirmation


def test_mode_config_get_range_normal():
    """Test getting normal range."""
    config = ModeConfig(
        machine_zero_homing_mm=250.0,
        machine_offset_battuta_mm=120.0,
        machine_max_travel_mm=4000.0,
        stock_length_mm=6500.0
    )
    
    range_obj = config.get_range_normal()
    
    assert range_obj.min_mm == 250.0
    assert range_obj.max_mm == 4000.0
    assert range_obj.name == "normal"
    assert not range_obj.requires_confirmation


def test_mode_range_contains():
    """Test ModeRange.contains method."""
    range_obj = ModeRange(
        min_mm=100.0,
        max_mm=200.0,
        name="test",
        color="green"
    )
    
    assert range_obj.contains(150.0)
    assert range_obj.contains(100.0)
    assert range_obj.contains(200.0)
    assert not range_obj.contains(50.0)
    assert not range_obj.contains(250.0)
