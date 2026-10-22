"""
Windows theme backend rule pins
-------------------------------

The backend owns the 'system' theme's detection rule; these pin it without
the module ever touching the host registry (the winreg surface is faked in
the backend's own namespace - winreg may not even exist off Windows - and
the platform the rule reads is faked with it, so the pins run on any host;
the off-Windows branch is simulated the way the controller tests simulate
sys.platform, through the fake's own platform attribute).
"""
from types import SimpleNamespace

import pytest

import utils.windows_theme as wt
from config import APP_CONFIG

from tests.fake_theme import FakeThemeBackend


class _FakeWinReg:
    """Stand-in for the winreg surface the backend reads through."""
    # The backend names the hive explicitly; the fake carries it as a
    # marker so OpenKey's root argument round-trips.
    HKEY_CURRENT_USER = None
    value = 1
    denial = None

    @staticmethod
    def OpenKey(root, path):
        return object()

    @staticmethod
    def QueryValueEx(key, name):
        if _FakeWinReg.denial is not None:
            raise _FakeWinReg.denial
        return _FakeWinReg.value, None

    @staticmethod
    def CloseKey(key):
        pass


@pytest.fixture(autouse=True)
def fake_winreg(monkeypatch):
    _FakeWinReg.value = 1
    _FakeWinReg.denial = None
    # Both surfaces the rule reads through are replaced in the backend's own
    # namespace: winreg with raising=False (the module guards its import by
    # platform, so the attribute may not exist at all), and sys with a
    # one-attribute namespace, because theme()'s own platform gate would
    # otherwise short-circuit to dark before the fake could answer.
    monkeypatch.setattr(wt, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(wt, "winreg", _FakeWinReg, raising=False)
    yield


def test_value_set_to_1_reads_light():
    assert wt.WindowsThemeBackend().theme() == APP_CONFIG.Theme.LIGHT


def test_value_other_than_1_reads_dark():
    _FakeWinReg.value = 0
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


def test_fake_backend_reads_its_settable_verdict():
    """The stand-in the theme tests reach for: a settable verdict that counts
    its reads, and an unset one degrading to the rule's own DARK default."""
    backend = FakeThemeBackend(APP_CONFIG.Theme.LIGHT)
    assert backend.theme() == APP_CONFIG.Theme.LIGHT
    assert backend.reads == 1
    assert FakeThemeBackend().theme() == APP_CONFIG.Theme.DARK
