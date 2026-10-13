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
    """The real wiring: the minute timer's timeout reaches update_tray_icon
    unforced, and an unchanged date ends in its early return - no icon work.
    """
    icons = []
    monkeypatch.setattr(tray, "setIcon", lambda icon: icons.append(icon))

    tray.update_tray_icon(force=True)  # establish the date the tray last drew
    icons.clear()

    tray.minute_timer.timeout.emit()
    assert icons == []  # unchanged date: the tick is a no-op

    # A changed date redraws through the same unpatched path.
    tray._last_tray_date = jdatetime.date.today() - datetime.timedelta(days=1)
    tray.minute_timer.timeout.emit()
    assert len(icons) == 1


def test_time_change_filter_is_inactive_off_windows(qtbot):
    seen = []
    event_filter = TimeChangeEventFilter(lambda: seen.append(1))
    # Non-Windows message streams are ignored; nothing may crash or fire.
    result = event_filter.nativeEventFilter("windows_generic_MSG", None)
    assert result in ((False, 0), False)
    result = event_filter.nativeEventFilter("cocoa_msg_event", None)
    assert result in ((False, 0), False)
    assert seen == []


# --- WM_TIMECHANGE coalescing -------------------------------------------------
#
# Windows broadcasts WM_TIMECHANGE to every top-level window and the time service
# can emit a burst of them while re-syncing. Each message used to cost a full
# refresh (expiry cleanup + calendar rebuild + tray repaint + midnight
# reschedule); a burst now costs exactly one. The coalescing window is patched
# down to 10 ms so these tests stay fast and deterministic.


def _fast_coalesce(monkeypatch):
    import core.app_controller as controller

    monkeypatch.setattr(controller, "TIME_CHANGE_COALESCE_MS", 10)


def test_time_change_burst_coalesces_into_one_refresh(tray, monkeypatch, qtbot):
    """A burst of native messages must cost exactly ONE application refresh."""
    _fast_coalesce(monkeypatch)
    calls = []
    monkeypatch.setattr(tray, "update_tray_icon", lambda force=False: calls.append(force))

    for _ in range(50):
        tray._on_system_time_change()

    assert calls == []                        # nothing ran per message
    assert tray._time_change_messages == 50   # every message was counted

    qtbot.waitUntil(lambda: calls == [True], timeout=2000)
    assert calls == [True]                    # exactly one coalesced refresh
    assert tray._time_change_messages == 0    # counter reset by the refresh


def test_time_change_burst_does_not_touch_the_midnight_timer(tray, monkeypatch):
    """Arming the coalescer must do no refresh work at all (no per-message churn)."""
    _fast_coalesce(monkeypatch)
    calls = []
    monkeypatch.setattr(tray, "update_tray_icon", lambda force=False: calls.append(force))
    before = tray._midnight_timer

    for _ in range(25):
        tray._on_system_time_change()

    assert calls == []
    assert tray._midnight_timer is before  # untouched until the burst settles


def test_single_time_change_is_not_lost_to_the_debounce(tray, monkeypatch, qtbot):
    """A genuine one-off change still refreshes (just after the quiet window)."""
    _fast_coalesce(monkeypatch)
    calls = []
    monkeypatch.setattr(tray, "update_tray_icon", lambda force=False: calls.append(force))

    tray._on_system_time_change()

    qtbot.waitUntil(lambda: calls == [True], timeout=2000)
    assert tray._midnight_timer.isActive()  # rollover still scheduled


def test_time_change_filter_feeds_the_coalescer(tray):
    """The installed filter must feed the coalescer, never the work directly."""
    assert tray.event_filter.on_time_change_callback == tray._on_system_time_change
