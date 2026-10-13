"""Tests for utils.logger: shared rotating handlers, dedup setup, the
benign-Qt-warning filter and the Qt message-handler routing."""
import logging
from types import SimpleNamespace

import pytest

from config import APP_CONFIG
from utils import logger as logger_module


@pytest.fixture
def fresh_shared_handlers(monkeypatch):
    """Reset the module-global shared-handler cache so handlers are rebuilt
    against the current (temp) user-data paths, and restore afterwards."""
    original = list(logger_module._shared_handlers)
    monkeypatch.setattr(logger_module, "_shared_handlers", [])
    yield
    # Detach handlers created during the test from any lingering loggers.
    for name in list(logging.root.manager.loggerDict):
        lg = logging.getLogger(name)
        for h in list(lg.handlers):
            if h not in original:
                lg.removeHandler(h)
                try:
                    h.close()
                except Exception:
                    pass


def test_formatter_has_millisecond_precision():
    fmt = logger_module.QLoggingFormatter("[%(levelname)s] %(message)s")
    record = logging.LogRecord("n", logging.INFO, "p", 1, "hello", None, None)
    stamp = fmt.formatTime(record)
    # 'YYYY-MM-DD HH:MM:SS,mmm' - the millisecond field is zero-padded.
    parts = stamp.split(",")
    assert len(parts) == 2
    assert len(parts[1]) == 3
    assert 0 <= int(parts[1]) <= 999


def test_formatter_honors_explicit_datefmt():
    fmt = logger_module.QLoggingFormatter("%(message)s")
    record = logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)
    stamp = fmt.formatTime(record, "%Y-%m-%dT%H")
    # The custom ',mmm' millisecond suffix must NOT be appended when an
    # explicit datefmt is given (its own 'T' literal marks the hour).
    assert "T" in stamp
    assert "," not in stamp


def test_setup_logging_writes_to_rotating_file(user_data, fresh_shared_handlers):
    logger = logger_module.setup_logging("logger-test-file")
    logger.info("rotating-file-probe")
    for handler in logger.handlers:
        handler.flush()
    content = APP_CONFIG.LOG_FILE_PATH.read_text(encoding="utf-8")
    assert "rotating-file-probe" in content
    assert "[INFO]" in content


def test_setup_logging_is_idempotent(fresh_shared_handlers):
    logger = logger_module.setup_logging("logger-test-idempotent")
    count = len(logger.handlers)
    assert count >= 1
    again = logger_module.setup_logging("logger-test-idempotent")
    assert again is logger
    assert len(again.handlers) == count  # no duplicate handlers
    assert again.propagate is False


def test_benign_qt_warning_matches_both_known_noise_lines():
    assert logger_module.is_benign_qt_warning(
        "QIODevice::read (QSslSocket): device not open")
    assert logger_module.is_benign_qt_warning(
        "QFont::setPointSize: Point size <= 0 (-1), must be greater than 0")
    # Substring match: surrounding context from Qt must not hide the match.
    assert logger_module.is_benign_qt_warning(
        "prefix QIODevice::read (QSslSocket): device not open suffix")


def test_benign_qt_warning_keeps_real_problems():
    assert not logger_module.is_benign_qt_warning("QIODevice::read: real problem")
    assert not logger_module.is_benign_qt_warning("QFont::setPointSizeF: weird")
    assert not logger_module.is_benign_qt_warning("")


def _prebind_qt_general() -> None:
    """Bind the app's shared handlers to qt.general before a test emits.

    Pytest attaches its own LogCaptureHandlers to qt.* loggers as records
    flow through them, which defeats ``setup_logging``'s only-if-empty guard
    for later tests in the same module. Clearing first and binding up-front
    keeps the file handler on the current (temp) path regardless."""
    qt_logger = logging.getLogger("qt.general")
    qt_logger.handlers.clear()
    logger_module.setup_logging("qt.general")


def test_qt_message_handler_routes_and_filters(user_data, fresh_shared_handlers):
    from PyQt6.QtCore import qInstallMessageHandler, qWarning

    _prebind_qt_general()
    logger_module.install_qt_message_handler()
    try:
        qWarning("QIODevice::read (QSslSocket): device not open")  # benign: dropped
        qWarning("qt-routing-problem-probe")                       # real: logged
    finally:
        qInstallMessageHandler(None)  # restore Qt's default handler

    for handler in logging.getLogger("qt.general").handlers:
        handler.flush()
    content = APP_CONFIG.LOG_FILE_PATH.read_text(encoding="utf-8")
    assert "qt-routing-problem-probe" in content
    assert "QIODevice::read (QSslSocket)" not in content


def test_qt_message_handler_survives_reinstall(user_data, fresh_shared_handlers):
    """Installing the handler twice must not break message routing."""
    from PyQt6.QtCore import qInstallMessageHandler, qWarning

    _prebind_qt_general()
    logger_module.install_qt_message_handler()
    logger_module.install_qt_message_handler()
    try:
        qWarning("qt-reinstall-probe")
    finally:
        qInstallMessageHandler(None)
    for handler in logging.getLogger("qt.general").handlers:
        handler.flush()
    assert "qt-reinstall-probe" in APP_CONFIG.LOG_FILE_PATH.read_text(encoding="utf-8")


def test_qt_critical_with_benign_text_is_still_logged(user_data, fresh_shared_handlers):
    """The benign filter is a WARNING filter: a critical that happens to carry
    one of those substrings must still reach the log, at its own severity."""
    from PyQt6.QtCore import QtMsgType

    _prebind_qt_general()
    logger_module._log_qt_message(
        QtMsgType.QtCriticalMsg,
        SimpleNamespace(category=""),
        "QIODevice::read (QSslSocket): device not open",
    )
    for handler in logging.getLogger("qt.general").handlers:
        handler.flush()
    content = APP_CONFIG.LOG_FILE_PATH.read_text(encoding="utf-8")
    assert "QIODevice::read (QSslSocket)" in content
    assert "[ERROR]" in content


def test_qt_fatal_with_benign_text_still_terminates(user_data, fresh_shared_handlers):
    """The fatal path must survive the benign filter: dropping the warning with
    the same text must not drop the SystemExit a fatal relies on."""
    from PyQt6.QtCore import QtMsgType

    _prebind_qt_general()
    with pytest.raises(SystemExit):
        logger_module._log_qt_message(
            QtMsgType.QtFatalMsg,
            SimpleNamespace(category=""),
            "QIODevice::read (QSslSocket): device not open",
        )
    for handler in logging.getLogger("qt.general").handlers:
        handler.flush()
    content = APP_CONFIG.LOG_FILE_PATH.read_text(encoding="utf-8")
    assert "QIODevice::read (QSslSocket)" in content
    assert "[CRITICAL]" in content
