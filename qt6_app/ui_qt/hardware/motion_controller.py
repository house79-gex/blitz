"""
Motion Controller with PID closed-loop control.

Manages precise positioning using PID feedback control with encoder position
feedback and motor driver output. Includes safety features and soft limits.

Features:
- PID control for ±0.5mm accuracy
- Soft limit enforcement
- Emergency stop handling
- Smooth motion profiles
- Homing sequences
"""

import time
import threading
from typing import Optional, Callable
import logging

try:
    from simple_pid import PID
    PID_AVAILABLE = True
except ImportError:
    PID = None
    PID_AVAILABLE = False

from .md25hv_driver import MD25HVDriver
from .encoder_reader_8alzard import EncoderReader8ALZARD


class MotionController:
    """
    PID-based motion controller for precise positioning.
    
    Combines motor driver output with encoder feedback to achieve
    accurate position control with software safety limits.
    """
    
    def __init__(
        self,
        motor: MD25HVDriver,
        encoder: EncoderReader8ALZARD,
        min_position_mm: float = 250.0,
        max_position_mm: float = 4000.0,
        pid_kp: float = 2.0,
        pid_ki: float = 0.5,
        pid_kd: float = 0.1,
        position_tolerance_mm: float = 0.5,
        max_speed_percent: float = 80.0,
        control_loop_hz: float = 50.0
    ):
        """
        Initialize motion controller.
        
        Args:
            motor: MD25HV motor driver instance
            encoder: Encoder reader instance
            min_position_mm: Minimum allowed position (soft limit)
            max_position_mm: Maximum allowed position (soft limit)
            pid_kp: PID proportional gain
            pid_ki: PID integral gain
            pid_kd: PID derivative gain
            position_tolerance_mm: Position accuracy tolerance
            max_speed_percent: Maximum speed for PID output
            control_loop_hz: PID control loop frequency
        """
        self.motor = motor
        self.encoder = encoder
        self.min_position_mm = min_position_mm
        self.max_position_mm = max_position_mm
        self.position_tolerance_mm = position_tolerance_mm
        self.max_speed_percent = max_speed_percent
        self.control_loop_hz = control_loop_hz
        
        self.logger = logging.getLogger("blitz.motion_controller")
        
        # PID controller
        if not PID_AVAILABLE:
            self.logger.error("simple-pid not available - motion controller disabled")
            self._pid = None
        else:
            self._pid = PID(
                Kp=pid_kp,
                Ki=pid_ki,
                Kd=pid_kd,
                setpoint=0,
                output_limits=(-max_speed_percent, max_speed_percent),
                sample_time=1.0/control_loop_hz
            )
        
        # State
        self._lock = threading.Lock()
        self._target_position_mm: Optional[float] = None
        self._moving = False
        self._homing = False
        self._emergency_stop = False
        self._closed = False
        
        # Control loop thread
        self._control_thread: Optional[threading.Thread] = None
        self._control_running = False
        
        # Callbacks
        self._move_complete_callback: Optional[Callable[[bool, str], None]] = None
        self._homing_complete_callback: Optional[Callable[[bool, str], None]] = None
        
        self.logger.info(
            f"Motion controller initialized: "
            f"range {min_position_mm}-{max_position_mm}mm, "
            f"PID(Kp={pid_kp}, Ki={pid_ki}, Kd={pid_kd})"
        )
    
    def start(self) -> bool:
        """
        Start motion control loop.
        
        Returns:
            True if successful
        """
        if not PID_AVAILABLE:
            self.logger.error("Cannot start - PID library not available")
            return False
        
        if not self.motor.is_connected() or not self.encoder.is_connected():
            self.logger.error("Cannot start - motor or encoder not connected")
            return False
        
        if self._control_running:
            self.logger.warning("Control loop already running")
            return True
        
        self._control_running = True
        self._control_thread = threading.Thread(target=self._control_loop, daemon=True)
        self._control_thread.start()
        
        self.logger.info("Motion control loop started")
        return True
    
    def stop(self):
        """Stop motion control loop."""
        self._control_running = False
        if self._control_thread:
            self._control_thread.join(timeout=2.0)
            self._control_thread = None
        
        self.motor.stop()
        self.logger.info("Motion control loop stopped")
    
    def _control_loop(self):
        """Main PID control loop (runs in separate thread)."""
        loop_period = 1.0 / self.control_loop_hz
        
        while self._control_running:
            start_time = time.time()
            
            try:
                with self._lock:
                    if self._emergency_stop:
                        # Emergency stop - halt immediately
                        self.motor.emergency_stop()
                        self._moving = False
                        self._homing = False
                        continue
                    
                    if not self._moving and not self._homing:
                        # Idle - ensure motor is stopped
                        if self.motor.get_state()["current_speed"] > 0:
                            self.motor.stop()
                        continue
                    
                    # Get current position from encoder
                    current_position = self.encoder.get_position_mm()
                    
                    if current_position is None:
                        self.logger.error("Cannot read encoder position")
                        self._moving = False
                        self._homing = False
                        continue
                    
                    # Check soft limits
                    if current_position < self.min_position_mm:
                        self.logger.error(f"Soft limit violation: {current_position:.2f} < {self.min_position_mm}")
                        self._emergency_stop = True
                        self._call_move_complete_callback(False, "Soft limit (min)")
                        continue
                    
                    if current_position > self.max_position_mm:
                        self.logger.error(f"Soft limit violation: {current_position:.2f} > {self.max_position_mm}")
                        self._emergency_stop = True
                        self._call_move_complete_callback(False, "Soft limit (max)")
                        continue
                    
                    if self._target_position_mm is None:
                        continue
                    
                    # Calculate position error
                    error = self._target_position_mm - current_position
                    
                    # Check if at target
                    if abs(error) < self.position_tolerance_mm:
                        if self._moving:
                            self.motor.stop()
                            self._moving = False
                            self.logger.info(f"Target reached: {current_position:.3f}mm")
                            self._call_move_complete_callback(True, "Target reached")
                        
                        if self._homing:
                            self._homing = False
                            self.logger.info("Homing complete")
                            self._call_homing_complete_callback(True, "Homing complete")
                        
                        continue
                    
                    # Update PID setpoint and get output
                    self._pid.setpoint = self._target_position_mm
                    speed_output = self._pid(current_position)
                    
                    # Apply speed to motor
                    if not self.motor.get_state()["enabled"]:
                        self.motor.enable()
                    
                    self.motor.set_speed(speed_output, smooth=False)
                    
            except Exception as e:
                self.logger.error(f"Control loop error: {e}")
            
            # Maintain loop rate
            elapsed = time.time() - start_time
            sleep_time = max(0, loop_period - elapsed)
            time.sleep(sleep_time)
    
    def move_to(
        self, 
        position_mm: float, 
        callback: Optional[Callable[[bool, str], None]] = None
    ) -> bool:
        """
        Move to target position.
        
        Args:
            position_mm: Target position in mm
            callback: Optional callback when move completes (success, message)
            
        Returns:
            True if move started successfully
        """
        if self._emergency_stop:
            self.logger.error("Cannot move - emergency stop active")
            return False
        
        if not self._control_running:
            self.logger.error("Cannot move - control loop not running")
            return False
        
        # Check soft limits
        if position_mm < self.min_position_mm or position_mm > self.max_position_mm:
            self.logger.error(
                f"Target position {position_mm:.2f}mm outside limits "
                f"[{self.min_position_mm}-{self.max_position_mm}]"
            )
            return False
        
        with self._lock:
            self._target_position_mm = position_mm
            self._moving = True
            self._move_complete_callback = callback
            
            # Reset PID
            if self._pid:
                self._pid.reset()
        
        self.logger.info(f"Moving to {position_mm:.3f}mm")
        return True
    
    def stop_motion(self, immediate: bool = True):
        """
        Stop current motion.
        
        Args:
            immediate: If True, stop immediately; if False, decelerate smoothly
        """
        with self._lock:
            self._moving = False
            self._homing = False
            self._target_position_mm = None
        
        self.motor.stop(immediate=immediate)
        self.logger.info("Motion stopped")
    
    def do_homing(
        self, 
        callback: Optional[Callable[[bool, str], None]] = None,
        use_index: bool = True
    ) -> bool:
        """
        Perform homing sequence.
        
        If use_index is True, searches for encoder index pulse.
        Otherwise, moves to minimum position.
        
        Args:
            callback: Optional callback when homing completes
            use_index: Use encoder index pulse for precise homing
            
        Returns:
            True if homing started successfully
        """
        if self._emergency_stop:
            self.logger.error("Cannot home - emergency stop active")
            return False
        
        if not self._control_running:
            self.logger.error("Cannot home - control loop not running")
            return False
        
        self.logger.info(f"Starting homing sequence (index={use_index})")
        
        with self._lock:
            self._homing = True
            self._homing_complete_callback = callback
        
        if use_index and self.encoder.enable_index:
            # Start homing with index pulse detection
            def index_detected(pulse_count):
                self.logger.info(f"Homing index pulse detected at {pulse_count}")
                # Set this as home position
                self.encoder.set_position(self.min_position_mm)
                with self._lock:
                    self._target_position_mm = self.min_position_mm
            
            self.encoder.set_index_callback(index_detected)
            
            # Move slowly backward to find index
            with self._lock:
                self._target_position_mm = self.min_position_mm - 10.0  # Move back slightly
        else:
            # Simple homing - move to min position
            with self._lock:
                self._target_position_mm = self.min_position_mm
        
        return True
    
    def emergency_stop(self):
        """Activate emergency stop."""
        self.logger.warning("EMERGENCY STOP activated")
        with self._lock:
            self._emergency_stop = True
        self.motor.emergency_stop()
    
    def reset_emergency(self) -> bool:
        """
        Reset emergency stop.
        
        Returns:
            True if successful
        """
        with self._lock:
            self._emergency_stop = False
        
        self.motor.reset_emergency()
        self.logger.info("Emergency stop reset")
        return True
    
    def is_moving(self) -> bool:
        """Check if currently moving."""
        with self._lock:
            return self._moving or self._homing
    
    def get_position(self) -> Optional[float]:
        """Get current position from encoder."""
        return self.encoder.get_position_mm()
    
    def get_target(self) -> Optional[float]:
        """Get current target position."""
        with self._lock:
            return self._target_position_mm
    
    def set_pid_params(self, kp: float, ki: float, kd: float):
        """
        Update PID parameters.
        
        Args:
            kp: Proportional gain
            ki: Integral gain
            kd: Derivative gain
        """
        if self._pid:
            self._pid.Kp = kp
            self._pid.Ki = ki
            self._pid.Kd = kd
            self.logger.info(f"PID parameters updated: Kp={kp}, Ki={ki}, Kd={kd}")
    
    def _call_move_complete_callback(self, success: bool, message: str):
        """Internal helper to call move complete callback."""
        if self._move_complete_callback:
            try:
                self._move_complete_callback(success, message)
            except Exception as e:
                self.logger.error(f"Move complete callback error: {e}")
    
    def _call_homing_complete_callback(self, success: bool, message: str):
        """Internal helper to call homing complete callback."""
        if self._homing_complete_callback:
            try:
                self._homing_complete_callback(success, message)
            except Exception as e:
                self.logger.error(f"Homing complete callback error: {e}")
    
    def get_state(self) -> dict:
        """
        Get current controller state.
        
        Returns:
            Dictionary with current state
        """
        with self._lock:
            return {
                "control_running": self._control_running,
                "moving": self._moving,
                "homing": self._homing,
                "emergency_stop": self._emergency_stop,
                "current_position": self.encoder.get_position_mm(),
                "target_position": self._target_position_mm,
                "position_error": (
                    abs(self._target_position_mm - self.encoder.get_position_mm())
                    if self._target_position_mm is not None
                    else None
                ),
                "motor_state": self.motor.get_state(),
                "encoder_state": self.encoder.get_state()
            }
    
    def close(self):
        """Close controller and cleanup resources."""
        self.logger.info("Closing motion controller")
        self._closed = True
        self.stop()
        # Note: Don't close motor/encoder here as they may be used elsewhere
    
    def __del__(self):
        """Cleanup on destruction."""
        if not self._closed:
            self.close()
