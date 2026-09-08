"""
Logging Configuration
---------------------

This module provides a centralized function for setting up a consistent
logging format across the entire application.

Every module logger shares the same handlers: a rotating file handler under
%LOCALAPPDATA%\\ShamsiTray\\logs plus a console handler when stderr exists.
The windowed EXE has no console, so the file handler is the only durable
record of what the app did.
"""
import logging
import sys
from logging.handlers import RotatingFileHandler

from config import APP_CONFIG

class QLoggingFormatter(logging.Formatter):
    """Custom formatter with milliseconds precision."""
    def formatTime(self, record, datefmt=None):
        if datefmt:
            return super().formatTime(record, datefmt)
        return f"{super().formatTime(record, '%Y-%m-%d %H:%M:%S')},{int(record.msecs):03d}"

_shared_handlers: list = []

def _get_shared_handlers(formatter: logging.Formatter) -> list:
    """Build (once) the handlers shared by all module loggers."""
    global _shared_handlers
    if not _shared_handlers:
        # Rotating file handler: keeps the log size bounded (1 MB x 3 backups).
        try:
            if APP_CONFIG.ensure_user_data_dirs():
                file_handler = RotatingFileHandler(
                    APP_CONFIG.LOG_FILE_PATH,
                    maxBytes=1_000_000,
                    backupCount=3,
                    encoding='utf-8')
                file_handler.setFormatter(formatter)
                _shared_handlers.append(file_handler)
        except OSError:
            # No writable user-data dir: degrade to console-only logging.
            pass
        if sys.stderr is not None:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            _shared_handlers.append(console_handler)
    return _shared_handlers

def setup_logging(name: str, level=logging.INFO) -> logging.Logger:
    """
    Set up and return a logger with a custom formatter.
    Avoids duplicate handlers and duplicate log propagation.
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        formatter = QLoggingFormatter(
            '[%(levelname)s] %(asctime)s - %(name)s - %(message)s'
        )
        for handler in _get_shared_handlers(formatter):
            logger.addHandler(handler)

        logger.setLevel(level)
        logger.propagate = False

    return logger
