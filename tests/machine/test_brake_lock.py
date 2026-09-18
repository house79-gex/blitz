"""Freno bloccato a fine posizionamento."""
from qt6_app.ui_qt.machine.simulation_machine import SimulationMachine


def test_simulation_locks_brake_when_move_completes():
    m = SimulationMachine()
    m.machine_homed = True
    m.encoder_position = 250.0
    assert m.command_move(500.0, 0.0, 0.0) is True
    assert m.brake_active is False
    assert m.is_positioning_active() is True
    m.encoder_position = 500.0
    m.tick()
    assert m.is_positioning_active() is False
    assert m.brake_active is True


def test_simulation_releases_brake_on_new_move():
    m = SimulationMachine()
    m.machine_homed = True
    m.command_lock_brake()
    assert m.brake_active is True
    m.command_move(800.0)
    assert m.brake_active is False
