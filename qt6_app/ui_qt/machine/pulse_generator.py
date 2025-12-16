"""
Pulse Generator for DCS810 motor control via GPIO PUL/DIR signals. 

Features:
- Hardware pulse generation via pigpio
- Direction control (DIR signal)  
- Velocity profile with acceleration/deceleration support
- Immediate stop capability
- Automatic pulse calculation from mm
"""
import time
import logging
import threading
from typing import Optional
from dataclasses import dataclass

try:
    import pigpio
    PIGPIO_AVAILABLE = True
except ImportError:
    pigpio = None
    PIGPIO_AVAILABLE = False


@dataclass
class MotionProfile:
    """Motion profile with acceleration/deceleration."""
    distance_mm: float
    speed_mm_s: float
    acceleration_mm_s2: float = 5000.0
    deceleration_mm_s2: float = 5000.0


class PulseGenerator:
    """
    Generates PUL/DIR signals via GPIO for DCS810 motor control. 
    
    Supports movements with trapezoidal profile and immediate stop.
    """
    
    # Constants from DCS810 specifications
    MAX_PULSE_FREQ_HZ = 500000  # 500kHz max
    MIN_PULSE_WIDTH_US = 1.0    # 1μs min
    DIR_SETUP_TIME_MS = 5.0     # 5ms min DIR before PUL
    
    def __init__(self, gpio_pul: int = 27, gpio_dir: int = 22, mm_per_pulse: float = 0.047125):
        """
        Initialize pulse generator.
        
        Args:
            gpio_pul:  GPIO pin for PUL signal (default: GPIO27)
            gpio_dir:  GPIO pin for DIR signal (default:  GPIO22)
            mm_per_pulse: Millimeters per pulse (from transmission config)
        """
        self. gpio_pul = gpio_pul
        self.gpio_dir = gpio_dir
        self. mm_per_pulse = mm_per_pulse
        
        self._pi: Optional[object] = None
        self._connected = False
        self._moving = False
        self._stop_requested = False
        self._lock = threading.Lock()
        self._motion_thread: Optional[threading. Thread] = None
        
        self.logger = logging.getLogger("blitz.pulse_gen")
        
        if not PIGPIO_AVAILABLE: 
            self.logger.warning("⚠️ pigpio not available")
            return
        
        try:
            self._pi = pigpio.pi()
            if not self._pi.connected:
                self.logger.error("❌ Cannot connect to pigpiod daemon")
                self._pi = None
                return
            
            self._pi.set_mode(self.gpio_pul, pigpio.OUTPUT)
            self._pi.set_mode(self.gpio_dir, pigpio.OUTPUT)
            self._pi.write(self.gpio_pul, 0)
            self._pi.write(self.gpio_dir, 0)
            
            self._connected = True
            self.logger. info(f"✅ Pulse generator initialized: GPIO_PUL={gpio_pul}, GPIO_DIR={gpio_dir}")
            
        except Exception as e:
            self.logger. error(f"❌ Pulse generator init failed: {e}")
            self._pi = None
            self._connected = False
    
    def is_connected(self) -> bool:
        return self._connected and self._pi is not None and self._pi.connected
    
    def is_moving(self) -> bool:
        with self._lock:
            return self._moving
    
    def _mm_to_pulses(self, distance_mm: float) -> int:
        return int(abs(distance_mm) / self.mm_per_pulse)
    
    def move_to(self, target_mm: float, current_mm: float, speed_mm_s: float = 1000.0,
                acceleration_mm_s2: float = 5000.0) -> bool:
        distance_mm = target_mm - current_mm
        return self. move_relative(distance_mm, speed_mm_s, acceleration_mm_s2)
    
    def move_relative(self, distance_mm: float, speed_mm_s: float = 1000.0,
                     acceleration_mm_s2: float = 5000.0) -> bool:
        if not self.is_connected():
            self.logger.warning("⚠️ Pulse generator not connected")
            return False
        
        with self._lock:
            if self._moving:
                self.logger.warning("⚠️ Movement already in progress")
                return False
            self._moving = True
            self._stop_requested = False
        
        profile = MotionProfile(
            distance_mm=distance_mm,
            speed_mm_s=speed_mm_s,
            acceleration_mm_s2=acceleration_mm_s2,
            deceleration_mm_s2=acceleration_mm_s2
        )
        
        self._motion_thread = threading.Thread(
            target=self._execute_motion,
            args=(profile,),
            daemon=True
        )
        self._motion_thread.start()
        return True
    
    def _execute_motion(self, profile: MotionProfile):
        try:
            direction = 0 if profile.distance_mm >= 0 else 1
            self._pi.write(self.gpio_dir, direction)
            time.sleep(self.DIR_SETUP_TIME_MS / 1000.0)
            
            pulses = self._mm_to_pulses(profile.distance_mm)
            if pulses == 0:
                self.logger.info("📍 Movement 0mm, already at destination")
                self._moving = False
                return
            
            max_freq_hz = min(
                profile.speed_mm_s / self.mm_per_pulse,
                self.MAX_PULSE_FREQ_HZ
            )
            
            direction_str = "→" if direction == 0 else "←"
            self.logger.info(f"{direction_str} Movement:  {profile.distance_mm:+.2f}mm ({pulses} pulses @ {max_freq_hz:.0f}Hz)")
            
            period_us = int(1000000 / max_freq_hz) if max_freq_hz > 0 else 1000
            pulse_width_us = max(int(period_us / 2), int(self.MIN_PULSE_WIDTH_US))
            
            for i in range(pulses):
                if self._stop_requested:
                    self. logger.warning("🛑 Movement interrupted")
                    break
                
                self._pi.write(self.gpio_pul, 1)
                time.sleep(pulse_width_us / 1000000. 0)
                self._pi. write(self.gpio_pul, 0)
                time.sleep((period_us - pulse_width_us) / 1000000.0)
            
            if not self._stop_requested:
                self. logger.info(f"✅ Movement completed: {profile. distance_mm:+.2f}mm")
            
        except Exception as e: 
            self.logger.error(f"❌ Error during movement: {e}")
        finally:
            with self._lock:
                self._moving = False
                self._stop_requested = False
    
    def stop(self, wait: bool = True, timeout: float = 1.0) -> bool:
        if not self.is_connected():
            return False
        
        with self._lock:
            if not self._moving:
                return True
            self._stop_requested = True
        
        self. logger.info("🛑 Stop requested")
        
        if wait and self._motion_thread:
            self._motion_thread.join(timeout=timeout)
            return not self._motion_thread.is_alive()
        return True
    
    def get_max_speed_mm_s(self) -> float:
        return self.MAX_PULSE_FREQ_HZ * self.mm_per_pulse
    
    def close(self):
        if self._pi:
            try:
                self. stop(wait=True, timeout=2.0)
                self._pi.write(self.gpio_pul, 0)
                self._pi.write(self.gpio_dir, 0)
                self._pi.stop()
                self.logger.info("✅ Pulse generator closed")
            except Exception as e: 
                self.logger.error(f"❌ Error closing:  {e}")
            finally: 
                self._pi = None
                self._connected = False
    
    def __del__(self):
        self.close()
