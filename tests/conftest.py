"""
Shared pytest fixtures
----------------------

- Forces the offscreen Qt platform before any QApplication exists so the
  suite runs headless (CI, containers, Windows without a desktop).
- Redirects the per-user data files (settings.json, user_events.json,
  holidays.json, logs) into a temp directory for every test that needs them.
- Boots a real SystemTrayIcon for controller-level tests.
"""
import os
import sys
from pathlib import Path

# Must happen before anything imports PyQt6 / constructs a QApplication.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from config import APP_CONFIG  # noqa: E402


@pytest.fixture(autouse=True)
def no_stray_network_checks(monkeypatch):
    """Keep scheduled auto update checks off the real network in tests.

    Every tray boot schedules ``QTimer.singleShot(30000, _auto_check_updates)``.
    In a long suite those stray timers fire mid-run with an empty "last check"
    stamp, and the check would contact api.github.com for real - slow (and
    sandbox-hostile). Tests exercise ``_auto_check_updates`` directly with
    stubbed checkers, so the scheduled call is dropped outright.
    """
    from PyQt6.QtCore import QTimer

    import core.app_controller as controller

    real_single_shot = QTimer.singleShot

    def guarded_single_shot(ms, callback, *args, **kwargs):
        if ms >= 30000 and getattr(callback, "__name__", "") == "_auto_check_updates":
            return None  # scheduled auto check: dropped under pytest
        return real_single_shot(ms, callback, *args, **kwargs)

    monkeypatch.setattr(controller.QTimer, "singleShot", guarded_single_shot)


@pytest.fixture
def user_data(tmp_path, monkeypatch):
    """Redirect every per-user data path to a fresh temp directory."""
    data_dir = tmp_path / "appdata"
    logs_dir = data_dir / "logs"
    monkeypatch.setattr(APP_CONFIG, "USER_DATA_DIR", data_dir)
    monkeypatch.setattr(APP_CONFIG, "USER_LOG_DIR", logs_dir)
    monkeypatch.setattr(APP_CONFIG, "LOG_FILE_PATH", logs_dir / "shamsitray.log")
    monkeypatch.setattr(APP_CONFIG, "SETTINGS_FILE_PATH", data_dir / "settings.json")
    monkeypatch.setattr(APP_CONFIG, "USER_EVENTS_FILE_PATH", data_dir / "user_events.json")
    monkeypatch.setattr(APP_CONFIG, "HOLIDAYS_STORE_PATH", data_dir / "holidays.json")
    return data_dir


@pytest.fixture
def tray(qtbot, user_data):
    """A booted SystemTrayIcon against the temp user-data dir.

    QSystemTrayIcon is not a QWidget, so it cannot go through
    qtbot.addWidget; it is garbage-collected with the qapp instead.
    """
    from utils.json_settings import JsonSettings
    from core.app_controller import SystemTrayIcon

    icon = SystemTrayIcon(settings=JsonSettings(APP_CONFIG.SETTINGS_FILE_PATH))
    yield icon
