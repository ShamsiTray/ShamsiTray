"""Date/calendar utility tests: digits, names, leap years, month lengths, rollover."""
import datetime

import jdatetime
import pytest

from utils.date_utils import (
    DateDistance,
    days_in_gregorian_month,
    days_in_jalali_month,
    describe_date_distance,
    format_distance_breakdown,
    format_distance_total,
    from_persian_digits,
    gregorian_month_name,
    is_gregorian_leap_year,
    is_jalali_leap_year,
    ms_until_midnight,
    persian_month_name,
    persian_weekday_name,
    to_persian_digits,
    validate_year_range,
    _add_jalali_months,
    _add_jalali_years,
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


@pytest.mark.parametrize("bad", [0, 13, -1])
def test_gregorian_month_out_of_range_raises(bad):
    """Month 0 used to fall through to 1 January of the previous year and answer
    31 — a confident answer to a question that has none."""
    with pytest.raises(ValueError):
        days_in_gregorian_month(2024, bad)


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


# --- numeric copy formats (کپی تاریخ submenu) ---

def test_format_jalali_numeric_zero_pads():
    from utils.date_utils import format_jalali_numeric
    assert format_jalali_numeric(jdatetime.date(1405, 7, 1)) == "1405/07/01"
    assert format_jalali_numeric(jdatetime.date(1200, 12, 29)) == "1200/12/29"


def test_format_gregorian_numeric_zero_pads_and_converts():
    from utils.date_utils import format_gregorian_numeric
    assert format_gregorian_numeric(jdatetime.date(1405, 7, 1)) == "2026/09/23"
    gdate = jdatetime.date(1404, 5, 2).togregorian()
    assert format_gregorian_numeric(jdatetime.date(1404, 5, 2)) == \
        f"{gdate.year}/{gdate.month:02d}/{gdate.day:02d}"


# --- date distance (فاصله تا امروز) ---


def test_distance_takes_whole_years_even_when_the_day_clamps():
    """1403 is leap so Esfand 30 exists, but 1405's Esfand stops at 29 - which is
    exactly where two years on lands, so the user reads «۲ سال», not 1 year 11 months."""
    distance = describe_date_distance(jdatetime.date(1405, 12, 29),
                                      today=jdatetime.date(1403, 12, 30))
    assert (distance.years, distance.months, distance.days) == (2, 0, 0)
    assert distance.total_days == 730


def test_distance_takes_whole_months_when_the_day_clamps_down():
    """Shahrivar has 31 days and Mehr 30, so a monthly anchor on 31 lands on 30."""
    distance = describe_date_distance(jdatetime.date(1405, 7, 30),
                                      today=jdatetime.date(1405, 6, 31))
    assert (distance.years, distance.months, distance.days) == (0, 1, 0)
    assert distance.total_days == 30


def test_total_days_is_not_a_conversion_of_the_units():
    """Ten whole years is 3653 days, not 3650 - three leap days fall in the span.
    A fixed-length reading of years/months/days is wrong here, and is the obvious
    'simplification' this decomposition must not be collapsed into."""
    distance = describe_date_distance(jdatetime.date(1405, 1, 1),
                                      today=jdatetime.date(1395, 1, 1))
    assert (distance.years, distance.months, distance.days) == (10, 0, 0)
    assert distance.total_days == 3653
    assert distance.total_days != 365 * distance.years


def test_identical_unit_breakdowns_can_span_different_day_counts():
    """Both gaps are three whole months; one covers 89 days and the other 90,
    because the months involved differ in length. The units alone cannot recover
    the day count."""
    shorter = describe_date_distance(jdatetime.date(1402, 1, 1),
                                     today=jdatetime.date(1401, 10, 1))
    longer = describe_date_distance(jdatetime.date(1405, 11, 1),
                                    today=jdatetime.date(1405, 8, 1))
    assert (shorter.years, shorter.months, shorter.days) == \
           (longer.years, longer.months, longer.days) == (0, 3, 0)
    assert (shorter.total_days, longer.total_days) == (89, 90)


def test_distance_is_signed_by_direction_and_symmetric():
    earlier, later = jdatetime.date(1403, 5, 5), jdatetime.date(1406, 8, 9)
    forward = describe_date_distance(later, today=earlier)
    backward = describe_date_distance(earlier, today=later)
    assert forward.total_days == -backward.total_days
    assert (forward.years, forward.months, forward.days) == \
           (backward.years, backward.months, backward.days)
    assert forward.total_days > 0 and backward.total_days < 0


def test_same_date_is_today_with_no_units():
    today = jdatetime.date(1405, 7, 1)
    distance = describe_date_distance(today, today=today)
    assert distance.is_today
    assert (distance.years, distance.months, distance.days, distance.total_days) == (0, 0, 0, 0)


def test_is_today_agrees_with_the_sign_of_total_days():
    base = jdatetime.date(1405, 7, 1)
    for offset in (-400, -30, -1, 0, 1, 30, 400):
        distance = describe_date_distance(base + datetime.timedelta(days=offset),
                                          today=base)
        assert distance.is_today == (distance.total_days == 0)
        assert distance.total_days == offset
        if offset == 0:
            assert (distance.years, distance.months, distance.days) == (0, 0, 0)


def test_distance_defaults_to_the_real_today():
    today = jdatetime.date.today()
    assert describe_date_distance(today) == describe_date_distance(today, today=today)
    assert describe_date_distance(today + datetime.timedelta(days=1)).total_days == 1


def test_distance_units_are_never_negative():
    base = jdatetime.date(1403, 1, 1)
    for offset in (-500, -45, -1, 1, 45, 500):
        distance = describe_date_distance(base + datetime.timedelta(days=offset),
                                          today=base)
        assert distance.years >= 0 and distance.months >= 0 and distance.days >= 0


def test_distance_reapplying_the_units_lands_exactly_on_the_target():
    """The decomposition is only useful if replaying it reproduces the later date,
    which is what pins the largest-unit-first order and the per-step clamping.
    The replay starts from the earlier of the pair, since that is where the
    units were counted from."""
    today = jdatetime.date(1399, 1, 1)
    for offset in range(-900, 901, 7):
        target = today + datetime.timedelta(days=offset)
        distance = describe_date_distance(target, today=today)
        earlier, later = (today, target) if offset >= 0 else (target, today)
        replayed = _add_jalali_months(_add_jalali_years(earlier, distance.years),
                                      distance.months)
        replayed += datetime.timedelta(days=distance.days)
        assert replayed == later
        assert distance.total_days == offset


@pytest.mark.parametrize("earlier,later,expected_years", [
    (jdatetime.date(1200, 1, 1), jdatetime.date(1600, 12, 29), 400),
    (jdatetime.date(1, 1, 1), jdatetime.date(1600, 12, 29), 1599),
])
def test_distance_survives_the_widest_supported_span(earlier, later, expected_years):
    """The extreme spans the calendar's supported range can produce."""
    distance = describe_date_distance(later, today=earlier)
    assert distance.years == expected_years
    assert distance.total_days == (later - earlier).days
    replayed = _add_jalali_months(_add_jalali_years(earlier, distance.years),
                                  distance.months)
    assert replayed + datetime.timedelta(days=distance.days) == later


def test_distance_formatters_read_as_persian_sentences():
    future = describe_date_distance(jdatetime.date(1406, 5, 10),
                                    today=jdatetime.date(1404, 3, 5))
    past = describe_date_distance(jdatetime.date(1395, 1, 1),
                                  today=jdatetime.date(1405, 1, 1))
    assert format_distance_total(future) == "۷۹۷ روز مانده"
    assert format_distance_breakdown(future) == "۲ سال و ۲ ماه و ۵ روز مانده"
    assert format_distance_total(past) == "۳۶۵۳ روز گذشته"
    assert format_distance_breakdown(past) == "۱۰ سال گذشته"


def test_distance_formatters_agree_on_direction():
    """Both renderers must name the same direction, or the dialog headline and its
    detail line would contradict each other."""
    base = jdatetime.date(1405, 7, 1)
    for offset in (-70, -1, 1, 70):
        distance = describe_date_distance(base + datetime.timedelta(days=offset),
                                          today=base)
        word = "مانده" if offset > 0 else "گذشته"
        assert format_distance_total(distance).endswith(word)
        assert format_distance_breakdown(distance).endswith(word)


def test_distance_breakdown_skips_empty_units():
    distance = describe_date_distance(jdatetime.date(1406, 1, 6),
                                      today=jdatetime.date(1404, 1, 1))
    assert (distance.years, distance.months, distance.days) == (2, 0, 5)
    assert format_distance_breakdown(distance) == "۲ سال و ۵ روز مانده"


def test_distance_is_immutable():
    distance = DateDistance(years=1, months=2, days=3, total_days=400)
    with pytest.raises(Exception):
        distance.years = 2
