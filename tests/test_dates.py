"""Date/calendar utility tests: digits, names, leap years, month lengths, rollover."""
import datetime

import jdatetime
import pytest

from utils.date_utils import (
    days_in_gregorian_month,
    days_in_jalali_month,
    from_persian_digits,
    gregorian_month_name,
    is_gregorian_leap_year,
    is_jalali_leap_year,
    ms_until_midnight,
    persian_month_name,
    persian_weekday_name,
    to_persian_digits,
    validate_year_range,
)


# --- Persian digits ---

def test_digit_conversion_roundtrip():
    assert to_persian_digits("1403/05/05") == "۱۴۰۳/۰۵/۰۵"
    assert from_persian_digits("۱۴۰۳/۰۵/۰۵") == "1403/05/05"
    assert to_persian_digits(from_persian_digits("۱۲۳۴۵")) == "۱۲۳۴۵"


def test_digit_conversion_preserves_non_digits():
    assert to_persian_digits("a1-b2") == "a۱-b۲"
    assert from_persian_digits("a۱-b۲") == "a1-b2"
    assert to_persian_digits(42) == "۴۲"
    assert from_persian_digits("۴۲") == "42"


# --- names ---

def test_month_and_weekday_names():
    assert persian_month_name(1) == "فروردین"
    assert persian_month_name(12) == "اسفند"
    assert gregorian_month_name(1) == "January"
    assert gregorian_month_name(12) == "December"
    assert persian_weekday_name(0) == "شنبه"
    assert persian_weekday_name(6) == "جمعه"


@pytest.mark.parametrize("bad", [0, 13, -1])
def test_month_name_out_of_range_raises(bad):
    with pytest.raises(ValueError):
        persian_month_name(bad)
    with pytest.raises(ValueError):
        gregorian_month_name(bad)


def test_weekday_name_out_of_range_raises():
    for bad in (-1, 7):
        with pytest.raises(ValueError):
            persian_weekday_name(bad)


# --- leap years ---

@pytest.mark.parametrize("year,expected", [
    (2000, True), (2024, True), (2023, False),
    (1900, False),  # century non-400
    (2100, False),
])
def test_gregorian_leap_years(year, expected):
    assert is_gregorian_leap_year(year) is expected


@pytest.mark.parametrize("year,expected", [
    (1387, True), (1391, True), (1395, True), (1399, True),
    (1403, True),  # the current cycle's most recent leap year
    (1400, False), (1401, False), (1402, False), (1404, False),
])
def test_jalali_leap_years(year, expected):
    assert is_jalali_leap_year(year) is expected


def test_jalali_leap_matches_esfand_length():
    # Esfand has 30 days exactly in leap years.
    for year in range(1390, 1420):
        assert is_jalali_leap_year(year) == (days_in_jalali_month(year, 12) == 30)


# --- month lengths ---

def test_jalali_month_lengths():
    for month in range(1, 7):
        assert days_in_jalali_month(1404, month) == 31
    for month in range(7, 12):
        assert days_in_jalali_month(1404, month) == 30
    assert days_in_jalali_month(1404, 12) == 29   # non-leap
    assert days_in_jalali_month(1403, 12) == 30   # leap


@pytest.mark.parametrize("bad", [0, 13])
def test_jalali_month_length_out_of_range_raises(bad):
    with pytest.raises(ValueError):
        days_in_jalali_month(1404, bad)


def test_gregorian_month_lengths():
    assert days_in_gregorian_month(2024, 2) == 29
    assert days_in_gregorian_month(2023, 2) == 28
    assert days_in_gregorian_month(2024, 4) == 30
    assert days_in_gregorian_month(2024, 12) == 31  # December uses the guarded path


# --- year-range validation messages ---

def test_validate_year_range():
    assert validate_year_range(1400, 1, 1600, is_jalali=True) is None
    assert validate_year_range(1601, 1, 1600, is_jalali=True) is not None
    assert "۱۶۰۰" in validate_year_range(1700, 1, 1600, is_jalali=True)
    assert validate_year_range(2000, 623, 2200, is_jalali=False) is None
    message = validate_year_range(300, 623, 2200, is_jalali=False)
    assert "623" in message and "2200" in message


# --- epoch / boundary edge cases ---

def test_jdatetime_boundary_dates_roundtrip():
    # Year 1 in both calendars round-trips through Gregorian without crashing.
    edge = jdatetime.date(1, 1, 1)
    greg = edge.togregorian()
    assert jdatetime.date.fromgregorian(date=greg) == edge


def test_jalali_gregorian_known_conversions():
    assert jdatetime.date(1403, 1, 1).togregorian() == datetime.date(2024, 3, 20)
    assert jdatetime.date.fromgregorian(date=datetime.date(2024, 3, 20)) == jdatetime.date(1403, 1, 1)
    assert jdatetime.date(1404, 1, 1).togregorian() == datetime.date(2025, 3, 21)


def test_last_day_of_month_roundtrip():
    # The last Jalali day of every month maps to a valid Gregorian date and back.
    for year in (1403, 1404):
        for month in range(1, 13):
            last = days_in_jalali_month(year, month)
            jdate = jdatetime.date(year, month, last)
            assert jdatetime.date.fromgregorian(date=jdate.togregorian()) == jdate


def test_weekday_mapping_matches_gregorian():
    # jdatetime weekday: Saturday=0 .. Friday=6; python weekday: Monday=0 .. Sunday=6.
    for offset in range(0, 400, 7):
        jdate = jdatetime.date(1404, 5, 1) + datetime.timedelta(days=offset)
        gdate = jdate.togregorian()
        assert (jdate.weekday() + 5) % 7 == gdate.weekday()


# --- midnight scheduling helper ---

def test_ms_until_midnight_known_points():
    assert ms_until_midnight(datetime.datetime(2025, 1, 1, 23, 59, 59, 500000)) == 500
    assert ms_until_midnight(datetime.datetime(2025, 1, 1, 12, 0, 0)) == 12 * 3600 * 1000
    assert ms_until_midnight(datetime.datetime(2025, 1, 1, 0, 0, 0)) == 24 * 3600 * 1000


def test_ms_until_midnight_across_month_end():
    assert ms_until_midnight(datetime.datetime(2025, 1, 31, 23, 59, 0)) == 60 * 1000
    assert ms_until_midnight(datetime.datetime(2025, 12, 31, 23, 0, 0)) == 3600 * 1000


def test_ms_until_midnight_never_negative():
    value = ms_until_midnight(datetime.datetime(2025, 6, 15, 13, 59, 59, 999999))
    assert value >= 0
