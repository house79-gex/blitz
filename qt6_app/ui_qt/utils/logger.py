"""
Production-grade logging system for Blitz CNC.

Features:
- Structured JSON logging to file
- Human-readable console output
- Rotating file handlers
- Separate error log
- Configurable log levels per module
"""

import logging
import logging.handlers
import json
from pathlib import Path
from datetime import datetime
from typing import Optional


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logs"""
    
    def format(self, record):
        log_data = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
            'thread': record.threadName,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': self.formatException(record.exc_info)
            }
        
        # Add extra fields if present
        if hasattr(record, 'extra_data'):
            log_data['extra'] = record.extra_data
        
        return json.dumps(log_data, ensure_ascii=False)


def setup_logging(
    log_dir: Optional[Path] = None,
    console_level=logging.INFO,
    file_level=logging.DEBUG
):
    """
    Setup production-grade logging.
    
    Args:
        log_dir: Directory for log files (default: ~/.blitz/logs)
        console_level: Logging level for console output
        file_level: Logging level for file output
    
    Creates:
        - blitz.log: All logs (rotating, 10MB, 5 backups)
        - errors.log: Error logs only (rotating, 5MB, 3 backups)
        - Console: INFO+ formatted output
    """
    if log_dir is None:
        log_dir = Path.home() / '.blitz' / 'logs'
    
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Root logger
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    
    # Remove existing handlers
    root.handlers.clear()
    
    # Console handler (INFO, human-readable)
    console = logging.StreamHandler()
    console.setLevel(console_level)
    console.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    ))
    root.addHandler(console)
    
    # Main file handler (DEBUG, structured JSON)
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / 'blitz.log',
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(file_level)
    file_handler.setFormatter(StructuredFormatter())
    root.addHandler(file_handler)
    
    # Error file handler (ERROR only)
    error_handler = logging.handlers.RotatingFileHandler(
        log_dir / 'errors.log',
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=3,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(StructuredFormatter())
    root.addHandler(error_handler)
    
    # Log startup with a specific logger to avoid handler ordering issues
    startup_logger = logging.getLogger("blitz.logging")
    startup_logger.info(f"Logging system initialized - log_dir={log_dir}")
    
    return log_dir


def get_logger(name: str) -> logging.Logger:
    """
    Get logger with specified name.
    
    Args:
        name: Logger name (usually __name__)
    
    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)
