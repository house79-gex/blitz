from __future__ import annotations
import time
import threading
from typing import Dict, Any, Optional, List, Callable
from ui_qt.machine.interfaces import MachineIO
from ui_qt.machine.rs485_modbus import ModbusRTUClient

try:
    import pigpio
except Exception:
    pigpio = None

class RealMachine(MachineIO):
    """
    Implementazione base "reale": 
    - RS485 Modbus:  due dispositivi (addr_a:  freno/frizione/pressori, addr_b: inibizioni).
    - Pulse/Dir (GPIO) per movimento open-loop stimato.
    - Homing placeholder con homing_in_progress:  porta la posizione a 250 mm.
    """

    def __init__(
        self,
        serial_port: str = "/dev/ttyUSB0",
        rs485_addr_a: int = 1,
        rs485_addr_b: int = 2,
        mm_per_pulse: float = 0.01,
        pulse_gpio: int = 18,
        dir_gpio: int = 23,
        enable_gpio: int = 24,
        poll_interval_ms: int = 80
    ):
        # Range macchina
        self. min_distance = 250.0
        self.max_cut_length = 4000.0

        # Modbus
        self._client = ModbusRTUClient(port=serial_port, baudrate=115200)
        self.addr_a = rs485_addr_a
        self.addr_b = rs485_addr_b

        # Motion
        self.mm_per_pulse = mm_per_pulse
        self._position_mm = self.min_distance
        self._target_mm:  Optional[float] = None
        self._moving = False

        # Angoli teste
        self.left_head_angle = 0.0
        self.right_head_angle = 0.0

        # Cache coils / inputs
        self._coils_a: List[bool] = [False]*8
        self._coils_b: List[bool] = [False]*8
        self._inputs_a: List[bool] = [False]*8
        self._inputs_b: List[bool] = [False]*8

        # Flag
        self. machine_homed = False
        self.homing_in_progress = False
        self.emergency_active = False

        # Tracking modalità per controllo morse
        self._software_morse_control_enabled = False
        self._current_mode = "idle"
        self._current_piece_length = 0.0
        self._bar_stock_length = 6500.0

        # GPIO pigpio
        self. pi = None
        self.pulse_gpio = pulse_gpio
        self.dir_gpio = dir_gpio
        self.enable_gpio = enable_gpio
        if pigpio: 
            try:
                self.pi = pigpio.pi()
                if self.pi. connected:
                    self.pi.set_mode(self.pulse_gpio, pigpio.OUTPUT)
                    self.pi.set_mode(self.dir_gpio, pigpio.OUTPUT)
                    self.pi.set_mode(self.enable_gpio, pigpio.OUTPUT)
                    self.pi.write(self.enable_gpio, 1)
                else:
                    self.pi = None
            except Exception:
                self.pi = None

        self._poll_interval = poll_interval_ms / 1000.0
        self._last_poll = 0.0
        self._lock = threading.Lock()
        self._closed = False

    def get_position(self) -> Optional[float]:
        return self._position_mm

    def is_positioning_active(self) -> bool:
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
        if self. emergency_active or not self.machine_homed or self. homing_in_progress: 
            return False
        with self._lock:
            self._target_mm = max(self.min_distance, min(float(length_mm), self.max_cut_length))
            self. left_head_angle = float(ang_sx)
            self.right_head_angle = float(ang_dx)
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

    def do_homing(self, callback:  Optional[Callable[..., None]] = None) -> None:
        import threading, time
        def seq():
            if self.emergency_active: 
                if callback:  callback(success=False, msg="EMERGENZA")
                return
            self.homing_in_progress = True
            self._moving = False
            time.sleep(1. 0)
            with self._lock:
                self._position_mm = self.min_distance
                self._target_mm = self.min_distance
                self._moving = False
                self. machine_homed = True
                self.homing_in_progress = False
                self._write_coil_a(0, False)
            if callback: callback(success=True, msg="HOMING OK")
        threading.Thread(target=seq, daemon=True).start()

    def tick(self) -> None:
        now = time.time()
        if now - self._last_poll < self._poll_interval:
            return
        self._last_poll = now
        try:
            inp_a = self._client.read_discrete_inputs(self.addr_a, 0, 8)
            if inp_a:  self._inputs_a = inp_a
        except Exception:
            pass
        try:
            inp_b = self._client.read_discrete_inputs(self.addr_b, 0, 8)
            if inp_b: self._inputs_b = inp_b
        except Exception:
            pass
        with self._lock:
            if self._moving and self._target_mm is not None:
                dist = abs(self._target_mm - self._position_mm)
                step = self.mm_per_pulse * 100
                if dist < step:
                    self._position_mm = self._target_mm
                    self._moving = False
                else:
                    if self._position_mm < self._target_mm:
                        self._position_mm += step
                    else:
                        self._position_mm -= step

    def get_state(self) -> Dict[str, Any]:
        return {
            "homed": self.machine_homed,
            "position_mm": self._position_mm,
            "target_mm": self._target_mm,
            "moving": self._moving,
            "homing_in_progress": self. homing_in_progress,
            "brake_active": self._coils_a[0],
            "clutch_active": self._coils_a[1],
            "left_morse_locked": self._coils_a[2],
            "right_morse_locked": self._coils_a[3],
            "left_blade_inhibit": self._coils_b[0],
            "right_blade_inhibit": self._coils_b[1],
            "emergency_active": self. emergency_active,
            "left_head_angle": self.left_head_angle,
            "right_head_angle": self. right_head_angle
        }

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._moving = False
        if self.pi:
            try:
                self.pi.stop()
            except Exception:
                pass
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
