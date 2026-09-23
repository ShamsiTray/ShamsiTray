"""Tests for core.event_service (EVT-6): the single owner of the event
store — transactional mutations, rollback that preserves dict identity,
and the one-save atomic import (review items #1/#2)."""
import json

import jdatetime
import pytest

from config import APP_CONFIG
from core.event_service import EventService
from utils import event_io
from utils.event_io import RECURRENCE_NONE, RECURRENCE_YEARLY


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
