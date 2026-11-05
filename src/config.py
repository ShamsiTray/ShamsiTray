"""
Application Configuration
-------------------------

This module centralizes all static configuration for the ShamsiTray application,
including application info, paths, settings keys, theme registry, and UI constants.

It's designed to be imported by any module that needs access to these settings.
"""
from pathlib import Path
import os
import sys

from themes import THEME_NAMES, THEMES

# Display-name fixups for the single words that title-casing gets wrong.
_THEME_NAME_OVERRIDES = {
    "oled": "OLED",
    "github": "GitHub",
}


def _theme_display_name(slug: str) -> str:
    """"dracula" -> "Dracula", "nord_light" -> "Nord Light": the exported
    whole-name map first (THEME_NAMES in themes.py carries the brand
    spellings word-splitting cannot produce), then per-word casing fixups."""
    if slug in THEME_NAMES:
        return THEME_NAMES[slug]
    words = [_THEME_NAME_OVERRIDES.get(w, w.capitalize())
             for w in slug.split("_")]
    return " ".join(words)


class Config:
    """Central configuration for the ShamsiTray app."""

    # --- App Info ---
    APP_NAME = "ShamsiTray"
    COMPANY_NAME = "ShamsiTray"
    # Must match build/SetupScript.iss and build/details.txt; run
    # `python build/check_versions.py` before tagging a release.
    APP_VERSION = "1.4.0"

    # --- Paths (dynamically calculated) ---
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        PROJECT_ROOT = Path(sys._MEIPASS)
    else:
        PROJECT_ROOT = Path(__file__).resolve().parent.parent
    ASSETS_DIR = PROJECT_ROOT / 'assets'
    ICON_PATH = ASSETS_DIR / 'images' / 'icons' / 'icon.ico'
    FONT_DIR = ASSETS_DIR / 'fonts'
    TUTORIAL_GIF_PATH = ASSETS_DIR / 'images' / 'welcome.gif'
    HOLIDAYS_FILE_PATH = ASSETS_DIR / 'data' / 'holidays.json'

    # --- User Data Paths (%LOCALAPPDATA%\ShamsiTray) ---
    USER_DATA_DIR = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local'))) / APP_NAME
    USER_LOG_DIR = USER_DATA_DIR / 'logs'
    LOG_FILE_PATH = USER_LOG_DIR / 'shamsitray.log'
    SETTINGS_FILE_PATH = USER_DATA_DIR / 'settings.json'
    USER_EVENTS_FILE_PATH = USER_DATA_DIR / 'user_events.json'
    HOLIDAYS_STORE_PATH = USER_DATA_DIR / 'holidays.json'

    def ensure_user_data_dirs(self) -> bool:
        """Create the user data directories if missing. Returns True when present."""
        try:
            self.USER_LOG_DIR.mkdir(parents=True, exist_ok=True)
            return True
        except OSError:
            return False

    # --- Settings Keys (for QSettings / JsonSettings) ---
    AUTO_START_SETTING_KEY = "General/OpenAtLogin"
    CURRENT_THEME_CHOICE_SETTING_KEY = "Appearance/ThemeChoice"
    # The gallery's favorite themes: a JSON list of theme keys, written the
    # moment a star is toggled (a favorite is a bookmark, not part of the
    # apply/cancel session).
    FAVORITE_THEMES_SETTING_KEY = "Appearance/FavoriteThemes"
    TUTORIAL_SHOWN_SETTING_KEY = "Tutorial/HasShown"
    # The legacy "UserData/Events" registry key is only read during the one-time
    # migration; it lives in utils.settings_migration now.
    # Whether the calendar popup is kept above other windows. Read with a True
    # default: a missing key means the preference was never set, and the popup
    # stays pinned until the user says otherwise.
    ALWAYS_ON_TOP_SETTING_KEY = "Calendar/AlwaysOnTop"
    UPDATE_CHECK_ENABLED_SETTING_KEY = "Updates/CheckEnabled"
    LAST_UPDATE_CHECK_SETTING_KEY = "Updates/LastCheckMs"
    IGNORED_UPDATE_VERSION_SETTING_KEY = "Updates/IgnoredVersion"

    # --- Update Check Endpoints ---
    APP_RELEASES_API_URL = "https://api.github.com/repos/ShamsiTray/ShamsiTray/releases/latest"
    APP_RELEASES_PAGE_URL = "https://github.com/ShamsiTray/ShamsiTray/releases/latest"
    HOLIDAYS_UPDATE_URL = "https://raw.githubusercontent.com/ShamsiTray/ShamsiTray/main/assets/data/holidays.json"

    # --- Font Families ---
    FONT_FAMILY = "Vazirmatn"
    GREGORIAN_FONT_FAMILY = "Inter"
    # Font Awesome Free (SIL OFL 1.1) — the Pro font must never ship in this
    # MIT-licensed repo. Qt reports the bundled OTF's typographic family.
    FONT_AWESOME_FAMILY = "Font Awesome 7 Free"

    # --- Theme registry ---------------------------------------------------------
    # Every palette lives in ``themes.py`` (the stock dark theme included);
    # this class only reads the registry and names the resolution rules.
    class Theme:
        SYSTEM = "system"
        DARK = "dark"

    # The light theme the 'system' (follow Windows) mode resolves to when
    # Windows is light. The original stock light palette was retired from the
    # selectable set - the packs carry better-designed light themes - so the
    # system mode needs a designated light gear, and a legacy "light" saved
    # preference maps onto the same theme (see SystemTrayIcon._theme_choice).
    SYSTEM_LIGHT_THEME = "catppuccin_latte"

    # The appearance preference stored under Appearance/ThemeChoice: "system"
    # follows Windows light/dark live, anything else pins that theme key. The
    # key's ABSENCE reads as "system" too - the behaviour a fresh install has
    # always had. (Re-declared below once the pack themes are known; this early
    # form covers intra-class readers.)
    THEME_CHOICES = (Theme.SYSTEM, Theme.DARK)

    # The stock dark theme ("Default" in the gallery), kept addressable by
    # name for every reader that predates the registry.
    DARK_PALETTE = THEMES[Theme.DARK]

    _theme_map = dict(THEMES)
    current_palette = DARK_PALETTE  # Default to dark

    # The plain day's glyph colors, named by the ground they must read on:
    # DARK_COLOR is the white for a dark taskbar strip, LIGHT_COLOR the black
    # for a light one. Which ground holds is the taskbar verdict
    # (WindowsThemeBackend.taskbar_uses_light through app_controller), not the
    # app palette's.
    TRAY_ICON_DARK_COLOR = "#FFFFFF"
    TRAY_ICON_LIGHT_COLOR = "#000000"

    # --- Theme gallery registry -------------------------------------------
    # Every gallery theme from ``themes.py`` joins the stock dark theme in the
    # selectable set. Every slug is persisted under Appearance/ThemeChoice
    # like "dark" always was, so an old settings.json keeps working and a
    # gallery pick survives restarts.
    EXTRA_THEMES = dict(THEMES)
    EXTRA_THEMES.pop(Theme.DARK)

    # Every valid value of the Appearance/ThemeChoice preference. The gallery
    # writes into this namespace; _theme_choice validates against it on load.
    THEME_CHOICES = (Theme.SYSTEM, Theme.DARK) + tuple(EXTRA_THEMES)

    @staticmethod
    def _relative_luminance(hex_color: str) -> float:
        """WCAG relative luminance of an opaque #rrggbb color (pure Python, so
        this module stays Qt-free)."""
        c = hex_color.lstrip("#")

        def channel(value: float) -> float:
            value /= 255.0
            return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        return (0.2126 * channel(int(c[0:2], 16))
                + 0.7152 * channel(int(c[2:4], 16))
                + 0.0722 * channel(int(c[4:6], 16)))

    @classmethod
    def palette_is_dark(cls, palette: dict | None = None) -> bool:
        """True when the palette's background is a dark surface.

        Reads the given palette or the active one. The gallery's dark/light
        grouping keys off this - the catalog order and the picker's filter
        both run on it. The tray digit's polarity does NOT: the ground it
        prints on is the taskbar strip, judged by
        WindowsThemeBackend.taskbar_uses_light (see TRAY_ICON_*_COLOR).
        """
        if palette is None:
            palette = cls.current_palette
        return cls._relative_luminance(palette["BACKGROUND_COLOR"]) < 0.5

    @classmethod
    def theme_catalog(cls) -> list:
        """The selectable themes in gallery order: (key, display name, palette).

        The stock dark theme leads - named "Default", the one the app ships
        wearing - then the gallery themes grouped dark-then-light in the
        themes module's file order, so the recognizable themes the picker
        opens on and the app's own custom sets at the tail are placed in
        source, not by name."""
        entries = [(cls.Theme.DARK, "Default", cls.DARK_PALETTE)]
        darks, lights = [], []
        for slug, palette in cls.EXTRA_THEMES.items():
            (darks if cls.palette_is_dark(palette) else lights).append((slug, palette))
        for group in (darks, lights):
            entries.extend((slug, _theme_display_name(slug), palette)
                           for slug, palette in group)
        return entries

    @classmethod
    def theme_display_name(cls, theme_key: str) -> str:
        """Human-facing name for a theme key; unknown keys name themselves."""
        if theme_key == cls.Theme.DARK:
            return "Default"
        return _theme_display_name(theme_key)

    @classmethod
    def set_theme(cls, theme_name: str):
        """Set app theme and update the current_palette."""
        from utils.logger import setup_logging
        logger = setup_logging(__name__)
        cls.current_palette = cls._theme_map.get(theme_name, cls.DARK_PALETTE)
        if theme_name not in cls._theme_map:
            logger.warning(f"Unknown theme '{theme_name}'. Defaulting to Dark.")
        logger.info(f"Theme set to {theme_name}.")

    @classmethod
    def get_current_palette(cls):
        """Get the current theme palette."""
        return cls.current_palette

    # --- UI Constants ---
    FONT_SIZE_LABEL = 15
    FONT_SIZE_HEADER = 28
    DAY_LABEL_SIZE = 35
    CALENDAR_WIDTH = 305
    CALENDAR_HEIGHT = 395
    CALENDAR_BORDER_RADIUS_PX = 25
    DRAGGABLE_AREA_HEIGHT = 40

    # --- Supported calendar range ---
    # Single source for every surface: go-to-date, the event editor and the
    # month navigation arrows all clamp to this window.
    SUPPORTED_MIN_YEAR = 1200
    SUPPORTED_MAX_YEAR = 1600

    # --- Date & Time Data ---
    PERSIAN_DIGITS = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹']
    _ENGLISH_DIGITS_MAP = {ord(p): str(e) for e, p in enumerate(PERSIAN_DIGITS)}

    PERSIAN_MONTHS = [
        "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
        "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"
    ]
    GREGORIAN_MONTHS = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]
    PERSIAN_WEEKDAYS_SHORT = ["ش", "ی", "د", "س", "چ", "پ", "ج"]
    PERSIAN_WEEKDAY_NAMES = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه"]
    # Monday-first to match datetime.date.weekday(); the Persian list above is
    # Saturday-first to match jdatetime. Reading a date's weekday without
    # knowing which convention a table uses is exactly the bug this avoids.
    GREGORIAN_WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday",
                               "Friday", "Saturday", "Sunday"]

    # --- FontAwesome Icon Characters ---
    # Every glyph below is covered by the bundled FA7 Free Solid cmap; the
    # coverage is asserted by tests/test_config.py.
    class FAS:
        FA_SQUARE_REGULAR = '\uf096'
        FA_SQUARE_CHECK_SOLID = '\uf14a'
        FA_XMARK = '\uf00d'
        FA_MINUS = '\uf068'
        FA_TRASH = '\uf1f8'
        FA_PEN = '\uf304'
        FA_ARROWS_ROTATE = '\uf021'  # f2f1 is the one-arrow arrow-rotate-right
        FA_PALETTE = '\uf53f'  # the theme picker row's glyph
        FA_DOWNLOAD = '\uf019'
        FA_UPLOAD = '\uf093'
        FA_CIRCLE_EXCLAMATION = '\uf06a'
        FA_CIRCLE_INFO = '\uf05a'
        FA_WIFI = '\uf1eb'
        FA_SAVE = '\uf0c7'
        FA_COPY = '\uf0c5'  # copy-all control on the distance card
        FA_CLOCK = '\uf017'

APP_CONFIG = Config()
