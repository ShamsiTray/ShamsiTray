"""
Logging Configuration
---------------------

This module provides a centralized function for setting up a consistent
logging format across the entire application.
"""
import logging
import time

class QLoggingFormatter(logging.Formatter):
    """Custom Formatter to include microseconds and ensure consistency."""
    def formatTime(self, record, datefmt=None):
        ct = self.converter(record.created)
        s = time.strftime('%Y-%m-%d %H:%M:%S', ct) if not datefmt else time.strftime(datefmt, ct)
        return f"{s},{int(record.msecs):03d}"

def setup_logging(name: str, level=logging.INFO) -> logging.Logger:
    """
    Sets up a logger with a custom formatter.
    Avoids adding duplicate handlers if already configured.
    """
    logger = logging.getLogger(name)
    if not logger.hasHandlers():
        handler = logging.StreamHandler()
        formatter = QLoggingFormatter('[%(levelname)s] %(asctime)s - %(name)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger
