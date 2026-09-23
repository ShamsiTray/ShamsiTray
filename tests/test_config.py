"""Tests for config: paths, settings keys, digit maps, themes and helpers."""
from config import APP_CONFIG, Config


def test_app_identity():
    assert APP_CONFIG.APP_NAME == "ShamsiTray"
    assert APP_CONFIG.COMPANY_NAME == "ShamsiTray"
    assert APP_CONFIG.APP_VERSION  # version string present


def test_asset_paths_live_under_project_root():
    assert APP_CONFIG.ASSETS_DIR == APP_CONFIG.PROJECT_ROOT / "assets"
    assert APP_CONFIG.ICON_PATH == APP_CONFIG.ASSETS_DIR / "images" / "icons" / "icon.ico"
    assert APP_CONFIG.FONT_DIR == APP_CONFIG.ASSETS_DIR / "fonts"
    assert APP_CONFIG.HOLIDAYS_FILE_PATH == APP_CONFIG.ASSETS_DIR / "data" / "holidays.json"
    assert APP_CONFIG.TUTORIAL_GIF_PATH == APP_CONFIG.ASSETS_DIR / "images" / "welcome.gif"


def test_user_data_paths_share_one_root():
    assert APP_CONFIG.USER_LOG_DIR == APP_CONFIG.USER_DATA_DIR / "logs"
    assert APP_CONFIG.LOG_FILE_PATH == APP_CONFIG.USER_LOG_DIR / "shamsitray.log"
    assert APP_CONFIG.SETTINGS_FILE_PATH == APP_CONFIG.USER_DATA_DIR / "settings.json"
    assert APP_CONFIG.USER_EVENTS_FILE_PATH == APP_CONFIG.USER_DATA_DIR / "user_events.json"
    assert APP_CONFIG.HOLIDAYS_STORE_PATH == APP_CONFIG.USER_DATA_DIR / "holidays.json"


def test_settings_keys_are_unique():
    keys = [
        APP_CONFIG.AUTO_START_SETTING_KEY,
        APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY,
        APP_CONFIG.TUTORIAL_SHOWN_SETTING_KEY,
        APP_CONFIG.UPDATE_CHECK_ENABLED_SETTING_KEY,
        APP_CONFIG.LAST_UPDATE_CHECK_SETTING_KEY,
        APP_CONFIG.IGNORED_UPDATE_VERSION_SETTING_KEY,
    ]
    assert len(keys) == len(set(keys))

    # The legacy registry-era events key is no longer a live setting key
    # (DEAD-6): it moved to settings_migration, where the one-time migration
    # reads the old registry blob.
    from utils.settings_migration import LEGACY_USER_EVENTS_SETTING_KEY
    assert LEGACY_USER_EVENTS_SETTING_KEY not in keys


def test_ensure_user_data_dirs_creates_tree(user_data):
    assert not APP_CONFIG.USER_LOG_DIR.exists()
    assert APP_CONFIG.ensure_user_data_dirs() is True
    assert APP_CONFIG.USER_LOG_DIR.is_dir()


def test_ensure_user_data_dirs_survives_unwritable_path(tmp_path, monkeypatch):
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file", encoding="utf-8")
    monkeypatch.setattr(APP_CONFIG, "USER_LOG_DIR", blocker / "logs")
    assert APP_CONFIG.ensure_user_data_dirs() is False


def test_persian_digit_map_roundtrip():
    assert APP_CONFIG._ENGLISH_DIGITS_MAP[ord("۰")] == "0"
    assert APP_CONFIG._ENGLISH_DIGITS_MAP[ord("۹")] == "9"
    assert len(APP_CONFIG.PERSIAN_DIGITS) == 10


def test_theme_switch_and_fallback():
    try:
        APP_CONFIG.set_theme(APP_CONFIG.Theme.LIGHT)
        assert APP_CONFIG.get_current_palette() is APP_CONFIG.LIGHT_PALETTE
        APP_CONFIG.set_theme("totally-unknown-theme")
        # Unknown themes fall back to dark.
        assert APP_CONFIG.get_current_palette() is APP_CONFIG.DARK_PALETTE
    finally:
        APP_CONFIG.set_theme(APP_CONFIG.Theme.DARK)  # restore default
    assert APP_CONFIG.get_current_palette() is APP_CONFIG.DARK_PALETTE


