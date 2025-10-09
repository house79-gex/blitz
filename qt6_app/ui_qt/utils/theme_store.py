import json
import os
from typing import Dict, Any

THEMES_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "themes.json")

_DEFAULT_COMBOS: Dict[str, Dict[str, Any]] = {
    "Classic": {
        "palette": {
            "APP_BG": "#1c2833", "SURFACE_BG": "#22313f", "PANEL_BG": "#2c3e50", "CARD_BG": "#34495e",
            "TILE_BG": "#2f4f6a", "ACCENT": "#2980b9", "ACCENT_2": "#9b59b6", "OK": "#27ae60",
            "WARN": "#e67e22", "ERR": "#e74c3c", "TEXT": "#ecf0f1", "TEXT_MUTED": "#bdc3c7",
            "OUTLINE": "#2c3e50", "OUTLINE_SOFT": "#3b4b5a", "HEADER_BG": "#2c3e50", "HEADER_FG": "#ecf0f1",
        },
        "icons": {}
    },
    "Dark": {
        "palette": {
            "APP_BG": "#121212", "SURFACE_BG": "#1e1e1e", "PANEL_BG": "#232323", "CARD_BG": "#262626",
            "TILE_BG": "#2a2a2a", "ACCENT": "#0a84ff", "ACCENT_2": "#64d2ff", "OK": "#34c759",
            "WARN": "#ff9f0a", "ERR": "#ff3b30", "TEXT": "#f5f5f5", "TEXT_MUTED": "#c7c7c7",
            "OUTLINE": "#333333", "OUTLINE_SOFT": "#3d3d3d", "HEADER_BG": "#1f1f1f", "HEADER_FG": "#f5f5f5",
        },
        "icons": {}
    },
    "Light": {
        "palette": {
            "APP_BG": "#f2f2f2", "SURFACE_BG": "#ffffff", "PANEL_BG": "#f7f9fb", "CARD_BG": "#ffffff",
            "TILE_BG": "#f0f4f9", "ACCENT": "#0078d4", "ACCENT_2": "#2b88d8", "OK": "#107c10",
            "WARN": "#ca5010", "ERR": "#d13438", "TEXT": "#1b1a19", "TEXT_MUTED": "#605e5c",
            "OUTLINE": "#d0d0d0", "OUTLINE_SOFT": "#e0e0e0", "HEADER_BG": "#ffffff", "HEADER_FG": "#1b1a19",
        },
        "icons": {}
    }
}

def _ensure_dir():
    os.makedirs(os.path.dirname(THEMES_FILE), exist_ok=True)

def _read_raw() -> Dict[str, Any]:
    if not os.path.exists(THEMES_FILE):
        return {"current_name": "Dark", "combos": _DEFAULT_COMBOS.copy()}
    try:
        with open(THEMES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"current_name": "Dark", "combos": _DEFAULT_COMBOS.copy()}

def _write_raw(data: Dict[str, Any]):
    _ensure_dir()
    with open(THEMES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def read_themes() -> Dict[str, Dict[str, Any]]:
    """
    Ritorna tutte le combinazioni disponibili (preset + salvate).
    """
    data = _read_raw()
    combos = data.get("combos", {}) or {}
    # Garantisci preset sempre presenti
    for k, v in _DEFAULT_COMBOS.items():
        combos.setdefault(k, v)
    return combos

def save_theme_combo(name: str, palette: Dict[str, str], icons: Dict[str, str] | None = None):
    """
    Salva/aggiorna una combinazione con nome.
    """
    data = _read_raw()
    combos = data.get("combos", {}) or {}
    combos[name] = {"palette": palette or {}, "icons": icons or {}}
    data["combos"] = combos
    # se non c'è current_name, impostalo
    if not data.get("current_name"):
        data["current_name"] = name
    _write_raw(data)

def get_current_theme_name() -> str:
    data = _read_raw()
    name = str(data.get("current_name") or "Dark")
    # se manca nei combos, ripiega su Dark
    combos = read_themes()
    return name if name in combos else "Dark"

def set_current_theme_name(name: str):
    data = _read_raw()
    data["current_name"] = name
    # assicurati che esista nei combos
    combos = data.get("combos", {}) or {}
    if name not in combos:
        combos[name] = _DEFAULT_COMBOS.get(name, {"palette": {}, "icons": {}})
        data["combos"] = combos
    _write_raw(data)

def get_active_theme() -> Dict[str, Any]:
    """
    Ritorna la combinazione attiva: {"palette": {...}, "icons": {...}}
    """
    name = get_current_theme_name()
    combos = read_themes()
    return combos.get(name, {"palette": {}, "icons": {}})
