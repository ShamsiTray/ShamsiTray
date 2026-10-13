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
from PyQt6.QtCore import QCoreApplication  # noqa: E402 - after the platform env

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from config import APP_CONFIG, Config  # noqa: E402


@pytest.fixture(autouse=True)
def restore_active_palette():
    """Put the active palette back the way the test found it.

    The palette is process-global, and tests legitimately switch it - a tray
    boot resolves "system" through ``_get_windows_theme()`` and leaves whatever
    the host reports active. Unrestored, that decision leaks into every later
    test, which is how parts of this suite came to pass or fail with the
    developer's own Windows personalization. Nothing is forced here: each test
    keeps the theme it selects, and only the leftovers are cleaned up.

    ``current_palette`` is exactly the state ``set_theme`` writes, so restoring
    the reference is precise - and keeps identity comparisons against
    ``DARK_PALETTE`` / ``LIGHT_PALETTE`` honest.
    """
    before = Config.current_palette
    yield
    Config.current_palette = before


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
def fake_startup_registry():
    """An in-memory stand-in for the HKCU autostart Run key.

    Booting a tray runs the real ``_validate_and_apply_startup_setting()`` path,
    which on Windows writes to the per-user Run key. Every booted tray therefore
    performs its autostart work against this fake instead of the developer's
    registry: the opt-out first run, the stale-entry heal and the
    persist-only-on-success rule all stay under test, while HKCU is never
    touched. See tests/fake_registry.py for the inspection hooks.
    """
    from tests.fake_registry import FakeStartupRegistry

    return FakeStartupRegistry()


@pytest.fixture
def tray(qtbot, user_data, fake_startup_registry):
    """A booted SystemTrayIcon against the temp user-data dir.

    QSystemTrayIcon is not a QWidget, so it cannot go through
    qtbot.addWidget; it is garbage-collected with the qapp instead.
    """
    from utils.json_settings import JsonSettings
    from core.app_controller import SystemTrayIcon

    icon = SystemTrayIcon(settings=JsonSettings(APP_CONFIG.SETTINGS_FILE_PATH),
                          startup_registry=fake_startup_registry)
    yield icon
    # The tray installs a native event filter on the application object, which
    # outlives the test: without this every tray test leaves another live filter
    # holding bound callbacks, and the boot timer it schedules can fire inside a
    # LATER test's event loop.
    QCoreApplication.instance().removeNativeEventFilter(icon.event_filter)
