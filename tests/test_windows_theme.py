"""
Windows theme backend rule pins
-------------------------------

The backend owns the 'system' theme's detection rule and the tray's taskbar
verdict; these pin both without the module ever touching the host registry
(the winreg surface is faked in the backend's own namespace - winreg may not
even exist off Windows - and the platform the rules read is faked with it, so
the pins run on any host; the off-Windows branch is simulated the way the
controller tests simulate sys.platform, through the fake's own platform
attribute).
"""
from types import SimpleNamespace

import pytest

import utils.windows_theme as wt
from config import APP_CONFIG

from tests.fake_theme import FakeThemeBackend


class _FakeWinReg:
    """Stand-in for the winreg surface the backends read through.

    ``values`` maps the personalization values each rule may ask for to their
    registry integers; a name ABSENT from the dict reads absent (the
    FileNotFoundError winreg raises for a missing value name), which is what
    the taskbar verdict's fallback chain steps on.
    """
    # The backends name the hive explicitly; the fake carries it as a marker
    # so OpenKey's root argument round-trips.
    HKEY_CURRENT_USER = None
    values = {"AppsUseLightTheme": 1, "SystemUsesLightTheme": 1}
    denial = None
    queries = ()

    @staticmethod
    def OpenKey(root, path):
        _FakeWinReg.queries = _FakeWinReg.queries + (path,)
        return object()

    @staticmethod
    def QueryValueEx(key, name):
        if _FakeWinReg.denial is not None:
            raise _FakeWinReg.denial
        if name not in _FakeWinReg.values:
            raise FileNotFoundError(name)
        return _FakeWinReg.values[name], None

    @staticmethod
    def CloseKey(key):
        pass


@pytest.fixture(autouse=True)
def fake_winreg(monkeypatch):
    _FakeWinReg.values = {"AppsUseLightTheme": 1, "SystemUsesLightTheme": 1}
    _FakeWinReg.denial = None
    _FakeWinReg.queries = ()
    # Both surfaces the rules read through are replaced in the backend's own
    # namespace: winreg with raising=False (the module guards its import by
    # platform, so the attribute may not exist at all), and sys with a
    # one-attribute namespace, because the rules' own platform gate would
    # otherwise short-circuit to dark before the fake could answer.
    monkeypatch.setattr(wt, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(wt, "winreg", _FakeWinReg, raising=False)
    yield


# --- the app-mode verdict ------------------------------------------------------------


def test_value_set_to_1_reads_light():
    """A light Windows resolves onto the designated light theme - the stock
    light palette's successor after its retirement from the catalogue."""
    assert wt.WindowsThemeBackend().theme() == APP_CONFIG.SYSTEM_LIGHT_THEME


def test_value_other_than_1_reads_dark():
    _FakeWinReg.values = {"AppsUseLightTheme": 0}
    assert wt.WindowsThemeBackend().theme() == APP_CONFIG.Theme.DARK


def test_failed_registry_read_degrades_to_dark():
    """The tray has always kept running in dark when detection was
    impossible; an unreadable registry must not raise out of the backend."""
    _FakeWinReg.denial = PermissionError("denied")
    assert wt.WindowsThemeBackend().theme() == APP_CONFIG.Theme.DARK


def test_off_windows_reads_dark_without_touching_winreg(monkeypatch):
    """Off Windows there is nothing reliable to read, so the verdict is dark
    without ever consulting the registry surface."""
    monkeypatch.setattr(wt.sys, "platform", "linux")
    assert wt.WindowsThemeBackend().theme() == APP_CONFIG.Theme.DARK


# --- the taskbar-ground verdict --------------------------------------------------------


def test_taskbar_shell_value_decides_on_its_own():
    """The strip follows SystemUsesLightTheme - the shell mode, read even
    when it disagrees with the app mode the theme verdict reads."""
    _FakeWinReg.values = {"AppsUseLightTheme": 0, "SystemUsesLightTheme": 1}
    backend = wt.WindowsThemeBackend()
    assert backend.taskbar_uses_light() is True
    assert backend.theme() == APP_CONFIG.Theme.DARK


def test_taskbar_shell_value_0_reads_dark():
    _FakeWinReg.values = {"AppsUseLightTheme": 1, "SystemUsesLightTheme": 0}
    assert wt.WindowsThemeBackend().taskbar_uses_light() is False


def test_taskbar_missing_shell_value_falls_back_to_the_app_value():
    """Older builds carry only AppsUseLightTheme; a missing shell value steps
    down to it instead of giving up."""
    _FakeWinReg.values = {"AppsUseLightTheme": 1}
    assert wt.WindowsThemeBackend().taskbar_uses_light() is True


def test_taskbar_read_failure_answers_dark_without_stepping_down():
    """A DENIED shell read is an unreadable ground, not a missing value: the
    verdict stops at dark instead of answering the app mode's, so a
    light-app user with an unreadable shell key is not mistaken for a light
    taskbar."""
    _FakeWinReg.values = {"AppsUseLightTheme": 1, "SystemUsesLightTheme": 1}
    _FakeWinReg.denial = PermissionError("denied")
    assert wt.WindowsThemeBackend().taskbar_uses_light() is False
    # The walk never reached the app value: exactly one open, on the shell.
    assert _FakeWinReg.queries == (wt.WindowsThemeBackend.KEY_PATH,)


def test_taskbar_nothing_readable_answers_dark():
    _FakeWinReg.values = {"AppsUseLightTheme": 1}
    _FakeWinReg.denial = PermissionError("denied")
    assert wt.WindowsThemeBackend().taskbar_uses_light() is False


def test_taskbar_off_windows_answers_dark_without_touching_winreg(monkeypatch):
    """The same degrade-dark rule theme() keeps, without a registry touch."""
    monkeypatch.setattr(wt.sys, "platform", "linux")
    assert wt.WindowsThemeBackend().taskbar_uses_light() is False
    assert _FakeWinReg.queries == ()


# --- the fake --------------------------------------------------------------------------


def test_fake_backend_reads_its_settable_verdict():
    """The stand-in the theme tests reach for: a settable verdict that counts
    its reads, and an unset one degrading to the rule's own DARK default."""
    backend = FakeThemeBackend(APP_CONFIG.SYSTEM_LIGHT_THEME)
    assert backend.theme() == APP_CONFIG.SYSTEM_LIGHT_THEME
    assert backend.reads == 1
    assert FakeThemeBackend().theme() == APP_CONFIG.Theme.DARK


def test_fake_backend_reads_its_settable_taskbar_verdict():
    """The tray tests' second hook: an unset ground degrades to the rule's
    own dark answer, a set one is handed through verbatim."""
    backend = FakeThemeBackend()
    assert backend.taskbar_uses_light() is False, "unset ground degrades dark"
    backend.taskbar_light = True
    assert backend.taskbar_uses_light() is True
    assert backend.taskbar_reads == 2
    backend.reset()
    assert backend.taskbar_reads == 0 and backend.taskbar_light is True, (
        "reset forgets the counts, not the verdicts")
