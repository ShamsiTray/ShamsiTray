"""
Windows theme backend rule pins
-------------------------------

The backend owns the 'system' theme's detection rule; these pin it without
the module ever touching the host registry (the winreg surface is faked in
the backend's own namespace, and the off-Windows branch is simulated the way
the controller tests do).
"""
import sys

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
    monkeypatch.setattr(wt, "winreg", _FakeWinReg)
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
    monkeypatch.setattr(sys, "platform", "linux")
    assert wt.WindowsThemeBackend().theme() == APP_CONFIG.Theme.DARK


def test_fake_backend_reads_its_settable_verdict():
    """The stand-in the theme tests reach for: a settable verdict that counts
    its reads, and an unset one degrading to the rule's own DARK default."""
    backend = FakeThemeBackend(APP_CONFIG.Theme.LIGHT)
    assert backend.theme() == APP_CONFIG.Theme.LIGHT
    assert backend.reads == 1
    assert FakeThemeBackend().theme() == APP_CONFIG.Theme.DARK
