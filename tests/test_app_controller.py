"""Tests for core.app_controller: the update-flow orchestration, tray icon
rendering, timers, theme/startup settings and the window lifecycle."""
import datetime

import jdatetime
import pytest
from PyQt6.QtCore import QUrl

import core.app_controller as controller_module
from config import APP_CONFIG
from core.app_controller import (AUTO_CHECK_MAX_RETRIES, AUTO_CHECK_RETRY_DELAY_MS,
                                 DEBUG_DATA_VERSION_ENV, SystemTrayIcon)


# --- helpers ---------------------------------------------------------------------


def _spy(obj, name):
    """Replace a bound method with a recorder; returns (calls, restore)."""
    calls = []
    original = getattr(obj, name)

    def recorder(*args, **kwargs):
        calls.append((args, kwargs))
        return None

    setattr(obj, name, recorder)
    return calls, original


# --- boot & settings ---------------------------------------------------------------


def test_boot_reads_stored_theme(tray):
    assert tray.current_theme in (APP_CONFIG.Theme.DARK, APP_CONFIG.Theme.LIGHT)


def test_boot_detects_dark_theme_off_windows(tray, monkeypatch):
    # On Linux _get_windows_theme cannot touch the registry and defaults to dark.
    assert tray._get_windows_theme() == APP_CONFIG.Theme.DARK


def test_saved_theme_preference_wins(user_data, monkeypatch, qtbot):
    from utils.json_settings import JsonSettings

    settings = JsonSettings(APP_CONFIG.SETTINGS_FILE_PATH)
    settings.setValue(APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY, APP_CONFIG.Theme.LIGHT)
    tray = SystemTrayIcon(settings=settings)
    assert tray.current_theme == APP_CONFIG.Theme.LIGHT
    APP_CONFIG.set_theme(APP_CONFIG.Theme.DARK)  # restore global palette


def test_debug_data_version_override(user_data, monkeypatch, qtbot):
    from utils.json_settings import JsonSettings

    monkeypatch.setenv(DEBUG_DATA_VERSION_ENV, "777")
    tray = SystemTrayIcon(settings=JsonSettings(APP_CONFIG.SETTINGS_FILE_PATH))
    assert tray.update_checker._current_data_version == 777


def test_debug_data_version_invalid_value_is_ignored(user_data, monkeypatch, qtbot):
    from utils.json_settings import JsonSettings

    monkeypatch.setenv(DEBUG_DATA_VERSION_ENV, "not-a-number")
    tray = SystemTrayIcon(settings=JsonSettings(APP_CONFIG.SETTINGS_FILE_PATH))
    assert tray.update_checker._current_data_version != "not-a-number"
    assert isinstance(tray.update_checker._current_data_version, int)


# --- update check scheduling ---------------------------------------------------------


def test_auto_check_disabled_by_setting(tray, monkeypatch):
    tray.settings.setValue(APP_CONFIG.UPDATE_CHECK_ENABLED_SETTING_KEY, False)
    check_calls, _ = _spy(tray.update_checker, "check")
    tray._auto_check_updates()
    assert check_calls == []


def test_auto_check_skipped_within_24h(tray, monkeypatch):
    now_ms = int(datetime.datetime.now().timestamp() * 1000)
    tray.settings.setValue(APP_CONFIG.LAST_UPDATE_CHECK_SETTING_KEY, now_ms)
    check_calls, _ = _spy(tray.update_checker, "check")
    tray._auto_check_updates()
    assert check_calls == []


def test_auto_check_runs_when_last_check_is_old(tray, monkeypatch):
    old_ms = int(datetime.datetime.now().timestamp() * 1000) - 25 * 60 * 60 * 1000
    tray.settings.setValue(APP_CONFIG.LAST_UPDATE_CHECK_SETTING_KEY, old_ms)
    check_calls, _ = _spy(tray.update_checker, "check")
    tray._auto_check_updates()
    assert len(check_calls) == 1


def test_successful_conclusion_stamps_last_check(tray):
    before = int(datetime.datetime.now().timestamp() * 1000)
    tray._on_check_concluded(False)
    stamped = tray.settings.value(APP_CONFIG.LAST_UPDATE_CHECK_SETTING_KEY, 0, type=int)
    assert stamped >= before
    assert tray._auto_check_retries == 0


