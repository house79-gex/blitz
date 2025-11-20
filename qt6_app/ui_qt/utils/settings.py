"""
Modulo per la gestione delle impostazioni dell'applicazione
File: qt6_app/ui_qt/utils/settings.py
Date: 2025-11-20
Author: house79-gex
"""

import json
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Path per il file delle impostazioni
SETTINGS_DIR = Path.home() / '.blitz'
SETTINGS_FILE = SETTINGS_DIR / 'settings.json'

# Impostazioni di default
DEFAULT_SETTINGS = {
    'application': {
        'version': '3.0.0',
        'language': 'it',
        'theme': 'light',
        'auto_save': True,
        'auto_save_interval': 300  # secondi
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
    'recent_plans': []
}


def ensure_settings_dir():
    """Assicura che la directory delle impostazioni esista"""
    if not SETTINGS_DIR.exists():
        try:
            SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
            logger.info(f"Directory impostazioni creata: {SETTINGS_DIR}")
        except Exception as e:
            logger.error(f"Impossibile creare directory impostazioni: {e}")
            

def load_settings() -> Dict[str, Any]:
    """
    Carica le impostazioni dal file JSON
    
    Returns:
        Dizionario con le impostazioni caricate o quelle di default
    """
    ensure_settings_dir()
    
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                
            # Merge con le impostazioni di default per aggiungere eventuali nuove chiavi
            merged_settings = merge_settings(DEFAULT_SETTINGS, settings)
            
            logger.info(f"Impostazioni caricate da {SETTINGS_FILE}")
            return merged_settings
            
        except json.JSONDecodeError as e:
            logger.error(f"Errore nel parsing del file impostazioni: {e}")
            logger.info("Utilizzo impostazioni di default")
            
        except Exception as e:
            logger.error(f"Errore nel caricamento impostazioni: {e}")
            
    # Se il file non esiste o c'è stato un errore, usa le impostazioni di default
    logger.info("Utilizzo impostazioni di default")
    return DEFAULT_SETTINGS.copy()


def save_settings(settings: Dict[str, Any]) -> bool:
    """
    Salva le impostazioni nel file JSON
    
    Args:
        settings: Dizionario con le impostazioni da salvare
        
    Returns:
        True se il salvataggio è riuscito, False altrimenti
    """
    ensure_settings_dir()
    
    try:
        # Backup del file esistente
        if SETTINGS_FILE.exists():
            backup_file = SETTINGS_FILE.with_suffix('.json.bak')
            try:
                backup_file.write_bytes(SETTINGS_FILE.read_bytes())
            except Exception as e:
                logger.warning(f"Impossibile creare backup impostazioni: {e}")
        
        # Salva le nuove impostazioni
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
            
        logger.info(f"Impostazioni salvate in {SETTINGS_FILE}")
        return True
        
    except Exception as e:
        logger.error(f"Errore nel salvataggio impostazioni: {e}")
        return False


def merge_settings(defaults: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
    """
    Unisce le impostazioni correnti con quelle di default
    
    Args:
        defaults: Impostazioni di default
        current: Impostazioni correnti
        
    Returns:
        Impostazioni unite
    """
    merged = defaults.copy()
    
    for key, value in current.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            # Ricorsione per dizionari annidati
            merged[key] = merge_settings(merged[key], value)
        else:
            # Sovrascrivi il valore
            merged[key] = value
            
    return merged


def get_setting(path: str, default: Any = None) -> Any:
    """
    Ottiene un'impostazione specifica usando un percorso puntato
    
    Args:
        path: Percorso dell'impostazione (es. "machine.max_length")
        default: Valore di default se l'impostazione non esiste
        
    Returns:
        Valore dell'impostazione o il default
    """
    settings = load_settings()
    
    keys = path.split('.')
    value = settings
    
    try:
        for key in keys:
            value = value[key]
        return value
    except (KeyError, TypeError):
        return default


def set_setting(path: str, value: Any) -> bool:
    """
    Imposta un valore specifico usando un percorso puntato
    
    Args:
        path: Percorso dell'impostazione (es. "machine.max_length")
        value: Valore da impostare
        
    Returns:
        True se l'impostazione è stata salvata con successo
    """
    settings = load_settings()
    
    keys = path.split('.')
    current = settings
    
    try:
        # Naviga fino al penultimo livello
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
            
        # Imposta il valore
        current[keys[-1]] = value
        
        # Salva le impostazioni
        return save_settings(settings)
        
    except Exception as e:
        logger.error(f"Errore nell'impostazione di {path}: {e}")
        return False


def reset_settings() -> bool:
    """
    Ripristina le impostazioni di default
    
    Returns:
        True se il ripristino è riuscito
    """
    return save_settings(DEFAULT_SETTINGS)


def add_recent_file(filepath: str, max_recent: int = 10):
    """
    Aggiunge un file alla lista dei file recenti
    
    Args:
        filepath: Path del file da aggiungere
        max_recent: Numero massimo di file recenti da mantenere
    """
    settings = load_settings()
    
    recent_files = settings.get('recent_files', [])
    
    # Rimuovi se già presente
    if filepath in recent_files:
        recent_files.remove(filepath)
        
    # Aggiungi all'inizio
    recent_files.insert(0, filepath)
    
    # Limita la lunghezza
    recent_files = recent_files[:max_recent]
    
    settings['recent_files'] = recent_files
    save_settings(settings)


def get_recent_files() -> list:
    """
    Ottiene la lista dei file recenti
    
    Returns:
        Lista dei file recenti
    """
    settings = load_settings()
    return settings.get('recent_files', [])


def add_recent_order(order_id: str, max_recent: int = 20):
    """
    Aggiunge un ordine alla lista degli ordini recenti
    
    Args:
        order_id: ID dell'ordine
        max_recent: Numero massimo di ordini recenti
    """
    settings = load_settings()
    
    recent_orders = settings.get('recent_orders', [])
    
    if order_id in recent_orders:
        recent_orders.remove(order_id)
        
    recent_orders.insert(0, order_id)
    recent_orders = recent_orders[:max_recent]
    
    settings['recent_orders'] = recent_orders
    save_settings(settings)


def get_recent_orders() -> list:
    """
    Ottiene la lista degli ordini recenti
    
    Returns:
        Lista degli ordini recenti
    """
    settings = load_settings()
    return settings.get('recent_orders', [])


def export_settings(filepath: str) -> bool:
    """
    Esporta le impostazioni in un file specifico
    
    Args:
        filepath: Path del file di destinazione
        
    Returns:
        True se l'esportazione è riuscita
    """
    settings = load_settings()
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        logger.info(f"Impostazioni esportate in {filepath}")
        return True
    except Exception as e:
        logger.error(f"Errore nell'esportazione impostazioni: {e}")
        return False


def import_settings(filepath: str) -> bool:
    """
    Importa le impostazioni da un file specifico
    
    Args:
        filepath: Path del file sorgente
        
    Returns:
        True se l'importazione è riuscita
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            imported_settings = json.load(f)
            
        # Valida le impostazioni importate
        if not isinstance(imported_settings, dict):
            logger.error("File impostazioni non valido")
            return False
            
        # Merge con le impostazioni di default
        merged_settings = merge_settings(DEFAULT_SETTINGS, imported_settings)
        
        # Salva le impostazioni
        return save_settings(merged_settings)
        
    except json.JSONDecodeError as e:
        logger.error(f"Errore nel parsing del file impostazioni: {e}")
        return False
    except Exception as e:
        logger.error(f"Errore nell'importazione impostazioni: {e}")
        return False


class SettingsManager:
    """Classe singleton per la gestione centralizzata delle impostazioni"""
    
    _instance = None
    _settings = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._settings = load_settings()
        return cls._instance
    
    def get(self, path: str, default: Any = None) -> Any:
        """Ottiene un'impostazione"""
        return get_setting(path, default)
    
    def set(self, path: str, value: Any) -> bool:
        """Imposta un valore"""
        result = set_setting(path, value)
        if result:
            self._settings = load_settings()  # Ricarica le impostazioni
        return result
    
    def reload(self):
        """Ricarica le impostazioni dal disco"""
        self._settings = load_settings()
        
    def save(self) -> bool:
        """Salva le impostazioni correnti"""
        return save_settings(self._settings)
    
    @property
    def settings(self) -> Dict[str, Any]:
        """Ottiene tutte le impostazioni"""
        return self._settings.copy()


# Esporta le funzioni principali
__all__ = [
    'load_settings',
    'save_settings',
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
