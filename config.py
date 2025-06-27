import os
import logging
from typing import Optional, List
from pathlib import Path
import jdatetime
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtCore import QSettings
import time

# --- Logging Setup (centralized for all modules) ---
def setup_logging(name: str = "config", level=logging.DEBUG) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.hasHandlers():
        handler = logging.StreamHandler()
        formatter = QLoggingFormatter('[%(levelname)s] %(asctime)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger

class QLoggingFormatter(logging.Formatter):
    """Custom Formatter to include microseconds and ensure consistency."""
    def formatTime(self, record, datefmt=None):
        ct = self.converter(record.created)
        if datefmt:
            s = time.strftime(datefmt, ct)
        else:
            s = time.strftime('%Y-%m-%d %H:%M:%S', ct)
        s = f"{s},{int(record.msecs):03d}"
        return s

logger = setup_logging("config")

class Config:
    """Central configuration for the ShamsiTray app."""

    # --- Font families ---
    FONT_FAMILY = "Vazirmatn"
    GREGORIAN_FONT_FAMILY = "Inter"
    FONT_AWESOME_FAMILY = "Font Awesome 6 Pro Solid"
    FONT_AWESOME_REGULAR_FAMILY = "Font Awesome 6 Pro Regular"

    # --- Theme Management ---
    class Theme:
        DARK = "dark"
        LIGHT = "light"

    DARK_PALETTE = {
        "TEXT_COLOR": "#e0e0e0",
        "BACKGROUND_COLOR": "#2c2c2c",
        "INPUT_BG_COLOR": "#3a3a3a",
        "ACCENT_COLOR": "#5cb85c",
        "HOVER_BG": "rgba(255, 255, 255, 0.08)",
        "SCROLLBAR_HANDLE_COLOR": "#505050",
        "SCROLLBAR_GROOVE_COLOR": "#303030",
        "HOLIDAY_COLOR": "#FF4C4C",
        "GREY_COLOR": "#808080",
        "CALENDAR_BACKGROUND_COLOR": "#2c2c2c",
        "CALENDAR_BORDER_COLOR": "#606060",
        "CALENDAR_TODAY_BG_COLOR": "rgba(128, 128, 128, 0.3)",
        "CALENDAR_TODAY_HOVER_BG_COLOR": "rgba(128, 128, 128, 0.5)",
        "CALENDAR_SELECTED_BG_COLOR": "rgba(224, 224, 224, 0.2)",
        "CALENDAR_SELECTED_HOVER_BG_COLOR": "rgba(224, 224, 224, 0.3)",
        "MENU_BACKGROUND_COLOR": "#2c2c2c",
        "MENU_BORDER_COLOR": "#606060",
        "MENU_HOVER_COLOR": "rgba(255, 255, 255, 0.08)"
    }

    LIGHT_PALETTE = {
        "TEXT_COLOR": "#303030",
        "BACKGROUND_COLOR": "#f0f0f0",
        "INPUT_BG_COLOR": "#e0e0e0",
        "ACCENT_COLOR": "#4CAF50",
        "HOVER_BG": "rgba(0, 0, 0, 0.05)",
        "SCROLLBAR_HANDLE_COLOR": "#b0b0b0",
        "SCROLLBAR_GROOVE_COLOR": "#e0e0e0",
        "HOLIDAY_COLOR": "#D32F2F",
        "GREY_COLOR": "#606060",
        "CALENDAR_BACKGROUND_COLOR": "#ffffff",
        "CALENDAR_BORDER_COLOR": "#d0d0d0",
        "CALENDAR_TODAY_BG_COLOR": "rgba(200, 200, 200, 0.5)",
        "CALENDAR_TODAY_HOVER_BG_COLOR": "rgba(200, 200, 200, 0.7)",
        "CALENDAR_SELECTED_BG_COLOR": "rgba(76, 175, 80, 0.5)",
        "CALENDAR_SELECTED_HOVER_BG_COLOR": "rgba(76, 175, 80, 0.7)",
        "MENU_BACKGROUND_COLOR": "#ffffff",
        "MENU_BORDER_COLOR": "#d0d0d0",
        "MENU_HOVER_COLOR": "rgba(0, 0, 0, 0.05)"
    }

    _theme_map = {
        Theme.DARK: DARK_PALETTE,
        Theme.LIGHT: LIGHT_PALETTE,
    }

    current_palette = DARK_PALETTE  # Default to dark

    TRAY_ICON_DARK_COLOR = "#FFFFFF"
    TRAY_ICON_LIGHT_COLOR = "#000000"

    @classmethod
    def set_theme(cls, theme: str):
        """Set app theme and update current_palette."""
        if theme in cls._theme_map:
            cls.current_palette = cls._theme_map[theme]
            logger.info(f"Theme set to {theme} with palette {cls.current_palette['BACKGROUND_COLOR']}")
        else:
            logger.warning(f"Unknown theme '{theme}' selected. Keeping current theme.")

    @classmethod
    def get_current_palette(cls):
        """Get the current theme palette."""
        return cls.current_palette

    @staticmethod
    def get_windows_theme() -> str:
        """Detect Windows theme (dark/light)."""
        try:
            key = QSettings("HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize", QSettings.NativeFormat)
            app_theme = key.value("AppsUseLightTheme", 1, type=int)
            return Config.Theme.LIGHT if app_theme == 1 else Config.Theme.DARK
        except Exception as e:
            logger.warning(f"Could not read Windows theme setting: {e}. Defaulting to Dark.")
            return Config.Theme.DARK

    # --- Logging ---
    LOG_LEVEL = logging.DEBUG

    # --- App meta ---
    APP_NAME = "ShamsiTray"
    COMPANY_NAME = ""
    BASE_DIR = Path(__file__).resolve().parent
    ICON_PATH = BASE_DIR / 'res' / 'icons' / 'icon.ico'
    AUTO_START_SETTING_KEY = "General/OpenAtLogin"
    CURRENT_THEME_SETTING_KEY = "Appearance/Theme"
    TUTORIAL_SHOWN_SETTING_KEY = "Tutorial/HasShown"
    TUTORIAL_GIF_PATH = BASE_DIR / 'res' / 'gifs' / 'welcome.gif'
    HOLIDAYS_FILE_PATH = BASE_DIR / 'res' / 'data' / 'holidays.json'

    # --- Calendar UI ---
    FONT_SIZE_LABEL = 15
    FONT_SIZE_HEADER = 28
    DAY_LABEL_SIZE = 35
    CONTENT_INNER_WIDTH = 275
    CALENDAR_WIDTH = 305
    CALENDAR_HEIGHT = 395
    CALENDAR_BORDER_RADIUS_PX = 25

    # --- Persian & Gregorian naming ---
    PERSIAN_DIGITS = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹']
    PERSIAN_MONTHS = [
        "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
        "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"
    ]
    GREGORIAN_MONTHS = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]
    PERSIAN_WEEKDAYS = ["ش", "ی", "د", "س", "چ", "پ", "ج"]
    PERSIAN_WEEKDAY_NAMES = [
        "شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه"
    ]

    # --- Checkbox and icons ---
    CHECKBOX_CHECKED_COLOR = "#5cb85c"

    class FAS:
        """Font Awesome 6 Pro Unicode characters."""
        FA_SQUARE_REGULAR = '\uf096'
        FA_SQUARE_CHECK_SOLID = '\uf14a'
        FA_CHECK_SOLID = '\uf00c'
        FA_SUN_SOLID = '\ue28f'
        FA_MOON_SOLID = '\uf186'

