"""Event key-model tests: recurrence keys, date matching, next occurrence, expiry."""
import jdatetime

from utils import event_io
from utils.date_utils import days_in_jalali_month


# --- key construction / parsing ---

def test_make_event_key_encodes_recurrence():
    jdate = jdatetime.date(1404, 5, 5)
    assert event_io.make_event_key(jdate, event_io.RECURRENCE_NONE) == "1404-05-05"
    assert event_io.make_event_key(jdate, event_io.RECURRENCE_YEARLY) == "0000-05-05"
    assert event_io.make_event_key(jdate, event_io.RECURRENCE_MONTHLY) == "0000-00-05"


def test_parse_event_key_roundtrip():
    assert event_io.parse_event_key("1404-05-05") == (1404, 5, 5)
    assert event_io.parse_event_key("0000-05-05") == (None, 5, 5)
    assert event_io.parse_event_key("0000-00-05") == (None, None, 5)


def test_parse_event_key_rejects_garbage():
    assert event_io.parse_event_key("not-a-date") is None
    assert event_io.parse_event_key("1404-13-05") is None   # month 13
    assert event_io.parse_event_key("1404-05-32") is None   # day 32
    assert event_io.parse_event_key("1404-05") is None      # missing part
    assert event_io.parse_event_key("") is None


# --- date matching ---

def test_key_matches_date_all_modes():
    jdate = jdatetime.date(1404, 5, 5)
    assert event_io.key_matches_date("1404-05-05", jdate)
    assert event_io.key_matches_date("0000-05-05", jdate)
    assert event_io.key_matches_date("0000-00-05", jdate)
    # Non-matching anchors:
    assert not event_io.key_matches_date("1404-05-06", jdate)
    assert not event_io.key_matches_date("0000-06-05", jdate)
    assert not event_io.key_matches_date("0000-00-06", jdate)


def test_keys_matching_date_collects_collisions():
    jdate = jdatetime.date(1404, 5, 5)
    events = {
        "1404-05-05": {"text": "a", "recurrence": "none", "remove_after_finish": False},
        "0000-05-05": {"text": "b", "recurrence": "yearly", "remove_after_finish": False},
        "0000-00-05": {"text": "c", "recurrence": "monthly", "remove_after_finish": False},
        "1404-06-06": {"text": "d", "recurrence": "none", "remove_after_finish": False},
    }
    assert sorted(event_io.keys_matching_date(events, jdate)) == ["0000-00-05", "0000-05-05", "1404-05-05"]


def test_events_for_date_priority_specific_then_yearly_then_monthly():
    jdate = jdatetime.date(1404, 5, 5)
    events = {
        "0000-05-05": {"text": "yearly", "recurrence": "yearly", "remove_after_finish": False},
        "0000-00-05": {"text": "monthly", "recurrence": "monthly", "remove_after_finish": False},
    }
    assert event_io.events_for_date(events, jdate)[0] == "0000-05-05"
    del events["0000-05-05"]
    assert event_io.events_for_date(events, jdate)[0] == "0000-00-05"
    del events["0000-00-05"]
    assert event_io.events_for_date(events, jdate) is None


def test_events_for_date_ignores_unparseable_keys():
    events = {"garbage": {"text": "x", "recurrence": "none", "remove_after_finish": False}}
    assert event_io.events_for_date(events, jdatetime.date(1404, 5, 5)) is None


# --- next occurrence ---

def test_next_occurrence_one_time_returns_stored_date_even_in_past():
    assert event_io.next_occurrence_jdate(
        "1400-01-01", today=jdatetime.date(1404, 1, 1)) == jdatetime.date(1400, 1, 1)


def test_next_occurrence_yearly_rolls_forward():
    today = jdatetime.date(1404, 5, 10)
    # Same year when not passed yet:
    assert event_io.next_occurrence_jdate("0000-05-20", today) == jdatetime.date(1404, 5, 20)
    # Next year when already passed:
    assert event_io.next_occurrence_jdate("0000-05-01", today) == jdatetime.date(1405, 5, 1)


def test_next_occurrence_yearly_today_counts_as_today():
    today = jdatetime.date(1404, 5, 5)
    assert event_io.next_occurrence_jdate("0000-05-05", today) == jdatetime.date(1404, 5, 5)