def test_palettes_carry_required_keys():
    required = {"TEXT_COLOR", "BACKGROUND_COLOR", "INPUT_BG_COLOR", "ACCENT_COLOR",
                "HOLIDAY_COLOR", "GREY_COLOR", "HOVER_BG", "MENU_BACKGROUND_COLOR"}
    assert required <= set(APP_CONFIG.DARK_PALETTE.keys())
    assert required <= set(APP_CONFIG.LIGHT_PALETTE.keys())


def test_calendar_constants_match_the_layout():
    # The calendar window is sized from these; drift here breaks placement math.
    assert APP_CONFIG.CALENDAR_WIDTH == 305
    assert APP_CONFIG.CALENDAR_HEIGHT == 395
    assert APP_CONFIG.DAY_LABEL_SIZE == 35
    assert len(APP_CONFIG.PERSIAN_WEEKDAYS_SHORT) == 7
    assert len(APP_CONFIG.PERSIAN_MONTHS) == 12
    assert len(APP_CONFIG.GREGORIAN_MONTHS) == 12


def test_month_names_are_nonempty_and_unique():
    assert len(set(APP_CONFIG.PERSIAN_MONTHS)) == 12
    assert all(APP_CONFIG.PERSIAN_MONTHS)
    assert len(set(APP_CONFIG.GREGORIAN_MONTHS)) == 12


def test_fas_icon_glyphs_are_distinct():
    glyphs = [APP_CONFIG.FAS.FA_SQUARE_REGULAR, APP_CONFIG.FAS.FA_SQUARE_CHECK_SOLID,
              APP_CONFIG.FAS.FA_SUN_SOLID, APP_CONFIG.FAS.FA_MOON_SOLID,
              APP_CONFIG.FAS.FA_XMARK, APP_CONFIG.FAS.FA_MINUS,
              APP_CONFIG.FAS.FA_TRASH, APP_CONFIG.FAS.FA_ARROWS_ROTATE,
              APP_CONFIG.FAS.FA_CIRCLE_EXCLAMATION, APP_CONFIG.FAS.FA_CIRCLE_INFO]
    assert len(set(glyphs)) == len(glyphs)
    assert all(ord(g) > 0xE000 for g in glyphs)  # private-use area


def test_update_endpoints_are_https():
    assert APP_CONFIG.APP_RELEASES_API_URL.startswith("https://")
    assert APP_CONFIG.APP_RELEASES_PAGE_URL.startswith("https://")
    assert APP_CONFIG.HOLIDAYS_UPDATE_URL.startswith("https://")


def test_new_instance_is_independent():
    fresh = Config()
    assert fresh.APP_NAME == APP_CONFIG.APP_NAME
    # Class-level paths resolve the same for every instance.
    assert fresh.PROJECT_ROOT == APP_CONFIG.PROJECT_ROOT


def test_theme_map_covers_both_themes():
    assert set(Config._theme_map.keys()) == {"dark", "light"}


def test_font_awesome_free_covers_every_used_glyph(qtbot):
    """WIN-4: the Free font must contain every glyph the app references.

    The Pro font was removed for license reasons; this keeps the swap
    honest - if a future glyph is added that Free lacks, the suite fails
    before the icon shows up as an empty box on Windows.
    """
    from PyQt6.QtGui import QFont, QFontDatabase, QFontMetrics

    font_file = APP_CONFIG.FONT_DIR / "Font Awesome 7 Free-Solid-900.otf"
    assert font_file.exists(), "the FA Free Solid font must ship with the app"
    font_id = QFontDatabase.addApplicationFont(str(font_file))
    assert font_id != -1, "the bundled FA Free font must load"
    families = QFontDatabase.applicationFontFamilies(font_id)
    assert APP_CONFIG.FONT_AWESOME_FAMILY in families
    font = QFont(APP_CONFIG.FONT_AWESOME_FAMILY)
    metrics = QFontMetrics(font)
    for name in ("FA_SQUARE_REGULAR", "FA_SQUARE_CHECK_SOLID", "FA_SUN_SOLID",
                 "FA_MOON_SOLID", "FA_XMARK", "FA_MINUS", "FA_TRASH",
                 "FA_ARROWS_ROTATE", "FA_DOWNLOAD", "FA_UPLOAD",
                 "FA_CIRCLE_EXCLAMATION", "FA_CIRCLE_INFO", "FA_WIFI",
                 "FA_SAVE"):
        glyph = ord(getattr(APP_CONFIG.FAS, name))
        assert metrics.inFontUcs4(glyph), f"{name} (U+{glyph:04X}) missing from {APP_CONFIG.FONT_AWESOME_FAMILY}"
