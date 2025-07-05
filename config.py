import os
import logging
import time
from pathlib import Path
from typing import List, Optional

import jdatetime
from PyQt5.QtCore import QSettings
from PyQt5.QtGui import QFontDatabase


# --- Logging Setup (centralized for all modules) ---
class QLoggingFormatter(logging.Formatter):
    """Custom Formatter to include microseconds and ensure consistency."""
    def formatTime(self, record, datefmt=None):
        ct = self.converter(record.created)
        s = time.strftime('%Y-%m-%d %H:%M:%S', ct) if not datefmt else time.strftime(datefmt, ct)
        return f"{s},{int(record.msecs):03d}"

def setup_logging(name: str, level=logging.DEBUG) -> logging.Logger:
    """
    Sets up a logger with a custom formatter.
    Avoids adding duplicate handlers if already configured.
    """
    logger = logging.getLogger(name)
    if not logger.hasHandlers():
        handler = logging.StreamHandler()
        formatter = QLoggingFormatter('[%(levelname)s] %(asctime)s - %(name)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger

logger = setup_logging("config")

# --- Main Configuration Class ---
class Config:
    """Central configuration for the ShamsiTray app."""

    # --- App Info ---
    APP_NAME = "ShamsiTray"
    COMPANY_NAME = "Rayden"
    BASE_DIR = Path(__file__).resolve().parent

    # --- Resource Paths ---
    RES_DIR = BASE_DIR / 'res'
    ICON_PATH = RES_DIR / 'icons' / 'icon.ico'
    FONT_DIR = RES_DIR / 'fonts'
    TUTORIAL_GIF_PATH = RES_DIR / 'gifs' / 'welcome.gif'
    HOLIDAYS_FILE_PATH = RES_DIR / 'data' / 'holidays.json'

    # --- Settings Keys ---
    AUTO_START_SETTING_KEY = "General/OpenAtLogin"
    CURRENT_THEME_CHOICE_SETTING_KEY = "Appearance/ThemeChoice"
    TUTORIAL_SHOWN_SETTING_KEY = "Tutorial/HasShown"

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
        "SCROLLBAR_GROOVE_COLOR": "#303030", "HOLIDAY_COLOR": "#FF4C4C", # Red holiday color
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
        "SCROLLBAR_GROOVE_COLOR": "#f3f4f6", "HOLIDAY_COLOR": "#b91c1c", # Red holiday color
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
        cls.current_palette = cls._theme_map.get(theme_name, cls.DARK_PALETTE)
        if theme_name not in cls._theme_map:
            logger.warning(f"Unknown theme '{theme_name}'. Defaulting to Dark.")
        logger.info(f"Theme set to {theme_name}.")

    @classmethod
    def get_current_palette(cls):
        """Get the current theme palette."""
        return cls.current_palette

    # --- Calendar UI ---
    FONT_SIZE_LABEL = 15
    FONT_SIZE_HEADER = 28
    DAY_LABEL_SIZE = 35
    CALENDAR_WIDTH = 305
    CALENDAR_HEIGHT = 395
    CALENDAR_BORDER_RADIUS_PX = 25

    # --- Date & Time Data ---
    PERSIAN_DIGITS = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹']
    _ENGLISH_DIGITS_MAP = {ord(p): str(e) for e, p in enumerate(PERSIAN_DIGITS)}
    
    PERSIAN_MONTHS = [
        "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
        "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"
    ]
    GREGORIAN_MONTHS = [
        "January", "February", "March", "April", "May", "June", # Corrected "March" to "April"
        "July", "August", "September", "October", "November", "December"
    ]
    PERSIAN_WEEKDAYS_SHORT = ["ش", "ی", "د", "س", "چ", "پ", "ج"]
    PERSIAN_WEEKDAY_NAMES = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه"]

    # --- Icons ---
    class FAS:
        FA_SQUARE_REGULAR = '\uf096'
        FA_SQUARE_CHECK_SOLID = '\uf14a'
        FA_SUN_SOLID = '\ue28f'
        FA_MOON_SOLID = '\uf186'

# Instantiate config for global access
APP_CONFIG = Config()

# --- Utility Functions ---
def to_persian_digits(s: str) -> str:
    """Convert all English digits in a string to Persian digits."""
    s = str(s) if not isinstance(s, str) else s
    return "".join(APP_CONFIG.PERSIAN_DIGITS[int(ch)] if ch.isdigit() else ch for ch in s)

def from_persian_digits(s: str) -> str:
    """Convert all Persian digits in a string to English digits."""
    s = str(s) if not isinstance(s, str) else s
    # Create a translation table if it doesn't exist or if APP_CONFIG._ENGLISH_DIGITS_MAP is not directly usable
    # For performance, this mapping should be pre-computed.
    # Given the existing _ENGLISH_DIGITS_MAP, using str.translate is correct.
    return s.translate(APP_CONFIG._ENGLISH_DIGITS_MAP)

def persian_month_name(month: int) -> str:
    """Get Persian month name (1-based index)."""
    if 1 <= month <= 12:
        return APP_CONFIG.PERSIAN_MONTHS[month - 1]
    raise ValueError("Month out of range (must be 1-12)")

def gregorian_month_name(month: int) -> str:
    """Get Gregorian month name (1-based index)."""
    if 1 <= month <= 12:
        return APP_CONFIG.GREGORIAN_MONTHS[month - 1]
    raise ValueError("Month out of range (must be 1-12)")

def persian_weekday_name(weekday: int) -> str:
    """Get Persian weekday name (0=Saturday)."""
    if 0 <= weekday < 7:
        return APP_CONFIG.PERSIAN_WEEKDAY_NAMES[weekday]
    raise ValueError("Weekday out of range (must be 0-6)")

def is_gregorian_leap_year(year: int) -> bool:
    """Return True if a Gregorian year is a leap year."""
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)

