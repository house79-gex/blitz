from __future__ import annotations
import time
import threading
import json
import os
from typing import Dict, Any, Optional, List, Callable
from ui_qt.machine.interfaces import MachineIO
from ui_qt.machine.rs485_modbus import ModbusRTUClient

# Mappa coils modulo 2 (ID=2) allineata allo schema elettrico
COIL_B_MORSA_SX_CHIUDI = 0
COIL_B_MORSA_SX_APRI = 1
COIL_B_MORSA_DX_CHIUDI = 2
COIL_B_MORSA_DX_APRI = 3
COIL_B_FRENO_BLOCCO = 4   # OUT5 impulso
COIL_B_FRENO_SBLOCCO = 5  # OUT6 impulso
COIL_B_FRIZIONE = 6       # OUT7 hold

# Inibizioni lama e inclinazione sul modulo 1 (ID=1)
COIL_A_SX_45 = 0
COIL_A_SX_0 = 1
COIL_A_DX_45 = 2
COIL_A_DX_0 = 3
COIL_A_INIB_LAMA_SX = 4
COIL_A_INIB_LAMA_DX = 5
BRAKE_PULSE_S = 0.25
HEAD_TILT_PULSE_S = 0.25

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
        self.brake_active = False
        self.clutch_active = True

        # Angoli teste (comandati + misurati da encoder GPIO/AL-ZARD o RS485)
        self.left_head_angle = 0.0
        self.right_head_angle = 0.0
        self.measured_left_head_angle = None
        self.measured_right_head_angle = None
        self._head_encoders = None
        self._head_home = None
        self._head_fc_cfg = {}
        self._head_tilt = None

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
        self._init_head_encoders(config)
        self._init_head_home_fc(config)
        self._init_head_tilt_drive(config)

    def _init_head_tilt_drive(self, config: dict) -> None:
        """Cilindri 0°/45° oggi; stub attuatori lineari per il futuro."""
        try:
            from ui_qt.hardware.head_tilt_drive import create_head_tilt_drive
            self._head_tilt = create_head_tilt_drive(
                config, pulse_fn=self._pulse_head_tilt
            )
        except Exception as e:
            print(f"Warning: azionamento inclinazione teste non disponibile: {e}")
            self._head_tilt = None

    def _init_head_home_fc(self, config: dict) -> None:
        """Finecorsa 0° teste su IN4/IN5 del modulo I/O #1."""
        try:
            from ui_qt.hardware.head_home_fc import HeadHomeLimitHelper
            cfg = (config or {}).get("head_home_fc") or {}
            self._head_fc_cfg = cfg
            self._head_home = HeadHomeLimitHelper(
                zero_fn=self.command_zero_head_encoder,
                enabled=bool(cfg.get("enabled", True)),
                auto_zero=bool(cfg.get("auto_zero", False)),
                settle_ms=int(cfg.get("settle_ms", 400)),
                stable_deg=float(cfg.get("stable_deg", 0.2)),
            )
        except Exception as e:
            print(f"Warning: finecorsa 0° teste non disponibili: {e}")
            self._head_home = None

    def _init_head_encoders(self, config: dict) -> None:
        """Inizializza lettura encoder inclinazione teste (GPIO/AL-ZARD o Modbus)."""
        try:
            from ui_qt.hardware.head_angle_encoder import create_head_angle_service
            enc_cfg = (config or {}).get("head_encoders") or {}
            if not enc_cfg.get("enabled", False):
                self._head_encoders = None
                return
            self._head_encoders = create_head_angle_service(
                enc_cfg, modbus_client=self._client
            )
        except Exception as e:
            print(f"Warning: encoder inclinazione teste non disponibili: {e}")
            self._head_encoders = None

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
        if name == "head_sx_zero":
            return bool(len(self._inputs_a) > 3 and self._inputs_a[3])
        if name == "head_dx_zero":
            return bool(len(self._inputs_a) > 4 and self._inputs_a[4])
        if name == "blade_pulse":
            # IN4 è il FC 0° testa SX: non usarlo come impulso taglio
            return False
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
                    self.command_release_brake()
                return success
            else:
                # Legacy motion control
                self._target_mm = target_mm
                self._moving = True
                self.command_release_brake()
                return True

    def command_lock_brake(self) -> bool:
        """Impulso BLOCCO sul freno bistabile (fine posizionamento)."""
        self.brake_active = True
        self._pulse_coil_b(COIL_B_FRENO_BLOCCO)
        return True

    def command_release_brake(self) -> bool:
        """Impulso SBLOCCO prima di muovere il carro."""
        self.brake_active = False
        self._pulse_coil_b(COIL_B_FRENO_SBLOCCO)
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
        self._write_coil_b(COIL_B_FRIZIONE, bool(active))
        self.clutch_active = bool(active)
        return True

    def command_set_head_angles(self, sx: float, dx: float) -> bool:
        if self.emergency_active:
            return False
        if self._head_tilt is not None:
            sx, dx = self._head_tilt.move_to_deg(sx, dx)
        self.left_head_angle = float(sx)
        self.right_head_angle = float(dx)
        return True

    def command_zero_head_encoder(self, side: str = "both") -> bool:
        """Azzera encoder inclinazione (testa meccanicamente a 0°)."""
        if self._head_encoders is None:
            return False
        return bool(self._head_encoders.zero(side))

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
                self._write_coil_b(COIL_B_MORSA_SX_CHIUDI, False)
                self._write_coil_b(COIL_B_MORSA_SX_APRI, False)
                self._write_coil_b(COIL_B_MORSA_DX_CHIUDI, False)
                self._write_coil_b(COIL_B_MORSA_DX_APRI, False)

    def command_set_morse(self, left_locked: bool, right_locked:  bool) -> bool:
        """
        Comanda morse SOLO se controllo software abilitato.
        
        Se controllo software disabilitato → ignora comando (pulsantiera controlla).
        """
        if not self._software_morse_control_enabled: 
            return False
        
        self._write_coil_b(COIL_B_MORSA_SX_CHIUDI, bool(left_locked))
        self._write_coil_b(COIL_B_MORSA_SX_APRI, not bool(left_locked))
        self._write_coil_b(COIL_B_MORSA_DX_CHIUDI, bool(right_locked))
        self._write_coil_b(COIL_B_MORSA_DX_APRI, not bool(right_locked))
        return True

    def command_set_blade_inhibit(self, left: Optional[bool]=None, right: Optional[bool]=None) -> bool:
        if left is not None:
            self._write_coil_a(COIL_A_INIB_LAMA_SX, bool(left))
        if right is not None:
            self._write_coil_a(COIL_A_INIB_LAMA_DX, bool(right))
        return True

    def command_sim_cut_pulse(self) -> None:
        pass

    def command_sim_start_pulse(self) -> None:
        pass

    def command_sim_dx_blade_out(self, on: bool) -> None:
        pass

    def do_homing(self, callback: Optional[Callable[..., None]] = None) -> None:
        """Homing unico: teste a 0° + encoder, poi carro."""
        if self.emergency_active:
            if callback: callback(success=False, msg="EMERGENZA")
            return

        def seq():
            self.homing_in_progress = True
            ok_h, msg_h = self._home_heads()
            if self.emergency_active:
                self.homing_in_progress = False
                if callback: callback(success=False, msg="EMERGENZA")
                return

            if self.use_new_motion_stack and self._motion_controller:
                def homing_callback(success: bool, message: str):
                    with self._lock:
                        self.machine_homed = bool(success)
                        self.homing_in_progress = False
                        if success:
                            self._position_mm = self.min_distance
                            self._target_mm = self.min_distance
                            self._moving = False
                            self.command_lock_brake()
                    if callback:
                        extra = "" if ok_h else f" | teste: {msg_h}"
                        callback(success=success, msg=f"{message}{extra}")

                self._motion_controller.do_homing(callback=homing_callback, use_index=True)
                return

            time.sleep(1.0)
            with self._lock:
                self._position_mm = self.min_distance
                self._target_mm = self.min_distance
                self._moving = False
                self.machine_homed = True
                self.homing_in_progress = False
                self.command_lock_brake()
            if callback:
                extra = "" if ok_h else f" | teste: {msg_h}"
                callback(success=True, msg=f"HOMING OK{extra}")

        threading.Thread(target=seq, daemon=True).start()

    def _home_heads(self) -> tuple:
        """Porta le teste a 0°, attende i FC, azzera gli encoder."""
        required = bool((self._head_fc_cfg or {}).get("heads_required", False))
        timeout_s = float((self._head_fc_cfg or {}).get("homing_timeout_s", 8.0))
        try:
            self.command_set_head_angles(0.0, 0.0)
        except Exception:
            pass
        if self._head_home is not None:
            self._head_home.reset()

        t0 = time.monotonic()
        saw_fc = False
        while (time.monotonic() - t0) < timeout_s:
            if self.emergency_active:
                return False, "EMERGENZA"
            try:
                inp_a = self._client.read_discrete_inputs(self.addr_a, 0, 8)
                if inp_a:
                    self._inputs_a = inp_a
            except Exception:
                pass
            if self._head_encoders is not None:
                try:
                    enc_state = self._head_encoders.poll()
                    self.measured_left_head_angle = enc_state.get("measured_left_head_angle")
                    self.measured_right_head_angle = enc_state.get("measured_right_head_angle")
                except Exception:
                    pass
            self._sample_head_home()
            if self._head_home is not None and (
                self._head_home.active_sx or self._head_home.active_dx
            ):
                saw_fc = True
            if self._head_home is None or (
                self._head_home.settled_sx and self._head_home.settled_dx
            ):
                self.command_zero_head_encoder("both")
                return True, "teste 0°"
            # FC non montati: non bloccare l'homing carro per 8 s
            if not saw_fc and (time.monotonic() - t0) >= 1.0:
                break
            time.sleep(0.08)

        self.command_zero_head_encoder("both")
        if required:
            return False, "timeout FC teste"
        if not saw_fc:
            return True, "teste 0° (FC assenti)"
        return True, "teste 0° (timeout FC)"

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
        
        # Aggiorna posizione e blocca il freno a fine corsa
        was_moving = self._moving
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
            if self._motion_controller:
                pos = self._motion_controller.get_position()
                if pos is not None:
                    self._position_mm = pos
                self._moving = self._motion_controller.is_moving()

        if was_moving and not self._moving:
            self.command_lock_brake()

        # Encoder inclinazione teste (GPIO/AL-ZARD o RS485)
        if self._head_encoders is not None:
            try:
                enc_state = self._head_encoders.poll()
                self.measured_left_head_angle = enc_state.get("measured_left_head_angle")
                self.measured_right_head_angle = enc_state.get("measured_right_head_angle")
            except Exception:
                pass

        self._sample_head_home()

    def _sample_head_home(self) -> None:
        """Aggiorna solo lo stato FC 0° (niente auto-zero: lo fa l'homing)."""
        if self._head_home is None:
            return
        cfg = self._head_fc_cfg or {}
        sx_i = int(cfg.get("sx_input_index", 3))
        dx_i = int(cfg.get("dx_input_index", 4))
        active_high = bool(cfg.get("active_high", True))
        sx_raw = bool(len(self._inputs_a) > sx_i and self._inputs_a[sx_i])
        dx_raw = bool(len(self._inputs_a) > dx_i and self._inputs_a[dx_i])
        sx_act = sx_raw if active_high else (not sx_raw)
        dx_act = dx_raw if active_high else (not dx_raw)
        self._head_home.update(
            sx_act,
            dx_act,
            sx_angle=self.measured_left_head_angle,
            dx_angle=self.measured_right_head_angle,
        )

    def get_state(self) -> Dict[str, Any]:
        """Get current machine state."""
        state = {
            "homed": self.machine_homed,
            "position_mm": self._position_mm,
            "target_mm": self._target_mm,
            "moving": self._moving,
            "homing_in_progress": self.homing_in_progress,
            "brake_active": self.brake_active,
            "clutch_active": self.clutch_active,
            "left_morse_locked": self._coils_b[COIL_B_MORSA_SX_CHIUDI],
            "right_morse_locked": self._coils_b[COIL_B_MORSA_DX_CHIUDI],
            "left_blade_inhibit": self._coils_a[COIL_A_INIB_LAMA_SX],
            "right_blade_inhibit": self._coils_a[COIL_A_INIB_LAMA_DX],
            "emergency_active": self.emergency_active,
            "left_head_angle": self.left_head_angle,
            "right_head_angle": self.right_head_angle,
            "measured_left_head_angle": self.measured_left_head_angle,
            "measured_right_head_angle": self.measured_right_head_angle,
            "head_fc_zero_sx": bool(self._head_home.active_sx) if self._head_home else False,
            "head_fc_zero_dx": bool(self._head_home.active_dx) if self._head_home else False,
            "head_tilt_mode": getattr(self._head_tilt, "mode", "none"),
            "motion_stack": "new" if self.use_new_motion_stack else "legacy"
        }
        if self._head_encoders is not None:
            state.update(self._head_encoders.as_state())
        if self._head_home is not None:
            state.update(self._head_home.as_state())
        
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

        if self._head_encoders is not None:
            try:
                self._head_encoders.close()
            except Exception:
                pass
        
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

    def _pulse_coil_b(self, address: int, duration_s: float = BRAKE_PULSE_S) -> None:
        """Impulso relè (freno bistabile): ON e poi OFF dopo duration_s."""
        self._write_coil_b(address, True)
        def _off():
            try:
                self._write_coil_b(address, False)
            except Exception:
                pass
        threading.Timer(max(0.05, float(duration_s)), _off).start()

    def _pulse_coil_a(self, address: int, duration_s: float = HEAD_TILT_PULSE_S) -> None:
        """Impulso relè inclinazione teste (EV 0°/45°)."""
        self._write_coil_a(address, True)
        def _off():
            try:
                self._write_coil_a(address, False)
            except Exception:
                pass
        threading.Timer(max(0.05, float(duration_s)), _off).start()

    def _pulse_head_tilt(self, side: str, to_45: bool) -> None:
        """Impulso bobina 45° o 0° per una testa."""
        if side == "dx":
            addr = COIL_A_DX_45 if to_45 else COIL_A_DX_0
        else:
            addr = COIL_A_SX_45 if to_45 else COIL_A_SX_0
        self._pulse_coil_a(addr)
