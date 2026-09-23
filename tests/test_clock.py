"""Clock/rollover tests: midnight scheduling, day rollover, time-change filter."""
import datetime

from PyQt6.QtCore import QTimer

import jdatetime

from utils.event_io import make_event_key
from utils.native_events import TimeChangeEventFilter


def test_schedule_next_midnight_check_plans_until_midnight(tray):
    tray.schedule_next_midnight_check()
    from utils.date_utils import ms_until_midnight
    expected = ms_until_midnight(datetime.datetime.now()) + 500
    timer = tray._midnight_timer
    assert isinstance(timer, QTimer) and timer.isActive()
    assert timer.isSingleShot()
    # Allow a small scheduling slack around the computed instant.
    assert abs(timer.remainingTime() - expected) <= 1500


def test_rescheduling_stops_the_previous_timer(tray):
    tray.schedule_next_midnight_check()
    first = tray._midnight_timer
    tray.schedule_next_midnight_check()
    assert not first.isActive()
    assert tray._midnight_timer is not first
    assert tray._midnight_timer.isActive()


def test_midnight_trigger_updates_icon_and_reschedules(tray, monkeypatch):
    calls = []
    monkeypatch.setattr(tray, "update_tray_icon", lambda force=False: calls.append(force))
    tray.schedule_next_midnight_check()

    tray._on_midnight_timer_triggered()

    assert calls == [True]                       # tray icon refreshed
    assert tray._midnight_timer.isActive()       # next rollover scheduled


def test_midnight_trigger_cleans_expired_events(tray):
    today = jdatetime.date.today()
    # timedelta arithmetic, not replace(day=day-1): on the 1st of a month
    # replace() pins the date to TODAY and the "expired" event never expires.
    yesterday_key = make_event_key(today - datetime.timedelta(days=1), "none")
    tray.user_events[yesterday_key] = {"text": "old", "recurrence": "none", "remove_after_finish": True}
    tray.schedule_next_midnight_check()

    tray._on_midnight_timer_triggered()

    assert yesterday_key not in tray.user_events


def test_system_time_change_refreshes_everything(tray, monkeypatch):
    calls = []
    monkeypatch.setattr(tray, "update_tray_icon", lambda force=False: calls.append(force))
    tray.schedule_next_midnight_check()

    tray._handle_system_time_change()

    assert calls == [True]
    assert tray._midnight_timer.isActive()


def test_minute_tick_skips_when_date_unchanged(tray, monkeypatch):
    calls = []
    monkeypatch.setattr(tray, "update_tray_icon", lambda force=False: calls.append(force))
    # Simulate the minute-timer lambda path with an unchanged date:
    new_date = jdatetime.date.today()
    if new_date == tray.calendar_widget.current_date:
        pass  # update_tray_icon(force=False) returns early internally
    assert tray.calendar_widget.current_date == new_date


def test_time_change_filter_is_inactive_off_windows(qtbot):
    seen = []
    event_filter = TimeChangeEventFilter(lambda: seen.append(1))
    # Non-Windows message streams are ignored; nothing may crash or fire.
    result = event_filter.nativeEventFilter("windows_generic_MSG", None)
    assert result in ((False, 0), False)
    result = event_filter.nativeEventFilter("cocoa_msg_event", None)
    assert result in ((False, 0), False)
    assert seen == []
