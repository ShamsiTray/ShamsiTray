"""
Application Configuration
-------------------------

This module centralizes all static configuration for the ShamsiTray application,
including application info, paths, settings keys, theme palettes, and UI constants.

It's designed to be imported by any module that needs access to these settings.
Date and asset-related helper functions have been moved to the `utils` package
to keep this file focused solely on configuration data.
"""
from pathlib import Path
import sys

class Config:
    """Central configuration for the ShamsiTray app."""

    # --- App Info ---
    APP_NAME = "ShamsiTray"
    COMPANY_NAME = "ShamsiTray"
    APP_VERSION = "1.3.0"
    
    # --- Paths (dynamically calculated) ---
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        PROJECT_ROOT = Path(sys._MEIPASS)
    else:
        PROJECT_ROOT = Path(__file__).resolve().parent.parent
    ASSETS_DIR = PROJECT_ROOT / 'assets'
    ICON_PATH = ASSETS_DIR / 'icons' / 'icon.ico'
    FONT_DIR = ASSETS_DIR / 'fonts'
    TUTORIAL_GIF_PATH = ASSETS_DIR / 'gifs' / 'welcome.gif'
    HOLIDAYS_FILE_PATH = ASSETS_DIR / 'data' / 'holidays.json'

    # --- Settings Keys (for QSettings) ---
    AUTO_START_SETTING_KEY = "General/OpenAtLogin"
    CURRENT_THEME_CHOICE_SETTING_KEY = "Appearance/ThemeChoice"
    TUTORIAL_SHOWN_SETTING_KEY = "Tutorial/HasShown"
    USER_EVENTS_SETTING_KEY = "UserData/Events"

    # --- Font Families ---
    FONT_FAMILY = "Vazirmatn"
    GREGORIAN_FONT_FAMILY = "Inter"
    FONT_AWESOME_FAMILY = "Font Awesome 6 Pro Solid"

    # --- Theme Management ---
    class Theme:
        DARK = "dark"
        LIGHT = "light"

    DARK_PALETTE = {
        "TEXT_COLOR": "#e0e0e0", "BACKGROUND_COLOR": "#2c2c2c",
        "INPUT_BG_COLOR": "#3a3a3a", "ACCENT_COLOR": "#4d9a4d",
        "HOVER_BG": "rgba(255, 255, 255, 0.08)", "SCROLLBAR_HANDLE_COLOR": "#505050",
        "SCROLLBAR_GROOVE_COLOR": "#303030", "HOLIDAY_COLOR": "#FF4C4C",
        "GREY_COLOR": "#808080", "WEEKDAY_NAMES_COLOR": "#b8b8b8",
        "CALENDAR_BACKGROUND_COLOR": "#2c2c2c", "CALENDAR_BORDER_COLOR": "#606060",
        "CALENDAR_TODAY_BG_COLOR": "rgba(128, 128, 128, 0.3)",
        "CALENDAR_TODAY_HOVER_BG_COLOR": "rgba(128, 128, 128, 0.5)",
        "CALENDAR_TODAY_SELECTED_BG_COLOR": "rgba(128, 128, 128, 0.6)",
        "CALENDAR_SELECTED_BG_COLOR": "rgba(224, 224, 224, 0.2)",
        "CALENDAR_SELECTED_HOVER_BG_COLOR": "rgba(224, 224, 224, 0.3)",
        "MENU_BACKGROUND_COLOR": "#2c2c2c", "MENU_BORDER_COLOR": "#606060",
        "MENU_HOVER_COLOR": (60, 60, 60, 180), "GREGORIAN_DATE_HOVER_BG": "rgba(255, 255, 255, 0.15)",
    }

    LIGHT_PALETTE = {
        "TEXT_COLOR": "#4b5563", "BACKGROUND_COLOR": "#f9fafb",
        "INPUT_BG_COLOR": "#ffffff", "ACCENT_COLOR": "#34bbff",
        "HOVER_BG": "#e5e7eb", "SCROLLBAR_HANDLE_COLOR": "#d1d5db",
        "SCROLLBAR_GROOVE_COLOR": "#f3f4f6", "HOLIDAY_COLOR": "#b91c1c",
        "GREY_COLOR": "#9ca3af", "WEEKDAY_NAMES_COLOR": "#616872",
        "CALENDAR_BACKGROUND_COLOR": "#ffffff", "CALENDAR_BORDER_COLOR": "#e5e7eb",
        "CALENDAR_TODAY_BG_COLOR": "rgba(156, 163, 175, 0.2)",
        "CALENDAR_TODAY_HOVER_BG_COLOR": "rgba(156, 163, 175, 0.35)",
        "CALENDAR_TODAY_SELECTED_BG_COLOR": "rgba(156, 163, 175, 0.45)",
        "CALENDAR_SELECTED_BG_COLOR": "rgba(75, 174, 79, 0.1)",
        "CALENDAR_SELECTED_HOVER_BG_COLOR": "rgba(75, 174, 79, 0.2)",
        "MENU_BACKGROUND_COLOR": "#ffffff", "MENU_BORDER_COLOR": "#e5e7eb",
        "MENU_HOVER_COLOR": (60, 60, 60, 40), "GREGORIAN_DATE_HOVER_BG": "rgba(0, 0, 0, 0.2)",
    }

    _theme_map = {Theme.DARK: DARK_PALETTE, Theme.LIGHT: LIGHT_PALETTE}
    current_palette = DARK_PALETTE  # Default to dark

    TRAY_ICON_DARK_COLOR = "#FFFFFF"
    TRAY_ICON_LIGHT_COLOR = "#000000"

    @classmethod
    def set_theme(cls, theme_name: str):
        """Set app theme and update the current_palette."""
        from utils.logging_setup import setup_logging
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

    # --- FontAwesome Icon Characters ---
    class FAS:
        FA_SQUARE_REGULAR = '\uf096'
        FA_SQUARE_CHECK_SOLID = '\uf14a'
        FA_SUN_SOLID = '\ue28f'
        FA_MOON_SOLID = '\uf186'

# Create a single, globally accessible instance of the configuration.
APP_CONFIG = Config()
