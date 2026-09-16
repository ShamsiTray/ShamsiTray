"""Tests for main.py: startup wiring, failure paths and the first-run
tutorial flow — with every external surface stubbed so main() can run to
completion inside pytest (it normally ends with app.exec()).
"""
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QPoint

import main as main_module
from config import APP_CONFIG


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

    critical = []
    monkeypatch.setattr(main_module.QMessageBox, "critical",
                        staticmethod(lambda *a: critical.append(a)))
    monkeypatch.setattr(main_module.QSystemTrayIcon, "isSystemTrayAvailable",
                        staticmethod(lambda: True))

    fake_sys = SimpleNamespace(argv=["shamsitray"], platform="linux",
                               exit=lambda code=0: (_ for _ in ()).throw(SystemExit(code)))
    monkeypatch.setattr(main_module, "sys", fake_sys)
    return SimpleNamespace(apps=FakeApp.instances, trays=FakeTray.instances,
                           tutorials=FakeTutorial.instances, critical=critical,
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
    assert stubbed.critical and "App icon" in stubbed.critical[0][2]
    assert stubbed.trays == []  # never reached the tray boot


def test_main_font_failure_exits_with_error(stubbed, monkeypatch):
    def boom():
        raise RuntimeError("No fonts were loaded from the font directory.")

    monkeypatch.setattr(main_module, "load_fonts", boom)
    with pytest.raises(SystemExit) as exit_info:
        main_module.main()
    assert exit_info.value.code == 1
    assert stubbed.critical and "Font" in stubbed.critical[0][1]


def test_main_without_tray_exits(stubbed):
    stubbed.sys  # keep reference
    import main as m

    # Patch the class method the stubbed module actually consults.
    m.QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: False)
    with pytest.raises(SystemExit) as exit_info:
        main_module.main()
    assert exit_info.value.code == 1
    assert stubbed.trays == []


def test_main_registers_windows_appid_only_on_windows(stubbed, monkeypatch):
    calls = []

    fake_ctypes = SimpleNamespace(windll=SimpleNamespace(shell32=SimpleNamespace(
        SetCurrentProcessExplicitAppUserModelID=lambda appid: calls.append(appid))))
    monkeypatch.setattr(main_module, "ctypes", fake_ctypes)
    with pytest.raises(SystemExit):
        main_module.main()
    assert calls == []  # on Linux the win32 branch is skipped entirely
