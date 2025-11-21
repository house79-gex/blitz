from ui_qt.machine.rs485_modbus import ModbusRTUClient
from typing import Dict, Any

class ModbusBus:
    """
    Wrapper alto livello su ModbusRTUClient per gestione canale RS485.
    Permette mapping coils/inputs su nome logico.
    """
    def __init__(self, port: str, addr_relays: int = 1, addr_inputs: int = 2):
        self.client = ModbusRTUClient(port=port, baudrate=115200)
        self.addr_relays = addr_relays
        self.addr_inputs = addr_inputs
        self.state: Dict[str, Any] = {
            "coils_a": [False]*8,
            "inputs_a": [False]*8,
            "coils_b": [False]*8,
            "inputs_b": [False]*8,
            "online": True
        }

    def poll(self) -> None:
        try:
            self.state["coils_a"] = self.client.read_coils(self.addr_relays, 0, 8)
            self.state["inputs_a"] = self.client.read_discrete_inputs(self.addr_relays, 0, 8)
        except Exception:
            self.state["online"] = False
        try:
            self.state["coils_b"] = self.client.read_coils(self.addr_inputs, 0, 8)
            self.state["inputs_b"] = self.client.read_discrete_inputs(self.addr_inputs, 0, 8)
        except Exception:
            self.state["online"] = False

    def write_coil_a(self, index: int, value: bool):
        try:
            if self.client.write_single_coil(self.addr_relays, index, value):
                self.state["coils_a"][index] = value
        except Exception:
            self.state["online"] = False

    def write_coil_b(self, index: int, value: bool):
        try:
            if self.client.write_single_coil(self.addr_inputs, index, value):
                self.state["coils_b"][index] = value
        except Exception:
            self.state["online"] = False

    def close(self):
        try: self.client.close()
        except Exception: pass
