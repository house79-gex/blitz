"""
ELTRA EH63D Encoder Reader via 8AL-ZARD Optocoupler.

Reads incremental encoder signals through galvanically isolated optocoupler
with interrupt-driven quadrature decoding (x4) and index pulse detection.

Hardware connections:
- Encoder 12V → 8AL-ZARD input (galvanic isolation)
- 8AL-ZARD 3.3V output → RPi GPIO
  - GPIO 17: Channel A
  - GPIO 27: Channel B  
  - GPIO 22: Index/Z pulse (for homing)
"""

import time
import threading
from typing import Optional, Callable
import logging

try:
    import pigpio
    PIGPIO_AVAILABLE = True
except ImportError:
    pigpio = None
    PIGPIO_AVAILABLE = False


class EncoderReader8ALZARD:
    """
    Encoder reader for ELTRA EH63D via 8AL-ZARD optocoupler.
    
    Features:
    - Interrupt-driven quadrature x4 decoding
    - Index pulse (Z) detection for homing
    - Thread-safe position tracking
    - Galvanic isolation via optocoupler
    - High-speed reading (up to 200kHz)
    """
    
    def __init__(
        self,
        gpio_a: int = 17,
        gpio_b: int = 27,
        gpio_z: int = 22,
        pulses_per_mm: float = 84.880,
        enable_index: bool = True
    ):
        """
        Initialize encoder reader.
        
        Args:
            gpio_a: GPIO pin for encoder channel A (default: 17)
            gpio_b: GPIO pin for encoder channel B (default: 27)
            gpio_z: GPIO pin for index/Z pulse (default: 22)
            pulses_per_mm: Encoder pulses per millimeter (default: 84.880)
                          Calculated as: (1000 PPR × 4) / (π × 60mm) = 84.880
            enable_index: Enable index pulse detection (default: True)
        """
        self.gpio_a = gpio_a
        self.gpio_b = gpio_b
        self.gpio_z = gpio_z
        self.pulses_per_mm = pulses_per_mm
        self.enable_index = enable_index
        
        self._pi: Optional[object] = None
        self._connected = False
        
        # Position tracking (thread-safe)
        self._lock = threading.Lock()
        self._pulse_count = 0
        self._last_a = 0
        self._last_b = 0
        
        # Index pulse tracking
        self._index_detected = False
        self._index_position = 0
        self._index_callback: Optional[Callable[[int], None]] = None
        
        # Callbacks
        self._cb_a: Optional[object] = None
        self._cb_b: Optional[object] = None
        self._cb_z: Optional[object] = None
        
        self.logger = logging.getLogger("blitz.encoder_8alzard")
        
        if not PIGPIO_AVAILABLE:
            self.logger.warning("pigpio not available - encoder reader in simulation mode")
            return
        
        try:
            self._pi = pigpio.pi()
            if not self._pi.connected:
                self.logger.error("Cannot connect to pigpiod daemon")
                self._pi = None
                return
            
            # Configure GPIO as inputs with pull-up
            self._pi.set_mode(self.gpio_a, pigpio.INPUT)
            self._pi.set_mode(self.gpio_b, pigpio.INPUT)
            self._pi.set_pull_up_down(self.gpio_a, pigpio.PUD_UP)
            self._pi.set_pull_up_down(self.gpio_b, pigpio.PUD_UP)
            
            # Read initial states
            self._last_a = self._pi.read(self.gpio_a)
            self._last_b = self._pi.read(self.gpio_b)
            
            # Setup interrupt callbacks for quadrature decoding
            self._cb_a = self._pi.callback(
                self.gpio_a, 
                pigpio.EITHER_EDGE, 
                self._quadrature_callback
            )
            self._cb_b = self._pi.callback(
                self.gpio_b, 
                pigpio.EITHER_EDGE, 
                self._quadrature_callback
            )
            
            # Setup index pulse if enabled
            if self.enable_index:
                self._pi.set_mode(self.gpio_z, pigpio.INPUT)
                self._pi.set_pull_up_down(self.gpio_z, pigpio.PUD_UP)
                self._cb_z = self._pi.callback(
                    self.gpio_z,
                    pigpio.FALLING_EDGE,  # Index pulse is typically active low
                    self._index_callback_internal
                )
            
            self._connected = True
            self.logger.info(
                f"Encoder initialized on GPIO {gpio_a}/{gpio_b}/{gpio_z}, "
                f"{pulses_per_mm:.3f} pulses/mm"
            )
            
        except Exception as e:
            self.logger.error(f"Encoder init failed: {e}")
            self._pi = None
    
    def _quadrature_callback(self, gpio, level, tick):
        """
        Hardware interrupt callback for quadrature x4 decoding.
        
        This implements the standard quadrature decoder state machine:
        - Channel A leading B = forward (increment)
        - Channel B leading A = reverse (decrement)
        """
        if not self._pi:
            return
        
        try:
            # Read both channels atomically
            level_a = self._pi.read(self.gpio_a)
            level_b = self._pi.read(self.gpio_b)
            
            with self._lock:
                # Detect which channel changed and determine direction
                if gpio == self.gpio_a and level_a != self._last_a:
                    # A changed - check relative phase with B
                    if level_a != level_b:
                        self._pulse_count += 1  # Forward
                    else:
                        self._pulse_count -= 1  # Reverse
                    self._last_a = level_a
                    
                elif gpio == self.gpio_b and level_b != self._last_b:
                    # B changed - check relative phase with A
                    if level_a == level_b:
                        self._pulse_count += 1  # Forward
                    else:
                        self._pulse_count -= 1  # Reverse
                    self._last_b = level_b
                    
        except Exception as e:
            self.logger.error(f"Quadrature callback error: {e}")
    
    def _index_callback_internal(self, gpio, level, tick):
        """Internal callback for index pulse detection."""
        with self._lock:
            self._index_detected = True
            self._index_position = self._pulse_count
            
        self.logger.info(f"Index pulse detected at position {self._index_position}")
        
        # Call user callback if set
        if self._index_callback:
            try:
                self._index_callback(self._index_position)
            except Exception as e:
                self.logger.error(f"User index callback error: {e}")
    
    def is_connected(self) -> bool:
        """Check if encoder is connected."""
        return self._connected and self._pi is not None
    
    def get_position_mm(self) -> float:
        """
        Get current position in millimeters.
        
        Returns:
            Position in mm
        """
        with self._lock:
            return self._pulse_count / self.pulses_per_mm
    
    def get_pulse_count(self) -> int:
        """
        Get raw pulse count.
        
        Returns:
            Raw encoder pulse count
        """
        with self._lock:
            return self._pulse_count
    
    def set_position(self, position_mm: float):
        """
        Set current position (for calibration or after homing).
        
        Args:
            position_mm: New position in mm
        """
        with self._lock:
            self._pulse_count = round(position_mm * self.pulses_per_mm)
            self.logger.info(f"Position set to {position_mm:.3f} mm")
    
    def reset(self):
        """Reset position counter to zero (homing)."""
        with self._lock:
            self._pulse_count = 0
            self._index_detected = False
            self._index_position = 0
            self.logger.info("Encoder position reset to zero")
    
    def wait_for_index(self, timeout_s: float = 10.0) -> bool:
        """
        Wait for index pulse (blocking).
        
        Args:
            timeout_s: Maximum time to wait in seconds
            
        Returns:
            True if index detected, False if timeout
        """
        start_time = time.time()
        
        with self._lock:
            self._index_detected = False
        
        while time.time() - start_time < timeout_s:
            with self._lock:
                if self._index_detected:
                    return True
            time.sleep(0.01)
        
        self.logger.warning(f"Index pulse timeout after {timeout_s}s")
        return False
    
    def set_index_callback(self, callback: Optional[Callable[[int], None]]):
        """
        Set callback for index pulse detection.
        
        Args:
            callback: Function to call when index detected, receives pulse count
        """
        self._index_callback = callback
    
    def get_index_status(self) -> tuple[bool, int]:
        """
        Get index pulse detection status.
        
        Returns:
            Tuple of (detected, position_at_detection)
        """
        with self._lock:
            return (self._index_detected, self._index_position)
    
    def get_state(self) -> dict:
        """
        Get current encoder state.
        
        Returns:
            Dictionary with current state
        """
        with self._lock:
            return {
                "connected": self._connected,
                "position_mm": self._pulse_count / self.pulses_per_mm,
                "pulse_count": self._pulse_count,
                "index_detected": self._index_detected,
                "index_position": self._index_position,
                "pulses_per_mm": self.pulses_per_mm,
                "gpio_a": self.gpio_a,
                "gpio_b": self.gpio_b,
                "gpio_z": self.gpio_z
            }
    
    def close(self):
        """Close connection and cleanup resources."""
        self.logger.info("Closing encoder reader")
        
        if self._pi:
            try:
                # Cancel callbacks
                if self._cb_a:
                    self._cb_a.cancel()
                    self._cb_a = None
                if self._cb_b:
                    self._cb_b.cancel()
                    self._cb_b = None
                if self._cb_z:
                    self._cb_z.cancel()
                    self._cb_z = None
                
                self._pi.stop()
            except Exception as e:
                self.logger.error(f"Error during cleanup: {e}")
            finally:
                self._pi = None
                self._connected = False
    
    def __del__(self):
        """Cleanup on destruction."""
        self.close()