def test_failed_auto_check_schedules_retry(tray, monkeypatch):
    scheduled = []
    monkeypatch.setattr(controller_module.QTimer, "singleShot",
                        lambda ms, cb: scheduled.append((ms, cb)))
    tray._manual_update_check = False
    tray._auto_check_retries = 0
    tray._on_check_concluded(True)
    assert tray._auto_check_retries == 1
    assert scheduled and scheduled[0][0] == AUTO_CHECK_RETRY_DELAY_MS
    assert scheduled[0][1] == tray._auto_check_updates


def test_failed_manual_check_does_not_retry(tray, monkeypatch):
    scheduled = []
    monkeypatch.setattr(controller_module.QTimer, "singleShot",
                        lambda ms, cb: scheduled.append((ms, cb)))
    tray._manual_update_check = True
    tray._on_check_concluded(True)
    assert tray._auto_check_retries == 0
    assert scheduled == []


def test_retries_stop_at_the_cap(tray, monkeypatch):
    scheduled = []
    monkeypatch.setattr(controller_module.QTimer, "singleShot",
                        lambda ms, cb: scheduled.append((ms, cb)))
    tray._manual_update_check = False
    tray._auto_check_retries = AUTO_CHECK_MAX_RETRIES
    tray._on_check_concluded(True)
    assert tray._auto_check_retries == AUTO_CHECK_MAX_RETRIES  # no increment
    assert scheduled == []


# --- update notification flow --------------------------------------------------------


def test_auto_notification_respects_ignored_version(tray):
    tray._manual_update_check = False
    tray.settings.setValue(APP_CONFIG.IGNORED_UPDATE_VERSION_SETTING_KEY, "9.9.9")
    popup_calls, _ = _spy(tray, "_show_update_popup")
    tray._on_app_update_available("9.9.9", "http://x", "")
    assert popup_calls == []


def test_auto_notification_fires_for_new_version(tray):
    tray._manual_update_check = False
    popup_calls, _ = _spy(tray, "_show_update_popup")
    tray._on_app_update_available("9.9.9", "http://x", "")
    assert len(popup_calls) == 1


def test_manual_notification_ignores_ignored_version(tray):
    tray._manual_update_check = True
    tray.settings.setValue(APP_CONFIG.IGNORED_UPDATE_VERSION_SETTING_KEY, "9.9.9")
    popup_calls, _ = _spy(tray, "_show_update_popup")
    tray._on_app_update_available("9.9.9", "http://x", "")
    assert len(popup_calls) == 1  # a manual check always reports


def test_update_popup_dialog_open_guard(tray, monkeypatch):
    tray._update_dialog_open = True
    chosen = []
    monkeypatch.setattr(controller_module.ConfirmDialog, "choose",
                        staticmethod(lambda *a, **k: chosen.append(a) or None))
    tray._show_update_popup("9.9.9", "http://x", "")
    assert chosen == []  # no second dialog while one is open


def test_update_popup_download_choice(tray, monkeypatch):
    monkeypatch.setattr(controller_module.ConfirmDialog, "choose",
                        staticmethod(lambda *a, **k: "دانلود"))
    download_calls, _ = _spy(tray, "_download_update")
    tray._update_dialog_open = False
    tray._show_update_popup("9.9.9", "http://x", "sha")
    assert download_calls == [(("9.9.9", "http://x", "sha"), {})]


def test_update_popup_ignore_choice_persists(tray, monkeypatch):
    monkeypatch.setattr(controller_module.ConfirmDialog, "choose",
                        staticmethod(lambda *a, **k: "نادیده گرفتن"))
    tray._show_update_popup("9.9.9", "http://x", "")
    assert tray.settings.value(APP_CONFIG.IGNORED_UPDATE_VERSION_SETTING_KEY) == "9.9.9"


def test_update_popup_dismissed_does_nothing(tray, monkeypatch):
    monkeypatch.setattr(controller_module.ConfirmDialog, "choose",
                        staticmethod(lambda *a, **k: None))
    download_calls, _ = _spy(tray, "_download_update")
    tray._show_update_popup("9.9.9", "http://x", "")
    assert download_calls == []
    assert tray.settings.value(APP_CONFIG.IGNORED_UPDATE_VERSION_SETTING_KEY) is None


