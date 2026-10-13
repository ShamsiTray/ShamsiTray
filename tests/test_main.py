"""Tests for main.py: startup wiring, failure paths and the first-run
tutorial flow — with every external surface stubbed so main() can run to
completion inside pytest (it normally ends with app.exec()).
"""
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QPoint

import main as main_module
from config import APP_CONFIG

# The tests below replace main_module.QLockFile wholesale; capturing the real
# error enum here lets their stubs hand main() genuine values.
REAL_LOCK_ERRORS = main_module.QLockFile.LockError


class FakeApp:
    """Stand-in for QApplication capturing the wiring main() performs."""
    instances = []

    def __init__(self, argv):
        self.argv = argv
        self.quit_on_last_window_closed = None
        self.font = None
        FakeApp.instances.append(self)

    @staticmethod
    def setHighDpiScaleFactorRoundingPolicy(policy):
        FakeApp.rounding_policy = policy

    @staticmethod
    def primaryScreen():
        return SimpleNamespace(
            availableGeometry=lambda: SimpleNamespace(center=lambda: QPoint(400, 300)))

    def setQuitOnLastWindowClosed(self, value):
        self.quit_on_last_window_closed = value

    def setFont(self, font):
        self.font = font

    def setStyleSheet(self, style):
        self.style_sheet = style

    def palette(self):
        return "PALETTE"

    def exec(self):
        return 0


class FakeTray:
    instances = []

    def __init__(self, settings=None):
        self.settings = settings
        self.shown = False
        self.tutorial_window = None
        FakeTray.instances.append(self)

    def show(self):
        self.shown = True


class FakeTutorial:
    instances = []

    def __init__(self):
        self.styled = False
        self.shown = False
        self.palette = None
        self.pos = None
        FakeTutorial.instances.append(self)

    def rect(self):
        return SimpleNamespace(center=lambda: QPoint(0, 0))

    def setPalette(self, palette):
        self.palette = palette

    def update_styles(self):
        self.styled = True

    def show(self):
        self.shown = True

    def move(self, pos):
        self.pos = pos


@pytest.fixture
def stubbed(monkeypatch, tmp_path):
    """Stub every external surface of main() and redirect user data."""
    monkeypatch.setattr(APP_CONFIG, "USER_DATA_DIR", tmp_path / "appdata")
    monkeypatch.setattr(APP_CONFIG, "USER_LOG_DIR", tmp_path / "appdata" / "logs")
    monkeypatch.setattr(APP_CONFIG, "LOG_FILE_PATH", tmp_path / "appdata" / "logs" / "app.log")
    monkeypatch.setattr(APP_CONFIG, "SETTINGS_FILE_PATH", tmp_path / "appdata" / "settings.json")
    monkeypatch.setattr(APP_CONFIG, "USER_EVENTS_FILE_PATH", tmp_path / "appdata" / "user_events.json")
    monkeypatch.setattr(APP_CONFIG, "HOLIDAYS_STORE_PATH", tmp_path / "appdata" / "holidays.json")

    FakeApp.instances = []
    FakeTray.instances = []
    FakeTutorial.instances = []
    monkeypatch.setattr(main_module, "QApplication", FakeApp)
    monkeypatch.setattr(main_module, "SystemTrayIcon", FakeTray)
    monkeypatch.setattr(main_module, "TutorialWindow", FakeTutorial)
    monkeypatch.setattr(main_module, "install_qt_message_handler", lambda: None)
    monkeypatch.setattr(main_module, "verify_assets", lambda: None)
    monkeypatch.setattr(main_module, "load_fonts", lambda: None)
    monkeypatch.setattr(main_module, "migrate_from_registry", lambda settings: None)

    notifies = []
    monkeypatch.setattr(main_module.ConfirmDialog, "notify",
                        staticmethod(lambda *a, **k: notifies.append((a, k))))
    monkeypatch.setattr(main_module.QSystemTrayIcon, "isSystemTrayAvailable",
                        staticmethod(lambda: True))

    fake_sys = SimpleNamespace(argv=["shamsitray"], platform="linux",
                               exit=lambda code=0: (_ for _ in ()).throw(SystemExit(code)))
    monkeypatch.setattr(main_module, "sys", fake_sys)
    return SimpleNamespace(apps=FakeApp.instances, trays=FakeTray.instances,
                           tutorials=FakeTutorial.instances, notifies=notifies,
                           sys=fake_sys)


