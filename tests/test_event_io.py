import json
import logging

import jdatetime
import pytest

from config import APP_CONFIG
from utils import event_io


@pytest.fixture
def store_path(tmp_path, monkeypatch):
    p = tmp_path / "user_events.json"
    monkeypatch.setattr(APP_CONFIG, "USER_EVENTS_FILE_PATH", p)
    return p


def test_load_missing_file_returns_empty(store_path):
    assert event_io.load_user_events() == {}


def test_save_load_roundtrip(store_path):
    events = {
        "0000-03-21": {"text": "Nowruz", "recurrence": "yearly", "remove_after_finish": False},
        "1405-05-05": {"text": "one-off", "recurrence": "none", "remove_after_finish": True},
    }
    assert event_io.save_user_events(events)
    assert event_io.load_user_events() == events


def test_save_writes_versioned_store(store_path):
    events = {"1405-05-05": {"text": "one-off", "recurrence": "none", "remove_after_finish": True}}
    assert event_io.save_user_events(events)
    raw = json.loads(store_path.read_text(encoding="utf-8"))
    assert raw["version"] == event_io.EVENTS_STORE_VERSION
    assert raw["events"] == events


def test_load_v1_store_auto_migrates_yearly_flag(store_path):
    """A legacy bare-mapping store loads fine and is rewritten as v2 on save."""
    store_path.write_text(json.dumps({
        "0000-03-21": {"text": "Nowruz", "yearly": True, "remove_after_finish": False},
        "1405-05-05": "plain one-off",
    }), encoding="utf-8")
    events = event_io.load_user_events()
    assert events["0000-03-21"] == {"text": "Nowruz", "recurrence": "yearly", "remove_after_finish": False}
    assert events["1405-05-05"] == {"text": "plain one-off", "recurrence": "none", "remove_after_finish": False}
    # Next save upgrades the on-disk format to the versioned envelope.
    assert event_io.save_user_events(events)
    raw = json.loads(store_path.read_text(encoding="utf-8"))
    assert raw["version"] == event_io.EVENTS_STORE_VERSION


def test_recurring_events_never_auto_delete():
    entry = event_io.normalize_event_entry({"text": "anniversary", "yearly": True, "remove_after_finish": True})
    assert entry["recurrence"] == "yearly"
    assert entry["remove_after_finish"] is False


def test_load_corrupt_file_returns_empty(store_path, caplog):
    store_path.write_text("{bad json", encoding="utf-8")
    with caplog.at_level(logging.ERROR):
        assert event_io.load_user_events() == {}
    assert any("unreadable" in r.message for r in caplog.records)


def test_load_skips_malformed_entries_and_migrates_strings(store_path):
    store_path.write_text(json.dumps({
        "1403-01-01": {"text": "ok"},
        "broken": {"no_text": True},
        "junk": 42,
    }), encoding="utf-8")
    events = event_io.load_user_events()
    # 'broken'/'junk' fail entry validation; a key that is not a valid event
    # date (e.g. 'legacy') is rejected too - it used to survive into the
    # store as an event the calendar could never display.
    assert set(events) == {"1403-01-01"}
    assert events["1403-01-01"] == {"text": "ok", "recurrence": "none", "remove_after_finish": False}


def test_load_normalizes_legacy_slash_keys(store_path):
    """Legacy '1403/07/07' keys normalize to the canonical dash form."""
    store_path.write_text(json.dumps({"1403/07/07": {"text": "from legacy"}}), encoding="utf-8")
    events = event_io.load_user_events()
    assert set(events) == {"1403-07-07"}
    # And the normalized event is actually visible to the calendar:
    assert event_io.key_matches_date("1403-07-07", jdatetime.date(1403, 7, 7))


def test_load_rekeys_legacy_yearly_flag_to_wildcard_key(store_path):
    """A v1 'yearly' entry on a specific date becomes a real yearly key.

    Matching runs on the key, expiry on the entry; when the two disagreed,
    a 'yearly' birthday on 1400-01-01 only ever fired in 1400.
    """
    store_path.write_text(json.dumps({"1400-01-01": {"text": "birthday", "yearly": True}}), encoding="utf-8")
    events = event_io.load_user_events()
    assert set(events) == {"0000-01-01"}
    assert events["0000-01-01"]["recurrence"] == "yearly"
    assert event_io.key_matches_date("0000-01-01", jdatetime.date(1407, 1, 1))


