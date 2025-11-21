from typing import Any

def build_machine(simulation: bool = False) -> Any:
    if simulation:
        from ui_qt.machine.simulation_machine import SimulationMachine
        return SimulationMachine()
    # Prova macchina reale
    try:
        from ui_qt.machine.real_machine import RealMachine  # ipotetico
        return RealMachine()
    except Exception:
        # Fallback simulazione
        from ui_qt.machine.simulation_machine import SimulationMachine
        return SimulationMachine()