def test_download_update_wires_dialog_and_installer(tray, monkeypatch):
    """The dialog cancel signal must be wired to cancel_download and the
    installer download must target ShamsiTraySetup-<version>.exe."""
    canceled_slots = []

    class FakeDialog:
        def __init__(self, version, parent=None):
            self.version = version
            self.shown = False
            self.closed = False
            self.canceled = type("Signal", (), {
                "connect": staticmethod(lambda slot: canceled_slots.append(slot))})()

        def show(self):
            self.shown = True

        def close(self):
            self.closed = True

    monkeypatch.setattr(controller_module, "DownloadUpdateDialog", FakeDialog)
    download_calls = []
    monkeypatch.setattr(tray.update_checker, "download_installer",
                        lambda url, dest, sha: download_calls.append((url, dest, sha)))

    tray._download_update("1.4.1", "http://x/installer.exe", "sha")

    assert len(download_calls) == 1
    url, dest, sha = download_calls[0]
    assert dest.name == "ShamsiTraySetup-1.4.1.exe"
    # The Downloads dir is missing in this container; the app falls back to
    # the (temp) user-data dir rather than failing.
    from pathlib import Path

    fallback = dest.parent == Path.home() / "Downloads" or dest.parent == APP_CONFIG.USER_DATA_DIR
    assert fallback
    assert canceled_slots == [tray.update_checker.cancel_download]
    assert tray._download_dialog is not None  # dialog kept for progress updates
    tray._close_download_dialog()
    assert tray._download_dialog is None


def test_download_progress_forwards_to_dialog(tray):
    class FakeDialog:
        def __init__(self):
            self.updates = []

        def set_progress(self, received, total):
            self.updates.append((received, total))

    tray._download_dialog = FakeDialog()
    tray._on_download_progress(25, 100)
    assert tray._download_dialog.updates == [(25, 100)]


def test_installer_downloaded_runs_installer_on_confirm(tray, monkeypatch):
    monkeypatch.setattr(controller_module.ConfirmDialog, "ask",
                        staticmethod(lambda *a, **k: True))
    opened = []
    monkeypatch.setattr(controller_module.QDesktopServices, "openUrl",
                        staticmethod(lambda url: opened.append(url)))
    tray._download_dialog = None
    tray._on_installer_downloaded("/tmp/ShamsiTraySetup-9.9.9.exe")
    assert len(opened) == 1
    assert opened[0].toString().endswith("ShamsiTraySetup-9.9.9.exe")
    assert tray._download_dialog is None


def test_installer_downloaded_deferred_on_decline(tray, monkeypatch):
    monkeypatch.setattr(controller_module.ConfirmDialog, "ask",
                        staticmethod(lambda *a, **k: False))
    opened = []
    monkeypatch.setattr(controller_module.QDesktopServices, "openUrl",
                        staticmethod(lambda url: opened.append(url)))
    tray._on_installer_downloaded("/tmp/installer.exe")
    assert opened == []  # installer NOT launched without consent


def test_download_failed_canceled_is_quiet(tray, monkeypatch):
    monkeypatch.setattr(controller_module.ConfirmDialog, "notify",
                        staticmethod(lambda *a, **k: pytest.fail("must not notify")))
    opened = []
    monkeypatch.setattr(controller_module.QDesktopServices, "openUrl",
                        staticmethod(lambda url: opened.append(url)))
    tray._on_download_failed("canceled")
    assert opened == []


def test_download_failed_shows_error_and_opens_releases(tray, monkeypatch):
    notified = []
    monkeypatch.setattr(controller_module.ConfirmDialog, "notify",
                        staticmethod(lambda *a, **k: notified.append(a)))
    opened = []
    monkeypatch.setattr(controller_module.QDesktopServices, "openUrl",
                        staticmethod(lambda url: opened.append(url)))
    tray._on_download_failed("network exploded")
    assert len(notified) == 1
    assert opened == [QUrl(APP_CONFIG.APP_RELEASES_PAGE_URL)]


def test_holidays_updated_refreshes_calendar_and_tray(tray, monkeypatch):
    set_calls, _ = _spy(tray.calendar_widget, "set_holidays")
    icon_calls, _ = _spy(tray, "update_tray_icon")
    tray._on_holidays_updated()
    assert len(set_calls) == 1
    assert len(icon_calls) == 1
    assert tray.holidays_cache  # re-resolved from the (seeded) store


def test_no_updates_manual_notifies(tray, monkeypatch):
    tray._manual_update_check = True
    notified = []
    monkeypatch.setattr(controller_module.ConfirmDialog, "notify",
                        staticmethod(lambda *a, **k: notified.append(a)))
    tray._on_no_updates()
    assert len(notified) == 1