APP_CONFIG = Config()

def to_persian_digits(s: str) -> str:
    """Convert all English digits in a string to Persian digits."""
    if not s:
        return ""
    if not isinstance(s, str):
        s = str(s)
    return ''.join(APP_CONFIG.PERSIAN_DIGITS[int(ch)] if ch.isdigit() else ch for ch in s)

def from_persian_digits(s: str) -> str:
    """Convert all Persian digits in a string to English digits."""
    if not s:
        return ""
    if not isinstance(s, str):
        s = str(s)
    english_digits_map = {v: str(k) for k, v in enumerate(APP_CONFIG.PERSIAN_DIGITS)}
    return ''.join(english_digits_map.get(ch, ch) for ch in s)

def persian_month_name(month: int) -> str:
    """Get Persian month name (1-based)."""
    if 1 <= month <= 12:
        return APP_CONFIG.PERSIAN_MONTHS[month - 1]
    raise ValueError("Month out of range (must be 1-12)")

def gregorian_month_name(month: int) -> str:
    """Get Gregorian month name (1-based)."""
    if 1 <= month <= 12:
        return APP_CONFIG.GREGORIAN_MONTHS[month - 1]
    raise ValueError("Month out of range (must be 1-12)")

def persian_weekday_name(weekday: int) -> str:
    """Get Persian weekday name (0=Saturday)."""
    if 0 <= weekday < 7:
        return APP_CONFIG.PERSIAN_WEEKDAY_NAMES[weekday]
    raise ValueError("Weekday out of range (must be 0-6)")

