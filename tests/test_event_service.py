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


def test_target_key_prefers_the_exact_day_over_a_clamped_match(service):
    """A clamped month can hold two monthly events whose keys both match the
    visible date - the exact 0000-00-30 and a clamped 0000-00-31. Mapping order
    used to decide, so the edit could land on the clamped key and the cleanup
    evict the exact one; the exact-day anchor must win."""
    service.events["0000-00-31"] = _entry("monthly on the 31st", RECURRENCE_MONTHLY)
    service.events["0000-00-30"] = _entry("monthly on the 30th", RECURRENCE_MONTHLY)
    month_with_30_days = jdatetime.date(1405, 7, 30)  # Mehr has 30 days

    assert service.target_key(month_with_30_days, RECURRENCE_MONTHLY) == "0000-00-30"
    # ... whichever order the two keys sit in the mapping (rebuild reversed).
    original = dict(service.events)
    service.events.clear()
    service.events.update(dict(reversed(list(original.items()))))
    assert list(service.events) == ["0000-00-30", "0000-00-31"]
    assert service.target_key(month_with_30_days, RECURRENCE_MONTHLY) == "0000-00-30"
    assert event_io.make_event_key(month_with_30_days, RECURRENCE_MONTHLY) == "0000-00-30"


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


def test_update_key_refuses_a_destination_that_clamps_onto_an_occupied_key(service):
    """Changing a one-time event on a clamped day into a monthly one used to
    derive a fresh 0000-00-30 key, miss the monthly event that actually
    occupies the shown date through its clamped 0000-00-31 key, and park a
    second monthly entry beside it. The destination resolves through the same
    anchor rule as ``target_key`` now, so the occupancy check sees the real
    neighbour and refuses - exactly as the UI would."""
    service.events["0000-00-31"] = _entry("monthly on the 31st", RECURRENCE_MONTHLY)
    service.events["1405-07-30"] = _entry("one-time")
    shown = jdatetime.date(1405, 7, 30)  # Mehr has 30 days: day 31 clamps to 30

    assert service.update_key("1405-07-30", shown, "edited", RECURRENCE_MONTHLY) is False
    assert service.events["1405-07-30"]["text"] == "one-time"   # untouched
    assert "0000-00-30" not in service.events                   # nothing parked beside

    # With the user's consent the edit folds into the occupied key instead.
    assert service.update_key("1405-07-30", shown, "edited", RECURRENCE_MONTHLY,
                              merge_into="0000-00-31") is True
    assert "1405-07-30" not in service.events
    assert "edited" in service.events["0000-00-31"]["text"]


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


def test_adding_a_one_time_event_keeps_a_recurring_one_on_that_date(service, monkeypatch):
    """Adding is keyed, not date-scoped: a one-time event added on a date that
    already shows a yearly one takes its own key instead of replacing it."""
    monkeypatch.setattr("core.event_service.save_user_events", lambda events: True)
    service.events["0000-12-30"] = _entry("سی ام اسفند", RECURRENCE_YEARLY)

    assert service.add(jdatetime.date(1404, 12, 29), "یک‌بار", RECURRENCE_NONE) is True

    assert service.events == {"1404-12-29": _entry("یک‌بار"),
                              "0000-12-30": _entry("سی ام اسفند", RECURRENCE_YEARLY)}


def test_add_replaces_only_the_same_recurrence_variant(service, monkeypatch):
    monkeypatch.setattr("core.event_service.save_user_events", lambda events: True)
    # A one-time and a yearly event both visible on 1405/08/01.
    service.events["1405-08-01"] = _entry("one-time")
    service.events["0000-08-01"] = _entry("yearly", RECURRENCE_YEARLY)
    assert service.add(jdatetime.date(1405, 8, 1), "new one") is True
    # Only the one-time event is the logical target; the yearly one is a
    # different event that happens to fall on the same date.
    assert service.events == {"1405-08-01": _entry("new one"),
                              "0000-08-01": _entry("yearly", RECURRENCE_YEARLY)}


def test_target_key_reuses_the_same_recurrence_anchor_only(service):
    """The verdict add() acts on, exposed because the event manager adds through
    its own editor and must reach the same one."""
    day = jdatetime.date(1405, 8, 1)
    service.events["1405-08-01"] = _entry("one-time")
    service.events["0000-08-01"] = _entry("yearly", RECURRENCE_YEARLY)
    service.events["0000-00-01"] = _entry("monthly", RECURRENCE_MONTHLY)

    assert service.target_key(day, RECURRENCE_NONE) == "1405-08-01"
    assert service.target_key(day, RECURRENCE_YEARLY) == "0000-08-01"
    assert service.target_key(day, RECURRENCE_MONTHLY) == "0000-00-01"
    # Nothing there yet, so the key is derived from the date itself.
    assert service.target_key(jdatetime.date(1405, 9, 3), RECURRENCE_MONTHLY) == "0000-00-03"


