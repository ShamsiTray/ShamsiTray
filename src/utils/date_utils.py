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

# --- free-text search normalization ---------------------------------------------
#
# A Persian keyboard layout does not stop users pasting text from elsewhere, and
# a search that fails on «علي» vs «علی» reads as "the event is gone". Both sides
# of the comparison go through this map, so the spellings converge on one form
# instead of the query having to match the stored text exactly.

_ARABIC_INDIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"  # U+0660 - U+0669

_SEARCH_NORMALIZE_MAP = {
    # Persian digits -> Latin
    **{ord(p): str(e) for e, p in enumerate(APP_CONFIG.PERSIAN_DIGITS)},
    # Arabic-Indic digits -> Latin (from_persian_digits covers the Persian set
    # only, which is why the search needs its own table)
    **{ord(p): str(e) for e, p in enumerate(_ARABIC_INDIC_DIGITS)},
    # Arabic yeh/kaf -> the Persian letters that are actually stored
    ord("ي"): "ی",
    ord("ك"): "ک",
    # ZWNJ: «می‌شود» must match «میشود»
    0x200C: None,  # None = dropped by translate
}


def normalize_search_text(text: str) -> str:
    """Normalize free-text search input on BOTH sides of a comparison.

    Persian and Arabic-Indic digits become Latin, Arabic yeh/kaf become the
    Persian letters, the zero-width non-joiner is dropped, and the result is
    lowercased - so «کتاب علي», «کتاب علی» and «کتاب‌علی» all match each other,
    and 12 / ۱۲ / ١٢ each find «جلسه ۱۲ نفره».
    """
    s = str(text) if not isinstance(text, str) else text
    return s.translate(_SEARCH_NORMALIZE_MAP).lower()


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

    @property
    def has_month_total(self) -> bool:
        """True when a whole-months reading adds something to the breakdown.

        Without a year, «۳ ماه و ۱۴ روز» already IS the months-and-days
        reading, so a second line would only repeat it.
        """
        return self.years > 0

    @property
    def has_full_weeks(self) -> bool:
        """True when the gap spans at least one whole week (7+ days, either way).

        Under a week ``format_distance_weeks`` would only restate the day
        total, so a surface asks this before showing a weeks line. Like
        ``has_calendar_units`` it is not a substitute for the ``is_today``
        branch.
        """
        return abs(self.total_days) >= 7

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

def _describe_distance(target, today, add_years, add_months) -> DateDistance:
    """The calendar-agnostic walk behind both describe_* entry points.

    ``add_years`` / ``add_months`` are the calendar's clamping shifts. Units are
    taken largest first - years, then months, then the leftover days - and each
    step clamps to the target month's last valid day, so the result is
    order-dependent and is not flat field arithmetic: from 1403/12/30, one year
    on is 1404/12/29, because 1404 has no Esfand 30.

    The walk advances a cursor instead of recomputing from the original date
    on every iteration, which would be quadratic across wide year spans.
    """
    delta = (target - today).days
    lo, hi = (today, target) if delta >= 0 else (target, today)

    cursor = lo
    years = 0
    while (nxt := _walk_step(cursor, add_years)) is not None and nxt <= hi:
        cursor = nxt
        years += 1

    months = 0
    while (nxt := _walk_step(cursor, add_months)) is not None and nxt <= hi:
        cursor = nxt
        months += 1

    return DateDistance(years=years, months=months, days=(hi - cursor).days,
                        total_days=delta)

def _walk_step(cursor, add_unit):
    """``add_unit(cursor, 1)``, or None at the calendar's edge: the probes
    must construct ``cursor.year + 1``, which both jdatetime and date raise
    on past their last representable year - the walk is then already at the
    widest date it can step to and simply stops."""
    try:
        return add_unit(cursor, 1)
    except ValueError:
        return None

def describe_date_distance(target: jdatetime.date,
                           today: Optional[jdatetime.date] = None) -> DateDistance:
    """Decompose the gap between ``target`` and ``today`` (today by default),
    in Jalali calendar units (see ``_describe_distance`` for the walk)."""
    today = today if today is not None else jdatetime.date.today()
    return _describe_distance(target, today, _add_jalali_years, _add_jalali_months)

def _add_gregorian_years(gdate: datetime.date, count: int) -> datetime.date:
    """Shift by whole years, clamping to the target month's last valid day."""
    year = gdate.year + count
    return datetime.date(year, gdate.month,
                         min(gdate.day, days_in_gregorian_month(year, gdate.month)))

def _add_gregorian_months(gdate: datetime.date, count: int) -> datetime.date:
    """Shift by whole months, clamping to the target month's last valid day."""
    year, month = gdate.year + count // 12, gdate.month + count % 12
    if month > 12:
        year, month = year + 1, month - 12
    return datetime.date(year, month,
                         min(gdate.day, days_in_gregorian_month(year, month)))

