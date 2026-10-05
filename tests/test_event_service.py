"""Tests for core.event_service (EVT-6): the single owner of the event
store — transactional mutations, rollback that preserves dict identity,
and the one-save atomic import (review items #1/#2)."""
import json

import jdatetime
import pytest

from config import APP_CONFIG
from core.event_service import EventService
from utils import event_io
from utils.event_io import RECURRENCE_MONTHLY, RECURRENCE_NONE, RECURRENCE_YEARLY


@pytest.fixture
def service(user_data, monkeypatch):
    """A fresh EventService against the temp user-data dir."""
    return EventService()


@pytest.fixture
def failing_save(monkeypatch):
    """Patch the service module's save_user_events to fail; returns the calls list."""
    calls = []
    monkeypatch.setattr("core.event_service.save_user_events",
                        lambda events: calls.append(dict(events)) and False)
    return calls


def _entry(text, recurrence=RECURRENCE_NONE, remove_after_finish=False):
    return {"text": text, "recurrence": recurrence, "remove_after_finish": remove_after_finish}


# --- load / save plumbing ---------------------------------------------------------


def test_service_loads_store_on_init(service, user_data):
    assert len(service) == 0
    APP_CONFIG.USER_EVENTS_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    APP_CONFIG.USER_EVENTS_FILE_PATH.write_text(
        json.dumps({"version": event_io.EVENTS_STORE_VERSION,
                    "events": {"1405-01-01": _entry("kept")}}), encoding="utf-8")
    service.reload()
    assert service.events["1405-01-01"]["text"] == "kept"


def test_reload_refreshes_the_live_reference_in_place(service, user_data):
    """The calendar widget keeps a live reference to service.events, so a reload
    that REBINDS the dict would leave the calendar reading an object nothing
    mutates again. It must see the new contents through its own reference."""
    APP_CONFIG.USER_EVENTS_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    APP_CONFIG.USER_EVENTS_FILE_PATH.write_text(
        json.dumps({"version": event_io.EVENTS_STORE_VERSION,
                    "events": {"1405-01-01": _entry("from disk")}}), encoding="utf-8")
    live_reference = service.events  # what the calendar widget would hold

    service.reload()

    assert live_reference is service.events, "dict identity must survive a reload"
    assert live_reference["1405-01-01"]["text"] == "from disk"


def test_reload_drops_entries_that_left_the_file(service, user_data, monkeypatch):
    """A reload is a mirror of the file, not an addition to memory: an entry
    only present in the stale dict must not survive."""
    service.events["1405-02-02"] = _entry("gone from disk")
    APP_CONFIG.USER_EVENTS_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    APP_CONFIG.USER_EVENTS_FILE_PATH.write_text(
        json.dumps({"version": event_io.EVENTS_STORE_VERSION,
                    "events": {"1405-01-01": _entry("on disk")}}), encoding="utf-8")
    live_reference = service.events

    service.reload()

    assert live_reference is service.events
    assert set(live_reference) == {"1405-01-01"}


def test_resaving_a_monthly_event_keeps_its_anchor(service, monkeypatch):
    """Day 31 exists in only half the months: re-saving the clamped 30th the
    user was shown must not walk the anchor towards the start of the month."""
    monkeypatch.setattr("core.event_service.save_user_events", lambda events: True)
    service.events["0000-00-31"] = _entry("پایان ماه", RECURRENCE_MONTHLY)

    assert service.add(jdatetime.date(1404, 7, 30), "پایان ماه ویرایش", RECURRENCE_MONTHLY) is True

    assert list(service.events) == ["0000-00-31"]
    assert service.events["0000-00-31"]["text"] == "پایان ماه ویرایش"


def test_resaving_a_yearly_event_keeps_its_anchor(service, monkeypatch):
    """Same rule for 30 Esfand, which only exists in a leap year."""
    monkeypatch.setattr("core.event_service.save_user_events", lambda events: True)
    service.events["0000-12-30"] = _entry("سی ام اسفند", RECURRENCE_YEARLY)

    assert service.add(jdatetime.date(1404, 12, 29), "سی ام اسفند ویرایش", RECURRENCE_YEARLY) is True

    assert list(service.events) == ["0000-12-30"]