def test_key_matches_date_clamps_monthly_day_31_to_shorter_months():
    """EVT-3: matching must agree with next_occurrence_jdate's clamping.

    A monthly event anchored on day 31 used to match by exact day only, so
    the calendar never showed it in 30- or 29-day months even though the
    next-occurrence calculation resolved it there.
    """
    key = event_io.make_event_key(jdatetime.date(1404, 1, 31), event_io.RECURRENCE_MONTHLY)
    assert key == "0000-00-31"
    # Mordad (5) has 31 days: exact match.
    assert event_io.key_matches_date(key, jdatetime.date(1404, 5, 31))
    # Mehr (7) has 30 days: the event fires on the clamped last day.
    assert event_io.key_matches_date(key, jdatetime.date(1404, 7, 30))
    assert not event_io.key_matches_date(key, jdatetime.date(1404, 7, 29))
    # Esfand in a non-leap year has 29 days.
    assert event_io.key_matches_date(key, jdatetime.date(1404, 12, 29))


def test_key_matches_date_clamps_yearly_30_esfand():
    """EVT-3: yearly 30 Esfand fires on 29 Esfand in non-leap years only."""
    key = event_io.make_event_key(jdatetime.date(1403, 12, 30), event_io.RECURRENCE_YEARLY)
    assert key == "0000-12-30"
    assert event_io.key_matches_date(key, jdatetime.date(1403, 12, 30))   # 1403: leap
    # 1404 is not leap, so 1404-12-30 cannot even be constructed; the event
    # fires on the clamped last day instead.
    assert event_io.key_matches_date(key, jdatetime.date(1404, 12, 29))   # clamped
    assert not event_io.key_matches_date(key, jdatetime.date(1404, 12, 28))


def test_key_matches_date_never_clamps_one_time_events():
    """One-time keys are real dates: they must stay exact."""
    key = "1403-12-30"  # a real leap-year date
    assert event_io.key_matches_date(key, jdatetime.date(1403, 12, 30))
    # And it does NOT clamp: a one-time event anchored to leap-30-Esfand
    # never fires in a non-leap year (29 Esfand is not its day).
    assert not event_io.key_matches_date(key, jdatetime.date(1403, 12, 29))
    assert not event_io.key_matches_date(key, jdatetime.date(1404, 12, 29))


def test_next_occurrence_and_matching_agree_on_clamped_days():
    """The Event Manager badge path and the calendar path must agree."""
    key = "0000-00-31"
    today = jdatetime.date(1404, 8, 1)
    next_date = event_io.next_occurrence_jdate(key, today)
    assert next_date == jdatetime.date(1404, 8, 30)
    assert event_io.key_matches_date(key, next_date)


def test_normalize_rejects_empty_text():
    assert event_io.normalize_event_entry({"text": "   "}) is None
    assert event_io.normalize_event_entry(42) is None
    assert event_io.normalize_event_entry("ok") is not None


@pytest.mark.parametrize("value", ["", "   ", "\n\t"])
def test_normalize_rejects_a_blank_legacy_string(value):
    """The oldest store form is a bare string; a blank one is not an event and
    used to load as an unnamed event with an empty title."""
    assert event_io.normalize_event_entry(value) is None


def test_normalize_trims_a_legacy_string():
    assert event_io.normalize_event_entry("  یادداشت  ")["text"] == "یادداشت"


def test_normalize_coerces_unknown_recurrence_to_none():
    entry = event_io.normalize_event_entry({"text": "x", "recurrence": "weekly"})
    assert entry["recurrence"] == "none"


def test_normalize_rekeys_yearly_key_on_monthly_entry():
    """Symmetric reconciliation: the key's recurrence loses to the entry's.

    A yearly key (0000-01-01) carrying a monthly entry used to stay yearly
    because only the specific-key direction was reconciled; matching (key)
    and expiry (entry) could therefore disagree forever.
    """
    events, skipped = event_io.normalize_events_mapping({
        "0000-01-01": {"text": "rent day", "recurrence": "monthly",
                       "remove_after_finish": False},
    })
    assert skipped == 0
    assert set(events) == {"0000-00-01"}
    assert events["0000-00-01"]["recurrence"] == "monthly"
    assert event_io.key_matches_date("0000-00-01", jdatetime.date(1407, 3, 1))
    assert not event_io.key_matches_date("0000-00-01", jdatetime.date(1407, 3, 2))


def test_normalize_reflags_yearly_entry_on_monthly_key():
    """A monthly key carries no month, so a yearly entry cannot be re-keyed
    from it - the entry is re-flagged to the key's recurrence instead."""
    events, skipped = event_io.normalize_events_mapping({
        "0000-00-05": {"text": "anniversary", "recurrence": "yearly",
                       "remove_after_finish": False},
    })
    assert skipped == 0
    assert set(events) == {"0000-00-05"}  # key untouched (no month to anchor)
    entry = events["0000-00-05"]
    assert entry["recurrence"] == "monthly"
    assert entry["remove_after_finish"] is False


