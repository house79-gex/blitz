"""Performance tests for mode detection."""

import pytest
import time
from qt6_app.ui_qt.logic.modes.mode_detector import ModeDetector
from qt6_app.ui_qt.logic.modes.mode_config import ModeConfig


@pytest.mark.performance
def test_mode_detection_speed():
    """Test mode detection completes quickly."""
    config = ModeConfig(
        machine_zero_homing_mm=250.0,
        machine_offset_battuta_mm=120.0,
        machine_max_travel_mm=4000.0,
        stock_length_mm=6500.0
    )
    detector = ModeDetector(config)
    
    # Test various lengths
    test_lengths = [100, 200, 500, 1000, 2000, 3000, 4000, 5000, 6000]
    
    start = time.time()
    for length in test_lengths:
        mode = detector.detect(length)
    elapsed = time.time() - start
    
    # Should complete 9 detections in < 0.1 seconds
    assert elapsed < 0.1


@pytest.mark.performance
def test_mode_detection_bulk():
    """Test bulk mode detection performance."""
    config = ModeConfig(
        machine_zero_homing_mm=250.0,
        machine_offset_battuta_mm=120.0,
        machine_max_travel_mm=4000.0,
        stock_length_mm=6500.0
    )
    detector = ModeDetector(config)
    
    # Test 1000 detections
    start = time.time()
    for i in range(1000):
        length = 100 + (i * 5)  # 100mm to 5100mm
        if length <= 6500:
            mode = detector.detect(length)
    elapsed = time.time() - start
    
    # Should complete 1000 detections in < 1 second
    assert elapsed < 1.0


@pytest.mark.performance
def test_mode_config_creation_speed():
    """Test mode config creation is fast."""
    start = time.time()
    
    for i in range(100):
        config = ModeConfig(
            machine_zero_homing_mm=250.0,
            machine_offset_battuta_mm=120.0,
            machine_max_travel_mm=4000.0,
            stock_length_mm=6500.0
        )
    
    elapsed = time.time() - start
    
    # Should create 100 configs in < 0.1 seconds
    assert elapsed < 0.1
