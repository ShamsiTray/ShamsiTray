"""Tests for config: paths, settings keys, digit maps, themes and helpers."""
import pytest

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


def test_arrows_rotate_is_the_two_arrow_glyph():
    """Font Awesome 7 names U+F021 `arrows-rotate` (the two-arrow spinner) and
    U+F2F1 `arrow-rotate-right` (one arrow), and the bundled cmap carries both,
    so only the codepoint itself tells the update cards' spinner from a plain
    arrow."""
    assert APP_CONFIG.FAS.FA_ARROWS_ROTATE == '\uf021'


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
                 "FA_SAVE", "FA_CLOCK"):
        glyph = ord(getattr(APP_CONFIG.FAS, name))
        assert metrics.inFontUcs4(glyph), f"{name} (U+{glyph:04X}) missing from {APP_CONFIG.FONT_AWESOME_FAMILY}"


# --- palette contrast -----------------------------------------------------------

def _srgb_luminance(hex_color: str) -> float:
    """WCAG relative luminance of an opaque #rrggbb color."""
    c = hex_color.lstrip("#")
    channels = []
    for i in (0, 2, 4):
        v = int(c[i:i + 2], 16) / 255.0
        channels.append(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(fg: str, bg: str) -> float:
    a, b = _srgb_luminance(fg), _srgb_luminance(bg)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def _parse_rgba(value: str):
    """Split 'rgba(r, g, b, a)' or '#rrggbb' into (hex, alpha 0..1)."""
    if value.startswith("#"):
        return value.lower(), 1.0
    inner = value[value.index("(") + 1:value.rindex(")")].replace(",", " ").split()
    r, g, b, a = (float(x) for x in inner[:4])
    # The palette spells alphas both ways - float fractions (0.2) and 0-255
    # ints (51) - and Qt's stylesheet parser accepts both, so read them the same
    # way: a value <= 1 is a fraction, anything larger is divided by 255.
    # Dividing a fraction by 255 composited a ~0.1% tint, so the "flattened
    # translucent fill" contrast assertions tested the plain backdrop instead.
    return "#%02x%02x%02x" % (int(r), int(g), int(b)), (a if a <= 1 else a / 255.0)


def _flatten(fg_rgba: str, bg_hex: str) -> str:
    """Composite a translucent fill over an opaque backdrop."""
    fg_hex, alpha = _parse_rgba(fg_rgba)
    br, bg_, bb = (int(bg_hex.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    fr, fg, fb = (int(fg_hex.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    def mix(f, b):
        return int(round(f * alpha + b * (1 - alpha)))
    return "#%02x%02x%02x" % (mix(fr, br), mix(fg, bg_), mix(fb, bb))


# AA for normal-size body text. The accent is used behind white label text in
# the accent buttons, the combo boxes' selected row and the dropdown list, so it
# has to clear this as a BACKGROUND, not merely be a visible blue.
WCAG_AA_NORMAL_TEXT = 4.5


def test_light_accent_backs_white_text_at_wcag_aa():
    """The light theme was retuned for this: its old accent could not carry
    white label text at AA. Pinned so a future "brighten the accent" change
    cannot quietly regress it."""
    palette = APP_CONFIG.LIGHT_PALETTE
    ratio = _contrast_ratio("#ffffff", palette["ACCENT_COLOR"])
    assert ratio >= WCAG_AA_NORMAL_TEXT, (
        f"light accent {palette['ACCENT_COLOR']} gives only {ratio:.2f}:1 "
        f"against white text (AA needs {WCAG_AA_NORMAL_TEXT}:1)")


def test_dark_accent_backs_white_text_at_wcag_aa():
    palette = APP_CONFIG.DARK_PALETTE
    ratio = _contrast_ratio("#ffffff", palette["ACCENT_COLOR"])
    assert ratio >= WCAG_AA_NORMAL_TEXT, (
        f"dark accent {palette['ACCENT_COLOR']} gives only {ratio:.2f}:1 "
        f"against white text")


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_body_text_meets_wcag_aa(theme):
    palette = APP_CONFIG.DARK_PALETTE if theme == "dark" else APP_CONFIG.LIGHT_PALETTE
    for surface in ("BACKGROUND_COLOR", "CALENDAR_BACKGROUND_COLOR",
                    "MENU_BACKGROUND_COLOR", "INPUT_BG_COLOR"):
        ratio = _contrast_ratio(palette["TEXT_COLOR"], palette[surface])
        assert ratio >= WCAG_AA_NORMAL_TEXT, (
            f"{theme} text on {surface} is only {ratio:.2f}:1")


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_selected_day_number_survives_its_own_tint(theme):
    """A selected day draws TEXT_COLOR over CALENDAR_SELECTED_BG_COLOR, which is
    itself translucent over the calendar surface. The tint has to be flattened
    onto that surface first - comparing the raw tint against the text would
    measure a color that is never actually painted."""
    palette = APP_CONFIG.DARK_PALETTE if theme == "dark" else APP_CONFIG.LIGHT_PALETTE
    surface = palette["CALENDAR_BACKGROUND_COLOR"]
    for key in ("CALENDAR_SELECTED_BG_COLOR", "CALENDAR_SELECTED_HOVER_BG_COLOR"):
        flattened = _flatten(palette[key], surface)
        ratio = _contrast_ratio(palette["TEXT_COLOR"], flattened)
        assert ratio >= WCAG_AA_NORMAL_TEXT, (
            f"{theme} {key} flattens to {flattened}: only {ratio:.2f}:1 "
            f"for the day number")


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_menu_row_hover_is_actually_visible(theme):
    """MENU_HOVER_COLOR is painted at its own alpha over the menu surface. A
    hover the eye cannot resolve is the same as no hover at all, so assert the
    composited change is perceptible rather than merely non-zero."""
    palette = APP_CONFIG.DARK_PALETTE if theme == "dark" else APP_CONFIG.LIGHT_PALETTE
    base = palette["MENU_BACKGROUND_COLOR"]
    _r, _g, _b, alpha = palette["MENU_HOVER_COLOR"]
    flattened = _flatten(f"rgba({_r}, {_g}, {_b}, {alpha})", base)
    before, after = _srgb_luminance(base), _srgb_luminance(flattened)
    delta = abs(after - before)
    assert alpha >= 50, f"{theme} menu hover alpha {alpha} is too faint to see"
    assert delta > 0.01, (
        f"{theme} menu hover composites to {flattened}, a luminance delta of "
        f"only {delta:.4f} from {base}")
