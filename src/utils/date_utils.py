"""
Date and Calendar Utilities
---------------------------

This module contains helper functions related to date manipulation, formatting,
and calendar-specific logic for both Jalali (Shamsi) and Gregorian systems.
"""
from typing import Optional

import datetime

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

def format_jalali_numeric(jdate: jdatetime.date) -> str:
    """Numeric Jalali string «1405/07/01» (English digits, zero-padded).

    The same convention the tray tooltip uses for its date line, so a copied
    date matches what the app shows elsewhere.
    """
    return f"{jdate.year}/{jdate.month:02d}/{jdate.day:02d}"

def format_gregorian_numeric(jdate: jdatetime.date) -> str:
    """Numeric Gregorian string «2026/09/23» for a Jalali date (zero-padded).

    Mirrors ``format_jalali_numeric`` so the two halves of a copied date pair
    are formatted identically.
    """
    gdate = jdate.togregorian()
    return f"{gdate.year}/{gdate.month:02d}/{gdate.day:02d}"

def is_gregorian_leap_year(year: int) -> bool:
    """Return True if a Gregorian year is a leap year."""
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)

def is_jalali_leap_year(year: int) -> bool:
    """Return True if a Jalali year is a leap year.

    A Jalali year is leap exactly when Esfand has 30 days; constructing that
    date is the arithmetic-free check (jdatetime has no static is-leap API).
    """
    try:
        jdatetime.date(year, 12, 30)
        return True
    except ValueError:
        return False

def days_in_jalali_month(year: int, month: int) -> int:
    """Return the number of days in a Jalali month (1-12)."""
    if 1 <= month <= 6:
        return 31
    if 7 <= month <= 11:
        return 30
    if month == 12:
        return 30 if is_jalali_leap_year(year) else 29
    raise ValueError("Month out of range (must be 1-12)")

def days_in_gregorian_month(year: int, month: int) -> int:
    """Return the number of days in a Gregorian month (1-12)."""
    # Guarded like the Jalali and month-name helpers: without this, month 0
    # falls through to 1 January of the previous year and reports 31 days.
    if not 1 <= month <= 12:
        raise ValueError("Month out of range (must be 1-12)")
    if month == 12:
        return 31
    return (datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)).day

def validate_year_range(year: int, min_year: int, max_year: int, is_jalali: bool) -> Optional[str]:
    """Check a year against its allowed range, returning a Persian error message or None."""
    if min_year <= year <= max_year:
        return None
    if is_jalali:
        return f"سال شمسی باید بین {to_persian_digits(min_year)} و {to_persian_digits(max_year)} باشد."
    return f"سال میلادی باید بین {min_year} و {max_year} باشد."

def ms_until_midnight(now: datetime.datetime) -> int:
    """Milliseconds from ``now`` local time until the next local midnight.

    Used to schedule the daily rollover; always returns a non-negative value
    (exactly-midnight input schedules the following midnight).
    """
    tomorrow = now + datetime.timedelta(days=1)
    next_midnight = datetime.datetime(tomorrow.year, tomorrow.month, tomorrow.day)
    return max(0, int((next_midnight - now).total_seconds() * 1000))
