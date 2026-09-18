"""Test encoder inclinazione teste via GPIO / AL-ZARD (senza pigpio)."""
from qt6_app.ui_qt.hardware.head_angle_encoder import create_head_angle_service, HeadAngleEncoderService
from qt6_app.ui_qt.hardware.head_gpio_encoder import (
    HeadAngleGpioService,
    QuadratureDecoder,
    pulses_to_degrees,
)


class FakePulseReader:
    """Simula un encoder AB già isolato dall'AL-ZARD."""

    def __init__(self, count=0, connected=True):
        self._count = int(count)
        self._connected = bool(connected)

    def get_pulse_count(self) -> int:
        return self._count

    def reset(self) -> None:
        self._count = 0

    def is_connected(self) -> bool:
        return self._connected

    def close(self) -> None:
        self._connected = False


def test_pulses_to_degrees_quarter_turn():
    # 600 P/R × 4 = 2400 conteggi/giro → 600 conteggi = 90°
    assert abs(pulses_to_degrees(600) - 90.0) < 1e-9
    assert abs(pulses_to_degrees(300) - 45.0) < 1e-9
    assert abs(pulses_to_degrees(2400) - 360.0) < 1e-9


def test_quadrature_forward_and_reverse():
    dec = QuadratureDecoder()
    dec.set_levels(0, 0)
    seq_fwd = [(True, 1, 0), (False, 1, 1), (True, 0, 1), (False, 0, 0)]
    for a_changed, a, b in seq_fwd:
        dec.feed(a_changed, a, b)
    assert dec.get_count() == 4

    seq_rev = [(False, 0, 1), (True, 1, 1), (False, 1, 0), (True, 0, 0)]
    for a_changed, a, b in seq_rev:
        dec.feed(a_changed, a, b)
    assert dec.get_count() == 0


def test_gpio_service_poll_and_zero():
    sx = FakePulseReader(300)
    dx = FakePulseReader(600)
    svc = HeadAngleGpioService({"enabled": True, "ppr": 600}, sx_reader=sx, dx_reader=dx)
    st = svc.poll()
    assert st["head_encoder_mode"] == "gpio"
    assert st["head_encoder_online"] is True
    assert abs(st["measured_left_head_angle"] - 45.0) < 0.01
    assert abs(st["measured_right_head_angle"] - 90.0) < 0.01
    assert svc.zero("sx") is True
    st = svc.poll()
    assert abs(st["measured_left_head_angle"]) < 0.01
    assert abs(st["measured_right_head_angle"] - 90.0) < 0.01


def test_gpio_invert_and_offset():
    sx = FakePulseReader(300)
    dx = FakePulseReader(0)
    svc = HeadAngleGpioService(
        {"enabled": True, "ppr": 600, "invert_sx": True, "zero_offset_sx_deg": 1.0},
        sx_reader=sx,
        dx_reader=dx,
    )
    st = svc.poll()
    assert abs(st["measured_left_head_angle"] - (-44.0)) < 0.01


def test_gpio_offline_reader():
    sx = FakePulseReader(0, connected=False)
    dx = FakePulseReader(0, connected=False)
    svc = HeadAngleGpioService({"enabled": True}, sx_reader=sx, dx_reader=dx)
    st = svc.poll()
    assert st["head_encoder_online"] is False
    assert st["head_encoder_online_sx"] is False
    assert st["measured_left_head_angle"] is None


def test_factory_defaults_to_gpio():
    svc = create_head_angle_service(
        {"enabled": True},
        sx_reader=FakePulseReader(0),
        dx_reader=FakePulseReader(0),
    )
    assert isinstance(svc, HeadAngleGpioService)


def test_factory_modbus_keeps_rs485_backend():
    svc = create_head_angle_service({"enabled": True, "interface": "modbus"}, modbus_client=None)
    assert isinstance(svc, HeadAngleEncoderService)