def describe_gregorian_distance(target: datetime.date,
                                today: Optional[datetime.date] = None) -> DateDistance:
    """``describe_date_distance`` for two Gregorian dates: the same walk in
    Gregorian calendar units. The day total is identical in both calendars;
    only the years/months/days split differs (month lengths differ)."""
    today = today if today is not None else datetime.date.today()
    return _describe_distance(target, today, _add_gregorian_years, _add_gregorian_months)

def _distance_status_word(distance: DateDistance) -> str:
    """The direction word; today is a caller branch, so it is never asked."""
    return "مانده" if distance.total_days > 0 else "گذشته"

def format_distance_total(distance: DateDistance) -> str:
    """«۶۹ روز مانده» - the day count and its direction. Not defined for today."""
    return f"{to_persian_digits(abs(distance.total_days))} روز {_distance_status_word(distance)}"

def format_distance_units(distance: DateDistance) -> str:
    """«۲ سال و ۲ ماه و ۱ روز» - the calendar breakdown with no direction word.

    For surfaces where the direction is not part of the question (the
    distance window measures two arbitrary dates). Not defined for today; a
    non-today distance always has at least one non-zero unit, so the part
    list is never empty.
    """
    parts = [f"{to_persian_digits(count)} {unit}" for count, unit in
             ((distance.years, "سال"), (distance.months, "ماه"), (distance.days, "روز"))
             if count]
    return ' و '.join(parts)

def format_distance_total_months(distance: DateDistance) -> str:
    """«۶۸ ماه و ۲۰ روز» - years folded into months, plus the leftover days.

    A direction-free sibling of ``format_distance_units``. Callers branch on
    ``is_today`` first and on ``has_month_total`` (without a year it would
    repeat the breakdown).
    """
    months = distance.years * 12 + distance.months
    parts = [f"{to_persian_digits(count)} {unit}" for count, unit in
             ((months, "ماه"), (distance.days, "روز")) if count]
    return ' و '.join(parts)

def format_distance_breakdown(distance: DateDistance) -> str:
    """«۲ سال و ۲ ماه و ۱ روز مانده». Not defined for today."""
    return f"{format_distance_units(distance)} {_distance_status_word(distance)}"

def format_distance_weeks(distance: DateDistance) -> str:
    """«۱۵ هفته و ۲ روز» - the day total as whole weeks plus the remainder.

    Unlike the calendar breakdown this is a fixed conversion (7 days a week),
    so it never depends on the anchor date, and it carries no direction word.
    Callers branch on ``is_today`` first and on ``has_full_weeks`` (under a
    week it would restate the day total).
    """
    weeks, days = divmod(abs(distance.total_days), 7)
    parts = [f"{to_persian_digits(count)} {unit}" for count, unit in
             ((weeks, "هفته"), (days, "روز")) if count]
    return ' و '.join(parts)

def validate_year_range(year: int, min_year: int, max_year: int, is_jalali: bool) -> Optional[str]:
    """Check a year against its allowed range, returning a Persian error message or None."""
    if min_year <= year <= max_year:
        return None
    if is_jalali:
        return f"سال شمسی باید بین {to_persian_digits(min_year)} و {to_persian_digits(max_year)} باشد."
    return f"سال میلادی باید بین {min_year} و {max_year} باشد."

def year_range_hint(min_year: int, max_year: int, persian_digits: bool = True) -> str:
    """The short range message for the year pickers: the red border says
    "wrong", this one shared template names the supported range the same way
    on every surface (the converter's validator above keeps its completed
    sentences, which must name the calendar being rejected). Gregorian
    surfaces pass ``persian_digits=False`` to show the years as typed.
    """
    lo, hi = ((to_persian_digits(min_year), to_persian_digits(max_year))
              if persian_digits else (min_year, max_year))
    return f"سال باید بین {lo} تا {hi} باشد"

def ms_until_midnight(now: datetime.datetime) -> int:
    """Milliseconds from ``now`` local time until the next local midnight.

    Used to schedule the daily rollover; always returns a non-negative value
    (exactly-midnight input schedules the following midnight).
    """
    tomorrow = now + datetime.timedelta(days=1)
    # The midnight carries ``now``'s own tzinfo (a naive constant would raise
    # TypeError against an aware ``now``), and the gap is measured through the
    # epoch: two datetimes sharing one tzinfo subtract as bare wall clocks, so
    # a DST shift inside the window would come out an hour wrong.
    next_midnight = datetime.datetime(tomorrow.year, tomorrow.month, tomorrow.day,
                                      tzinfo=now.tzinfo)
    return max(0, int((next_midnight.timestamp() - now.timestamp()) * 1000))


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

