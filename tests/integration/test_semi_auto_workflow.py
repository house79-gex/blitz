"""Integration tests for semi-auto workflow."""

import pytest
from unittest.mock import Mock, patch, MagicMock


@pytest.mark.integration
def test_mode_system_integration(sample_mode_config):
    """Test mode system components work together."""
    from qt6_app.ui_qt.logic.modes.mode_detector import ModeDetector
    from qt6_app.ui_qt.logic.modes.mode_config import ModeConfig
    
    # Test that config and detector work together
    config = ModeConfig(
        machine_zero_homing_mm=250.0,
        machine_offset_battuta_mm=120.0,
        machine_max_travel_mm=4000.0,
        stock_length_mm=6500.0
    )
    detector = ModeDetector(config)
    
    # Test various lengths produce correct modes
    ultra_short = detector.detect(100.0)
    assert ultra_short.mode_name == "ultra_short"
    assert ultra_short.is_valid
    
    out_of_quota = detector.detect(200.0)
    assert out_of_quota.mode_name == "out_of_quota"
    assert out_of_quota.is_valid
    
    normal = detector.detect(1000.0)
    assert normal.mode_name == "normal"
    assert normal.is_valid
    
    extra_long = detector.detect(5000.0)
    assert extra_long.mode_name == "extra_long"
    assert extra_long.is_valid


@pytest.mark.integration
def test_mode_range_integration(sample_mode_config):
    """Test mode ranges integrate correctly with config."""
    from qt6_app.ui_qt.logic.modes.mode_config import ModeConfig
    
    config = ModeConfig(
        machine_zero_homing_mm=250.0,
        machine_offset_battuta_mm=120.0,
        machine_max_travel_mm=4000.0,
        stock_length_mm=6500.0
    )
    
    # Get all ranges
    ultra_short_range = config.get_range_ultra_short()
    out_of_quota_range = config.get_range_out_of_quota()
    normal_range = config.get_range_normal()
    extra_long_range = config.get_range_extra_long()
    
    # Test that ranges don't overlap
    assert ultra_short_range.max_mm <= out_of_quota_range.min_mm
    assert out_of_quota_range.max_mm <= normal_range.min_mm
    assert normal_range.max_mm <= extra_long_range.min_mm
    
    # Test that ranges cover expected values
    assert ultra_short_range.contains(100.0)
    assert out_of_quota_range.contains(200.0)
    assert normal_range.contains(1000.0)
    assert extra_long_range.contains(5000.0)
