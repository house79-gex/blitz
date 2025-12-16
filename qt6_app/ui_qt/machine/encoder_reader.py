"""
Encoder Reader for GPIO-based position feedback.
Supports quadrature x4 decoding with hardware interrupts via pigpio.
"""
import logging
from typing import Optional

try:
    import pigpio
    PIGPIO_AVAILABLE = True
except ImportError:
    pigpio = None
    PIGPIO_AVAILABLE = False


class EncoderReader:
    """Reads incremental encoder via GPIO with quadrature x4 decoding."""
    
    def __init__(self, gpio_a: int = 17, gpio_b: int = 18, mm_per_pulse: float = 0.047125):
        """
        Initialize encoder reader.
        
        Args:
            gpio_a: GPIO pin for encoder channel A
            gpio_b: GPIO pin for encoder channel B
            mm_per_pulse: Millimeters per pulse (from transmission config)
        """
        self.gpio_a = gpio_a
        self.gpio_b = gpio_b
        self.mm_per_pulse = mm_per_pulse
        
        self._pulse_count = 0
        self._last_a = 0
        self._last_b = 0
        self._pi = None
        self._connected = False
        self._cb_a = None
        self._cb_b = None
        
        self.logger = logging.getLogger("blitz.encoder")
        
        if not PIGPIO_AVAILABLE:
            self.logger.warning("pigpio not available")
            return
        
        try:
            self._pi = pigpio.pi()
            if not self._pi.connected:
                self.logger.error("Cannot connect to pigpiod daemon")
                self._pi = None
                return
            
            self._pi.set_mode(self.gpio_a, pigpio.INPUT)
            self._pi.set_mode(self.gpio_b, pigpio.INPUT)
            self._pi.set_pull_up_down(self.gpio_a, pigpio.PUD_UP)
            self._pi.set_pull_up_down(self.gpio_b, pigpio.PUD_UP)
            
            self._last_a = self._pi.read(self.gpio_a)
            self._last_b = self._pi.read(self.gpio_b)
            
            self._cb_a = self._pi.callback(self.gpio_a, pigpio.EITHER_EDGE, self._pulse_callback)
            self._cb_b = self._pi.callback(self.gpio_b, pigpio.EITHER_EDGE, self._pulse_callback)
            
            self._connected = True
            self.logger.info(f"Encoder initialized on GPIO{gpio_a}/{gpio_b}")
            
        except Exception as e:
            self.logger.error(f"Encoder init failed: {e}")
            self._pi = None
    
    def _pulse_callback(self, gpio, level, tick):
        """Hardware interrupt callback for quadrature decoding."""
        if not self._pi:
            return
        
        try:
            level_a = self._pi.read(self.gpio_a)
            level_b = self._pi.read(self.gpio_b)
            
            if gpio == self.gpio_a and level_a != self._last_a:
                self._pulse_count += 1 if level_a != level_b else -1
                self._last_a = level_a
            elif gpio == self.gpio_b and level_b != self._last_b:
                self._pulse_count += 1 if level_a == level_b else -1
                self._last_b = level_b
        except Exception:
            pass
    
    def is_connected(self) -> bool:
        """Check if encoder is connected."""
        return self._connected and self._pi is not None
    
    def get_position_mm(self) -> Optional[float]:
        """Get current position in mm."""
        if not self.is_connected():
            return None
        return self._pulse_count * self.mm_per_pulse
    
    def get_pulse_count(self) -> int:
        """Get raw pulse count."""
        return self._pulse_count
    
    def reset(self):
        """Reset position counter (homing)."""
        self._pulse_count = 0
        self.logger.info("Encoder reset")
    
    def set_position(self, position_mm: float):
        """Set current position (calibration)."""
        self._pulse_count = round(position_mm / self.mm_per_pulse)
    
    def close(self):
        """Close connection and free resources."""
        if self._pi:
            try:
                if self._cb_a:
                    self._cb_a.cancel()
                    self._cb_a = None
                if self._cb_b:
                    self._cb_b.cancel()
                    self._cb_b = None
                self._pi.stop()
            except Exception:
                pass
            finally:
                self._pi = None
                self._connected = False
    
    def __del__(self):
        self.close()
