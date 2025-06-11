import jdatetime
import datetime
from typing import List
import os
from PyQt5.QtGui import QFontDatabase


class Config:
    FONT_FAMILY = "Vazirmatn"
    GREGORIAN_FONT_FAMILY = "Inter"
    FONT_AWESOME_FAMILY = "Font Awesome 6 Pro Solid" # Added Font Awesome Font Family
    TEXT_COLOR = "#e0e0e0"
    BACKGROUND_COLOR = "#2c2c2c"
    INPUT_BG_COLOR = "#3a3a3a"
    ACCENT_COLOR = "#5cb85c"
    HOVER_BG = "rgba(255, 255, 255, 0.08)"
    SCROLLBAR_HANDLE_COLOR = "#505050"
    SCROLLBAR_GROOVE_COLOR = "#303030"
    HOLIDAY_COLOR = "#FF4C4C"
    GREY_COLOR = "#808080"
    LOG_LEVEL = 10  # logging.DEBUG
    API_URL_TEMPLATE = "https://api.persian-calendar.ir/api/v1/calendar/{year}/holidays"
    CACHE_FILENAME = "holidays_cache.json"
    APP_NAME = "ShamsiTray"
    COMPANY_NAME = ""
    FONT_SIZE_LABEL = 15
    FONT_SIZE_HEADER = 28
    DAY_LABEL_SIZE = 35
    CONTENT_INNER_WIDTH = 275
    CALENDAR_WIDTH = 305
    CALENDAR_HEIGHT = 395
    CALENDAR_BACKGROUND_COLOR = "#2c2c2c"
    CALENDAR_BORDER_RADIUS_PX = 25
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
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    ICON_PATH = os.path.join(BASE_DIR, 'assets', 'icons', 'icon.ico')
    AUTO_START_SETTING_KEY = "General/OpenAtLogin"


def to_persian_digits(s: str) -> str:
    """Convert English digits in a string to Persian digits."""
    return ''.join(Config.PERSIAN_DIGITS[int(ch)] if ch.isdigit() else ch for ch in s)

def from_persian_digits(s: str) -> str:
    """Convert Persian digits in a string to English digits."""
    english_digits_map = {v: k for k, v in enumerate(Config.PERSIAN_DIGITS)}
    return ''.join(str(english_digits_map.get(ch, ch)) for ch in s)

def persian_month_name(month: int) -> str:
    return Config.PERSIAN_MONTHS[month - 1]

def gregorian_month_name(month: int) -> str:
    return Config.GREGORIAN_MONTHS[month - 1]

def persian_weekday_name(weekday: int) -> str:
    return Config.PERSIAN_WEEKDAY_NAMES[weekday]

def is_gregorian_leap_year(year: int) -> bool:
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)

def is_jalali_leap_year(year: int) -> bool:
    try:
        jdatetime.date(year, 12, 30)
        return True
    except ValueError:
        return False

def safe_jdate(year: int, month: int, day: int):
    try:
        return jdatetime.date(year, month, day)
    except ValueError:
        return None
    
def load_fonts():
    font_dir = os.path.join(os.path.dirname(__file__), "assets", "fonts")
    for font in os.listdir(font_dir):
        # Load both .ttf and .otf font files
        if font.endswith(".ttf") or font.endswith(".otf"):
            QFontDatabase.addApplicationFont(os.path.join(font_dir, font))