def test_no_updates_auto_is_silent(tray, monkeypatch):
    tray._manual_update_check = False
    monkeypatch.setattr(controller_module.ConfirmDialog, "notify",
                        staticmethod(lambda *a, **k: pytest.fail("must not notify")))
    tray._on_no_updates()


def test_check_failed_manual_notifies(tray, monkeypatch):
    tray._manual_update_check = True
    notified = []
    monkeypatch.setattr(controller_module.ConfirmDialog, "notify",
                        staticmethod(lambda *a, **k: notified.append(a)))
    tray._on_check_failed("network")
    assert len(notified) == 1


def test_check_failed_auto_is_silent(tray, monkeypatch):
    tray._manual_update_check = False
    monkeypatch.setattr(controller_module.ConfirmDialog, "notify",
                        staticmethod(lambda *a, **k: pytest.fail("must not notify")))
    tray._on_check_failed("network")


# --- tray icon rendering --------------------------------------------------------------


def test_update_tray_icon_force_sets_icon_and_tooltip(tray):
    tray.update_tray_icon(force=True)
    assert not tray.icon().isNull()
    tooltip = tray.toolTip()
    assert tooltip  # weekday + date + Persian month line


def test_update_tray_icon_without_force_skips_same_day(tray):
    tray.update_tray_icon(force=True)
    tray.calendar_widget.current_date = jdatetime.date.today()
    icon_calls, _ = _spy(tray, "setIcon")
    tray.update_tray_icon(force=False)
    assert icon_calls == []


def test_tray_tooltip_includes_user_event(tray):
    today = jdatetime.date.today()
    tray.add_user_event(today, "doctor appointment", "none", False)
    tray.update_tray_icon(force=True)
    assert "doctor appointment" in tray.toolTip()
    assert "رویداد:" in tray.toolTip()
    # cleanup
    tray.remove_user_event(today)


def test_tray_tooltip_includes_holiday_reason(tray, monkeypatch):
    """Pick a real holiday date from the cache; the tooltip lists its reasons."""
    holiday_date, reasons = None, None
    for year, entries in tray.holidays_cache.items():
        for (month, day), texts in entries.items():
            if texts:
                holiday_date = jdatetime.date(year, month, day)
                reasons = texts
                break
        if holiday_date:
            break
    assert holiday_date is not None

    real_today = jdatetime.date.today
    monkeypatch.setattr(controller_module.jdatetime.date, "today",
                        staticmethod(lambda: holiday_date))
    try:
        tray.update_tray_icon(force=True)
    finally:
        monkeypatch.setattr(controller_module.jdatetime.date, "today",
                            staticmethod(real_today))
    tooltip = tray.toolTip()
    assert "تعطیلی:" in tooltip
    assert reasons[0] in tooltip


def test_tray_tooltip_plain_day_has_no_sections(tray, monkeypatch):
    """A day with no event/holiday/friday must not carry special sections."""
    plain = None
    for day in range(1, 28):
        candidate = jdatetime.date(1405, 7, day)
        matched_holiday = tray.holidays_cache.get(1405, {}).get((7, day))
        if not matched_holiday and candidate.weekday() != 6:
            plain = candidate
            break
    assert plain is not None
    real_today = jdatetime.date.today
    monkeypatch.setattr(controller_module.jdatetime.date, "today",
                        staticmethod(lambda: plain))
    try:
        tray.update_tray_icon(force=True)
    finally:
        monkeypatch.setattr(controller_module.jdatetime.date, "today",
                            staticmethod(real_today))
    tooltip = tray.toolTip()
    assert "تعطیلی:" not in tooltip
    assert "رویداد:" not in tooltip


# --- timers & system events ------------------------------------------------------------


def test_midnight_timer_scheduled_and_rescheduled(tray):
    tray.schedule_next_midnight_check()
    assert tray._midnight_timer.isActive()
    assert tray._midnight_timer.isSingleShot()
    first = tray._midnight_timer
    tray.schedule_next_midnight_check()
    assert tray._midnight_timer is not first
    assert not first.isActive()  # the old timer was replaced


def test_midnight_trigger_refreshes_everything(tray):
    go_calls, _ = _spy(tray.calendar_widget, "go_to_today")
    icon_calls, _ = _spy(tray, "update_tray_icon")
    tray._on_midnight_timer_triggered()
    assert len(go_calls) == 1
    assert len(icon_calls) == 1
    assert tray._midnight_timer.isActive()  # next midnight scheduled


