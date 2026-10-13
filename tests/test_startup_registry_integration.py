"""
Opt-in integration test for the REAL winreg autostart backend.

This is the only test in the suite that touches the live Windows registry, so it
is excluded from the default run by ``pytest.ini``
(``addopts = -m "not windows_integration"``) and must be asked for explicitly:

    pytest -m windows_integration

It works under a throwaway value name - never the app's own - and removes
whatever it created, so a developer's real ShamsiTray autostart entry is never
touched even when the integration test is run.

Everything else exercises the autostart policy through the in-memory fake
(``tests/fake_registry.py``) via the ``fake_startup_registry`` fixture.
"""
import sys
import uuid

import pytest

from utils.startup_registry import StartupRegistry

pytestmark = [
    pytest.mark.windows_integration,
    pytest.mark.skipif(not sys.platform.startswith("win"),
                       reason="the real autostart backend is Windows-only"),
]

TEST_VALUE_PREFIX = "ShamsiTrayIntegrationTest"
FAKE_EXE = '"C:\\Program Files\\ShamsiTray\\ShamsiTray.exe"'


@pytest.fixture
def registry():
    """A real backend under a per-run throwaway value name, cleaned up after.

    The name is deliberately not the app's own; the uuid suffix additionally
    keeps two runs - or a leftover from a crashed one - from colliding with
    each other or with a pre-existing Run value of the same base name.
    """
    reg = StartupRegistry(value_name=f"{TEST_VALUE_PREFIX}-{uuid.uuid4().hex[:8]}")
    reg.delete()  # start from a known-absent state
    try:
        yield reg
    finally:
        reg.delete()


def test_real_registry_delete_is_idempotent(registry):
    """delete() reports success for an already-absent value (the heal contract)."""
    assert registry.read() is None
    assert registry.delete() is True
    assert registry.read() is None


def test_real_registry_write_read_delete_round_trip(registry):
    assert registry.write(FAKE_EXE) is True
    assert registry.read() == FAKE_EXE
    assert registry.delete() is True
    assert registry.read() is None


def test_real_registry_write_replaces_an_existing_value(registry):
    assert registry.write('"C:\\old\\ShamsiTray.exe"') is True
    assert registry.write(FAKE_EXE) is True
    assert registry.read() == FAKE_EXE