def test_main_happy_path_wires_everything(stubbed):
    from utils.json_settings import JsonSettings

    with pytest.raises(SystemExit) as exit_info:
        main_module.main()
    assert exit_info.value.code == 0
    assert len(stubbed.apps) == 1
    app = stubbed.apps[0]
    assert app.quit_on_last_window_closed is False  # tray app: closing windows is fine
    assert app.font is not None                     # concrete default font (pointSize >= 0)
    assert app.font.pointSize() == 10
    # Tray booted with the settings object and shown.
    assert len(stubbed.trays) == 1
    assert isinstance(stubbed.trays[0].settings, JsonSettings)
    assert stubbed.trays[0].shown
    # Tutorial already shown before? Not: fresh settings -> no tutorial here is
    # wrong; first run SHOWS it. Checked in the dedicated test below.


def test_main_first_run_shows_tutorial(stubbed):
    with pytest.raises(SystemExit):
        main_module.main()
    assert len(stubbed.tutorials) == 1
    tutorial = stubbed.tutorials[0]
    assert tutorial.styled and tutorial.shown
    assert tutorial.palette == "PALETTE"
    tray = stubbed.trays[0]
    assert tray.tutorial_window is tutorial  # kept alive by the controller
    # Marked as shown for the next launch.
    from utils.json_settings import JsonSettings

    settings = JsonSettings(APP_CONFIG.SETTINGS_FILE_PATH)
    assert settings.value(APP_CONFIG.TUTORIAL_SHOWN_SETTING_KEY, False, type=bool) is True


def test_main_second_run_skips_tutorial(stubbed):
    # Pre-mark the tutorial as shown.
    from utils.json_settings import JsonSettings

    settings = JsonSettings(APP_CONFIG.SETTINGS_FILE_PATH)
    settings.setValue(APP_CONFIG.TUTORIAL_SHOWN_SETTING_KEY, True)

    with pytest.raises(SystemExit):
        main_module.main()
    assert stubbed.tutorials == []
    assert stubbed.trays[0].tutorial_window is None


def test_main_missing_assets_exits_with_error(stubbed, monkeypatch):
    def boom():
        raise FileNotFoundError("One or more required assets are missing: App icon")

    monkeypatch.setattr(main_module, "verify_assets", boom)
    with pytest.raises(SystemExit) as exit_info:
        main_module.main()
    assert exit_info.value.code == 1
    # Fatal surfaces use the themed dialog (no stock QMessageBox left).
    assert stubbed.notifies and "App icon" in stubbed.notifies[0][0][2]
    assert stubbed.notifies[0][1]["danger"] is True
    assert stubbed.trays == []  # never reached the tray boot


def test_main_font_failure_exits_with_error(stubbed, monkeypatch):
    def boom():
        raise RuntimeError("No fonts were loaded from the font directory.")

    monkeypatch.setattr(main_module, "load_fonts", boom)
    with pytest.raises(SystemExit) as exit_info:
        main_module.main()
    assert exit_info.value.code == 1
    assert stubbed.notifies and "fonts were loaded" in stubbed.notifies[0][0][2]


def test_main_without_tray_exits(stubbed):
    stubbed.sys  # keep reference
    import main as m

    # Patch the class method the stubbed module actually consults.
    m.QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: False)
    with pytest.raises(SystemExit) as exit_info:
        main_module.main()
    assert exit_info.value.code == 1
    assert stubbed.trays == []
    assert stubbed.notifies  # themed error dialog instead of QMessageBox


def test_main_single_instance_shows_themed_notice(stubbed, monkeypatch):
    """WIN-1 revisited: the 'another instance is running' popup is a themed
    ConfirmDialog (the last native QMessageBox in the app), then exit 0."""

    class LockedLock:
        stale_ms = None
        LockError = REAL_LOCK_ERRORS

        def __init__(self, _path):
            pass

        def setStaleLockTime(self, ms):
            LockedLock.stale_ms = ms

        def tryLock(self, timeout):
            return False  # another instance holds the lock

        def error(self):
            return REAL_LOCK_ERRORS.LockFailedError

    monkeypatch.setattr(main_module, "QLockFile", LockedLock)
    with pytest.raises(SystemExit) as exit_info:
        main_module.main()
    assert exit_info.value.code == 0
    # The lock guards the app for its whole runtime, so its age must never
    # expire it; 0 is Qt's "no timestamp expiry" (the pid check still heals a
    # lock left by a crashed process).
    assert LockedLock.stale_ms == 0
    assert stubbed.trays == []  # never booted a second tray
    assert stubbed.notifies and "در حال اجرا" in stubbed.notifies[0][0][2]
    # Informational notice: not styled as a failure (danger=False default).
    assert stubbed.notifies[0][1].get("danger") is None


