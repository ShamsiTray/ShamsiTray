"""
Date and Calendar Utilities
---------------------------

This module contains helper functions related to date manipulation, formatting,
and calendar-specific logic for both Jalali (Shamsi) and Gregorian systems.
"""
from typing import Optional

import jdatetime

from config import APP_CONFIG


def to_persian_digits(s: str) -> str:
    """Convert all English digits in a string to Persian digits."""
    s = str(s) if not isinstance(s, str) else s
    return "".join(APP_CONFIG.PERSIAN_DIGITS[int(ch)] if ch.isdigit() else ch for ch in s)

def from_persian_digits(s: str) -> str:
    """Convert all Persian digits in a string to English digits."""
    s = str(s) if not isinstance(s, str) else s
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
        return jdatetime.date.is_leap(year)
    except AttributeError:
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
