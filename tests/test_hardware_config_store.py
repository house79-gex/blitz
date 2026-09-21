"""Test store hardware_config e mappa digital_inputs."""
from ui_qt.utils.hardware_config_store import (
    default_digital_inputs,
    resolve_digital_input,
    deep_update,
    load_hardware_config,
    hardware_config_path,
)


def test_default_digital_inputs_keys():
    d = default_digital_inputs()
    for key in (
        "fc_min",
        "blade_pulse",
        "start_pressed",
        "head_sx_zero",
        "head_dx_zero",
    ):
        assert key in d
        assert "module" in d[key]
        assert "index" in d[key]


def test_resolve_digital_input_override():
    cfg = {
        "digital_inputs": {
            "blade_pulse": {"module": 2, "index": 5, "active_high": False},
        }
    }
    meta = resolve_digital_input(cfg, "blade_pulse")
    assert meta["module"] == 2
    assert meta["index"] == 5
    assert meta["active_high"] is False


def test_deep_update_nested():
    base = {"a": {"x": 1, "y": 2}, "b": 3}
    out = deep_update(base, {"a": {"y": 9}, "c": 4})
    assert out["a"]["x"] == 1
    assert out["a"]["y"] == 9
    assert out["b"] == 3
    assert out["c"] == 4


def test_hardware_config_file_exists():
    path = hardware_config_path()
    assert path.name == "hardware_config.json"
    cfg = load_hardware_config()
    assert isinstance(cfg, dict)
    if cfg:
        assert "digital_inputs" in cfg or "motion_control" in cfg