def test_normalize_reflags_recurring_key_on_one_time_entry():
    """A wildcard key can never become a one-time key (no year to anchor to),
    so the ENTRY is re-flagged to the key's recurrence instead - key and
    entry must agree in whichever direction is encodable."""
    events, skipped = event_io.normalize_events_mapping({
        "0000-07-07": {"text": "legacy", "recurrence": "none",
                       "remove_after_finish": True},
    })
    assert skipped == 0
    assert set(events) == {"0000-07-07"}  # key untouched
    entry = events["0000-07-07"]
    assert entry["recurrence"] == "yearly"
    assert entry["remove_after_finish"] is False  # recurring never auto-deletes


def test_normalize_agreeing_key_and_entry_stay_untouched():
    events, skipped = event_io.normalize_events_mapping({
        "1405-03-01": {"text": "one-shot", "recurrence": "none",
                       "remove_after_finish": True},
        "0000-01-01": {"text": "nowruz", "recurrence": "yearly",
                       "remove_after_finish": False},
    })
    assert skipped == 0
    assert set(events) == {"1405-03-01", "0000-01-01"}
    assert events["1405-03-01"]["recurrence"] == "none"
    assert events["0000-01-01"]["recurrence"] == "yearly"


def test_save_failure_reports_false(store_path, monkeypatch):
    import os

    def broken_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", broken_replace)
    assert event_io.save_user_events({"k": {"text": "x"}}) is False


def test_export_import_roundtrip(tmp_path):
    events = {"1403-05-05": {"text": "meeting", "recurrence": "none", "remove_after_finish": True}}
    out = tmp_path / "export.json"
    assert event_io.export_events_to_file(events, out)
    imported, skipped = event_io.import_events_from_file(out)
    assert imported == events
    assert skipped == 0


def test_import_counts_malformed_entries(tmp_path):
    p = tmp_path / "import.json"
    p.write_text(json.dumps({
        "a": {"text": "x"},       # key 'a' is not a valid event date -> skipped
        "b": 123,                  # malformed entry -> skipped
        "c": None,                 # malformed entry -> skipped
    }), encoding="utf-8")
    result = event_io.import_events_from_file(p)
    assert result is not None
    imported, skipped = result
    assert imported == {}
    assert skipped == 3


def test_import_unreadable_or_invalid_root_returns_none(tmp_path):
    assert event_io.import_events_from_file(tmp_path / "missing.json") is None
    p = tmp_path / "list.json"
    p.write_text("[1, 2]", encoding="utf-8")
    assert event_io.import_events_from_file(p) is None


def test_save_empty_allowed_after_trusted_empty_load(store_path):
    assert event_io.load_user_events() == {}
    assert event_io.save_user_events({}) is True


def test_save_empty_refused_after_unreadable_load(store_path, caplog):
    store_path.write_text("{bad json", encoding="utf-8")
    with caplog.at_level(logging.CRITICAL):
        assert event_io.load_user_events() == {}
        assert event_io.save_user_events({}) is False
    assert any("Refusing to persist" in r.message for r in caplog.records)
    assert store_path.read_text(encoding="utf-8") == "{bad json"


def test_save_empty_refused_after_foreign_format_load(store_path):
    # A v2 envelope whose payload yields zero trusted events must not be
    # bulldozed with an empty save.
    store_path.write_text(json.dumps({"version": 2, "events": [1, 2]}), encoding="utf-8")
    assert event_io.load_user_events() == {}
    assert event_io.save_user_events({}) is False
    assert json.loads(store_path.read_text(encoding="utf-8"))["version"] == 2


def test_save_nonempty_allowed_even_after_untrusted_load(store_path):
    store_path.write_text("{bad json", encoding="utf-8")
    event_io.load_user_events()
    key = "1405-01-01"
    assert event_io.save_user_events({key: {"text": "x", "recurrence": "none", "remove_after_finish": False}}) is True
    assert event_io.load_user_events()[key]["text"] == "x"


def test_successful_save_heals_trust_flag(store_path):
    """EVT-1: the untrusted-load protection must not stick forever.

    corrupt -> load (untrusted) -> save (heals) -> delete the last event ->
    the resulting EMPTY save must be allowed; previously the stale flag
    refused it forever.
    """
    store_path.write_text("{bad json", encoding="utf-8")
    assert event_io.load_user_events() == {}
    assert event_io.last_load_trusted() is False
    key = "1405-01-01"
    assert event_io.save_user_events({key: {"text": "x", "recurrence": "none", "remove_after_finish": False}})
    assert event_io.last_load_trusted() is True
    # User deletes the last event -> empty store -> must persist now.
    assert event_io.save_user_events({}) is True
    assert event_io.load_user_events() == {}


