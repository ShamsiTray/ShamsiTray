"""Tests for utils.asset_loader: font loading and asset verification."""
import os
import subprocess
import sys

import pytest

from config import APP_CONFIG
from utils import asset_loader as asset_loader_module
from utils.asset_loader import load_fonts, verify_assets

_SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")


def test_load_fonts_succeeds_on_real_assets(qapp):
    """The bundled font directory has .ttf/.otf files; all must load.

    QFontDatabase needs a QApplication instance (qapp) before any call.
    """
    load_fonts()  # must not raise


def test_load_fonts_requires_a_live_application(monkeypatch):
    """Without a QApplication the guard must raise instead of reaching
    QFontDatabase, whose pre-app call access-violates the process."""

    class _NoApplication:
        @staticmethod
        def instance():
            return None

    monkeypatch.setattr(asset_loader_module, "QApplication", _NoApplication)
    with pytest.raises(RuntimeError, match="requires a live QApplication"):
        load_fonts()


_QCOREAPP_CHILD_SOURCE = """\
import sys
sys.path.insert(0, {src!r})
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtGui import QFontDatabase

# A stub in place of the real call: without the guard, load_fonts reaches
# QFontDatabase in a GUI-less process, which access-violates instead of
# raising - the stub turns that into a countable, assertable failure.
_calls = []


def _record(_path):
    _calls.append(_path)
    return -1


QFontDatabase.addApplicationFont = staticmethod(_record)

app = QCoreApplication(sys.argv)  # noqa: F841

from utils.asset_loader import load_fonts

try:
    load_fonts()
except RuntimeError as error:
    if "requires a live QApplication" in str(error):
        print("GUARD_RAISED")
        print("FONT_CALLS:", len(_calls))
    else:
        print("WRONG_RUNTIME_ERROR:", error)
else:
    print("NO_GUARD_FONT_CALLS:", len(_calls))
"""


def test_load_fonts_rejects_a_bare_qcoreapplication(tmp_path):
    """The guard's real trap: ``QApplication.instance`` does not answer None
    for a core-only process - it returns the QCoreApplication object - so a
    null check would let the font walk reach QFontDatabase in a GUI-less
    process, which access-violates. The isinstance guard must raise from the
    child, with no font call attempted. (A subprocess, so a guard regression
    crashes only the child instead of this whole test run.)"""
    child = tmp_path / "child_load_fonts.py"
    child.write_text(_QCOREAPP_CHILD_SOURCE.format(src=_SRC_DIR))
    result = subprocess.run([sys.executable, str(child)], capture_output=True,
                            text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert "GUARD_RAISED" in result.stdout
    assert "FONT_CALLS: 0" in result.stdout


def test_load_fonts_missing_dir_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(APP_CONFIG, "FONT_DIR", tmp_path / "nope")
    with pytest.raises(FileNotFoundError, match="Font directory not found"):
        load_fonts()


def test_load_fonts_empty_dir_raises(tmp_path, monkeypatch):
    font_dir = tmp_path / "fonts"
    font_dir.mkdir()
    monkeypatch.setattr(APP_CONFIG, "FONT_DIR", font_dir)
    with pytest.raises(RuntimeError, match="No fonts were loaded"):
        load_fonts()


def test_load_fonts_logs_failures_but_continues(qapp, tmp_path, monkeypatch):
    """A corrupt font file is skipped with a warning; valid ones still load."""
    import logging

    font_dir = tmp_path / "fonts"
    font_dir.mkdir()
    real_font = next(APP_CONFIG.FONT_DIR.glob("*.ttf"))
    (font_dir / "good.ttf").write_bytes(real_font.read_bytes())
    (font_dir / "broken.ttf").write_bytes(b"not a font at all")
    monkeypatch.setattr(APP_CONFIG, "FONT_DIR", font_dir)

    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    module_logger = logging.getLogger("utils.asset_loader")
    capture = Capture()
    module_logger.addHandler(capture)
    try:
        load_fonts()
    finally:
        module_logger.removeHandler(capture)

    assert any("Failed to load font: broken.ttf" in r for r in records)


def test_verify_assets_passes_on_real_project():
    verify_assets()  # must not raise


def test_verify_assets_reports_every_missing_asset(tmp_path, monkeypatch):
    empty = tmp_path / "missing"
    monkeypatch.setattr(APP_CONFIG, "ICON_PATH", empty / "icon.ico")
    monkeypatch.setattr(APP_CONFIG, "HOLIDAYS_FILE_PATH", empty / "holidays.json")
    monkeypatch.setattr(APP_CONFIG, "TUTORIAL_GIF_PATH", empty / "welcome.gif")
    monkeypatch.setattr(APP_CONFIG, "FONT_DIR", empty / "fonts")

    with pytest.raises(FileNotFoundError) as excinfo:
        verify_assets()
    message = str(excinfo.value)
    for expected in ("App icon", "Holidays data file", "Tutorial GIF",
                     "Font directory", "Any .ttf or .otf font file"):
        assert expected in message


def test_verify_assets_only_complains_about_missing_items(tmp_path, monkeypatch):
    """Present assets stay silent; only the missing one is listed."""
    monkeypatch.setattr(APP_CONFIG, "ICON_PATH", APP_CONFIG.ASSETS_DIR / "images" / "icons" / "icon.ico")
    monkeypatch.setattr(APP_CONFIG, "HOLIDAYS_FILE_PATH", tmp_path / "gone.json")

    with pytest.raises(FileNotFoundError) as excinfo:
        verify_assets()
    assert "Holidays data file" in str(excinfo.value)
    assert "App icon" not in str(excinfo.value)
