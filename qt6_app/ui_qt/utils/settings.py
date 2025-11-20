"""
Modulo per la gestione delle impostazioni dell'applicazione
File: qt6_app/ui_qt/utils/settings.py
Date: 2025-11-20
Author: house79-gex

AGGIORNAMENTO:
Aggiunti i wrapper read_settings / write_settings richiesti dal resto dell'app
(OptimizationRunDialog, AutomaticoPage, ecc.) che nella versione precedente
non esistevano, causando il fallback a funzioni stub e quindi la NON
persistenza delle modifiche.

Inoltre introdotti i TOP-LEVEL keys usati dal modulo di ottimizzazione:
  opt_stock_mm, opt_stock_usable_mm, opt_kerf_mm, opt_ripasso_mm, opt_solver,
  opt_time_limit_s, opt_refine_tail_bars, opt_refine_time_s,
  opt_kerf_max_angle_deg, opt_kerf_max_factor, opt_knap_conservative_angle_deg,
  opt_current_profile_reversible, opt_current_profile_thickness_mm,
  opt_reversible_angle_tol_deg, opt_warn_overflow_mm, opt_auto_continue_enabled,
  opt_auto_continue_across_bars, opt_strict_bar_sequence, opt_enable_tail_refine,
  opt_show_graph, opt_collapse_done_bars, auto_after_cut_pause_ms,
  semi_offset_mm, inpos_tol_mm, label_enabled, label_printer_model,
  label_backend, label_printer_name, label_paper, label_rotate.

Questi vengono salvati DIRECTLY a livello root insieme alla struttura originale
per retro–compatibilità. I wrapper scrivono solo i campi forniti senza perdere
gli altri (merge).
"""

import json
import os
import logging
import contextlib
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Directory & file
SETTINGS_DIR = Path.home() / '.blitz'
SETTINGS_FILE = SETTINGS_DIR / 'settings.json'
TMP_SUFFIX = '.tmp'

# Impostazioni di default (originali + aggiunta top-level per ottimizzazione)
DEFAULT_SETTINGS: Dict[str, Any] = {
    # Struttura originale
    'application': {
        'version': '3.0.0',
        'language': 'it',
        'theme': 'light',
        'auto_save': True,
        'auto_save_interval': 300
    },
    'machine': {
        'max_length': 7000,
        'min_length': 10,
        'default_speed': 50,
        'default_acceleration': 100,
        'home_position': 0,
        'park_position': 6000,
        'serial_port': 'COM1',
        'baud_rate': 115200
    },
    'cutting': {
        'default_kerf': 3.0,
        'default_ripasso': 5.0,
        'default_angle': 90,
        'min_angle': 15,
        'max_angle': 165,
        'default_tolerance': 0.5
    },
    'automatic': {
        'speed': 50,
        'kerf': 3.0,
        'ripasso': 5.0,
        'recupero': True,
        'auto_advance': True,
        'confirm_cut': False,
        'sound_enabled': True
    },
    'optimization': {
        'solver': 'ILP',
        'timeout': 60,
        'kerf': 3.0,
        'ripasso': 5.0,
        'tolerance': 0.5,
        'enable_refining': True,
        'enable_sequencing': True,
        'recupero': True,
        'group_by_angle': False,
        'min_scrap_length': 100
    },
    'ui': {
        'window_maximized': False,
        'window_width': 1200,
        'window_height': 800,
        'sidebar_width': 200,
        'show_tooltips': True,
        'animation_speed': 300
    },
    'paths': {
        'last_order_dir': '',
        'last_plan_dir': '',
        'last_export_dir': '',
        'database_path': ''
    },
    'recent_files': [],
    'recent_orders': [],
    'recent_plans': [],
    # --- Top-level optimization & run-time compat keys (NEW) ---
    'opt_stock_mm':            6500.0,
    'opt_stock_usable_mm':     0.0,
    'opt_kerf_mm':             3.0,
    'opt_ripasso_mm':          0.0,
    'opt_solver':              'ILP_KNAP',
    'opt_time_limit_s':        15,
    'opt_refine_tail_bars':    6,
    'opt_refine_time_s':       25,
    'opt_kerf_max_angle_deg':  60.0,
    'opt_kerf_max_factor':     2.0,
    'opt_knap_conservative_angle_deg': 45.0,
    'opt_current_profile_reversible': False,
    'opt_current_profile_thickness_mm': 0.0,
    'opt_reversible_angle_tol_deg': 0.5,
    'opt_warn_overflow_mm':    0.5,
    'opt_auto_continue_enabled': False,
    'opt_auto_continue_across_bars': False,
    'opt_strict_bar_sequence': True,
    'opt_enable_tail_refine':  True,
    'opt_show_graph':          True,
    'opt_collapse_done_bars':  True,
    'auto_after_cut_pause_ms': 300,
    'semi_offset_mm':          120.0,
    'inpos_tol_mm':            0.20,
    # Etichette (top-level) per compat
    'label_enabled':           False,
    'label_printer_model':     'QL-800',
    'label_backend':           'wspool',
    'label_printer_name':      '',
    'label_paper':             'DK-11201',
    'label_rotate':            0
}