def is_jalali_leap_year(year: int) -> bool:
    """Return True if a Jalali year is a leap year."""
    try:
        # noinspection PyUnresolvedReferences
        return jdatetime.date.is_leap(year)
    except AttributeError:
        # Fallback for older jdatetime versions if `is_leap` doesn't exist.
        # This fallback for jdatetime.date(year, 12, 30) for leap year detection
        # is a common heuristic if is_leap is not available.
        try:
            jdatetime.date(year, 12, 30)
            return True
        except ValueError:
            return False


def safe_jdate(year: int, month: int, day: int) -> Optional[jdatetime.date]:
    """Safely create a Jalali date, returning None if invalid."""
    try:
        return jdatetime.date(year, month, day)
    except ValueError:
        return None

def load_fonts() -> None:
    """Load all .ttf and .otf fonts from the resources directory."""
    font_dir = APP_CONFIG.FONT_DIR
    if not font_dir.is_dir():
        raise FileNotFoundError(f"Font directory not found: {font_dir}")
    
    loaded_fonts = []
    for extension in ("*.ttf", "*.otf"):
        for font_path in font_dir.glob(extension):
            if QFontDatabase.addApplicationFont(str(font_path)) != -1:
                loaded_fonts.append(font_path.name)
            else:
                logger.warning(f"Failed to load font: {font_path.name}")
            
    if loaded_fonts:
        logger.info(f"Loaded fonts: {', '.join(loaded_fonts)}")
    else:
        raise RuntimeError("No fonts were loaded from the font directory.")

def verify_assets() -> None:
    """
    Verify that required assets exist. Raises FileNotFoundError if any are missing.
    """
    assets_to_check = {
        "App icon": APP_CONFIG.ICON_PATH,
        "Holidays data file": APP_CONFIG.HOLIDAYS_FILE_PATH,
        "Tutorial GIF": APP_CONFIG.TUTORIAL_GIF_PATH,
        "Font directory": APP_CONFIG.FONT_DIR,
    }
    
    missing_assets = [name for name, path in assets_to_check.items() if not path.exists()]
    
    # Special check for font files inside the font directory
    if not any(APP_CONFIG.FONT_DIR.glob("*.ttf")) and not any(APP_CONFIG.FONT_DIR.glob("*.otf")):
        missing_assets.append("Any .ttf or .otf font file")

    if missing_assets:
        error_msg = "One or more required assets are missing: " + ", ".join(missing_assets)
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)
    
    logger.info("All required assets verified successfully.")