def test_system_time_change_refreshes_and_reschedules(tray):
    go_calls, _ = _spy(tray.calendar_widget, "go_to_today")
    icon_calls, _ = _spy(tray, "update_tray_icon")
    tray._handle_system_time_change()
    assert len(go_calls) == 1
    assert len(icon_calls) == 1
    assert tray._midnight_timer.isActive()


def test_minute_timer_exists(tray):
    assert tray.minute_timer.isActive()
    assert tray.minute_timer.interval() == 60 * 1000


# --- theme & startup settings -----------------------------------------------------------


def test_toggle_theme_flips_and_persists(tray):
    original = tray.current_theme
    tray._toggle_theme()
    flipped = tray.current_theme
    assert flipped != original
    assert tray.settings.value(APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY) == flipped
    tray._toggle_theme()  # back
    assert tray.current_theme == original


def test_toggle_open_at_boot_persists_setting(tray, monkeypatch):
    registry_calls = []
    monkeypatch.setattr(tray, "_set_startup_registry",
                        lambda enable: registry_calls.append(enable))
    tray._toggle_open_at_boot(True)
    assert tray.is_open_at_login is True
    assert tray.settings.value(APP_CONFIG.AUTO_START_SETTING_KEY, False, type=bool) is True
    assert registry_calls == [True]
    tray._toggle_open_at_boot(False)


def test_startup_registry_skipped_off_windows(tray):
    # On Linux: logs a warning, does not raise.
    tray._set_startup_registry(True)
    tray._set_startup_registry(False)


def test_validate_startup_setting_early_return_off_windows(tray):
    # is_open_at_login False on Linux default → early return either way.
    tray._validate_and_apply_startup_setting()  # must not raise


# --- windows lifecycle --------------------------------------------------------------------


def test_open_date_converter_reuses_window(tray, qtbot):
    tray._open_date_converter()
    window = tray.converter_window
    qtbot.addWidget(window)
    assert window.isVisible()
    tray._open_date_converter()
    assert tray.converter_window is window  # activated, not recreated
    window.close()


def test_open_date_converter_recreates_after_close(tray, qtbot):
    tray._open_date_converter()
    first = tray.converter_window
    qtbot.addWidget(first)
    first.close()
    tray._open_date_converter()
    qtbot.addWidget(tray.converter_window)
    assert tray.converter_window is not first
    tray.converter_window.close()


def test_open_event_manager_reuses_window(tray, qtbot):
    tray._open_event_manager()
    window = tray.event_manager_window
    qtbot.addWidget(window)
    assert window.isVisible()
    tray._open_event_manager()
    assert tray.event_manager_window is window
    window.close()


def test_open_holiday_viewer_reuses_window(tray, qtbot):
    tray._open_holiday_viewer()
    window = tray.holiday_viewer_window
    qtbot.addWidget(window)
    assert window.isVisible()
    tray._open_holiday_viewer()
    assert tray.holiday_viewer_window is window
    window.close()


def test_refresh_event_manager_when_visible(tray):
    class FakeManager:
        def __init__(self):
            self.refreshed = 0
            self._visible = True

        def isVisible(self):
            return self._visible

        def refresh_list(self):
            self.refreshed += 1

    manager = FakeManager()
    tray.event_manager_window = manager
    tray._refresh_event_manager()
    assert manager.refreshed == 1
    manager._visible = False
    tray._refresh_event_manager()
    assert manager.refreshed == 1  # hidden manager is not refreshed
    tray.event_manager_window = None


def test_events_changed_by_manager_refreshes_calendar(tray):
    set_calls, _ = _spy(tray.calendar_widget, "set_user_events")
    icon_calls, _ = _spy(tray, "update_tray_icon")
    tray._on_events_changed_by_manager()
    assert len(set_calls) == 1
    assert len(icon_calls) == 1


def test_close_menu_then_closes_and_defers(tray, monkeypatch):
    menu = tray.contextMenu()
    closed = []
    monkeypatch.setattr(menu, "close", lambda: closed.append(1))
    scheduled = []
    monkeypatch.setattr(controller_module.QTimer, "singleShot",
                        lambda ms, cb: scheduled.append(cb))
    marker = []
    tray._close_menu_then(lambda: marker.append(1))
    assert closed == [1]
    assert marker == []          # deferred
    scheduled[0]()               # run the deferred callback
    assert marker == [1]


