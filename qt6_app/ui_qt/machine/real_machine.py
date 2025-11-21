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
    Implementazione “base” macchina reale:
    - RS485 Modbus: due dispositivi (addr_a per freno/frizione/pressori, addr_b per inibizioni).
    - Pulse/Dir (GPIO) per movimento open-loop stimato.
    - Homing simulato (sostituire con routine vera: finecorsa / drive).
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
        # Range macchina (impostare ai valori reali)
        self.min_distance = 250.0
        self.max_cut_length = 4000.0

        # Modbus
        self._client = ModbusRTUClient(port=serial_port, baudrate=115200)
        self.addr_a = rs485_addr_a
        self.addr_b = rs485_addr_b

        # Motion
        self.mm_per_pulse = mm_per_pulse
        self._position_mm = self.min_distance
        self._target_mm: Optional[float] = None
        self._moving = False

        # Angoli teste
        self.left_head_angle = 0.0
        self.right_head_angle = 0.0

        # Cache coils / inputs
        self._coils_a: List[bool] = [False]*8   # 0 brake, 1 clutch, 2 left_presser, 3 right_presser
        self._coils_b: List[bool] = [False]*8   # 0 left_blade_inhibit, 1 right_blade_inhibit
        self._inputs_a: List[bool] = [False]*8
        self._inputs_b: List[bool] = [False]*8

        # Flag
        self.machine_homed = False   # non azzerata all'avvio
        self.emergency_active = False

        # GPIO pigpio
        self.pi = None
        self.pulse_gpio = pulse_gpio
        self.dir_gpio = dir_gpio
        self.enable_gpio = enable_gpio
        if pigpio:
            try:
                self.pi = pigpio.pi()
                if self.pi.connected:
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

    # --- MachineIO ---
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
            return self._inputs_a[1] or self.emergency_active
        return False

    def command_move(
        self,
        length_mm: float,
        ang_sx: float = 0.0,
        ang_dx: float = 0.0,
        profile: str = "",
        element: str = ""
    ) -> bool:
        if self.emergency_active or not self.machine_homed:
            return False
        with self._lock:
            self._target_mm = max(self.min_distance, min(float(length_mm), self.max_cut_length))
            self.left_head_angle = float(ang_sx)
            self.right_head_angle = float(ang_dx)
            self._moving = True
            self._write_coil_a(0, False)  # release brake
        return True

    def command_lock_brake(self) -> bool:
        self._write_coil_a(0, True)
        return True

    def command_release_brake(self) -> bool:
        self._write_coil_a(0, False)
        return True

    def command_set_head_angles(self, sx: float, dx: float) -> bool:
        self.left_head_angle = float(sx)
        self.right_head_angle = float(dx)
        return True

    def command_set_pressers(self, left_locked: bool, right_locked: bool) -> bool:
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
        """
        Homing 'placeholder':
        - In reale: qui dovresti muovere verso finecorsa, attendere, azzerare encoder.
        - Ora: simula ritardo e imposta position a min_distance.
        """
        import threading, time
        def seq():
            if self.emergency_active:
                if callback: callback(success=False, msg="EMERGENZA")
                return
            time.sleep(1.0)
            with self._lock:
                self._position_mm = self.min_distance
                self._target_mm = self.min_distance
                self._moving = False
                self.machine_homed = True
                # Rilascia freno a fine homing
                self._write_coil_a(0, False)
            if callback: callback(success=True, msg="HOMING OK")
        threading.Thread(target=seq, daemon=True).start()

    def tick(self) -> None:
        now = time.time()
        if now - self._last_poll >= self._poll_interval:
            self._poll_rs485()
            self._last_poll = now

        with self._lock:
            if self._moving and self._target_mm is not None:
                diff = self._target_mm - self._position_mm
                direction = 1 if diff >= 0 else -1
                step_mm = 5.0  # mm per tick (grezzo)
                if abs(diff) <= step_mm:
                    self._position_mm = self._target_mm
                    self._moving = False
                    self._write_coil_a(0, True)  # auto-lock brake
                else:
                    self._position_mm += direction * step_mm
                    if self.pi:
                        self.pi.write(self.dir_gpio, 1 if direction > 0 else 0)
                        pulses = int(abs(step_mm / self.mm_per_pulse))
                        for _ in range(pulses):
                            self.pi.write(self.pulse_gpio, 1)
                            self.pi.write(self.pulse_gpio, 0)

        # Aggiorna Emergency
        if self.get_input("emergency_active"):
            self.emergency_active = True
            with self._lock:
                self._moving = False
                self._target_mm = self._position_mm
            self._write_coil_a(0, True)

    def get_state(self) -> Dict[str, Any]:
        return {
            "position_mm": self._position_mm,
            "target_mm": self._target_mm,
            "moving": self._moving,
            "brake_active": self._coils_a[0],
            "clutch_active": self._coils_a[1],
            "left_presser_locked": self._coils_a[2],
            "right_presser_locked": self._coils_a[3],
            "left_blade_inhibit": self._coils_b[0],
            "right_blade_inhibit": self._coils_b[1],
            "head_angles": {"sx": self.left_head_angle, "dx": self.right_head_angle},
            "inputs_a": list(self._inputs_a),
            "inputs_b": list(self._inputs_b),
            "emergency_active": self.emergency_active,
            "homed": self.machine_homed,
            "min_distance": self.min_distance,
            "max_cut_length": self.max_cut_length
        }

    def close(self) -> None:
        self._closed = True
        try: self._client.close()
        except Exception: pass
        if self.pi:
            try: self.pi.stop()
            except Exception: pass

    # --- RS485 ---
    def _poll_rs485(self):
        try:
            self._coils_a = self._client.read_coils(self.addr_a, 0, 8)
            self._inputs_a = self._client.read_discrete_inputs(self.addr_a, 0, 8)
        except Exception:
            pass
        try:
            self._coils_b = self._client.read_coils(self.addr_b, 0, 8)
            self._inputs_b = self._client.read_discrete_inputs(self.addr_b, 0, 8)
        except Exception:
            pass

    def _write_coil_a(self, index: int, value: bool):
        if 0 <= index < 8:
            try:
                ok=self._client.write_single_coil(self.addr_a, index, value)
                if ok: self._coils_a[index] = value
            except Exception:
                pass

    def _write_coil_b(self, index: int, value: bool):
        if 0 <= index < 8:
            try:
                ok=self._client.write_single_coil(self.addr_b, index, value)
                if ok: self._coils_b[index] = value
            except Exception:
                pass