def test_main_reports_a_settings_reset(tmp_path, stubbed):
    """An unreadable settings store is not a first run: the app says so at
    startup instead of silently reverting every preference."""
    settings_path = APP_CONFIG.SETTINGS_FILE_PATH
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text("{not json", encoding="utf-8")

    with pytest.raises(SystemExit) as exit_info:
        main_module.main()

    assert exit_info.value.code == 0
    assert stubbed.trays  # booted normally, with defaults
    assert any("بازنشانی تنظیمات" in args[1] for args, _kwargs in stubbed.notifies)
    _args, kwargs = next(n for n in stubbed.notifies if "بازنشانی تنظیمات" in n[0][1])
    assert "settings.json.corrupt" in kwargs["detail"]


def test_main_warns_when_the_unreadable_store_cannot_be_preserved(tmp_path, stubbed, monkeypatch):
    """Neither path could keep the bytes, so the store refuses to write over the
    only copy left: the notice has to say saving is off for this session and
    that changes made in it are lost at exit - not that a backup was kept."""
    settings_path = APP_CONFIG.SETTINGS_FILE_PATH
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text("{not json", encoding="utf-8")

    def refused(*_args, **_kwargs):
        raise OSError("locked")

    monkeypatch.setattr("utils.json_settings.os.replace", refused)
    monkeypatch.setattr("utils.json_settings._copy_bytes", refused)

    with pytest.raises(SystemExit) as exit_info:
        main_module.main()

    assert exit_info.value.code == 0
    _args, kwargs = next(n for n in stubbed.notifies if "خطا در ذخیره تنظیمات" in n[0][1])
    assert "نسخه پشتیبان" in _args[2]              # no backup could be made
    assert "غیرفعال شده است" in kwargs["detail"]    # saving is off this session
    assert "از بین خواهند رفت" in kwargs["detail"]   # and the changes die with it
    assert kwargs["danger"] is True                 # a failure, not a plain notice
    # The kept-aside wording must not appear: nothing was preserved.
    assert not any("بازنشانی تنظیمات" in args[1] for args, _kwargs in stubbed.notifies)
    assert settings_path.read_text(encoding="utf-8") == "{not json"  # untouched


def test_main_stays_quiet_on_a_first_run(tmp_path, stubbed):
    """No store at all is a first run, not a loss: no reset notice."""
    with pytest.raises(SystemExit) as exit_info:
        main_module.main()

    assert exit_info.value.code == 0
    assert not any("بازنشانی تنظیمات" in args[1] for args, _kwargs in stubbed.notifies)


def test_main_lock_error_other_than_contention_exits_non_zero(stubbed, monkeypatch):
    """An unwritable data dir or a full disk fails the lock with no other
    instance running; reporting that as "already running" and exiting 0 would
    make the launch look fine while nothing actually started."""

    class BrokenLock:
        LockError = REAL_LOCK_ERRORS

        def __init__(self, _path):
            pass

        def setStaleLockTime(self, ms):
            pass

        def tryLock(self, timeout):
            return False

        def error(self):
            return REAL_LOCK_ERRORS.UnknownError

    monkeypatch.setattr(main_module, "QLockFile", BrokenLock)
    with pytest.raises(SystemExit) as exit_info:
        main_module.main()
    assert exit_info.value.code == 1
    assert stubbed.trays == []  # never booted a tray on a broken lock
    assert stubbed.notifies and "قفل" in stubbed.notifies[0][0][2]
    # Styled as a failure, unlike the already-running informational notice.
    assert stubbed.notifies[0][1].get("danger") is True


def test_main_registers_windows_appid_only_on_windows(stubbed, monkeypatch):
    calls = []

    fake_ctypes = SimpleNamespace(windll=SimpleNamespace(shell32=SimpleNamespace(
        SetCurrentProcessExplicitAppUserModelID=lambda appid: calls.append(appid))))
    monkeypatch.setattr(main_module, "ctypes", fake_ctypes)
    with pytest.raises(SystemExit):
        main_module.main()
    assert calls == []  # on Linux the win32 branch is skipped entirely


def test_main_appusermodelid_is_stable_across_releases(stubbed, monkeypatch):
    """WIN-3 revisited: the AppUserModelID must NOT carry the version.

    Microsoft's AppUserModelID docs: the version segment is only for apps
    whose versions must coexist as distinct taskbar entities and should be
    omitted otherwise, so an upgrade keeps the same identity (pinning, jump
    lists). The version-qualified ID reset taskbar identity every release."""
    calls = []

    fake_ctypes = SimpleNamespace(windll=SimpleNamespace(shell32=SimpleNamespace(
        SetCurrentProcessExplicitAppUserModelID=lambda appid: calls.append(appid))))
    monkeypatch.setattr(main_module, "ctypes", fake_ctypes)
    stubbed.sys.platform = "win32"
    with pytest.raises(SystemExit):
        main_module.main()
    assert calls == [f"{APP_CONFIG.COMPANY_NAME}.{APP_CONFIG.APP_NAME}"]
    assert APP_CONFIG.APP_VERSION not in calls[0]  # stable, version-free
