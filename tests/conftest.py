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

# Must happen before anything imports PySide6 / constructs a QApplication.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402 - after the platform env

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from config import APP_CONFIG, Config  # noqa: E402

# Every ConfirmDialog built under a test, held by the session so no wrapper is
# garbage-collected mid-run - see hold_static_dialogs for why.
_HELD_DIALOGS = []


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
    ``DARK_PALETTE`` and the gallery's registry palettes honest.
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
    from PySide6.QtCore import QTimer

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


@pytest.fixture(autouse=True)
def dispose_tray_controllers(monkeypatch):
    """Dispose every booted SystemTrayIcon between tests.

    A booted controller is otherwise referenced forever: pytest-qt holds every
    widget, and scheduled callbacks hold its bound methods, so each module's
    boots pile up live controllers (with their pending timers) across tests -
    the pile-up that access-violated long runs. Disposal sits in teardown and
    the fixture itself flushes the deferred deletes: every controller dies
    between tests, never mid-dispatch, and no delete stays pending for some
    later pump. Tracking __init__ catches the controller fixtures' boots and
    the inline constructions in test bodies alike.
    """
    from core.app_controller import SystemTrayIcon

    born = []
    real_init = SystemTrayIcon.__init__

    def tracking_init(self, *args, **kwargs):
        real_init(self, *args, **kwargs)
        born.append(self)

    monkeypatch.setattr(SystemTrayIcon, "__init__", tracking_init)
    yield
    app = QCoreApplication.instance()
    for icon in born:
        try:
            app.removeNativeEventFilter(icon.event_filter)
            icon.deleteLater()
            for name in ("calendar_widget", "converter_window", "distance_window",
                         "event_manager_window", "holiday_viewer_window"):
                window = getattr(icon, name, None)
                if window is not None:
                    window.deleteLater()
        except RuntimeError:
            pass  # this controller's C++ side is already gone
    # Land every deferred delete inside THIS teardown: a delete still pending
    # past teardown fires inside some later event pump, where a queued timer
    # of the same dying tree can still dispatch into Python while Qt tears
    # its sender out from under it (the shape that access-violated the suite).
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture(autouse=True)
def hold_static_dialogs(monkeypatch):
    """Hold every ConfirmDialog the static flows build until interpreter exit.

    ask/choose/notify build parentless dialogs inside their own frame, and tests
    reach them by monkeypatching exec instead of execing - so no qtbot.addWidget
    ever sees the dialog and its Python wrapper dies wherever the test's own
    references do. A wrapper dropped mid-run (function return) is a C++ deletion
    the teardown still trips over at interpreter finalization under PySide 6.12:
    an access violation with no Python frame, after the whole suite already
    passed. Destroying the dialogs here instead collides with pytest-qt's own
    teardown hook, which closes every addWidget'd widget and finds deleteLater'd
    shells. Holding the wrapper alive (proven safe in isolation: the C++ side
    then dies inside QApplication's own static teardown) parks it inert until
    the very end, where the application tears it down in one piece.

    addWidget'd dialogs stay out of the hold: pytest-qt closes and deleteLater's
    them at its own teardown, and holding their wrappers turns that close into a
    RuntimeError on a dead shell - the parent chain dies mid-run either way,
    so there is nothing left for the interpreter to trip over.

    Dialogs the production code pinned itself (the static flows and the
    controller's prompts, via pin_dialog_wrappers) stay out of the hold too:
    the app-level list retains them for the whole session, and duplicating
    that retention here would mask a dropped production pin - the static-flow
    test asserts the app list directly instead (test_new_windows.py).
    """
    from pytestqt.qtbot import QtBot

    import ui.widgets.confirm_dialog as confirm_dialog_module
    from ui.widgets.confirm_dialog import ConfirmDialog

    # Identity keys, not references: pytest-qt resolves its weakrefs to close
    # the widgets, so a reference kept here would turn that close into a
    # RuntimeError on a dead shell for any dialog whose parent died mid-run.
    marked_ids = set()
    real_add_widget = QtBot.addWidget

    def add_widget_if_unheld(self, widget, *args, **kwargs):
        if isinstance(widget, ConfirmDialog):
            marked_ids.add(id(widget))
            # Prune immediately, because pytest-qt's close pass runs while this
            # fixture is still only a fixture - intermediates between here and
            # the finalizer must never keep a wrapper it wants to close.
            _HELD_DIALOGS[:] = [dialog for dialog in _HELD_DIALOGS
                                if id(dialog) not in marked_ids]
        return real_add_widget(self, widget, *args, **kwargs)

    real_init = ConfirmDialog.__init__

    def tracking_init(self, *args, **kwargs):
        real_init(self, *args, **kwargs)
        _HELD_DIALOGS.append(self)

    monkeypatch.setattr(QtBot, "addWidget", add_widget_if_unheld)
    monkeypatch.setattr(ConfirmDialog, "__init__", tracking_init)
    yield
    import shiboken6

    # Drop the wrappers pytest-qt manages (their C++ side is already gone
    # by now, deleted mid-run, and holding them would trip its close pass),
    # any C++-deleted shells the rest of the session produced, and everything
    # production pinned itself (the app-level list owns that retention). What
    # survives is exactly the un-pinned set the interpreter cannot tear down
    # safely. Two live objects cannot share an id, and a held dialog keeps its
    # id while it is alive, so an id reissued to some new widget can never
    # match here.
    _HELD_DIALOGS[:] = [dialog for dialog in _HELD_DIALOGS
                        if id(dialog) not in marked_ids
                        and shiboken6.isValid(dialog)
                        and dialog not in confirm_dialog_module._DIALOG_WRAPPERS]


def pytest_sessionfinish(session, exitstatus):
    """Tear Qt down HERE, while every Python frame is still alive.

    pytest-qt keeps the session QApplication in a module global, so under
    PySide 6.12 its destructor only runs during interpreter finalization -
    and destroying the surviving widgets from there dispatches into a
    Python state that is already gone: the suite exits fail-fast after it
    has fully passed. The same teardown at session end deletes every
    remaining top-level widget and drops the plugin's hold on the app, so
    the C++ side dies inside a living interpreter instead. Whatever a late
    reference still pins is the interpreter's problem exactly as it always
    was; the widgets - the crash's fuel - are not.
    """
    import gc

    import pytestqt.plugin as qt_plugin
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return
    for widget in list(app.topLevelWidgets()):
        try:
            widget.deleteLater()
        except RuntimeError:
            pass  # this widget's C++ side is already gone
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qt_plugin._qapp_instance = None
    del app
    gc.collect()
