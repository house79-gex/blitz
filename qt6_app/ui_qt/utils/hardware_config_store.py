"""
Caricamento/salvataggio di data/hardware_config.json.
"""
from __future__ import annotations

import json
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("hardware_config_store")


def project_root() -> Path:
    """Radice repo (cartella che contiene data/ e qt6_app/)."""
    here = Path(__file__).resolve()
    # ui_qt/utils → ui_qt → qt6_app → root
    return here.parents[3]


def hardware_config_path() -> Path:
    return project_root() / "data" / "hardware_config.json"


def load_hardware_config() -> Dict[str, Any]:
    path = hardware_config_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except FileNotFoundError:
        logger.warning("hardware_config.json non trovato: %s", path)
    except Exception as e:
        logger.error("Errore lettura hardware_config: %s", e)
    return {}


def save_hardware_config(data: Dict[str, Any]) -> bool:
    """Salva l'intero dict (sovrascrittura controllata dal chiamante)."""
    path = hardware_config_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        logger.info("hardware_config salvato: %s", path)
        return True
    except Exception as e:
        logger.error("Errore salvataggio hardware_config: %s", e)
        return False


def deep_update(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    """Merge ricorsivo: aggiorna solo le chiavi presenti in updates."""
    out = deepcopy(base) if base else {}
    for key, value in (updates or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_update(out[key], value)
        else:
            out[key] = deepcopy(value)
    return out


def merge_and_save(updates: Dict[str, Any]) -> bool:
    current = load_hardware_config()
    merged = deep_update(current, updates)
    from datetime import date
    merged["last_updated"] = date.today().isoformat()
    return save_hardware_config(merged)


def default_digital_inputs() -> Dict[str, Any]:
    """Mappa logica ingressi → modulo Waveshare / canale (0-based)."""
    return {
        "description": "Mappa segnali logici software → ingressi Modbus Waveshare",
        "fc_min": {
            "module": 1,
            "index": 0,
            "active_high": True,
            "label": "FC_MIN (induttivo NPN NO)",
        },
        "fc_max": {
            "module": 1,
            "index": 1,
            "active_high": True,
            "label": "FC_MAX (microswitch NA)",
        },
        "emergency_ok": {
            "module": 1,
            "index": 2,
            "active_high": True,
            "label": "EMERG OK (1=OK, 0=emergenza)",
        },
        "head_sx_zero": {
            "module": 1,
            "index": 3,
            "active_high": True,
            "label": "FC testa SX 0° (induttivo)",
        },
        "head_dx_zero": {
            "module": 1,
            "index": 4,
            "active_high": True,
            "label": "FC testa DX 0° (induttivo)",
        },
        "piece_count_sx": {
            "module": 2,
            "index": 0,
            "active_high": False,
            "label": "Micro SX: conteggio + rientro testa + fine taglio",
        },
        "piece_count_dx": {
            "module": 2,
            "index": 1,
            "active_high": False,
            "label": "Micro DX: conteggio + rientro testa + fine taglio",
        },
        "blade_pulse": {
            "module": 2,
            "index": 2,
            "active_high": True,
            "label": "Opzionale: impulso dedicato (se non usi i micro)",
        },
        "start_pressed": {
            "module": 2,
            "index": 3,
            "active_high": True,
            "label": "START macchina / conferma sequenza",
        },
        "dx_blade_out": {
            "module": 2,
            "index": 4,
            "active_high": True,
            "label": "Uscita lama DX",
        },
    }


def resolve_digital_input(
    config: Optional[Dict[str, Any]],
    signal: str,
) -> Dict[str, Any]:
    """Restituisce {module, index, active_high, label} per un segnale logico."""
    defaults = default_digital_inputs()
    dig = (config or {}).get("digital_inputs") or {}
    base = dict(defaults.get(signal) or {})
    override = dig.get(signal) if isinstance(dig.get(signal), dict) else {}
    base.update(override or {})
    return base


__all__ = [
    "project_root",
    "hardware_config_path",
    "load_hardware_config",
    "save_hardware_config",
    "deep_update",
    "merge_and_save",
    "default_digital_inputs",
    "resolve_digital_input",
]
