from __future__ import annotations
import time
import threading
import json
import os
from typing import Dict, Any, Optional, List, Callable
from ui_qt.machine.interfaces import MachineIO
from ui_qt.machine.rs485_modbus import ModbusRTUClient

# Import new hardware stack
try:
    from ui_qt.hardware.md25hv_driver import MD25HVDriver
    from ui_qt.hardware.encoder_reader_8alzard import EncoderReader8ALZARD
    from ui_qt.hardware.motion_controller import MotionController
    HARDWARE_STACK_AVAILABLE = True
except ImportError:
    HARDWARE_STACK_AVAILABLE = False

try:
    import pigpio
except Exception:
    pigpio = None

class RealMachine(MachineIO):
    """
    Implementazione macchina reale con nuovo stack di controllo movimento:
    - Cytron MD25HV: controllo motore via PWM
    - 8AL-ZARD + ELTRA EH63D: encoder con isolamento galvanico
    - MotionController: controllo PID closed-loop
    - RS485 Modbus: I/O freno/frizione/morse/inibizioni (invariato)
    """

    def __init__(
        self,
        serial_port: str = "/dev/ttyUSB0",
        rs485_addr_a: int = 1,
        rs485_addr_b: int = 2,
        poll_interval_ms: int = 80,
        use_new_motion_stack: bool = True
    ):
        # Range macchina
        self.min_distance = 250.0
        self.max_cut_length = 4000.0

        # Modbus (invariato)
        self._client = ModbusRTUClient(port=serial_port, baudrate=115200)
        self.addr_a = rs485_addr_a
        self.addr_b = rs485_addr_b

        # Cache coils / inputs
        self._coils_a: List[bool] = [False]*8
        self._coils_b: List[bool] = [False]*8
        self._inputs_a: List[bool] = [False]*8
        self._inputs_b: List[bool] = [False]*8

        # Flag
        self.machine_homed = False
        self.homing_in_progress = False
        self.emergency_active = False

        # Angoli teste
        self.left_head_angle = 0.0
        self.right_head_angle = 0.0

        # Tracking modalità per controllo morse
        self._software_morse_control_enabled = False
        self._current_mode = "idle"
        self._current_piece_length = 0.0
        self._bar_stock_length = 6500.0

        # Motion control
        self._position_mm = self.min_distance
        self._target_mm: Optional[float] = None
        self._moving = False
        
        # Load hardware configuration
        config = self._load_hardware_config()
        
        # Initialize new motion stack if available and enabled
        self.use_new_motion_stack = use_new_motion_stack and HARDWARE_STACK_AVAILABLE
        self._motor_driver: Optional[MD25HVDriver] = None
        self._encoder_reader: Optional[EncoderReader8ALZARD] = None
        self._motion_controller: Optional[MotionController] = None
        
        if self.use_new_motion_stack:
            self._init_new_motion_stack(config)
        else:
            # Fallback to old GPIO-based motion (for compatibility)
            self._init_legacy_motion()

        self._poll_interval = poll_interval_ms / 1000.0
        self._last_poll = 0.0
        self._lock = threading.Lock()
        self._closed = False

    def _load_hardware_config(self) -> dict:
        """Load hardware configuration from JSON file."""
        try:
            config_path = os.path.join(
                os.path.dirname(__file__), 
                "../../../data/hardware_config.json"
            )
            with open(config_path, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load hardware config: {e}")
            return {}
    
    def _init_new_motion_stack(self, config: dict):
        """Initialize new MD25HV + 8AL-ZARD + PID motion stack."""
        try:
            motion_config = config.get("motion_control", {})
            
            # Get GPIO pins from config
            gpio_motor = motion_config.get("gpio_motor", {})
            gpio_encoder = motion_config.get("gpio_encoder", {})
            encoder_cal = motion_config.get("encoder_calibration", {})
            pid_params = motion_config.get("pid_parameters", {})
            motion_limits = motion_config.get("motion_limits", {})
            
            # Initialize motor driver
            self._motor_driver = MD25HVDriver(
                pwm_gpio=gpio_motor.get("pwm_pin", 12),
                dir_gpio=gpio_motor.get("dir_pin", 13),
                enable_gpio=gpio_motor.get("enable_pin", 16),
                pwm_frequency=gpio_motor.get("pwm_frequency_hz", 20000),
                max_speed_percent=motion_limits.get("max_speed_percent", 80.0),
                ramp_time_s=motion_limits.get("ramp_time_s", 0.5)
            )
            
            # Initialize encoder reader
            self._encoder_reader = EncoderReader8ALZARD(
                gpio_a=gpio_encoder.get("channel_a_pin", 17),
                gpio_b=gpio_encoder.get("channel_b_pin", 27),
                gpio_z=gpio_encoder.get("index_z_pin", 22),
                pulses_per_mm=encoder_cal.get("pulses_per_mm", 84.880),
                enable_index=gpio_encoder.get("enable_index", True)
            )
            
            # Initialize motion controller with PID
            self._motion_controller = MotionController(
                motor=self._motor_driver,
                encoder=self._encoder_reader,
                min_position_mm=self.min_distance,
                max_position_mm=self.max_cut_length,
                pid_kp=pid_params.get("kp", 2.0),
                pid_ki=pid_params.get("ki", 0.5),
                pid_kd=pid_params.get("kd", 0.1),
                position_tolerance_mm=pid_params.get("position_tolerance_mm", 0.5),
                max_speed_percent=motion_limits.get("max_speed_percent", 80.0),
                control_loop_hz=pid_params.get("control_loop_hz", 50.0)
            )
            
            # Start motion control loop
            if self._motion_controller:
                self._motion_controller.start()
            
            print("✅ New motion control stack initialized successfully")
            print(f"   - MD25HV motor driver on GPIO {gpio_motor.get('pwm_pin', 12)}/{gpio_motor.get('dir_pin', 13)}/{gpio_motor.get('enable_pin', 16)}")
            print(f"   - Encoder reader on GPIO {gpio_encoder.get('channel_a_pin', 17)}/{gpio_encoder.get('channel_b_pin', 27)}/{gpio_encoder.get('index_z_pin', 22)}")
            print(f"   - PID controller (Kp={pid_params.get('kp', 2.0)}, Ki={pid_params.get('ki', 0.5)}, Kd={pid_params.get('kd', 0.1)})")
            
        except Exception as e:
            print(f"❌ Failed to initialize new motion stack: {e}")
            print("   Falling back to legacy motion control")
            self.use_new_motion_stack = False
            self._init_legacy_motion()
    
    def _init_legacy_motion(self):
        """Initialize legacy GPIO-based motion (fallback)."""
        self.pi = None
        if pigpio:
            try:
                self.pi = pigpio.pi()
                if self.pi.connected:
                    # Old GPIO pins for legacy support
                    self.pi.set_mode(18, pigpio.OUTPUT)
                    self.pi.set_mode(23, pigpio.OUTPUT)
                    self.pi.set_mode(24, pigpio.OUTPUT)
                    self.pi.write(24, 1)
                    print("✅ Legacy motion control initialized")
                else:
                    self.pi = None
            except Exception:
                self.pi = None

    def get_position(self) -> Optional[float]:
        """Get current position from encoder or fallback."""
        if self.use_new_motion_stack and self._motion_controller:
            return self._motion_controller.get_position()
        return self._position_mm

    def is_positioning_active(self) -> bool:
        """Check if machine is currently moving."""
        if self.use_new_motion_stack and self._motion_controller:
            return self._motion_controller.is_moving()
        return self._moving

    def get_input(self, name: str) -> bool:
        if name == "blade_pulse":
            return self._inputs_a[3]
        if name == "start_pressed":
            return self._inputs_a[0]
        if name == "dx_blade_out":
            return self._inputs_a[2]
        if name == "emergency_active":
            return self._inputs_a[1] or self. emergency_active
        return False

    def command_move(
        self,
        length_mm: float,
        ang_sx: float = 0.0,
        ang_dx: float = 0.0,
        profile: str = "",
        element: str = ""
    ) -> bool:
        """Command movement to target position."""
        if self.emergency_active or not self.machine_homed or self.homing_in_progress: 
            return False
        
        with self._lock:
            target_mm = max(self.min_distance, min(float(length_mm), self.max_cut_length))
            self.left_head_angle = float(ang_sx)
            self.right_head_angle = float(ang_dx)
            
            if self.use_new_motion_stack and self._motion_controller:
                # Use new motion controller with PID
                success = self._motion_controller.move_to(target_mm)
                if success:
                    self._target_mm = target_mm
                    self._moving = True
                    self._write_coil_a(0, False)  # Release brake
                return success
            else:
                # Legacy motion control
                self._target_mm = target_mm
                self._moving = True
                self._write_coil_a(0, False)
                return True

    def command_lock_brake(self) -> bool:
        self._write_coil_a(0, True)
        return True

    def command_release_brake(self) -> bool:
        self._write_coil_a(0, False)
        return True

    def command_set_clutch(self, active: bool) -> bool:
        """
        Controlla frizione via Modbus. 
        
        Args:
            active: True = frizione inserita (trazione attiva)
                   False = frizione disinserita (testa libera)
        
        Returns: 
            True se comando inviato
        """
        self._write_coil_a(1, bool(active))
        return True

    def command_set_head_angles(self, sx: float, dx: float) -> bool:
        self.left_head_angle = float(sx)
        self.right_head_angle = float(dx)
        return True

    def set_mode_context(self, mode: str, piece_length_mm: float = 0.0, 
                         bar_length_mm: float = 6500.0):
        """
        Imposta contesto modalità per decisione controllo morse.
        
        Args:
            mode: "idle" | "manual" | "plan" | "semi" | "ultra_long_head" | "ultra_long_retract" | "ultra_long_final"
            piece_length_mm: Lunghezza pezzo corrente
            bar_length_mm: Lunghezza barra stock
        """
        self._current_mode = str(mode)
        self._current_piece_length = float(piece_length_mm)
        self._bar_stock_length = float(bar_length_mm)
        self._update_morse_control_mode()

    def _update_morse_control_mode(self):
        """
        Decide se abilitare controllo software morse.
        
        Logica:
        - Ultra-lunga: sempre controllo software
        - Manuale: mai controllo software (pulsantiera)
        - Automatico/Semi: solo se fuori quota O ultra corto (<500mm)
        """
        was_enabled = self._software_morse_control_enabled
        
        if self._current_mode. startswith("ultra_long"):
            self._software_morse_control_enabled = True
        elif self._current_mode == "manual":
            self._software_morse_control_enabled = False
        elif self._current_mode in ("plan", "semi"):
            is_out_of_quota = self._current_piece_length > self._bar_stock_length
            is_ultra_short = 0 < self._current_piece_length < 500.0
            self._software_morse_control_enabled = (is_out_of_quota or is_ultra_short)
        else:
            self._software_morse_control_enabled = False
        
        if was_enabled != self._software_morse_control_enabled: 
            mode_str = "SOFTWARE" if self._software_morse_control_enabled else "PULSANTIERA"
            print(f"🔧 Controllo morse: {mode_str}")
            
            if not self._software_morse_control_enabled:
                self._write_coil_a(2, False)
                self._write_coil_a(3, False)

    def command_set_morse(self, left_locked: bool, right_locked:  bool) -> bool:
        """
        Comanda morse SOLO se controllo software abilitato.
        
        Se controllo software disabilitato → ignora comando (pulsantiera controlla).
        """
        if not self._software_morse_control_enabled: 
            return False
        
        self._write_coil_a(2, bool(left_locked))
        self._write_coil_a(3, bool(right_locked))
        return True

    def command_set_blade_inhibit(self, left: Optional[bool]=None, right: Optional[bool]=None) -> bool:
        if left is not None:
            self._write_coil_b(0, bool(left))
        if right is not None:
            self._write_coil_b(1, bool(right))
        return True

    def command_sim_cut_pulse(self) -> None:
        pass

    def command_sim_start_pulse(self) -> None:
        pass

    def command_sim_dx_blade_out(self, on: bool) -> None:
        pass

    def do_homing(self, callback: Optional[Callable[..., None]] = None) -> None:
        """Perform homing sequence."""
        if self.emergency_active:
            if callback: callback(success=False, msg="EMERGENZA")
            return
        
        if self.use_new_motion_stack and self._motion_controller:
            # Use new motion controller homing with index pulse
            def homing_callback(success: bool, message: str):
                with self._lock:
                    self.machine_homed = success
                    self.homing_in_progress = False
                    if success:
                        self._position_mm = self.min_distance
                        self._target_mm = self.min_distance
                        self._moving = False
                        self._write_coil_a(0, False)
                if callback:
                    callback(success=success, msg=message)
            
            self.homing_in_progress = True
            self._motion_controller.do_homing(callback=homing_callback, use_index=True)
        else:
            # Legacy homing
            import threading
            def seq():
                if self.emergency_active: 
                    if callback: callback(success=False, msg="EMERGENZA")
                    return
                self.homing_in_progress = True
                self._moving = False
                time.sleep(1.0)
                with self._lock:
                    self._position_mm = self.min_distance
                    self._target_mm = self.min_distance
                    self._moving = False
                    self.machine_homed = True
                    self.homing_in_progress = False
                    self._write_coil_a(0, False)
                if callback: callback(success=True, msg="HOMING OK")
            threading.Thread(target=seq, daemon=True).start()

    def tick(self) -> None:
        """Periodic update for Modbus polling and legacy motion simulation."""
        now = time.time()
        if now - self._last_poll < self._poll_interval:
            return
        self._last_poll = now
        
        # Poll Modbus inputs (unchanged)
        try:
            inp_a = self._client.read_discrete_inputs(self.addr_a, 0, 8)
            if inp_a: self._inputs_a = inp_a
        except Exception:
            pass
        try:
            inp_b = self._client.read_discrete_inputs(self.addr_b, 0, 8)
            if inp_b: self._inputs_b = inp_b
        except Exception:
            pass
        
        # Update position for legacy motion only (new stack manages position automatically)
        if not self.use_new_motion_stack:
            with self._lock:
                if self._moving and self._target_mm is not None:
                    dist = abs(self._target_mm - self._position_mm)
                    step = 0.01 * 100  # mm_per_pulse * speed_factor
                    if dist < step:
                        self._position_mm = self._target_mm
                        self._moving = False
                    else:
                        if self._position_mm < self._target_mm:
                            self._position_mm += step
                        else:
                            self._position_mm -= step
        else:
            # Update internal position from motion controller
            if self._motion_controller:
                pos = self._motion_controller.get_position()
                if pos is not None:
                    self._position_mm = pos
                self._moving = self._motion_controller.is_moving()

    def get_state(self) -> Dict[str, Any]:
        """Get current machine state."""
        state = {
            "homed": self.machine_homed,
            "position_mm": self._position_mm,
            "target_mm": self._target_mm,
            "moving": self._moving,
            "homing_in_progress": self.homing_in_progress,
            "brake_active": self._coils_a[0],
            "clutch_active": self._coils_a[1],
            "left_morse_locked": self._coils_a[2],
            "right_morse_locked": self._coils_a[3],
            "left_blade_inhibit": self._coils_b[0],
            "right_blade_inhibit": self._coils_b[1],
            "emergency_active": self.emergency_active,
            "left_head_angle": self.left_head_angle,
            "right_head_angle": self.right_head_angle,
            "motion_stack": "new" if self.use_new_motion_stack else "legacy"
        }
        
        # Add motion controller state if using new stack
        if self.use_new_motion_stack and self._motion_controller:
            state["motion_controller"] = self._motion_controller.get_state()
        
        return state

    def close(self) -> None:
        """Close all connections and cleanup."""
        with self._lock:
            self._closed = True
            self._moving = False
        
        # Close new motion stack
        if self.use_new_motion_stack:
            if self._motion_controller:
                self._motion_controller.close()
            if self._motor_driver:
                self._motor_driver.close()
            if self._encoder_reader:
                self._encoder_reader.close()
        
        # Close legacy GPIO
        if hasattr(self, 'pi') and self.pi:
            try:
                self.pi.stop()
            except Exception:
                pass
        
        # Close Modbus
        try:
            self._client.close()
        except Exception:
            pass

    def _write_coil_a(self, address:  int, value: bool):
        if 0 <= address < 8:
            self._coils_a[address] = bool(value)
        try:
            self._client.write_coil(self.addr_a, address, bool(value))
        except Exception: 
            pass

    def _write_coil_b(self, address: int, value: bool):
        if 0 <= address < 8:
            self._coils_b[address] = bool(value)
        try:
            self._client.write_coil(self.addr_b, address, bool(value))
        except Exception:
            pass
