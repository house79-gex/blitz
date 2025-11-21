from __future__ import annotations
import time, threading
from typing import Dict, Any, Optional
from ui_qt.machine.interfaces import MachineIO
from ui_qt.machine.modbus_bus import ModbusBus
from ui_qt.machine.drive_serial import DriveSerial

try:
    import pigpio
except Exception:
    pigpio = None

class RealMachineMultiPort(MachineIO):
    """
    Variante RealMachine che usa:
    - RS485 (ModbusBus) per relè/ingressi
    - RS232 (DriveSerial) per DCS810
    - GPIO per motion (pulse/dir)
    """
    def __init__(self,
                 rs232_port: str = "/dev/ft4232_rs232",
                 rs485_port: str = "/dev/ft4232_rs485",
                 mm_per_pulse: float = 0.01,
                 pulse_gpio: int = 18,
                 dir_gpio: int = 23,
                 enable_gpio: int = 24,
                 poll_interval_ms: int = 80):
        self.bus = ModbusBus(port=rs485_port)
        self.drive = DriveSerial(port=rs232_port, line_callback=self._on_drive_line)

        self.mm_per_pulse = mm_per_pulse
        self._position_mm = 0.0
        self._target_mm: Optional[float] = None
        self._moving = False

        self.left_head_angle = 0.0
        self.right_head_angle = 0.0

        self.machine_homed = True
        self.emergency_active = False

        self._poll_interval = poll_interval_ms / 1000.0
        self._last_poll = 0.0
        self._lock = threading.Lock()

        self._drive_buffer = []
        self._closed = False

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

    def _on_drive_line(self, line: str):
        """
        Callback linee RS232 dal drive: puoi parsare errori, stato, posizione reale (se disponibile).
        Esempio: 'ALARM:OVERCURRENT', 'POS:123.45'.
        """
        self._drive_buffer.append((time.time(), line))
        if line.startswith("ALARM"):
            self.emergency_active = True

    # --- MachineIO ---
    def get_position(self) -> Optional[float]:
        return self._position_mm

    def is_positioning_active(self) -> bool:
        return self._moving

    def get_input(self, name: str) -> bool:
        # Mappa inputs dal Modbus bus
        st = self.bus.state
        # Esempio mapping:
        if name == "blade_pulse": return st["inputs_a"][3]
        if name == "start_pressed": return st["inputs_a"][0]
        if name == "dx_blade_out": return st["inputs_a"][2]
        if name == "emergency_active": return st["inputs_a"][1] or self.emergency_active
        return False

    def command_move(self, length_mm: float, ang_sx: float = 0.0, ang_dx: float = 0.0,
                     profile: str = "", element: str = "") -> bool:
        if self.emergency_active:
            return False
        with self._lock:
            self._target_mm = max(0.0, float(length_mm))
            self.left_head_angle = float(ang_sx)
            self.right_head_angle = float(ang_dx)
            self._moving = True
            self.bus.write_coil_a(0, False)  # brake release
        return True

    def command_lock_brake(self) -> bool:
        self.bus.write_coil_a(0, True)
        return True

    def command_release_brake(self) -> bool:
        self.bus.write_coil_a(0, False)
        return True

    def command_set_head_angles(self, sx: float, dx: float) -> bool:
        self.left_head_angle = float(sx)
        self.right_head_angle = float(dx)
        return True

    def command_set_pressers(self, left_locked: bool, right_locked: bool) -> bool:
        self.bus.write_coil_a(2, bool(left_locked))
        self.bus.write_coil_a(3, bool(right_locked))
        return True

    def command_set_blade_inhibit(self, left: Optional[bool]=None, right: Optional[bool]=None) -> bool:
        if left is not None: self.bus.write_coil_b(0, bool(left))
        if right is not None: self.bus.write_coil_b(1, bool(right))
        return True

    def command_sim_cut_pulse(self) -> None: pass
    def command_sim_start_pulse(self) -> None: pass
    def command_sim_dx_blade_out(self, on: bool) -> None: pass

    def tick(self) -> None:
        now = time.time()
        if now - self._last_poll >= self._poll_interval:
            self.bus.poll()
            self._last_poll = now

        with self._lock:
            if self._moving and self._target_mm is not None:
                diff = self._target_mm - self._position_mm
                direction = 1 if diff >= 0 else -1
                step_mm = 5.0
                if abs(diff) <= step_mm:
                    self._position_mm = self._target_mm
                    self._moving = False
                    self.bus.write_coil_a(0, True)  # auto lock brake
                else:
                    self._position_mm += direction * step_mm
                    if self.pi:
                        self.pi.write(self.dir_gpio, 1 if direction > 0 else 0)
                        pulses = int(abs(step_mm / self.mm_per_pulse))
                        for _ in range(pulses):
                            self.pi.write(self.pulse_gpio, 1)
                            self.pi.write(self.pulse_gpio, 0)

        # Aggiorna emergency se input dedicato
        if self.get_input("emergency_active"):
            self.emergency_active = True
            with self._lock:
                self._moving = False
                self._target_mm = self._position_mm
            self.bus.write_coil_a(0, True)

    def get_state(self) -> Dict[str, Any]:
        st = self.bus.state
        return {
            "position_mm": self._position_mm,
            "target_mm": self._target_mm,
            "moving": self._moving,
            "brake_active": st["coils_a"][0],
            "clutch_active": st["coils_a"][1],
            "left_presser_locked": st["coils_a"][2],
            "right_presser_locked": st["coils_a"][3],
            "left_blade_inhibit": st["coils_b"][0],
            "right_blade_inhibit": st["coils_b"][1],
            "head_angles": {"sx": self.left_head_angle, "dx": self.right_head_angle},
            "inputs_a": st["inputs_a"],
            "inputs_b": st["inputs_b"],
            "emergency_active": self.emergency_active,
            "homed": self.machine_homed,
            "drive_buffer_tail": self._drive_buffer[-5:]  # ultime 5 linee drive
        }

    def close(self) -> None:
        try: self.bus.close()
        except Exception: pass
        try: self.drive.close()
        except Exception: pass
        if self.pi:
            try: self.pi.stop()
            except Exception: pass
