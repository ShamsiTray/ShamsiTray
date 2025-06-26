import os
import logging
from typing import Optional, List
from pathlib import Path
import jdatetime
from PyQt5.QtGui import QFontDatabase

# --- Logging Setup ---
logger = logging.getLogger("config")
if not logger.hasHandlers():
    handler = logging.StreamHandler()
    formatter = logging.Formatter('[%(levelname)s] %(asctime)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

class Config:
    """Central configuration for the ShamsiTray app.

    All visual, API, and logic constants are defined here.
    """

    # --- Font families ---
    FONT_FAMILY = "Vazirmatn"
    GREGORIAN_FONT_FAMILY = "Inter"
    FONT_AWESOME_FAMILY = "Font Awesome 6 Pro Solid"
    FONT_AWESOME_REGULAR_FAMILY = "Font Awesome 6 Pro Regular"

    # --- Colors ---
    TEXT_COLOR = "#e0e0e0"
    BACKGROUND_COLOR = "#2c2c2c"
    INPUT_BG_COLOR = "#3a3a3a"
    ACCENT_COLOR = "#5cb85c"
    HOVER_BG = "rgba(255, 255, 255, 0.08)"
    SCROLLBAR_HANDLE_COLOR = "#505050"
    SCROLLBAR_GROOVE_COLOR = "#303030"
    HOLIDAY_COLOR = "#FF4C4C"
    GREY_COLOR = "#808080"

    # --- Logging ---
    LOG_LEVEL = logging.DEBUG

    # --- App meta ---
    APP_NAME = "ShamsiTray"
    COMPANY_NAME = ""
    BASE_DIR = Path(__file__).resolve().parent
    ICON_PATH = BASE_DIR / 'res' / 'icons' / 'icon.ico'
    AUTO_START_SETTING_KEY = "General/OpenAtLogin"

    # --- Holidays Data Source ---
    HOLIDAYS_FILE_PATH = BASE_DIR / 'res' / 'data' / 'holidays.json'

    # --- Calendar UI ---
    FONT_SIZE_LABEL = 15
    FONT_SIZE_HEADER = 28
    DAY_LABEL_SIZE = 35
    CONTENT_INNER_WIDTH = 275
    CALENDAR_WIDTH = 305
    CALENDAR_HEIGHT = 395
    CALENDAR_BACKGROUND_COLOR = "#2c2c2c"
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
    CHECKBOX_CHECKED_COLOR = "#5cb85c"   # Color for the checked square icon

    class FAS:
        """Font Awesome 6 Pro Unicode characters."""
        FA_SQUARE_REGULAR = '\uf096'  # Regular square (unchecked)
        FA_SQUARE_CHECK_SOLID = '\uf14a'  # Solid square-check (checked)

def to_persian_digits(s: str) -> str:
    """Convert all English digits in a string to Persian digits."""
    if not isinstance(s, str):
        s = str(s)
    return ''.join(Config.PERSIAN_DIGITS[int(ch)] if ch.isdigit() else ch for ch in s)

def from_persian_digits(s: str) -> str:
    """Convert all Persian digits in a string to English digits."""
    if not isinstance(s, str):
        s = str(s)
    english_digits_map = {v: str(k) for k, v in enumerate(Config.PERSIAN_DIGITS)}
    return ''.join(english_digits_map.get(ch, ch) for ch in s)

def persian_month_name(month: int) -> str:
    """Get Persian month name (1-based)."""
    if 1 <= month <= 12:
        return Config.PERSIAN_MONTHS[month - 1]
    raise ValueError("Month out of range (must be 1-12)")

def gregorian_month_name(month: int) -> str:
    """Get Gregorian month name (1-based)."""
    if 1 <= month <= 12:
        return Config.GREGORIAN_MONTHS[month - 1]
    raise ValueError("Month out of range (must be 1-12)")

def persian_weekday_name(weekday: int) -> str:
    """Get Persian weekday name (0=Saturday)."""
    if 0 <= weekday < 7:
        return Config.PERSIAN_WEEKDAY_NAMES[weekday]
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
    # More efficient than try/except: use jdatetime's .isleap() if available
    try:
        return jdatetime.j_isleap(year)
    except AttributeError:
        # Fallback for older jdatetime versions
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
    font_dir = Config.BASE_DIR / "res" / "fonts"
    if not font_dir.is_dir():
        logger.warning(f"Font directory not found: {font_dir}")
        return
    loaded_fonts = []
    for font_path in font_dir.iterdir():
        if font_path.suffix.lower() in (".ttf", ".otf"):
            result = QFontDatabase.addApplicationFont(str(font_path))
            if result != -1:
                loaded_fonts.append(font_path.name)
            else:
                logger.warning(f"Failed to load font: {font_path.name}")
    if loaded_fonts:
        logger.info(f"Loaded fonts: {', '.join(loaded_fonts)}")
    else:
        logger.warning("No fonts were loaded from font directory.")

def verify_assets() -> bool:
    """Verify that required assets (icons, fonts, data) exist; log error if missing."""
    errors: List[str] = []
    # Check for icon
    if not Config.ICON_PATH.exists():
        errors.append(f"App icon not found: {Config.ICON_PATH}")
    # Check for fonts directory
    font_dir = Config.BASE_DIR / "res" / "fonts"
    if not font_dir.is_dir():
        errors.append(f"Font directory not found: {font_dir}")
    else:
        fonts = [f for f in font_dir.iterdir() if f.suffix.lower() in ('.ttf', '.otf')]
        if not fonts:
            errors.append(f"No font files found in: {font_dir}")
    # Check for holidays data file
    if not Config.HOLIDAYS_FILE_PATH.exists():
        errors.append(f"Holidays data file not found: {Config.HOLIDAYS_FILE_PATH}")
    if errors:
        for err in errors:
            logger.error(err)
        return False
    return True