def is_gregorian_leap_year(year: int) -> bool:
    """Return True if a Gregorian year is leap."""
    if year < 1:
        return False
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)

def is_jalali_leap_year(year: int) -> bool:
    """Return True if a Jalali year is leap (has Esfand 30)."""
    if year < 1:
        return False
    # Use jdatetime's .j_isleap() if available
    try:
        return jdatetime.j_isleap(year)
    except AttributeError:
        try:
            jdatetime.date(year, 12, 30)
            return True
        except ValueError:
            return False

def safe_jdate(year: int, month: int, day: int) -> Optional[jdatetime.date]:
    """Safely create a Jalali date, return None if invalid."""
    try:
        return jdatetime.date(year, month, day)
    except ValueError:
        return None

def load_fonts() -> None:
    """Load all .ttf/.otf fonts from the assets/fonts directory and log what was loaded."""
    font_dir = APP_CONFIG.BASE_DIR / "res" / "fonts"
    if not font_dir.is_dir():
        logger.error(f"Font directory not found: {font_dir}")
        raise FileNotFoundError(f"Font directory not found: {font_dir}")
    loaded_fonts = []
    for font_path in font_dir.glob("*.ttf"):
        result = QFontDatabase.addApplicationFont(str(font_path))
        if result != -1:
            loaded_fonts.append(font_path.name)
        else:
            logger.warning(f"Failed to load font: {font_path.name}")
    for font_path in font_dir.glob("*.otf"):
        result = QFontDatabase.addApplicationFont(str(font_path))
        if result != -1:
            loaded_fonts.append(font_path.name)
        else:
            logger.warning(f"Failed to load font: {font_path.name}")
    if loaded_fonts:
        logger.info(f"Loaded fonts: {', '.join(loaded_fonts)}")
    else:
        logger.error("No fonts were loaded from font directory.")
        raise RuntimeError("No fonts were loaded from font directory.")

def verify_assets() -> bool:
    """Verify that required assets (icons, fonts, data) exist; log error if missing."""
    errors: List[str] = []
    if not APP_CONFIG.ICON_PATH.exists():
        errors.append(f"App icon not found: {APP_CONFIG.ICON_PATH}")
    font_dir = APP_CONFIG.BASE_DIR / "res" / "fonts"
    if not font_dir.is_dir():
        errors.append(f"Font directory not found: {font_dir}")
    else:
        fonts = list(font_dir.glob('*.ttf')) + list(font_dir.glob('*.otf'))
        if not fonts:
            errors.append(f"No font files found in: {font_dir}")
    if not APP_CONFIG.HOLIDAYS_FILE_PATH.exists():
        errors.append(f"Holidays data file not found: {APP_CONFIG.HOLIDAYS_FILE_PATH}")
    if not APP_CONFIG.TUTORIAL_GIF_PATH.exists():
        errors.append(f"Tutorial GIF file not found: {APP_CONFIG.TUTORIAL_GIF_PATH}")

    if errors:
        for err in errors:
            logger.error(err)
        raise FileNotFoundError("One or more required assets are missing:\n" + '\n'.join(errors))
    return True