def test_failed_load_then_successful_reload_allows_empty_save(store_path):
    """GPT's second EVT-1 scenario: a clean reload clears the flag too."""
    store_path.write_text("{bad json", encoding="utf-8")
    assert event_io.load_user_events() == {}
    assert event_io.last_load_trusted() is False
    store_path.unlink()  # back to the clean missing-file state
    assert event_io.load_user_events() == {}
    assert event_io.last_load_trusted() is True
    assert event_io.save_user_events({}) is True


# --- Import reconciliation (EVT-5) ---------------------------------------------


def _entry(text, recurrence="none", remove_after_finish=False):
    return {"text": text, "recurrence": recurrence, "remove_after_finish": remove_after_finish}


def test_keys_share_visible_date_matrix():
    share = event_io.keys_share_visible_date
    # Identical keys always share (trivially).
    assert share("1405-08-01", "1405-08-01") is True
    assert share("0000-08-01", "0000-08-01") is True
    # The reported scenario: one-time 1405-08-01 vs yearly 0000-08-01.
    assert share("1405-08-01", "0000-08-01") is True
    assert share("0000-08-01", "1405-08-01") is True
    # One-time vs yearly on different days/months: never.
    assert share("1405-08-01", "0000-08-02") is False
    assert share("1405-08-01", "0000-09-01") is False
    # One-time vs monthly on the same day-of-month.
    assert share("1405-08-01", "0000-00-01") is True
    assert share("1405-08-01", "0000-00-02") is False
    # Two different one-time keys are two different real dates: never.
    assert share("1405-08-01", "1405-08-02") is False
    assert share("1405-08-01", "1406-08-01") is False
    # Yearly vs yearly: same month/day only (day 1 never clamps).
    assert share("0000-08-01", "0000-09-01") is False
    assert share("0000-08-01", "0000-08-15") is False
    # Monthly day 31 vs monthly day 30: BOTH clamp onto 30-day and 29-day
    # months' last day, so they share dates (e.g. every month 7-12).
    assert share("0000-00-31", "0000-00-30") is True
    # Yearly Esfand 30 clamps onto Esfand 29 in non-leap years: shares with
    # monthly day 29 (and with yearly Esfand 29).
    assert share("0000-12-30", "0000-00-29") is True
    assert share("0000-12-30", "0000-12-29") is True


def test_dedupe_events_by_visible_date_later_wins():
    events = dict([
        ("1405-08-01", _entry("one-time first")),
        ("0000-08-01", _entry("yearly wins", "yearly")),
        ("1405-09-10", _entry("unrelated")),
        ("0000-00-01", _entry("monthly later")),
    ])
    deduped, replaced = event_io.dedupe_events_by_visible_date(events)
    # 1405-08-01 (one-time) and 0000-08-01 (yearly) share 1405/08/01 ->
    # the later yearly entry wins. The monthly day-01 entry then fires on
    # 1405/08/01 too, so it replaces the yearly winner in turn.
    assert "1405-08-01" not in deduped
    assert "0000-08-01" not in deduped
    assert deduped["0000-00-01"]["text"] == "monthly later"
    assert deduped["1405-09-10"]["text"] == "unrelated"
    assert replaced == 2


def test_build_import_plan_counts_exact_and_cross_collisions():
    existing = {
        "1405-08-01": _entry("existing one-time"),
        "0000-09-15": _entry("existing yearly other month", "yearly"),
    }
    imported = {
        # Exact-key overwrite of the existing one-time.
        "1405-08-01": _entry("imported same key"),
        # Exact-key overwrite of the existing yearly (same canonical key).
        "0000-09-15": _entry("imported yearly", "yearly"),
        # Disjoint date: no collision.
        "1406-01-20": _entry("clean import"),
    }
    plan = event_io.build_import_plan(existing, imported)
    assert set(plan.applied) == {"1405-08-01", "0000-09-15", "1406-01-20"}
    assert set(plan.replaced_existing) == {"1405-08-01", "0000-09-15"}
    assert plan.replaced_existing["1405-08-01"]["text"] == "existing one-time"
    assert plan.internal_replaced == 0


def test_build_import_plan_folds_import_internal_collisions():
    existing = {}
    imported = {
        "1405-08-01": _entry("first"),
        "0000-08-01": _entry("second (yearly, same day)", "yearly"),
    }
    plan = event_io.build_import_plan(existing, imported)
    # The two imported entries collide with each other; nothing exists yet.
    assert plan.replaced_existing == {}
    assert plan.internal_replaced == 1
    assert "1405-08-01" not in plan.applied
    assert plan.applied["0000-08-01"]["text"].startswith("second")


def test_build_import_plan_no_collisions():
    existing = {"1405-08-01": _entry("a")}
    imported = {"1406-03-05": _entry("b")}
    plan = event_io.build_import_plan(existing, imported)
    assert plan.replaced_existing == {}
    assert plan.internal_replaced == 0
    assert set(plan.applied) == {"1406-03-05"}
