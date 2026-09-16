"""Tests for utils.asset_loader: font loading and asset verification."""
import pytest

from config import APP_CONFIG
from utils.asset_loader import load_fonts, verify_assets


def test_load_fonts_succeeds_on_real_assets(qapp):
    """The bundled font directory has .ttf/.otf files; all must load.

    QFontDatabase needs a QApplication instance (qapp) before any call.
    """
    load_fonts()  # must not raise


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