def test_next_occurrence_monthly_rolls_to_next_month():
    today = jdatetime.date(1404, 5, 10)
    assert event_io.next_occurrence_jdate("0000-00-20", today) == jdatetime.date(1404, 5, 20)
    assert event_io.next_occurrence_jdate("0000-00-05", today) == jdatetime.date(1404, 6, 5)


def test_next_occurrence_monthly_wraps_year():
    today = jdatetime.date(1404, 12, 15)
    assert event_io.next_occurrence_jdate("0000-00-05", today) == jdatetime.date(1405, 1, 5)


def test_next_occurrence_monthly_clamps_day_to_month_length():
    today = jdatetime.date(1404, 7, 1)  # target month 7 has 30 days; day 31 clamps to 30
    assert event_io.next_occurrence_jdate("0000-00-31", today) == jdatetime.date(1404, 7, 30)


def test_next_occurrence_yearly_clamps_esfand_30_into_non_leap_years():
    # From a non-leap year (1405, Esfand has 29 days), yearly Esfand 30 clamps
    # to Esfand 29 of that same year when not yet passed.
    today = jdatetime.date(1405, 12, 28)
    assert event_io.next_occurrence_jdate("0000-12-30", today) == jdatetime.date(1405, 12, 29)
    assert days_in_jalali_month(1405, 12) == 29
    # In a leap year (1403) the real 30th still wins.
    today = jdatetime.date(1403, 12, 28)
    assert event_io.next_occurrence_jdate("0000-12-30", today) == jdatetime.date(1403, 12, 30)


# --- ordering ---

def test_events_sorted_by_next_occurrence():
    events = {
        "0000-00-05": {"text": "monthly", "recurrence": "monthly", "remove_after_finish": False},   # 1404/06/05
        "0000-05-20": {"text": "yearly", "recurrence": "yearly", "remove_after_finish": False},     # 1404/05/20
        "1404-05-12": {"text": "soon", "recurrence": "none", "remove_after_finish": False},         # 1404/05/12
        "1400-01-01": {"text": "past", "recurrence": "none", "remove_after_finish": False},         # past: last group
        "broken-key": {"text": "bad", "recurrence": "none", "remove_after_finish": False},          # unparseable: very last
    }
    order = event_io.events_sorted_by_next_occurrence(events, today=jdatetime.date(1404, 5, 10))
    assert order[:3] == ["1404-05-12", "0000-05-20", "0000-00-05"]
    assert order[3] == "1400-01-01"
    assert order[-1] == "broken-key"


# --- expiry (auto-delete) ---

def test_clean_expired_keys_removes_only_past_one_time_auto_delete():
    today = jdatetime.date(1404, 5, 10)
    events = {
        "1404-05-01": {"text": "expired", "recurrence": "none", "remove_after_finish": True},
        "1404-05-10": {"text": "today, not yet expired", "recurrence": "none", "remove_after_finish": True},
        "1404-05-20": {"text": "future", "recurrence": "none", "remove_after_finish": True},
        "1404-05-02": {"text": "past but keep", "recurrence": "none", "remove_after_finish": False},
        "0000-05-01": {"text": "recurring never expires", "recurrence": "yearly", "remove_after_finish": False},
    }
    expired = event_io.clean_expired_keys(events, today)
    assert expired == ["1404-05-01"]


def test_clean_expired_keys_skips_unparseable():
    today = jdatetime.date(1404, 5, 10)
    events = {"bad-key": {"text": "x", "recurrence": "none", "remove_after_finish": True}}
    assert event_io.clean_expired_keys(events, today) == []


def test_clean_expired_keys_empty_store():
    assert event_io.clean_expired_keys({}, jdatetime.date(1404, 5, 10)) == []


# --- recurrence normalization ---

def test_normalize_recurrence():
    assert event_io.normalize_recurrence("none") == "none"
    assert event_io.normalize_recurrence("monthly") == "monthly"
    assert event_io.normalize_recurrence("yearly") == "yearly"
    assert event_io.normalize_recurrence("weekly") == "none"
    assert event_io.normalize_recurrence(None, legacy_yearly=True) == "yearly"
    assert event_io.normalize_recurrence("bogus", legacy_yearly=True) == "yearly"
