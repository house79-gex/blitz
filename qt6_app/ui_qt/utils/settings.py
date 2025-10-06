import json
import os
from typing import Any, Dict

SETTINGS_PATH = os.path.join("data", "settings.json")
THEMES_PATH = os.path.join("data", "themes.json")

DEFAULT_SETTINGS = {
    "solver": "ILP",          # "ILP" oppure "BFD"
    "ilp_time_limit_s": 15,   # time limit in secondi
}

def _ensure_dir(path: str):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def _read_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path: str, data: Any):
    _ensure_dir(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def read_settings() -> Dict[str, Any]:
    data = _read_json(SETTINGS_PATH, DEFAULT_SETTINGS)
    # fallback per chiavi mancanti
    for k, v in DEFAULT_SETTINGS.items():
        data.setdefault(k, v)
    return data

def write_settings(data: Dict[str, Any]):
    # salva solo chiavi conosciute + extra consentite
    base = read_settings()
    base.update(data or {})
    _write_json(SETTINGS_PATH, base)

def read_themes() -> Dict[str, Any]:
    return _read_json(THEMES_PATH, {})

def save_theme_combo(name: str, palette: Dict[str, Any], icons: Dict[str, Any] | None = None):
    data = read_themes()
    data[name] = {
        "palette": palette or {},
        "icons": icons or {},
    }
    _write_json(THEMES_PATH, data)