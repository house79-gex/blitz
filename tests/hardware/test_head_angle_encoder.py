"""Test servizio encoder inclinazione teste (Modbus mock)."""
from qt6_app.ui_qt.hardware.head_angle_encoder import HeadAngleEncoderService, _s16


class FakeModbus:
    def __init__(self, mapping):
        self.mapping = mapping  # addr -> list of regs
        self.coils = {}

    def read_holding_registers(self, address, start, count):
        regs = self.mapping.get(address)
        if regs is None:
            return None
        return regs[start:start + count]

    def write_single_coil(self, address, coil, value):
        self.coils[(address, coil)] = bool(value)
        return True


def test_s16_negative():
    assert _s16(4500) == 4500
    assert _s16(0xFFFF) == -1


def test_combined_poll_degrees():
    client = FakeModbus({20: [4500, 1250]})
    svc = HeadAngleEncoderService(client, {"enabled": True, "mode": "combined", "combined_addr": 20})
    st = svc.poll()
    assert st["head_encoder_online"] is True
    assert abs(st["measured_left_head_angle"] - 45.0) < 0.01
    assert abs(st["measured_right_head_angle"] - 12.5) < 0.01


def test_split_poll_and_zero():
    client = FakeModbus({20: [1000], 21: [2000]})
    svc = HeadAngleEncoderService(client, {
        "enabled": True, "mode": "split", "sx_addr": 20, "dx_addr": 21
    })
    st = svc.poll()
    assert abs(st["measured_left_head_angle"] - 10.0) < 0.01
    assert abs(st["measured_right_head_angle"] - 20.0) < 0.01
    assert svc.zero("sx") is True
    assert client.coils[(20, 0)] is True


def test_invert_and_offset():
    client = FakeModbus({20: [1000, 0]})
    svc = HeadAngleEncoderService(client, {
        "enabled": True,
        "mode": "combined",
        "invert_sx": True,
        "zero_offset_sx_deg": 1.0,
    })
    st = svc.poll()
    # raw 10°, invert → -10, offset +1 → -9
    assert abs(st["measured_left_head_angle"] - (-9.0)) < 0.01


def test_offline_when_no_response():
    client = FakeModbus({})
    svc = HeadAngleEncoderService(client, {"enabled": True, "mode": "combined"})
    st = svc.poll()
    assert st["head_encoder_online"] is False
    assert st["head_encoder_online_sx"] is False