def test_target_key_keeps_a_clamped_monthly_on_its_own_anchor(service):
    """The editor can be opened on a clamped occurrence (a day-31 monthly shown on
    the 30th); the target is still the day-31 event, not a new day-30 anchor."""
    service.events["0000-00-31"] = _entry("monthly", RECURRENCE_MONTHLY)
    assert service.target_key(jdatetime.date(1405, 7, 30), RECURRENCE_MONTHLY) == "0000-00-31"


@pytest.mark.parametrize("first,second", [
    (RECURRENCE_NONE, RECURRENCE_YEARLY),
    (RECURRENCE_NONE, RECURRENCE_MONTHLY),
    (RECURRENCE_YEARLY, RECURRENCE_MONTHLY),
])
def test_two_recurrences_can_coexist_on_one_visible_date(service, monkeypatch, first, second):
    """Events of different recurrences are different logical events: adding the
    second one must never delete the first."""
    monkeypatch.setattr("core.event_service.save_user_events", lambda events: True)
    day = jdatetime.date(1405, 8, 1)
    assert service.add(day, "first", first) is True
    assert service.add(day, "second", second) is True

    assert len(service.events) == 2
    assert set(service.events.keys()) == set(event_io.keys_matching_date(service.events, day))
    assert {entry["text"] for entry in service.events.values()} == {"first", "second"}


def test_adding_the_same_recurrence_twice_replaces_the_single_key(service, monkeypatch):
    monkeypatch.setattr("core.event_service.save_user_events", lambda events: True)
    day = jdatetime.date(1405, 8, 1)
    assert service.add(day, "first", RECURRENCE_MONTHLY) is True
    assert service.add(day, "second", RECURRENCE_MONTHLY) is True
    assert service.events == {"0000-00-01": _entry("second", RECURRENCE_MONTHLY)}


# --- key-scoped edit ---------------------------------------------------------------


def test_update_key_edits_only_the_selected_event(service, monkeypatch):
    """The calendar's per-event menu edits ONE of the events visible on a date;
    the other one must come out untouched."""
    monkeypatch.setattr("core.event_service.save_user_events", lambda events: True)
    service.events["1405-08-01"] = _entry("one-time", remove_after_finish=True)
    service.events["0000-08-01"] = _entry("yearly", RECURRENCE_YEARLY)
    day = jdatetime.date(1405, 8, 1)

    assert service.update_key("0000-08-01", day, "yearly edited", RECURRENCE_YEARLY) is True

    assert service.events == {"1405-08-01": _entry("one-time", remove_after_finish=True),
                              "0000-08-01": _entry("yearly edited", RECURRENCE_YEARLY)}


def test_update_key_keeps_the_key_when_the_recurrence_is_unchanged(service, monkeypatch):
    """Same anchor rule as add(): day 31 exists in only half the months, so an
    edit of the clamped 30th the user was shown must not move the anchor."""
    monkeypatch.setattr("core.event_service.save_user_events", lambda events: True)
    service.events["0000-00-31"] = _entry("پایان ماه", RECURRENCE_MONTHLY)

    assert service.update_key("0000-00-31", jdatetime.date(1404, 7, 30),
                              "پایان ماه ویرایش", RECURRENCE_MONTHLY) is True

    assert list(service.events) == ["0000-00-31"]
    assert service.events["0000-00-31"]["text"] == "پایان ماه ویرایش"


def test_update_key_rekeys_only_itself_on_a_recurrence_change(service, monkeypatch):
    monkeypatch.setattr("core.event_service.save_user_events", lambda events: True)
    service.events["1405-08-01"] = _entry("one-time", remove_after_finish=True)
    service.events["0000-08-01"] = _entry("yearly", RECURRENCE_YEARLY)
    day = jdatetime.date(1405, 8, 1)

    assert service.update_key("1405-08-01", day, "now monthly", RECURRENCE_MONTHLY) is True

    assert service.events == {"0000-00-01": _entry("now monthly", RECURRENCE_MONTHLY),
                              "0000-08-01": _entry("yearly", RECURRENCE_YEARLY)}


def test_update_key_switching_to_one_time_uses_the_shown_date(service, monkeypatch):
    monkeypatch.setattr("core.event_service.save_user_events", lambda events: True)
    service.events["0000-12-30"] = _entry("سی ام اسفند", RECURRENCE_YEARLY)

    assert service.update_key("0000-12-30", jdatetime.date(1404, 12, 29),
                              "یک‌بار", RECURRENCE_NONE) is True

    assert service.events == {"1404-12-29": _entry("یک‌بار")}


def test_update_key_refuses_to_overwrite_an_occupied_key(service, monkeypatch):
    """An edit must never silently destroy a different event: the caller has to
    ask the user and pass merge_into."""
    written = []
    monkeypatch.setattr("core.event_service.save_user_events",
                        lambda events: written.append(dict(events)) or True)
    service.events["1405-08-01"] = _entry("one-time")
    service.events["0000-00-01"] = _entry("monthly", RECURRENCE_MONTHLY)
    day = jdatetime.date(1405, 8, 1)
    snapshot = dict(service.events)

    assert service.update_key("1405-08-01", day, "now monthly", RECURRENCE_MONTHLY) is False

    assert service.events == {"1405-08-01": _entry("one-time"),
                              "0000-00-01": _entry("monthly", RECURRENCE_MONTHLY)}
    # Refused means refused: the edit must not reach the file either, or the
    # next boot would resurrect the change the user declined.
    assert service.events == snapshot
    assert written == []


