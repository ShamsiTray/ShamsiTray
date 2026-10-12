"""
Application Configuration
-------------------------

This module centralizes all static configuration for the ShamsiTray application,
including application info, paths, settings keys, theme palettes, and UI constants.

It's designed to be imported by any module that needs access to these settings.
"""
from pathlib import Path
import os
import sys

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

    # --- Theme Management ---
    class Theme:
        SYSTEM = "system"
        DARK = "dark"
        LIGHT = "light"

    # The three-valued appearance preference stored under
    # Appearance/ThemeChoice: "system" follows Windows light/dark live,
    # "light"/"dark" pin the theme. The key's ABSENCE reads as "system" too -
    # the behaviour a fresh install has always had - and a stored "light"/"dark"
    # stays pinned, so a preference written before the three-way choice keeps
    # working.
    THEME_CHOICES = (Theme.SYSTEM, Theme.LIGHT, Theme.DARK)

    DARK_PALETTE = {
        "TEXT_COLOR": "#e0e0e0", "BACKGROUND_COLOR": "#2c2c2c",
        "INPUT_BG_COLOR": "#3a3a3a", "ACCENT_COLOR": "#398439",
        "HOVER_BG": "rgba(255, 255, 255, 0.08)", "SCROLLBAR_HANDLE_COLOR": "#505050",
        "SCROLLBAR_GROOVE_COLOR": "#303030", "HOLIDAY_COLOR": "#FF4C4C",
        "GREY_COLOR": "#808080", "WEEKDAY_NAMES_COLOR": "#b8b8b8",
        "CALENDAR_BACKGROUND_COLOR": "#2c2c2c", "CALENDAR_BORDER_COLOR": "#3B3B3B",
        "CALENDAR_TODAY_BG_COLOR": "rgba(128, 128, 128, 0.3)",
        "CALENDAR_TODAY_HOVER_BG_COLOR": "rgba(128, 128, 128, 0.5)",
        "CALENDAR_SELECTED_BG_COLOR": "rgba(224, 224, 224, 0.2)",
        "CALENDAR_SELECTED_HOVER_BG_COLOR": "rgba(224, 224, 224, 0.3)",
        "MENU_BACKGROUND_COLOR": "#2c2c2c", "MENU_BORDER_COLOR": "#606060",
        "MENU_HOVER_COLOR": (60, 60, 60, 180), "GREGORIAN_DATE_HOVER_BG": "rgba(255, 255, 255, 0.15)",
    }

    # The light accent sits deliberately deeper than a "bright blue" would be:
    # #34bbff needs white-on-accent text in the buttons, the dropdown's selected
    # row and the tray icon's event tint, and against those it fell short of the
    # 4.5:1 WCAG AA floor for body text. #1a6fa8 clears it with room to spare
    # while staying in the same hue family, so the theme keeps its identity.
    LIGHT_PALETTE = {
        "TEXT_COLOR": "#4b5563", "BACKGROUND_COLOR": "#f9fafb",
        "INPUT_BG_COLOR": "#ffffff", "ACCENT_COLOR": "#1a6fa8",
        "HOVER_BG": "#e5e7eb", "SCROLLBAR_HANDLE_COLOR": "#d1d5db",
        "SCROLLBAR_GROOVE_COLOR": "#f3f4f6", "HOLIDAY_COLOR": "#b91c1c",
        "GREY_COLOR": "#9ca3af", "WEEKDAY_NAMES_COLOR": "#616872",
        "CALENDAR_BACKGROUND_COLOR": "#ffffff", "CALENDAR_BORDER_COLOR": "#e5e7eb",
        "CALENDAR_TODAY_BG_COLOR": "rgba(156, 163, 175, 0.2)",
        "CALENDAR_TODAY_HOVER_BG_COLOR": "rgba(156, 163, 175, 0.35)",
        # Tinted from the accent so the selected day shares the hue of the
        # today pill instead of reading as an unrelated state; the alpha keeps
        # the day number legible over the accent.
        "CALENDAR_SELECTED_BG_COLOR": "rgba(26, 111, 168, 0.14)",
        "CALENDAR_SELECTED_HOVER_BG_COLOR": "rgba(26, 111, 168, 0.24)",
        "MENU_BACKGROUND_COLOR": "#ffffff", "MENU_BORDER_COLOR": "#e5e7eb",
        # 60 alpha keeps the hover row visible against white without competing
        # with the menu's own border.
        "MENU_HOVER_COLOR": (60, 60, 60, 60), "GREGORIAN_DATE_HOVER_BG": "rgba(0, 0, 0, 0.2)",
    }

    _theme_map = {Theme.DARK: DARK_PALETTE, Theme.LIGHT: LIGHT_PALETTE}
    current_palette = DARK_PALETTE  # Default to dark

    TRAY_ICON_DARK_COLOR = "#FFFFFF"
    TRAY_ICON_LIGHT_COLOR = "#000000"

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
        FA_SUN_SOLID = '\uf185'  # f185 replaces the Pro-only e28f codepoint
        FA_MOON_SOLID = '\uf186'
        FA_DESKTOP = '\uf390'  # the "follow system" stop of the theme cycle
        FA_XMARK = '\uf00d'
        FA_MINUS = '\uf068'
        FA_TRASH = '\uf1f8'
        FA_ARROWS_ROTATE = '\uf021'  # f2f1 is the one-arrow arrow-rotate-right
        FA_DOWNLOAD = '\uf019'
        FA_UPLOAD = '\uf093'
        FA_CIRCLE_EXCLAMATION = '\uf06a'
        FA_CIRCLE_INFO = '\uf05a'
        FA_WIFI = '\uf1eb'
        FA_SAVE = '\uf0c7'
        FA_CLOCK = '\uf017'

APP_CONFIG = Config()