# Chiavi di mapping (se un giorno vuoi sincronizzare con la struttura annidata)
# Al momento lasciamo il top-level come fonte di verità per i moduli che lo usano.
MAPPING_FLAT_TO_NESTED = {
    # 'opt_kerf_mm': ('optimization', 'kerf'),  # esempio se vuoi sincronizzare
}

# Lock semplice
_lock = None
def _get_lock():
    global _lock
    if _lock is None:
        import threading
        _lock = threading.Lock()
    return _lock


def ensure_settings_dir():
    if not SETTINGS_DIR.exists():
        try:
            SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
            logger.info(f"Directory impostazioni creata: {SETTINGS_DIR}")
        except Exception as e:
            logger.error(f"Impossibile creare directory impostazioni: {e}")


def merge_settings(defaults: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
    merged = defaults.copy()
    for key, value in current.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = merge_settings(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_settings() -> Dict[str, Any]:
    ensure_settings_dir()
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("File impostazioni non è un dict valido.")
            return merge_settings(DEFAULT_SETTINGS, data)
        except Exception as e:
            logger.error(f"Errore caricamento impostazioni: {e}")
            return DEFAULT_SETTINGS.copy()
    # file assente
    return DEFAULT_SETTINGS.copy()


def save_settings(settings: Dict[str, Any]) -> bool:
    ensure_settings_dir()
    # merge con defaults prima di scrivere
    settings = merge_settings(DEFAULT_SETTINGS, settings)
    tmp_path = SETTINGS_FILE.with_suffix(SETTINGS_FILE.suffix + TMP_SUFFIX)
    try:
        with _get_lock():
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
            os.replace(str(tmp_path), str(SETTINGS_FILE))
        return True
    except Exception as e:
        logger.error(f"Errore salvataggio impostazioni: {e}")
        with contextlib.suppress(Exception):
            if tmp_path.exists():
                tmp_path.unlink()
        return False


# ------------- Wrapper COMPAT richiesti dal codice esistente -------------
def read_settings() -> Dict[str, Any]:
    """
    Wrapper compatibile: ritorna un dict con TUTTO (annidato + top-level).
    """
    return load_settings()


def write_settings(new_data: Dict[str, Any]) -> None:
    """
    Wrapper compatibile: merge dei dati e salva.
    Non elimina nessuna chiave esistente.
    """
    if not isinstance(new_data, dict):
        return
    current = load_settings()
    # Aggiorna top-level
    for k, v in new_data.items():
        current[k] = v
        # Se hai definito mapping per sync con nested, applicalo:
        if k in MAPPING_FLAT_TO_NESTED:
            path = MAPPING_FLAT_TO_NESTED[k]
            if isinstance(path, tuple) and len(path) >= 2:
                level = current
                for subkey in path[:-1]:
                    if subkey not in level or not isinstance(level[subkey], dict):
                        level[subkey] = {}
                    level = level[subkey]
                level[path[-1]] = v
    save_settings(current)


# ------------- Funzioni puntate originali -------------
def get_setting(path: str, default: Any = None) -> Any:
    settings = load_settings()
    keys = path.split('.')
    value: Any = settings
    try:
        for key in keys:
            value = value[key]
        return value
    except (KeyError, TypeError):
        return default


def set_setting(path: str, value: Any) -> bool:
    settings = load_settings()
    keys = path.split('.')
    cur = settings
    try:
        for k in keys[:-1]:
            if k not in cur or not isinstance(cur[k], dict):
                cur[k] = {}
            cur = cur[k]
        cur[keys[-1]] = value
        # se la chiave finale coincide con un top-level compat, aggiorna anche quello
        top_key = path.replace('.', '_')
        if top_key in DEFAULT_SETTINGS:
            settings[top_key] = value
        return save_settings(settings)
    except Exception as e:
        logger.error(f"Errore set_setting({path}): {e}")
        return False


def reset_settings() -> bool:
    return save_settings(DEFAULT_SETTINGS.copy())


# ------------- Recent items -------------
def add_recent_file(filepath: str, max_recent: int = 10):
    settings = load_settings()
    recent_files = settings.get('recent_files', [])
    if filepath in recent_files:
        recent_files.remove(filepath)
    recent_files.insert(0, filepath)
    recent_files = recent_files[:max_recent]
    settings['recent_files'] = recent_files
    save_settings(settings)


def get_recent_files() -> list:
    settings = load_settings()
    return settings.get('recent_files', [])


def add_recent_order(order_id: str, max_recent: int = 20):
    settings = load_settings()
    recent_orders = settings.get('recent_orders', [])
    if order_id in recent_orders:
        recent_orders.remove(order_id)
    recent_orders.insert(0, order_id)
    recent_orders = recent_orders[:max_recent]
    settings['recent_orders'] = recent_orders
    save_settings(settings)


def get_recent_orders() -> list:
    settings = load_settings()
    return settings.get('recent_orders', [])


def export_settings(filepath: str) -> bool:
    settings = load_settings()
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        logger.info(f"Impostazioni esportate in {filepath}")
        return True
    except Exception as e:
        logger.error(f"Errore esportazione impostazioni: {e}")
        return False


def import_settings(filepath: str) -> bool:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            imported = json.load(f)
        if not isinstance(imported, dict):
            logger.error("File impostazioni non valido")
            return False
        merged = merge_settings(DEFAULT_SETTINGS, imported)
        return save_settings(merged)
    except Exception as e:
        logger.error(f"Errore import impostazioni: {e}")
        return False


# ------------- SettingsManager -------------
class SettingsManager:
    _instance = None
    _settings: Dict[str, Any]

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._settings = load_settings()
        return cls._instance

    def get(self, path: str, default: Any = None) -> Any:
        return get_setting(path, default)

    def set(self, path: str, value: Any) -> bool:
        ok = set_setting(path, value)
        if ok:
            self._settings = load_settings()
        return ok

    def reload(self):
        self._settings = load_settings()

    def save(self) -> bool:
        return save_settings(self._settings)

    @property
    def settings(self) -> Dict[str, Any]:
        return self._settings.copy()


__all__ = [
    'load_settings',
    'save_settings',
    'read_settings',
    'write_settings',
    'get_setting',
    'set_setting',
    'reset_settings',
    'add_recent_file',
    'get_recent_files',
    'add_recent_order',
    'get_recent_orders',
    'export_settings',
    'import_settings',
    'SettingsManager',
    'DEFAULT_SETTINGS'
]