def test_editing_one_event_leaves_the_other_on_the_date_untouched(service, monkeypatch):
    """A date can carry several events, told apart by key. Editing one must not
    disturb another - not its text, not its flags, not its presence."""
    written = []
    monkeypatch.setattr("core.event_service.save_user_events",
                        lambda events: written.append(dict(events)) or True)
    service.events["1405-08-01"] = _entry("Doctor", remove_after_finish=True)
    service.events["0000-00-01"] = _entry("Pay bills", RECURRENCE_MONTHLY)
    monthly_before = dict(service.events["0000-00-01"])

    assert service.update_key("1405-08-01", jdatetime.date(1405, 8, 1),
                              "Doctor checkup", RECURRENCE_NONE, True) is True

    assert set(service.events) == {"1405-08-01", "0000-00-01"}
    assert service.events["1405-08-01"] == _entry("Doctor checkup", remove_after_finish=True)
    assert service.events["0000-00-01"] == monthly_before
    # Exactly one save for one edit.
    assert len(written) == 1


def test_update_key_merging_folds_the_text_into_the_target(service, monkeypatch):
    """The three outcomes of a confirmed merge, asserted one by one: the edited
    key is gone, the event already on the date is the entry that survives, and
    both texts end up on it."""
    monkeypatch.setattr("core.event_service.save_user_events", lambda events: True)
    service.events["1405-08-01"] = _entry("Doctor", remove_after_finish=True)
    service.events["0000-00-01"] = _entry("Pay bills", RECURRENCE_MONTHLY)
    day = jdatetime.date(1405, 8, 1)

    assert service.update_key("1405-08-01", day, "Doctor", RECURRENCE_MONTHLY,
                              merge_into="0000-00-01") is True

    assert "1405-08-01" not in service.events, "the edited key must be gone"
    assert set(service.events) == {"0000-00-01"}, "the event already there survives"
    assert service.events["0000-00-01"]["text"] == "Pay bills\nDoctor"
    assert service.events["0000-00-01"]["recurrence"] == RECURRENCE_MONTHLY


def test_update_key_merging_never_duplicates_an_identical_line(service, monkeypatch):
    monkeypatch.setattr("core.event_service.save_user_events", lambda events: True)
    service.events["1405-08-01"] = _entry("Doctor")
    service.events["0000-00-01"] = _entry("Pay bills\nDoctor", RECURRENCE_MONTHLY)
    day = jdatetime.date(1405, 8, 1)

    assert service.update_key("1405-08-01", day, "Doctor", RECURRENCE_MONTHLY,
                              merge_into="0000-00-01") is True

    assert service.events["0000-00-01"]["text"] == "Pay bills\nDoctor"


def test_update_key_ignores_unknown_key_and_empty_text(service, monkeypatch):
    monkeypatch.setattr("core.event_service.save_user_events", lambda events: True)
    service.events["1405-08-01"] = _entry("one-time")
    day = jdatetime.date(1405, 8, 1)

    assert service.update_key("0000-01-01", day, "ghost") is False
    assert service.update_key("1405-08-01", day, "   ") is False
    assert service.update_key("1405-08-01", None, "no date") is False
    assert service.events == {"1405-08-01": _entry("one-time")}


def test_update_key_rolls_back_on_save_failure(service, failing_save):
    """One save per edit: a failed write restores the whole store in place, so a
    re-key or a merge can never half-apply."""
    service.events["1405-08-01"] = _entry("one-time")
    service.events["0000-00-01"] = _entry("monthly", RECURRENCE_MONTHLY)
    live_reference = service.events
    snapshot = dict(service.events)

    assert service.update_key("1405-08-01", jdatetime.date(1405, 8, 1), "Doctor",
                              RECURRENCE_MONTHLY, merge_into="0000-00-01") is False

    assert live_reference is service.events, "dict identity must survive a rollback"
    assert live_reference == snapshot


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


def test_commit_inside_the_composition_does_not_reannounce(service, monkeypatch):
    """A commit the running composition makes is announced by that
    composition in flight: before the latch, the ride-along cleanup that
    landed a removal ran the whole refresh twice per user save."""
    monkeypatch.setattr("core.event_service.save_user_events", lambda events: True)
    announcements = []

    def composition():
        announcements.append(1)
        service.clean_expired(notify=False)  # its commit re-enters; swallowed

    service.on_store_changed = composition
    assert service.add(jdatetime.date(1400, 1, 1), "past auto-delete",
                       remove_after_finish=True) is True
    assert announcements == [1]  # once, not one pass nested inside another
    assert service.events == {}  # the past-dated add expired; cleanup still landed


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