def test_switching_a_recurring_event_to_one_time_uses_the_shown_date(service, monkeypatch):
    monkeypatch.setattr("core.event_service.save_user_events", lambda events: True)
    service.events["0000-12-30"] = _entry("سی ام اسفند", RECURRENCE_YEARLY)

    assert service.add(jdatetime.date(1404, 12, 29), "یک‌بار", RECURRENCE_NONE) is True

    assert list(service.events) == ["1404-12-29"]


def test_add_replaces_every_event_matching_the_date(service, monkeypatch):
    monkeypatch.setattr("core.event_service.save_user_events", lambda events: True)
    # A one-time and a yearly event both visible on 1405/08/01.
    service.events["1405-08-01"] = _entry("one-time")
    service.events["0000-08-01"] = _entry("yearly", RECURRENCE_YEARLY)
    assert service.add(jdatetime.date(1405, 8, 1), "new one") is True
    # One event per visible date: both previous variants are gone.
    assert service.events == {"1405-08-01": _entry("new one")}


def test_add_rejects_empty_text_and_none_date(service):
    snapshot = dict(service.events)
    assert service.add(None, "x") is False
    assert service.add(jdatetime.date(1405, 1, 1), "   ") is False
    assert service.events == snapshot


def test_remove_for_date_without_match_is_noop(service):
    assert service.remove_for_date(jdatetime.date(1500, 1, 1)) is False


def test_delete_key_removes_and_persists(service, user_data):
    service.events["1405-01-01"] = _entry("x")
    assert service.delete_key("1405-01-01") is True
    assert service.events == {}
    saved = json.loads(APP_CONFIG.USER_EVENTS_FILE_PATH.read_text(encoding="utf-8"))
    assert saved["events"] == {}


def test_upsert_replaces_old_key_on_move(service, monkeypatch):
    monkeypatch.setattr("core.event_service.save_user_events", lambda events: True)
    service.events["1405-01-01"] = _entry("before move")
    assert service.upsert("1405-02-02", _entry("moved"),
                          replace_keys=["1405-01-01"]) is True
    assert service.events == {"1405-02-02": _entry("moved")}


def test_clean_expired_drops_only_expired(service, monkeypatch):
    monkeypatch.setattr("core.event_service.save_user_events", lambda events: True)
    service.events["1400-01-01"] = _entry("expired", remove_after_finish=True)
    service.events["1400-01-02"] = _entry("expired but kept")  # no auto-delete flag
    service.events["0000-01-01"] = _entry("recurring never expires", RECURRENCE_YEARLY)
    removed = service.clean_expired(notify=False)
    assert removed == ["1400-01-01"]
    assert set(service.events) == {"1400-01-02", "0000-01-01"}


# --- transactional rollback ---------------------------------------------------------


def test_rollback_restores_snapshot_in_place(service, failing_save):
    """The calendar holds a live reference to service.events: a rollback that
    REBINDS the dict would restore the service while the calendar kept reading
    the mutated object. The restore must therefore be in place."""
    service.events["1405-03-01"] = _entry("keep me")
    live_reference = service.events  # what the calendar widget would hold
    snapshot = dict(service.events)

    assert service.add(jdatetime.date(1405, 3, 3), "will fail") is False

    assert service.events == snapshot
    assert live_reference is service.events, "dict identity must survive a rollback"
    assert live_reference == snapshot, "reference holders must see the rollback"
    assert len(failing_save) == 1


def test_rollback_restores_after_delete_failure(service, failing_save):
    service.events["1405-01-01"] = _entry("survivor")
    snapshot = dict(service.events)
    assert service.delete_key("1405-01-01") is False
    assert service.events == snapshot


def test_clean_expired_failure_stays_quiet(service, failing_save):
    fired = []
    service.on_save_error = lambda: fired.append(1)
    service.events["1400-01-01"] = _entry("expired", remove_after_finish=True)
    assert service.clean_expired(notify=False) == []
    assert service.events == {"1400-01-01": _entry("expired", remove_after_finish=True)}
    assert fired == [], "background cleanup must not fire the UI error hook"


def test_interactive_failure_fires_save_error_hook(service, failing_save):
    fired = []
    service.on_save_error = lambda: fired.append(1)
    assert service.add(jdatetime.date(1405, 3, 3), "interactive") is False
    assert fired == [1]


