"""
Cytron MD25HV Motor Driver Controller.

Controls DC motor via GPIO pins with PWM speed control, direction,
and enable/brake functionality. Includes smooth speed ramping and safety limits.

Hardware connections:
- GPIO 12: PWM speed control (0-100%)
- GPIO 13: Direction (0=forward, 1=reverse)
- GPIO 16: Enable/brake (1=enabled, 0=brake)
"""

import time
import threading
from typing import Optional
import logging

try:
    import pigpio
    PIGPIO_AVAILABLE = True
except ImportError:
    pigpio = None
    PIGPIO_AVAILABLE = False


class MD25HVDriver:
    """
    Driver for Cytron MD25HV motor controller.
    
    Features:
    - PWM-based speed control (0-100%)
    - Digital direction control
    - Enable/brake control
    - Smooth speed ramping to prevent mechanical shock
    - Safety limits and emergency stop
    """
    
    def __init__(
        self,
        pwm_gpio: int = 12,
        dir_gpio: int = 13,
        enable_gpio: int = 16,
        pwm_frequency: int = 20000,
        max_speed_percent: float = 100.0,
        ramp_time_s: float = 0.5
    ):
        """
        Initialize MD25HV motor driver.
        
        Args:
            pwm_gpio: GPIO pin for PWM speed control (default: 12)
            dir_gpio: GPIO pin for direction control (default: 13)
            enable_gpio: GPIO pin for enable/brake (default: 16)
            pwm_frequency: PWM frequency in Hz (default: 20kHz)
            max_speed_percent: Maximum allowed speed percentage (default: 100%)
            ramp_time_s: Time for speed ramping in seconds (default: 0.5s)
        """
        self.pwm_gpio = pwm_gpio
        self.dir_gpio = dir_gpio
        self.enable_gpio = enable_gpio
        self.pwm_frequency = pwm_frequency
        self.max_speed_percent = max_speed_percent
        self.ramp_time_s = ramp_time_s
        
        self._pi: Optional[object] = None
        self._connected = False
        self._current_speed = 0.0
        self._target_speed = 0.0
        self._current_direction = 0  # 0=forward, 1=reverse
        self._enabled = False
        self._emergency_stop = False
        
        self._lock = threading.Lock()
        self._ramp_thread: Optional[threading.Thread] = None
        self._ramp_active = False
        
        self.logger = logging.getLogger("blitz.md25hv")
        
        if not PIGPIO_AVAILABLE:
            self.logger.warning("pigpio not available - MD25HV driver in simulation mode")
            return
        
        try:
            self._pi = pigpio.pi()
            if not self._pi.connected:
                self.logger.error("Cannot connect to pigpiod daemon")
                self._pi = None
                return
            
            # Configure GPIO modes
            self._pi.set_mode(self.pwm_gpio, pigpio.OUTPUT)
            self._pi.set_mode(self.dir_gpio, pigpio.OUTPUT)
            self._pi.set_mode(self.enable_gpio, pigpio.OUTPUT)
            
            # Initialize to safe state
            self._pi.set_PWM_frequency(self.pwm_gpio, self.pwm_frequency)
            self._pi.set_PWM_dutycycle(self.pwm_gpio, 0)
            self._pi.write(self.dir_gpio, 0)
            self._pi.write(self.enable_gpio, 0)  # Start disabled
            
            self._connected = True
            self.logger.info(f"MD25HV initialized on GPIO {pwm_gpio}/{dir_gpio}/{enable_gpio}")
            
        except Exception as e:
            self.logger.error(f"MD25HV init failed: {e}")
            self._pi = None
    
    def is_connected(self) -> bool:
        """Check if driver is connected to hardware."""
        return self._connected and self._pi is not None
    
    def enable(self) -> bool:
        """
        Enable motor driver.
        
        Returns:
            True if successful
        """
        if self._emergency_stop:
            self.logger.warning("Cannot enable - emergency stop active")
            return False
        
        with self._lock:
            if self._pi:
                self._pi.write(self.enable_gpio, 1)
            self._enabled = True
            self.logger.info("Motor enabled")
        return True
    
    def disable(self) -> bool:
        """
        Disable motor driver (engages brake).
        
        Returns:
            True if successful
        """
        with self._lock:
            if self._pi:
                self._pi.write(self.enable_gpio, 0)
                self._pi.set_PWM_dutycycle(self.pwm_gpio, 0)
            self._enabled = False
            self._current_speed = 0.0
            self._target_speed = 0.0
            self.logger.info("Motor disabled")
        return True
    
    def set_direction(self, direction: int) -> bool:
        """
        Set motor direction.
        
        Args:
            direction: 0 for forward, 1 for reverse
            
        Returns:
            True if successful
        """
        if not self._enabled:
            self.logger.warning("Cannot set direction - motor disabled")
            return False
        
        with self._lock:
            direction = 1 if direction else 0
            if self._pi:
                self._pi.write(self.dir_gpio, direction)
            self._current_direction = direction
            self.logger.debug(f"Direction set to {'reverse' if direction else 'forward'}")
        return True
    
    def set_speed(self, speed_percent: float, smooth: bool = True) -> bool:
        """
        Set motor speed with optional ramping.
        
        Args:
            speed_percent: Speed as percentage (0-100, can be negative for reverse)
            smooth: If True, use smooth ramping; if False, change immediately
            
        Returns:
            True if successful
        """
        if self._emergency_stop:
            self.logger.warning("Cannot set speed - emergency stop active")
            return False
        
        # Handle negative speeds (reverse direction)
        if speed_percent < 0:
            direction = 1
            speed_percent = abs(speed_percent)
        else:
            direction = 0
        
        # Clamp to limits
        speed_percent = max(0.0, min(speed_percent, self.max_speed_percent))
        
        with self._lock:
            self._target_speed = speed_percent
            
            # Update direction if needed
            if direction != self._current_direction:
                self.set_direction(direction)
        
        if smooth and self.ramp_time_s > 0:
            # Start ramping thread if not already running
            if not self._ramp_active:
                self._ramp_active = True
                self._ramp_thread = threading.Thread(target=self._ramp_speed, daemon=True)
                self._ramp_thread.start()
        else:
            # Immediate change
            self._apply_speed(speed_percent)
        
        return True
    
    def _ramp_speed(self):
        """Internal thread for smooth speed ramping."""
        while self._ramp_active:
            with self._lock:
                if abs(self._current_speed - self._target_speed) < 1.0:
                    # Close enough - set to target and stop ramping
                    self._apply_speed(self._target_speed)
                    self._ramp_active = False
                    break
                
                # Calculate ramp step
                speed_diff = self._target_speed - self._current_speed
                ramp_step = (self.max_speed_percent / self.ramp_time_s) * 0.05  # 50ms steps
                
                if abs(speed_diff) < ramp_step:
                    new_speed = self._target_speed
                else:
                    new_speed = self._current_speed + (ramp_step if speed_diff > 0 else -ramp_step)
                
                self._apply_speed(new_speed)
            
            time.sleep(0.05)  # 50ms update rate
    
    def _apply_speed(self, speed_percent: float):
        """Apply speed to PWM output (must be called with lock held)."""
        if not self._enabled:
            return
        
        # Convert percentage to duty cycle (0-255)
        duty_cycle = int((speed_percent / 100.0) * 255)
        
        if self._pi:
            self._pi.set_PWM_dutycycle(self.pwm_gpio, duty_cycle)
        
        self._current_speed = speed_percent
    
    def stop(self, immediate: bool = False) -> bool:
        """
        Stop motor.
        
        Args:
            immediate: If True, stop without ramping; if False, ramp down
            
        Returns:
            True if successful
        """
        return self.set_speed(0.0, smooth=not immediate)
    
    def emergency_stop(self) -> bool:
        """
        Immediate emergency stop - disables motor and sets flag.
        
        Returns:
            True if successful
        """
        self.logger.warning("EMERGENCY STOP activated")
        self._emergency_stop = True
        self._ramp_active = False
        return self.disable()
    
    def reset_emergency(self) -> bool:
        """
        Reset emergency stop flag.
        
        Returns:
            True if successful
        """
        with self._lock:
            self._emergency_stop = False
            self.logger.info("Emergency stop reset")
        return True
    
    def get_state(self) -> dict:
        """
        Get current driver state.
        
        Returns:
            Dictionary with current state
        """
        return {
            "connected": self._connected,
            "enabled": self._enabled,
            "current_speed": self._current_speed,
            "target_speed": self._target_speed,
            "direction": "reverse" if self._current_direction else "forward",
            "emergency_stop": self._emergency_stop,
            "ramping": self._ramp_active
        }
    
    def close(self):
        """Close connection and cleanup resources."""
        self.logger.info("Closing MD25HV driver")
        self._ramp_active = False
        
        if self._ramp_thread and self._ramp_thread.is_alive():
            self._ramp_thread.join(timeout=1.0)
        
        self.disable()
        
        if self._pi:
            try:
                self._pi.stop()
            except Exception:
                pass
            finally:
                self._pi = None
                self._connected = False
    
    def __del__(self):
        """Cleanup on destruction."""
        self.close()
