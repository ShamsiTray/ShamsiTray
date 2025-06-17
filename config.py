import os
import logging
import jdatetime
from typing import List, Optional
from PyQt5.QtGui import QFontDatabase

logger = logging.getLogger("config")

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
    LOG_LEVEL = 10  # logging.DEBUG

    # --- API & cache ---
    API_URL_TEMPLATE = os.environ.get(
        "SHAMSITRAY_API_URL_TEMPLATE", 
        "https://api.persian-calendar.ir/api/v1/calendar/{year}/holidays"
    )
    CACHE_FILENAME = "holidays_cache.json"

    # --- App meta ---
    APP_NAME = "ShamsiTray"
    COMPANY_NAME = ""
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    ICON_PATH = os.path.join(BASE_DIR, 'assets', 'icons', 'icon.ico')
    AUTO_START_SETTING_KEY = "General/OpenAtLogin"

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

    class FAS:  # Font Awesome Unicode characters
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
    raise ValueError("Month out of range")

def gregorian_month_name(month: int) -> str:
    """Get Gregorian month name (1-based)."""
    if 1 <= month <= 12:
        return Config.GREGORIAN_MONTHS[month - 1]
    raise ValueError("Month out of range")

def persian_weekday_name(weekday: int) -> str:
    """Get Persian weekday name (0=Saturday)."""
    if 0 <= weekday < 7:
        return Config.PERSIAN_WEEKDAY_NAMES[weekday]
    raise ValueError("Weekday out of range")

def is_gregorian_leap_year(year: int) -> bool:
    """Return True if a Gregorian year is leap."""
    if year < 1:
        return False
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)

def is_jalali_leap_year(year: int) -> bool:
    """Return True if a Jalali year is leap (has Esfand 30)."""
    if year < 1:
        return False
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

def load_fonts():
    """Load all .ttf/.otf fonts from the assets/fonts directory and log what was loaded."""
    font_dir = os.path.join(Config.BASE_DIR, "assets", "fonts")
    if not os.path.isdir(font_dir):
        logger.warning(f"Font directory not found: {font_dir}")
        return
    loaded_fonts = []
    for font_filename in os.listdir(font_dir):
        if font_filename.lower().endswith((".ttf", ".otf")):
            font_path = os.path.join(font_dir, font_filename)
            result = QFontDatabase.addApplicationFont(font_path)
            if result != -1:
                loaded_fonts.append(font_filename)
            else:
                logger.warning(f"Failed to load font: {font_filename}")
    if loaded_fonts:
        logger.info(f"Loaded fonts: {', '.join(loaded_fonts)}")
    else:
        logger.warning("No fonts were loaded from font directory.")

def verify_assets():
    """Verify that required assets (icons, fonts) exist; log error if missing."""
    errors = []
    if not os.path.exists(Config.ICON_PATH):
        errors.append(f"App icon not found: {Config.ICON_PATH}")
    font_dir = os.path.join(Config.BASE_DIR, "assets", "fonts")
    if not os.path.isdir(font_dir):
        errors.append(f"Font directory not found: {font_dir}")
    else:
        fonts = [f for f in os.listdir(font_dir) if f.lower().endswith(('.ttf', '.otf'))]
        if not fonts:
            errors.append(f"No font files found in: {font_dir}")
    if errors:
        for err in errors:
            logger.error(err)
        return False
    return True

def parse_holidays_from_api(data) -> dict:
    """
    Parse the 'data' list from the API and return {(month, day): description} mapping.
    """
    holidays_for_year = {}
    for holiday_info in data:
        jalali_date_str = holiday_info.get('date')
        description = holiday_info.get('holidayDesription') or holiday_info.get('holidayDescription')
        if jalali_date_str and description:
            try:
                y, m, d = map(int, jalali_date_str.split('/'))
                holidays_for_year[(m, d)] = description
            except Exception as e:
                logger.warning(f"Invalid Jalali date: {jalali_date_str}, error: {e}")
    return holidays_for_year