# --- import (EVT-5 + #1/#2) ---------------------------------------------------------


def test_apply_import_is_exactly_one_save(service, monkeypatch, user_data):
    """Review item #2: merge, replaced-event removal and expiry cleanup are
    computed in memory; the resulting complete state is saved EXACTLY ONCE.
    The old flow wrote mid-import (expired cleanup) and again afterwards."""
    real_save = event_io.save_user_events
    saves = []

    def counting_save(events):
        saves.append(dict(events))
        return real_save(events)  # still hit the disk for the end-to-end check

    monkeypatch.setattr("core.event_service.save_user_events", counting_save)
    today = jdatetime.date.today()
    past = today.replace(year=today.year - 5)
    service.events["1400-01-01"] = _entry("existing expired", remove_after_finish=True)
    service.events["1405-06-01"] = _entry("existing keeper")
    imported = {
        "1405-08-01": _entry("imported fresh"),
        # Imported expired auto-delete event: dropped in the same write.
        past.strftime("%Y-%m-%d"): _entry("imported expired", remove_after_finish=True),
    }
    plan = service.plan_import(imported)
    assert service.apply_import(plan) is True
    assert len(saves) == 1, "import must be a single atomic save"
    assert set(saves[0]) == {"1405-06-01", "1405-08-01"}
    assert set(service.events) == set(saves[0])
    # And the disk really got that complete state:
    on_disk = json.loads(APP_CONFIG.USER_EVENTS_FILE_PATH.read_text(encoding="utf-8"))
    assert set(on_disk["events"]) == {"1405-06-01", "1405-08-01"}


def test_apply_import_rolls_back_completely_on_save_failure(service, failing_save):
    service.events["1405-06-01"] = _entry("keeper")
    imported = {"1405-08-01": _entry("imported")}
    plan = service.plan_import(imported)
    assert service.apply_import(plan) is False
    assert service.events == {"1405-06-01": _entry("keeper")}
    # Nothing was written to disk: a half-imported file can never exist.
    assert not APP_CONFIG.USER_EVENTS_FILE_PATH.exists()


def test_plan_import_reports_replaced_existing(service):
    service.events["1405-08-01"] = _entry("existing one-time")
    imported = {"0000-08-01": _entry("imported yearly", RECURRENCE_YEARLY)}
    plan = service.plan_import(imported)
    # Nothing has been mutated by planning:
    assert set(service.events) == {"1405-08-01"}
    assert set(plan.replaced_existing) == {"1405-08-01"}
    assert set(plan.applied) == {"0000-08-01"}


def test_apply_import_removes_shadowed_existing(service, monkeypatch):
    """The import replaces the same-date existing event (exact overwrite or
    cross-representation alike) - the confirm dialog's promise is kept."""
    monkeypatch.setattr("core.event_service.save_user_events", lambda events: True)
    service.events["1405-08-01"] = _entry("existing one-time")
    imported = {"0000-08-01": _entry("imported yearly", RECURRENCE_YEARLY)}
    assert service.apply_import(service.plan_import(imported)) is True
    assert service.events == {"0000-08-01": _entry("imported yearly", RECURRENCE_YEARLY)}


# --- service-level recurrence validation ---------------------------------------


def test_add_rejects_unsupported_recurrence_value(service):
    """'weekly' is not a recurrence mode: it used to fall through key
    generation as a one-time key while the ENTRY said 'weekly' - an
    inconsistent key/entry pair the calendar and manager disagreed on."""
    service.add(jdatetime.date(1405, 4, 4), "gym", "weekly", False)
    assert set(service.events) == {"1405-04-04"}     # one-time key
    entry = service.events["1405-04-04"]
    assert entry["recurrence"] == RECURRENCE_NONE    # entry normalized too
    assert entry["remove_after_finish"] is False


def test_add_still_accepts_every_valid_recurrence(service):
    service.add(jdatetime.date(1405, 4, 4), "once", RECURRENCE_NONE, False)
    service.add(jdatetime.date(1405, 4, 5), "yearly", RECURRENCE_YEARLY, False)
    service.add(jdatetime.date(1405, 4, 6), "monthly", RECURRENCE_MONTHLY, False)
    assert set(service.events) == {"1405-04-04", "0000-04-05", "0000-00-06"}