# --- tray activation ------------------------------------------------------------------------


def test_tray_click_shows_hidden_calendar(tray, monkeypatch):
    tray.calendar_widget.hide()
    shown = []
    monkeypatch.setattr(tray, "show_calendar", lambda: shown.append(1))
    from PyQt6.QtWidgets import QSystemTrayIcon

    tray.on_tray_icon_activated(QSystemTrayIcon.ActivationReason.Trigger)
    assert shown == [1]


def test_tray_click_hides_visible_calendar(tray, monkeypatch):
    tray.calendar_widget.show()
    from PyQt6.QtWidgets import QSystemTrayIcon

    tray.on_tray_icon_activated(QSystemTrayIcon.ActivationReason.Trigger)
    assert not tray.calendar_widget.isVisible()


def test_other_activation_reasons_ignored(tray, monkeypatch):
    from PyQt6.QtWidgets import QSystemTrayIcon

    shown = []
    monkeypatch.setattr(tray, "show_calendar", lambda: shown.append(1))
    tray.on_tray_icon_activated(QSystemTrayIcon.ActivationReason.Context)
    assert shown == []


# --- import / export flows -----------------------------------------------------------------


def test_import_events_from_dialog_success(tray, monkeypatch, tmp_path):
    import json

    from utils.event_io import EVENTS_STORE_VERSION

    payload = {"version": EVENTS_STORE_VERSION,
               "events": {"1405-08-01": {"text": "imported", "recurrence": "none",
                                          "remove_after_finish": False}}}
    import_file = tmp_path / "import.json"
    import_file.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(controller_module.QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(import_file), "")))
    boxes = []
    monkeypatch.setattr(controller_module.QMessageBox, "information",
                        staticmethod(lambda *a, **k: boxes.append(a)))

    assert tray.import_events_from_dialog() is True
    assert tray.user_events["1405-08-01"]["text"] == "imported"
    assert boxes  # summary box shown


def test_import_events_from_dialog_canceled(tray, monkeypatch):
    monkeypatch.setattr(controller_module.QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: ("", "")))
    assert tray.import_events_from_dialog() is False


def test_import_events_from_dialog_bad_file(tray, monkeypatch, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("}not json{", encoding="utf-8")
    monkeypatch.setattr(controller_module.QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(bad), "")))
    errors = []
    monkeypatch.setattr(controller_module.QMessageBox, "critical",
                        staticmethod(lambda *a, **k: errors.append(a)))
    assert tray.import_events_from_dialog() is False
    assert errors


def test_export_events_empty_shows_info(tray, monkeypatch):
    tray.user_events = {}
    boxes = []
    monkeypatch.setattr(controller_module.QMessageBox, "information",
                        staticmethod(lambda *a, **k: boxes.append(a)))
    assert tray.export_events_to_dialog() is False
    assert boxes


def test_export_events_success(tray, monkeypatch, tmp_path):
    tray.add_user_event(jdatetime.date(1405, 9, 10), "export me", "none", False)
    out = tmp_path / "out.json"
    monkeypatch.setattr(controller_module.QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(out), "")))
    boxes = []
    monkeypatch.setattr(controller_module.QMessageBox, "information",
                        staticmethod(lambda *a, **k: boxes.append(a)))
    assert tray.export_events_to_dialog() is True
    assert out.exists()
    tray.remove_user_event(jdatetime.date(1405, 9, 10))


def test_export_events_canceled(tray, monkeypatch):
    tray.add_user_event(jdatetime.date(1405, 9, 11), "keep", "none", False)
    monkeypatch.setattr(controller_module.QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: ("", "")))
    assert tray.export_events_to_dialog() is False
    tray.remove_user_event(jdatetime.date(1405, 9, 11))


# --- event add/remove guards -----------------------------------------------------------


def test_add_user_event_rejects_empty_text(tray):
    today = jdatetime.date.today()
    before = dict(tray.user_events)
    tray.add_user_event(today, "   ", "none", False)
    assert tray.user_events == before


def test_add_user_event_rejects_none_date(tray):
    tray.add_user_event(None, "text", "none", False)  # must not raise


def test_remove_user_event_with_no_match_is_safe(tray):
    tray.remove_user_event(jdatetime.date(1500, 1, 1))  # no matching events
