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


# Qt prints a couple of warnings from its own internals that are known to be
# benign for this app: they accompany normal resource teardown, not a failure.
# They are dropped at the message-handler level so they stop alarming the user
# on stderr; everything else Qt prints is mirrored into the rotating log.
_QT_BENIGN_WARNINGS = (
    # TLS connections being recycled/closed in Qt's HTTP thread after a
    # transfer ends (e.g. right after the installer download finishes). The
    # download already verified its sha256 by then; no data is affected.
    "QIODevice::read (QSslSocket): device not open",
    # QSS pixel-size fonts ("font-size: NNpx") re-resolved against a
    # point-size default font under Windows fractional DPI scaling. Qt-internal
    # font merging; every widget ends up with a concrete font regardless.
    "QFont::setPointSize: Point size <= 0 (-1)",
)


def is_benign_qt_warning(message: str) -> bool:
    """True when a Qt message is one of the known-benign internals warnings."""
    return any(benign in message for benign in _QT_BENIGN_WARNINGS)


def install_qt_message_handler() -> None:
    """Route Qt's native diagnostics (qDebug/qWarning/qCritical) into the app log.

    Qt's own messages previously went straight to stderr, so in the windowed
    EXE they were invisible, while in dev runs they appeared unformatted and
    uncorrelated with the log file. This handler mirrors every Qt message into
    the shared rotating log (category kept when Qt provides one), drops the
    known-benign warnings listed in ``_QT_BENIGN_WARNINGS`` entirely, and lets
    fatal messages terminate the process like the default handler would.
    """
    from PyQt6.QtCore import QtMsgType, qInstallMessageHandler

    def handler(msg_type, context, message):
        if is_benign_qt_warning(message):
            return
        level = {
            QtMsgType.QtDebugMsg: logging.DEBUG,
            QtMsgType.QtInfoMsg: logging.INFO,
            QtMsgType.QtWarningMsg: logging.WARNING,
            QtMsgType.QtCriticalMsg: logging.ERROR,
            QtMsgType.QtFatalMsg: logging.CRITICAL,
        }.get(msg_type, logging.WARNING)
        try:
            # PyQt6 hands the category over as a str already, so the old
            # .decode() raised AttributeError on every message and its except
            # branch funnelled everything into "general". Qt names uncategorized
            # messages "default", which this app logs as qt.general.
            category = context.category if context.category and context.category != "default" else "general"
        except Exception:
            category = "general"
        setup_logging(f"qt.{category}").log(level, message)
        if msg_type == QtMsgType.QtFatalMsg:
            raise SystemExit(1)

    qInstallMessageHandler(handler)
