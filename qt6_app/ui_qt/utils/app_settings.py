from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict

SETTINGS_PATH = Path(__file__).resolve().parents[3] / "data" / "settings.json"

_DEFAULTS: Dict[str, Any] = {
    "probe_profiles_enabled": False,  # tastatore profili (sperimentale)
}

def _read() -> Dict[str, Any]:
    if not SETTINGS_PATH.exists():
        return dict(_DEFAULTS)
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return dict(_DEFAULTS)

def _write(data: Dict[str, Any]):
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def get(key: str, default: Any = None) -> Any:
    data = _read()
    return data.get(key, _DEFAULTS.get(key, default))

def set_value(key: str, value: Any):
    data = _read()
    data[key] = value
    _write(data)

def get_bool(key: str, default: bool = False) -> bool:
    v = get(key, default)
    return bool(v)

def set_bool(key: str, value: bool):
    set_value(key, bool(value))
