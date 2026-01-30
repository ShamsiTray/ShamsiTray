"""
Logging Configuration
---------------------

This module provides a centralized function for setting up a consistent
logging format across the entire application.
"""
import logging

class QLoggingFormatter(logging.Formatter):
    """Custom formatter with milliseconds precision."""
    def formatTime(self, record, datefmt=None):
        if datefmt:
            return super().formatTime(record, datefmt)
        return f"{super().formatTime(record, '%Y-%m-%d %H:%M:%S')},{int(record.msecs):03d}"

def setup_logging(name: str, level=logging.INFO) -> logging.Logger:
    """
    Set up and return a logger with a custom formatter.
    Avoids duplicate handlers and duplicate log propagation.
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = QLoggingFormatter(
            '[%(levelname)s] %(asctime)s - %(name)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        logger.setLevel(level)
        logger.propagate = False

    return logger