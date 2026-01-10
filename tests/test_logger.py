"""
Unit tests for the production-grade logging system.
"""

import pytest
import logging
import json
import tempfile
from pathlib import Path
from qt6_app.ui_qt.utils.logger import (
    StructuredFormatter,
    setup_logging,
    get_logger
)


def test_structured_formatter_basic():
    """Test StructuredFormatter formats basic log records."""
    formatter = StructuredFormatter()
    
    logger = logging.getLogger("test_logger")
    record = logger.makeRecord(
        name="test_logger",
        level=logging.INFO,
        fn="test_file.py",
        lno=42,
        msg="Test message",
        args=(),
        exc_info=None
    )
    
    result = formatter.format(record)
    
    # Should be valid JSON
    data = json.loads(result)
    
    assert data['level'] == 'INFO'
    assert data['logger'] == 'test_logger'
    assert data['message'] == 'Test message'
    assert data['line'] == 42
    assert 'timestamp' in data


def test_structured_formatter_with_exception():
    """Test StructuredFormatter includes exception info."""
    formatter = StructuredFormatter()
    
    logger = logging.getLogger("test_logger")
    
    try:
        raise ValueError("Test error")
    except ValueError:
        import sys
        exc_info = sys.exc_info()
        
        record = logger.makeRecord(
            name="test_logger",
            level=logging.ERROR,
            fn="test_file.py",
            lno=100,
            msg="Error occurred",
            args=(),
            exc_info=exc_info
        )
        
        result = formatter.format(record)
        data = json.loads(result)
        
        assert 'exception' in data
        assert data['exception']['type'] == 'ValueError'
        assert 'Test error' in data['exception']['message']
        assert 'traceback' in data['exception']


def test_structured_formatter_with_extra_data():
    """Test StructuredFormatter includes extra data."""
    formatter = StructuredFormatter()
    
    logger = logging.getLogger("test_logger")
    record = logger.makeRecord(
        name="test_logger",
        level=logging.INFO,
        fn="test_file.py",
        lno=42,
        msg="Test message",
        args=(),
        exc_info=None
    )
    
    # Add extra data
    record.extra_data = {'operation': 'test_op', 'user_id': 123}
    
    result = formatter.format(record)
    data = json.loads(result)
    
    assert 'extra' in data
    assert data['extra']['operation'] == 'test_op'
    assert data['extra']['user_id'] == 123


def test_setup_logging_creates_handlers():
    """Test setup_logging creates appropriate handlers."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir) / 'test_logs'
        
        result_dir = setup_logging(log_dir=log_dir)
        
        assert result_dir == log_dir
        assert log_dir.exists()
        assert (log_dir / 'blitz.log').exists()
        assert (log_dir / 'errors.log').exists()
        
        # Check root logger has handlers
        root = logging.getLogger()
        assert len(root.handlers) >= 3  # Console, main file, error file
        
        # Cleanup handlers to avoid interference with other tests
        root.handlers.clear()


def test_setup_logging_default_directory():
    """Test setup_logging uses default directory."""
    # Clear any existing handlers
    logging.getLogger().handlers.clear()
    
    log_dir = setup_logging()
    
    expected_dir = Path.home() / '.blitz' / 'logs'
    assert log_dir == expected_dir
    assert log_dir.exists()
    
    # Cleanup handlers
    logging.getLogger().handlers.clear()


def test_get_logger_returns_logger():
    """Test get_logger returns a Logger instance."""
    logger = get_logger("test_module")
    
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test_module"


def test_logging_levels():
    """Test that different log levels are handled correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir) / 'test_logs'
        setup_logging(log_dir=log_dir, console_level=logging.WARNING, file_level=logging.DEBUG)
        
        logger = get_logger("level_test")
        
        # These should work without errors
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")
        logger.critical("Critical message")
        
        # Check that logs were written
        assert (log_dir / 'blitz.log').exists()
        assert (log_dir / 'errors.log').exists()
        
        # Check error log only contains errors
        error_content = (log_dir / 'errors.log').read_text()
        assert 'Error message' in error_content
        assert 'Critical message' in error_content
        
        # Cleanup
        logging.getLogger().handlers.clear()


def test_rotating_file_handler_config():
    """Test that rotating file handlers are configured correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir) / 'test_logs'
        setup_logging(log_dir=log_dir)
        
        root = logging.getLogger()
        
        # Find rotating file handlers
        rotating_handlers = [
            h for h in root.handlers 
            if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        
        assert len(rotating_handlers) >= 2  # Main log + error log
        
        # Check main file handler (10MB, 5 backups)
        main_handler = None
        error_handler = None
        
        for handler in rotating_handlers:
            if 'blitz.log' in handler.baseFilename:
                main_handler = handler
            elif 'errors.log' in handler.baseFilename:
                error_handler = handler
        
        assert main_handler is not None
        assert main_handler.maxBytes == 10 * 1024 * 1024
        assert main_handler.backupCount == 5
        
        assert error_handler is not None
        assert error_handler.maxBytes == 5 * 1024 * 1024
        assert error_handler.backupCount == 3
        
        # Cleanup
        root.handlers.clear()
