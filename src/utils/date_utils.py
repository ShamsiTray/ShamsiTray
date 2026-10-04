"""
Date and Calendar Utilities
---------------------------

This module contains helper functions related to date manipulation, formatting,
and calendar-specific logic for both Jalali (Shamsi) and Gregorian systems.
"""
from dataclasses import dataclass
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

@dataclass(frozen=True)
class DateDistance:
    """How far apart two Jalali dates are, measured from the earlier one.

    ``total_days`` is signed (``target - today``), so its sign is the
    direction: negative past, zero today, positive future. It is not a
    conversion of the other three fields - Jalali months run 29 to 31 days,
    years 365 or 366, and the clamped decomposition depends on the anchor
    date. 1395/01/01 -> 1405/01/01 is ten years and 3653 days, not 3650, and
    1401/10/01 -> 1402/01/01 is three months and 89 days where
    1405/08/01 -> 1405/11/01 is three months and 90.

    ``years``, ``months`` and ``days`` are all non-negative: the pair is
    always oriented earlier -> later.
    """

    years: int
    months: int
    days: int
    total_days: int

    @property
    def is_today(self) -> bool:
        return self.total_days == 0

    @property
    def has_calendar_units(self) -> bool:
        """True when the decomposition says more than the plain day total.

        ``years == 0 and months == 0`` is exactly the case where
        ``format_distance_breakdown`` renders the same sentence as
        ``format_distance_total``: the breakdown is pure days, and those days
        *are* the total. A surface showing both would repeat one line, so it
        asks this first. Any non-zero month or year makes the two differ,
        because the breakdown then leads with a different unit word.

        Not a substitute for the ``is_today`` branch: today has no calendar
        units either, but both formatters are undefined for it.
        """
        return self.years > 0 or self.months > 0

def _add_jalali_years(jdate: jdatetime.date, count: int) -> jdatetime.date:
    """Shift by whole years, clamping to the target month's last valid day."""
    year = jdate.year + count
    return jdatetime.date(year, jdate.month,
                          min(jdate.day, days_in_jalali_month(year, jdate.month)))

def _add_jalali_months(jdate: jdatetime.date, count: int) -> jdatetime.date:
    """Shift by whole months, clamping to the target month's last valid day."""
    year, month = jdate.year + count // 12, jdate.month + count % 12
    if month > 12:
        year, month = year + 1, month - 12
    return jdatetime.date(year, month,
                          min(jdate.day, days_in_jalali_month(year, month)))

def describe_date_distance(target: jdatetime.date,
                           today: Optional[jdatetime.date] = None) -> DateDistance:
    """Decompose the gap between ``target`` and ``today`` (today by default).

    Units are taken largest first - years, then months, then the leftover
    days - and each step clamps to the target month's last valid day, so the
    result is order-dependent and is not flat field arithmetic: from
    1403/12/30, one year on is 1404/12/29, because 1404 has no Esfand 30.

    The walk advances a cursor instead of recomputing from the original date
    on every iteration, which would be quadratic across wide year spans.
    """
    today = today if today is not None else jdatetime.date.today()
    delta = (target - today).days
    lo, hi = (today, target) if delta >= 0 else (target, today)

    cursor = lo
    years = 0
    while _add_jalali_years(cursor, 1) <= hi:
        cursor = _add_jalali_years(cursor, 1)
        years += 1

    months = 0
    while _add_jalali_months(cursor, 1) <= hi:
        cursor = _add_jalali_months(cursor, 1)
        months += 1

    return DateDistance(years=years, months=months, days=(hi - cursor).days,
                        total_days=delta)

def _distance_status_word(distance: DateDistance) -> str:
    """The direction word; today is a caller branch, so it is never asked."""
    return "مانده" if distance.total_days > 0 else "گذشته"

def format_distance_total(distance: DateDistance) -> str:
    """«۶۹ روز مانده» - the day count and its direction. Not defined for today."""
    return f"{to_persian_digits(abs(distance.total_days))} روز {_distance_status_word(distance)}"

def format_distance_breakdown(distance: DateDistance) -> str:
    """«۲ سال و ۲ ماه و ۱ روز مانده». Not defined for today.

    A non-today distance always has at least one non-zero unit, so the part
    list is never empty.
    """
    parts = [f"{to_persian_digits(count)} {unit}" for count, unit in
             ((distance.years, "سال"), (distance.months, "ماه"), (distance.days, "روز"))
             if count]
    return f"{' و '.join(parts)} {_distance_status_word(distance)}"

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


def format_jalali_long(jdate, *, persian_digits=True):
    day_str = to_persian_digits(jdate.day) if persian_digits else str(jdate.day)
    year_str = to_persian_digits(jdate.year) if persian_digits else str(jdate.year)
    return persian_weekday_name(jdate.weekday()) + " " + day_str + " " + persian_month_name(jdate.month) + " " + year_str

def format_gregorian_long(gdate, *, persian_digits=True):
    """Readable Gregorian date, e.g. «Tuesday 21 October 2025».

    The weekday and month names come from the app's own tables rather than
    ``strftime('%A'/'%B')``: those follow the process locale, so the same call
    returned Persian names on a Persian Windows install and English ones
    elsewhere. ``persian_digits`` defaults True to match ``format_jalali_long`` -
    the two are read side by side, and the copy entry that wants Latin digits
    asks for them explicitly.
    """
    if not 1 <= gdate.month <= 12 or not 0 <= gdate.weekday() <= 6:
        raise ValueError("Gregorian month or weekday out of range")
    day_str = to_persian_digits(gdate.day) if persian_digits else str(gdate.day)
    year_str = to_persian_digits(gdate.year) if persian_digits else str(gdate.year)
    return (f"{APP_CONFIG.GREGORIAN_WEEKDAY_NAMES[gdate.weekday()]} {day_str} "
            f"{gregorian_month_name(gdate.month)} {year_str}")

