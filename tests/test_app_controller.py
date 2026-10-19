"""Tests for core.app_controller: the update-flow orchestration, tray icon
rendering, timers, theme/startup settings and the window lifecycle."""
import datetime
import sys

import jdatetime
import pytest
from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtTest import QTest

import core.app_controller as controller_module
import core.event_service as event_service_module
from config import APP_CONFIG
from core.app_controller import (AUTO_CHECK_MAX_RETRIES, AUTO_CHECK_RETRY_DELAY_MS,
                                 DEBUG_DATA_VERSION_ENV, HOLIDAY_RETRY_DELAY_MS,
                                 HOLIDAY_RETRY_MAX_ATTEMPTS, SystemTrayIcon,
                                 TIME_CHANGE_COALESCE_MS)
from ui.widgets.checkbox import IconCheckboxActionWidget


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
    """Off Windows there is no registry to read, so detection falls back to dark
    instead of raising - a verdict that must not depend on the host's own
    personalization, hence the simulated platform."""
    monkeypatch.setattr(sys, "platform", "linux")

    assert tray._get_windows_theme() == APP_CONFIG.Theme.DARK


def test_saved_theme_preference_wins(user_data, monkeypatch, qtbot, fake_startup_registry):
    from utils.json_settings import JsonSettings

    settings = JsonSettings(APP_CONFIG.SETTINGS_FILE_PATH)
    settings.setValue(APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY, APP_CONFIG.Theme.LIGHT)
    tray = SystemTrayIcon(settings=settings, startup_registry=fake_startup_registry)
    assert tray.current_theme == APP_CONFIG.Theme.LIGHT
    APP_CONFIG.set_theme(APP_CONFIG.Theme.DARK)  # restore global palette


def test_boot_warns_when_current_year_has_no_holidays(user_data, monkeypatch, fake_startup_registry):
    """A missing current Jalali year is a silent data cliff: Fridays still
    render red while the official holidays quietly vanish, so boot says so."""
    import logging

    from utils.json_settings import JsonSettings

    monkeypatch.setattr(controller_module, "resolve_holidays_store", lambda: {})
    records = []
    capture = logging.Handler()
    capture.emit = lambda record: records.append(record)
    controller_logger = logging.getLogger("core.app_controller")
    old_level = controller_logger.level
    controller_logger.addHandler(capture)
    controller_logger.setLevel(logging.WARNING)
    try:
        SystemTrayIcon(settings=JsonSettings(APP_CONFIG.SETTINGS_FILE_PATH),
                       startup_registry=fake_startup_registry)
    finally:
        controller_logger.removeHandler(capture)
        controller_logger.setLevel(old_level)
    assert any("No holiday data for the current Jalali year" in r.getMessage()
               for r in records)


def test_debug_data_version_override(user_data, monkeypatch, qtbot, fake_startup_registry):
    from utils.json_settings import JsonSettings

    monkeypatch.setenv(DEBUG_DATA_VERSION_ENV, "777")
    tray = SystemTrayIcon(settings=JsonSettings(APP_CONFIG.SETTINGS_FILE_PATH),
                          startup_registry=fake_startup_registry)
    assert tray.update_checker._current_data_version == 777


def test_debug_data_version_invalid_value_is_ignored(user_data, monkeypatch, qtbot, fake_startup_registry):
    from utils.json_settings import JsonSettings

    monkeypatch.setenv(DEBUG_DATA_VERSION_ENV, "not-a-number")
    tray = SystemTrayIcon(settings=JsonSettings(APP_CONFIG.SETTINGS_FILE_PATH),
                          startup_registry=fake_startup_registry)
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
    tray._on_round_finished(controller_module.APP_STATE_FAILED,
                            controller_module.HOLIDAYS_STATE_CURRENT)
    tray._on_check_concluded(True)
    assert tray._auto_check_retries == 1
    assert scheduled and scheduled[0][0] == AUTO_CHECK_RETRY_DELAY_MS
    assert scheduled[0][1] == tray._auto_check_updates


def test_failed_manual_check_does_not_retry(tray, monkeypatch):
    scheduled = []
    monkeypatch.setattr(controller_module.QTimer, "singleShot",
                        lambda ms, cb: scheduled.append((ms, cb)))
    monkeypatch.setattr(controller_module.ConfirmDialog, "notify",
                        staticmethod(lambda *a, **k: None))  # modal guard
    tray._manual_update_check = True
    tray._on_round_finished(controller_module.APP_STATE_FAILED,
                            controller_module.HOLIDAYS_STATE_CURRENT)
    tray._on_check_concluded(True)  # reads the snapshot, not the live flag
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


def test_auto_notification_fires_for_new_version(tray, qtbot):
    """The popup is deferred out of the checker's signal path (singleShot 0):
    _conclude() must be able to finish its check_concluded bookkeeping while
    nobody is blocking inside a modal dialog."""
    tray._manual_update_check = False
    popup_calls, _ = _spy(tray, "_show_update_popup")
    tray._on_app_update_available("9.9.9", "http://x", "")
    qtbot.waitUntil(lambda: len(popup_calls) == 1, timeout=5000)


def test_manual_notification_ignores_ignored_version(tray, qtbot):
    tray._manual_update_check = True
    tray.settings.setValue(APP_CONFIG.IGNORED_UPDATE_VERSION_SETTING_KEY, "9.9.9")
    popup_calls, _ = _spy(tray, "_show_update_popup")
    tray._on_app_update_available("9.9.9", "http://x", "")
    qtbot.waitUntil(lambda: len(popup_calls) == 1, timeout=5000)  # manual always reports


def test_update_popup_pending_blocks_duplicate_schedule(tray, qtbot):
    """Two app_update_available emissions inside one tick (original round +
    a retry that concluded while the first popup was still pending) must
    produce exactly one dialog."""
    tray._manual_update_check = False
    popup_calls, _ = _spy(tray, "_show_update_popup")
    tray._on_app_update_available("9.9.9", "http://x", "")
    tray._on_app_update_available("9.9.9", "http://x", "")
    qtbot.waitUntil(lambda: len(popup_calls) == 1, timeout=5000)
    qtbot.wait(50)  # allow any (wrongly) scheduled second popup to fire
    assert len(popup_calls) == 1
    tray._update_popup_pending = False  # restore for later tests on this tray


def test_check_failed_quiet_while_update_popup_is_open(tray, monkeypatch):
    """A check failing while the update popup is up must never stack the
    offline dialog on top of the user's decision - the exact bug where
    hitting 'remind later' seemed to summon a 'no internet' error."""
    notified = []
    monkeypatch.setattr(controller_module.ConfirmDialog, "notify",
                        staticmethod(lambda *a, **k: notified.append(a)))
    # The offline dialog now lives in the round matrix, so drive the round
    # itself under each guard the old _on_check_failed code honoured.
    tray._manual_update_check = True  # would normally notify
    tray._update_dialog_open = True
    tray._on_round_finished(controller_module.APP_STATE_FAILED,
                            controller_module.HOLIDAYS_STATE_FAILED)
    tray._update_dialog_open = False
    tray._update_popup_pending = True
    tray._on_round_finished(controller_module.APP_STATE_FAILED,
                            controller_module.HOLIDAYS_STATE_FAILED)
    tray._update_popup_pending = False
    assert notified == []


def test_manual_round_notices_share_the_replacement_key(tray, monkeypatch):
    """Every round report is keyed, so a newer result rewrites the open notice."""
    notified = _notify_recorder(monkeypatch)
    _drive_round(tray, controller_module.APP_STATE_CURRENT,
                 controller_module.HOLIDAYS_STATE_CURRENT)
    assert notified[0][1].get("key") == controller_module.UPDATE_CHECK_NOTICE_KEY


def test_manual_round_notice_yields_to_an_open_update_popup(tray, monkeypatch):
    """The popup outranks the round report: ANY manual verdict that would have
    opened a notice instead raises the open popup and stays silent."""
    notified = _notify_recorder(monkeypatch)

    class _Popup:
        def __init__(self):
            self.raised = 0

        def raise_(self):
            self.raised += 1

        def activateWindow(self):
            pass

    popup = _Popup()
    tray._active_update_popup = popup
    tray._update_dialog_open = True
    for app_state in (controller_module.APP_STATE_UNAVAILABLE,
                      controller_module.APP_STATE_CURRENT,
                      controller_module.APP_STATE_FAILED):
        tray._manual_update_check = True
        tray._on_round_finished(app_state, controller_module.HOLIDAYS_STATE_FAILED)
    tray._update_dialog_open = False
    tray._active_update_popup = None
    assert notified == []
    assert popup.raised == 3  # brought forward once per suppressed notice


def test_manual_round_notice_silent_while_popup_pending(tray, monkeypatch):
    """A popup already scheduled is still a decision the notice must not cover."""
    notified = _notify_recorder(monkeypatch)
    tray._active_update_popup = None
    tray._update_popup_pending = True
    tray._manual_update_check = True
    tray._on_round_finished(controller_module.APP_STATE_CURRENT,
                            controller_module.HOLIDAYS_STATE_CURRENT)
    tray._update_popup_pending = False
    assert notified == []


def test_update_popup_dismisses_open_round_notice(tray, monkeypatch):
    """When the popup takes over, the round notice must not sit underneath it."""
    dismissed = []
    monkeypatch.setattr(controller_module.ConfirmDialog, "dismiss_active_notice",
                        staticmethod(lambda key: dismissed.append(key) or True))
    _answer_update_popup(tray, monkeypatch, None)  # popup is dismissed again
    tray._show_update_popup("9.9.9", "http://x", "")
    assert dismissed == [controller_module.UPDATE_CHECK_NOTICE_KEY]



    tray._update_dialog_open = True
    chosen = []
    monkeypatch.setattr(controller_module.ConfirmDialog, "choose",
                        staticmethod(lambda *a, **k: chosen.append(a) or None))
    tray._show_update_popup("9.9.9", "http://x", "")
    assert chosen == []  # no second dialog while one is open


def _answer_update_popup(tray, monkeypatch, choice):
    """Build the popup's dialog path without a modal loop: exec_centered is the
    shared present-tail the popup ends with."""
    def fake_exec_centered(self, parent=None):
        self.choice = choice
        return 0

    monkeypatch.setattr(controller_module.ConfirmDialog, "exec_centered", fake_exec_centered)


def test_update_popup_download_choice(tray, monkeypatch):
    _answer_update_popup(tray, monkeypatch, "دانلود")
    download_calls, _ = _spy(tray, "_download_update")
    tray._update_dialog_open = False
    tray._show_update_popup("9.9.9", "http://x", "sha")
    assert download_calls == [(("9.9.9", "http://x", "sha"), {})]


def test_update_popup_ignore_choice_persists(tray, monkeypatch):
    _answer_update_popup(tray, monkeypatch, "نادیده گرفتن")
    tray._show_update_popup("9.9.9", "http://x", "")
    assert tray.settings.value(APP_CONFIG.IGNORED_UPDATE_VERSION_SETTING_KEY) == "9.9.9"


def test_update_popup_dismissed_does_nothing(tray, monkeypatch):
    _answer_update_popup(tray, monkeypatch, None)
    download_calls, _ = _spy(tray, "_download_update")
    tray._show_update_popup("9.9.9", "http://x", "")
    assert download_calls == []
    assert tray.settings.value(APP_CONFIG.IGNORED_UPDATE_VERSION_SETTING_KEY) is None


def test_update_popup_keeps_a_reference_while_it_runs(tray, monkeypatch):
    """The reference is what lets a manual arrival RAISE the open popup instead
    of dropping the result silently; it is cleared in the finally block."""
    captured = {}

    def fake_exec_centered(self, parent=None):
        captured["dialog"] = tray._active_update_popup
        self.choice = None
        return 0

    monkeypatch.setattr(controller_module.ConfirmDialog, "exec_centered", fake_exec_centered)
    tray._show_update_popup("9.9.9", "http://x", "")
    assert captured["dialog"] is not None
    assert tray._active_update_popup is None  # released after the round


def test_manual_offer_while_popup_open_raises_it(tray):
    """A manual result arriving while the popup is up must not be dropped -
    the existing dialog is raised instead of re-offered."""

    class FakePopup:
        def __init__(self):
            self.raise_calls = 0
            self.activate_calls = 0

        def raise_(self):
            self.raise_calls += 1

        def activateWindow(self):
            self.activate_calls += 1

    existing = FakePopup()
    tray._active_update_popup = existing
    tray._update_dialog_open = True
    tray._manual_update_check = True
    tray._on_app_update_available("9.9.9", "http://x", "")
    assert existing.raise_calls == 1
    assert existing.activate_calls == 1
    tray._update_dialog_open = False
    tray._active_update_popup = None
    tray._manual_update_check = False


def _capture_popup_dialog(tray, monkeypatch):
    """Build the popup without a modal loop; returns the dialog it constructed."""
    captured = {}

    def fake_exec_centered(self, parent=None):
        captured["dialog"] = self
        self.choice = None
        return 0

    monkeypatch.setattr(controller_module.ConfirmDialog, "exec_centered", fake_exec_centered)
    tray._show_update_popup("9.9.9", "http://x", "")
    return captured["dialog"]


def test_manual_popup_with_holiday_refresh_carries_extra_line(tray, monkeypatch):
    """The popup gains one extra line when the same manual round refreshed
    the holiday file - the report covers the whole round."""
    tray._round_was_manual = True
    tray._round_holidays_state = controller_module.HOLIDAYS_STATE_UPDATED
    dialog = _capture_popup_dialog(tray, monkeypatch)
    assert dialog.detail_label.text() == "فایل تعطیلات نیز به‌روزرسانی شد."


def test_auto_popup_without_holiday_refresh_has_no_extra_line(tray, monkeypatch):
    tray._round_was_manual = False
    tray._round_holidays_state = controller_module.HOLIDAYS_STATE_UPDATED
    dialog = _capture_popup_dialog(tray, monkeypatch)
    assert dialog.detail_label.text() == ""


def test_download_update_wires_dialog_and_installer(tray, monkeypatch):
    """The dialog cancel signal must be wired to cancel_download and the
    installer download must target ShamsiTraySetup-<version>.exe."""
    canceled_slots = []

    class FakeDialog:
        def __init__(self, version, parent=None):
            self.version = version
            self.shown = False
            self.dismissed = False
            self.canceled = type("Signal", (), {
                "connect": staticmethod(lambda slot: canceled_slots.append(slot))})()

        def show(self):
            self.shown = True

        def dismiss(self):
            self.dismissed = True

    monkeypatch.setattr(controller_module, "DownloadUpdateDialog", FakeDialog)
    download_calls = []
    monkeypatch.setattr(tray.update_checker, "download_installer",
                        lambda url, dest, sha: download_calls.append((url, dest, sha)) or True)

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


def test_download_failed_shows_error_without_opening_releases(tray, monkeypatch):
    """UPD-8: the failure notice is themed and informative; no browser opens."""
    notified = []
    monkeypatch.setattr(controller_module.ConfirmDialog, "notify",
                        staticmethod(lambda *a, **k: notified.append(a)))
    opened = []
    monkeypatch.setattr(controller_module.QDesktopServices, "openUrl",
                        staticmethod(lambda url: opened.append(url)))
    tray._on_download_failed("network exploded")
    assert len(notified) == 1
    assert opened == []  # the release page is no longer auto-opened


def test_holidays_updated_refreshes_calendar_and_tray(tray, monkeypatch):
    set_calls, _ = _spy(tray.calendar_widget, "set_holidays")
    icon_calls, _ = _spy(tray, "update_tray_icon")
    tray._on_holidays_updated()
    assert len(set_calls) == 1
    assert len(icon_calls) == 1
    assert tray.holidays_cache  # re-resolved from the (seeded) store


def _notify_recorder(monkeypatch):
    notified = []
    monkeypatch.setattr(controller_module.ConfirmDialog, "notify",
                        staticmethod(lambda *a, **k: notified.append((a, k))))
    return notified


def _notice(notified):
    """First notify() body: (parent, title, message, **kw)."""
    return notified[0][0][2]


def _drive_round(tray, app_state, holidays_state, manual=True):
    """End one round exactly as the checker does: round_finished, then the
    conclusion signal."""
    tray._manual_update_check = manual
    tray._on_round_finished(app_state, holidays_state)
    tray._on_check_concluded(app_state in (controller_module.APP_STATE_FAILED,
                                           controller_module.APP_STATE_UNAVAILABLE))


def test_manual_round_current_updated_notifies_holiday_refresh(tray, monkeypatch):
    notified = _notify_recorder(monkeypatch)
    _drive_round(tray, controller_module.APP_STATE_CURRENT,
                 controller_module.HOLIDAYS_STATE_UPDATED)
    assert len(notified) == 1
    assert "فایل تعطیلات به‌روزرسانی شد." in _notice(notified)


def test_manual_round_current_current_reports_both_current(tray, monkeypatch):
    notified = _notify_recorder(monkeypatch)
    _drive_round(tray, controller_module.APP_STATE_CURRENT,
                 controller_module.HOLIDAYS_STATE_CURRENT)
    assert len(notified) == 1
    assert "برنامه و فایل تعطیلات بروز است." in _notice(notified)


def test_manual_round_current_failed_says_holiday_check_failed(tray, monkeypatch):
    """The false "up to date": a failed holiday fetch must not be reported as
    the app AND holiday file being current."""
    notified = _notify_recorder(monkeypatch)
    _drive_round(tray, controller_module.APP_STATE_CURRENT,
                 controller_module.HOLIDAYS_STATE_FAILED)
    assert len(notified) == 1
    assert "بررسی فایل تعطیلات ناموفق بود" in _notice(notified)


def test_manual_round_unavailable_says_download_impossible(tray, monkeypatch):
    notified = _notify_recorder(monkeypatch)
    _drive_round(tray, controller_module.APP_STATE_UNAVAILABLE,
                 controller_module.HOLIDAYS_STATE_CURRENT)
    assert len(notified) == 1
    assert "دانلود امن آن ممکن نیست" in _notice(notified)
    assert notified[0][1].get("danger") is True


def test_manual_round_failed_updated_reports_both_halves(tray, monkeypatch):
    notified = _notify_recorder(monkeypatch)
    _drive_round(tray, controller_module.APP_STATE_FAILED,
                 controller_module.HOLIDAYS_STATE_UPDATED)
    assert len(notified) == 1
    assert "فایل تعطیلات به‌روزرسانی شد، اما بررسی برنامه ناموفق بود." in _notice(notified)


def test_manual_round_failed_failed_keeps_the_offline_dialog(tray, monkeypatch):
    notified = _notify_recorder(monkeypatch)
    _drive_round(tray, controller_module.APP_STATE_FAILED,
                 controller_module.HOLIDAYS_STATE_FAILED)
    assert len(notified) == 1
    assert "اینترنت را بررسی کنید" in _notice(notified)


def test_automatic_round_is_silent_whatever_happens(tray, monkeypatch):
    notified = _notify_recorder(monkeypatch)
    for holidays in (controller_module.HOLIDAYS_STATE_UPDATED,
                     controller_module.HOLIDAYS_STATE_CURRENT,
                     controller_module.HOLIDAYS_STATE_FAILED):
        _drive_round(tray, controller_module.APP_STATE_CURRENT, holidays, manual=False)
    assert notified == []


def test_update_found_round_defers_to_the_popup(tray, monkeypatch):
    """The popup itself carries the report - the round must not message twice."""
    notified = _notify_recorder(monkeypatch)
    _drive_round(tray, controller_module.APP_STATE_UPDATE_FOUND,
                 controller_module.HOLIDAYS_STATE_UPDATED)
    assert notified == []


def test_skipped_round_never_messages(tray, monkeypatch):
    """A quiet holidays-only refresh is background traffic: no report, ever."""
    notified = _notify_recorder(monkeypatch)
    _drive_round(tray, controller_module.APP_STATE_SKIPPED,
                 controller_module.HOLIDAYS_STATE_FAILED)
    assert notified == []


def test_manual_press_behind_a_quiet_refresh_is_queued_then_runs(tray, monkeypatch):
    """Pressing «بررسی بروزرسانی» during the holidays-only refresh must not be
    swallowed: the full check starts (and is flagged manual) the moment the
    refresh concludes."""
    monkeypatch.setattr(type(tray.update_checker), "round_kind",
                        property(lambda self: "holidays"))
    monkeypatch.setattr(tray.update_checker, "check", lambda: False)
    tray._manual_update_check = False
    tray._check_for_updates(manual=True)
    assert tray._manual_update_check is False       # never marked manual
    assert tray._queued_full_check_after_holidays is True
    # The busy round is over: the queued press now starts a full round.
    monkeypatch.setattr(type(tray.update_checker), "round_kind",
                        property(lambda self: "full"))
    monkeypatch.setattr(tray.update_checker, "check", lambda: True)
    tray._on_round_finished(controller_module.APP_STATE_SKIPPED,
                            controller_module.HOLIDAYS_STATE_CURRENT)
    assert tray._queued_full_check_after_holidays is False
    assert tray._manual_update_check is True        # the queued press is honoured


def test_press_during_a_full_round_marks_that_round_manual(tray, monkeypatch):
    """The first minute after launch used to be a dead click: the scheduled
    round was running, so the press did nothing and the button looked broken."""
    monkeypatch.setattr(type(tray.update_checker), "round_kind",
                        property(lambda self: "full"))
    monkeypatch.setattr(tray.update_checker, "check", lambda: False)
    tray._manual_update_check = False
    tray._check_for_updates(manual=True)
    assert tray._manual_update_check is True


def test_no_updates_auto_is_silent(tray, monkeypatch):
    monkeypatch.setattr(controller_module.ConfirmDialog, "notify",
                        staticmethod(lambda *a, **k: pytest.fail("must not notify")))
    tray._on_no_updates()


def test_check_failed_auto_is_silent(tray, monkeypatch):
    monkeypatch.setattr(controller_module.ConfirmDialog, "notify",
                        staticmethod(lambda *a, **k: pytest.fail("must not notify")))
    tray._on_check_failed("network")


def test_manual_check_flag_not_set_when_check_is_noop(tray, monkeypatch):
    """An AUTO call landing on a no-op check() must never flag the in-flight
    round as manual - a silent round would then report like a pressed one."""
    monkeypatch.setattr(tray.update_checker, "check", lambda: False)
    tray._manual_update_check = False
    tray._check_for_updates(manual=False)
    assert tray._manual_update_check is False


# --- quiet holiday retry and round bookkeeping --------------------------------------


def _capture_single_shots(monkeypatch):
    """Record (ms, callback) instead of arming real timers; the rounds under
    test schedule their retries through QTimer.singleShot."""
    scheduled = []
    monkeypatch.setattr(controller_module.QTimer, "singleShot",
                        lambda ms, cb: scheduled.append((ms, cb)))
    return scheduled


def test_round_finished_holiday_failure_schedules_quiet_retry(tray, monkeypatch):
    """A failed holiday fetch arms its own quiet retry (holidays only - it
    never re-runs the app check, re-pops the popup or stamps)."""
    scheduled = _capture_single_shots(monkeypatch)
    tray._manual_update_check = False
    tray._holiday_retries = 0
    tray._on_round_finished(controller_module.APP_STATE_CURRENT,
                            controller_module.HOLIDAYS_STATE_FAILED)
    assert tray._holiday_retries == 1
    assert scheduled and scheduled[0][0] == HOLIDAY_RETRY_DELAY_MS
    assert scheduled[0][1] == tray._retry_holiday_check


def test_holiday_retry_cap_is_respected(tray, monkeypatch):
    scheduled = _capture_single_shots(monkeypatch)
    tray._manual_update_check = False
    tray._holiday_retries = HOLIDAY_RETRY_MAX_ATTEMPTS
    tray._on_round_finished(controller_module.APP_STATE_FAILED,
                            controller_module.HOLIDAYS_STATE_FAILED)
    assert tray._holiday_retries == HOLIDAY_RETRY_MAX_ATTEMPTS
    assert scheduled == []


def test_holiday_retry_not_armed_after_manual_round(tray, monkeypatch):
    """The user already saw the «ناموفق بود» message and can press again; no
    quiet retry runs behind their back."""
    scheduled = _capture_single_shots(monkeypatch)
    notified = _notify_recorder(monkeypatch)
    tray._manual_update_check = True
    tray._holiday_retries = 0
    tray._on_round_finished(controller_module.APP_STATE_CURRENT,
                            controller_module.HOLIDAYS_STATE_FAILED)
    assert tray._holiday_retries == 0
    assert scheduled == []
    assert len(notified) == 1  # the failure was reported as usual


def test_holiday_retry_success_resets_counter(tray, monkeypatch):
    _capture_single_shots(monkeypatch)
    tray._holiday_retries = 2
    tray._on_round_finished(controller_module.APP_STATE_SKIPPED,
                            controller_module.HOLIDAYS_STATE_UPDATED)
    assert tray._holiday_retries == 0


def test_holiday_retry_suppressed_when_auto_check_disabled(tray, monkeypatch):
    """The quiet retry is background network traffic - a user who switched
    «بررسی خودکار بروزرسانی» off must not get up to three retries per session
    behind their back."""
    scheduled = _capture_single_shots(monkeypatch)
    tray.settings.setValue(APP_CONFIG.UPDATE_CHECK_ENABLED_SETTING_KEY, False)
    tray._manual_update_check = False
    tray._holiday_retries = 0
    tray._on_round_finished(controller_module.APP_STATE_SKIPPED,
                            controller_module.HOLIDAYS_STATE_FAILED)
    assert tray._holiday_retries == 0
    assert scheduled == []


def test_retry_holiday_check_dropped_when_auto_check_disabled(tray, monkeypatch):
    """A retry armed BEFORE the toggle changed is dropped when it fires,
    instead of firing background traffic anyway."""
    tray.settings.setValue(APP_CONFIG.UPDATE_CHECK_ENABLED_SETTING_KEY, False)
    calls, _ = _spy(tray.update_checker, "check_holidays")
    tray._retry_holiday_check()
    assert calls == []


def test_retry_holiday_check_starts_a_holidays_only_round(tray):
    calls, _ = _spy(tray.update_checker, "check_holidays")
    tray._retry_holiday_check()
    assert len(calls) == 1


def test_skipped_round_without_queued_manual_starts_nothing(tray):
    """The quiet refresh only releases a queued full check when a manual press
    actually queued one; ordinary retry rounds end without side effects."""
    check_calls, _ = _spy(tray.update_checker, "check")
    tray._on_round_finished(controller_module.APP_STATE_SKIPPED,
                            controller_module.HOLIDAYS_STATE_UPDATED)
    assert check_calls == []


def test_unavailable_round_never_stamps_last_check(tray, monkeypatch):
    """An UNAVAILABLE round concludes as failed for bookkeeping: no clean
    «last checked» stamp, so the release is re-checked instead of waiting out
    the 24h gate."""
    scheduled = _capture_single_shots(monkeypatch)
    tray._auto_check_retries = 0
    _drive_round(tray, controller_module.APP_STATE_UNAVAILABLE,
                 controller_module.HOLIDAYS_STATE_CURRENT, manual=False)
    stamped = tray.settings.value(APP_CONFIG.LAST_UPDATE_CHECK_SETTING_KEY, 0, type=int)
    assert stamped == 0
    assert tray._auto_check_retries == 1  # bounded retry, like a failed round
    assert scheduled and scheduled[0][0] == AUTO_CHECK_RETRY_DELAY_MS


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


def test_tray_date_is_logged_not_blank(tray):
    """jdatetime renders itself as "" under an empty format spec, so the refresh
    used to log «new date: » with nothing after it — once a minute, forever.

    The record is captured on the module logger itself, the way the other
    logging tests in the suite do, instead of filtering every logger's output
    by message text.
    """
    import logging

    messages = []

    class Capture(logging.Handler):
        def emit(self, record):
            messages.append(record.getMessage())

    module_logger = logging.getLogger("core.app_controller")
    capture = Capture()
    module_logger.addHandler(capture)
    try:
        tray.update_tray_icon(force=True)
    finally:
        module_logger.removeHandler(capture)

    logged = [m for m in messages if "Updating tray icon for new date" in m]
    assert logged
    assert all(m.rstrip().endswith(str(jdatetime.date.today())) for m in logged)


def test_tray_tooltip_includes_user_event(tray):
    today = jdatetime.date.today()
    tray.add_user_event(today, "doctor appointment", "none", False)
    tray.update_tray_icon(force=True)
    assert "doctor appointment" in tray.toolTip()
    assert "رویداد:" in tray.toolTip()
    # cleanup
    tray.remove_user_event(today)


def test_tray_tooltip_lists_every_event_on_the_day(tray):
    """A one-time and a monthly event on the same date are both listed.

    Only the priority winner used to be shown, so the monthly one looked absent
    even though it was stored and editable."""
    today = jdatetime.date.today()
    # Two adds of DIFFERENT recurrences on one date: they coexist, which is the
    # case the tooltip has to survive.
    tray.add_user_event(today, "doctor appointment", "none", False)
    tray.add_user_event(today, "monthly bill", "monthly", False)
    tray.update_tray_icon(force=True)
    tooltip = tray.toolTip()
    assert "doctor appointment" in tooltip
    assert "monthly bill" in tooltip
    assert "رویدادها:" in tooltip


def test_tray_tooltip_stays_singular_for_one_event(tray):
    """The plural header is for 2+ only; a single event keeps «رویداد:»."""
    today = jdatetime.date.today()
    tray.add_user_event(today, "lunch", "none", False)
    tray.update_tray_icon(force=True)
    tooltip = tray.toolTip()
    assert "رویداد:" in tooltip
    assert "رویدادها:" not in tooltip


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


def test_theme_cycle_advances_and_persists(tray, monkeypatch):
    """The theme row advances the persisted three-valued choice; two presses
    land on the opposite pin, a third returns to following the system.

    Detection is stubbed to light rather than read from the host: the stop
    before the last one is dark, so landing on light proves that "system"
    re-detected instead of staying on the pin it came from.
    """
    monkeypatch.setattr(tray, "_get_windows_theme",
                        lambda: APP_CONFIG.Theme.LIGHT, raising=True)
    monkeypatch.setattr(tray, "_apply_theme", lambda: None)
    key = APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY

    tray._cycle_theme_choice()   # system -> light
    assert tray.current_theme == APP_CONFIG.Theme.LIGHT
    assert tray.settings.value(key) == APP_CONFIG.Theme.LIGHT
    tray._cycle_theme_choice()   # light -> dark
    assert tray.current_theme == APP_CONFIG.Theme.DARK
    assert tray.settings.value(key) == APP_CONFIG.Theme.DARK
    tray._cycle_theme_choice()   # dark -> system, re-detected as light
    assert tray.current_theme == APP_CONFIG.Theme.LIGHT
    assert tray.settings.value(key) == APP_CONFIG.Theme.SYSTEM


def test_theme_cycle_persists_every_stop_and_returns_to_system(tray, monkeypatch):
    """The row cycles system → light → dark → system, saving each stop
    explicitly - «هماهنگ با سیستم» is reachable again after any pin."""
    monkeypatch.setattr(tray, "_get_windows_theme",
                        lambda: APP_CONFIG.Theme.LIGHT, raising=True)
    applied = []
    monkeypatch.setattr(tray, "_apply_theme", lambda: applied.append(1))
    key = APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY

    tray._cycle_theme_choice()
    assert tray.settings.value(key) == APP_CONFIG.Theme.LIGHT
    assert tray.current_theme == APP_CONFIG.Theme.LIGHT
    assert tray._theme_choice() == APP_CONFIG.Theme.LIGHT
    tray._cycle_theme_choice()
    assert tray.settings.value(key) == APP_CONFIG.Theme.DARK
    assert tray.current_theme == APP_CONFIG.Theme.DARK
    tray._cycle_theme_choice()
    # Back on "system": the choice is persisted explicitly and the theme is
    # re-detected (LIGHT here), not stuck on the last pin.
    assert tray.settings.value(key) == APP_CONFIG.Theme.SYSTEM
    assert tray._theme_choice() == APP_CONFIG.Theme.SYSTEM
    assert tray.current_theme == APP_CONFIG.Theme.LIGHT
    assert len(applied) == 3


def test_theme_follows_system_when_no_preference_saved(tray, monkeypatch):
    monkeypatch.setattr(controller_module.sys, "platform", "win32")
    monkeypatch.setattr(tray, "_get_windows_theme",
                        lambda: APP_CONFIG.Theme.LIGHT, raising=True)
    applied = []
    monkeypatch.setattr(tray, "_apply_theme", lambda: applied.append(1))
    tray.current_theme = APP_CONFIG.Theme.DARK
    # Fresh boot: no Appearance/ThemeChoice saved yet.
    assert not tray.settings.contains(APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY)

    tray._handle_system_theme_change()

    assert tray.current_theme == APP_CONFIG.Theme.LIGHT
    assert applied == [1]


def test_theme_follow_ignores_saved_user_choice(tray, monkeypatch):
    monkeypatch.setattr(controller_module.sys, "platform", "win32")
    monkeypatch.setattr(tray, "_get_windows_theme",
                        lambda: APP_CONFIG.Theme.LIGHT, raising=True)
    applied = []
    monkeypatch.setattr(tray, "_apply_theme", lambda: applied.append(1))
    tray.current_theme = APP_CONFIG.Theme.DARK
    tray.settings.setValue(APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY, APP_CONFIG.Theme.DARK)

    tray._handle_system_theme_change()

    assert tray.current_theme == APP_CONFIG.Theme.DARK
    assert applied == []


def test_theme_follow_ignores_same_theme(tray, monkeypatch):
    monkeypatch.setattr(controller_module.sys, "platform", "win32")
    monkeypatch.setattr(tray, "_get_windows_theme",
                        lambda: APP_CONFIG.Theme.DARK, raising=True)
    applied = []
    monkeypatch.setattr(tray, "_apply_theme", lambda: applied.append(1))
    tray.current_theme = APP_CONFIG.Theme.DARK
    tray.settings._data.pop(APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY, None)

    tray._handle_system_theme_change()

    assert applied == []


def test_setting_change_debounces_only_the_theme_broadcast(tray, monkeypatch):
    started = []
    monkeypatch.setattr(tray._theme_change_timer, "start",
                        lambda ms: started.append(ms), raising=True)
    tray._on_system_setting_change("Environment")
    assert started == []
    tray._on_system_setting_change("ImmersiveColorSet")
    assert started == [TIME_CHANGE_COALESCE_MS]


def test_explicit_system_choice_still_follows_windows(tray, monkeypatch):
    """An explicit «هماهنگ با سیستم» value keeps following Windows - only a
    pinned light/dark choice stops the broadcast from applying."""
    monkeypatch.setattr(controller_module.sys, "platform", "win32")
    monkeypatch.setattr(tray, "_get_windows_theme",
                        lambda: APP_CONFIG.Theme.LIGHT, raising=True)
    applied = []
    monkeypatch.setattr(tray, "_apply_theme", lambda: applied.append(1))
    tray.current_theme = APP_CONFIG.Theme.DARK
    tray.settings.setValue(APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY, APP_CONFIG.Theme.SYSTEM)

    tray._handle_system_theme_change()

    assert tray.current_theme == APP_CONFIG.Theme.LIGHT
    assert applied == [1]


def test_saved_theme_preference_wins_over_cycle_detection(tray):
    """A user pinned by the old two-way toggle keeps the pin on boot."""
    tray.settings.setValue(APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY, APP_CONFIG.Theme.DARK)
    assert tray._theme_choice() == APP_CONFIG.Theme.DARK


def test_unknown_saved_theme_value_falls_back_to_system(tray):
    tray.settings.setValue(APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY, "sepia")
    assert tray._theme_choice() == APP_CONFIG.Theme.SYSTEM


def test_toggle_open_at_boot_persists_setting(tray, fake_startup_registry, monkeypatch):
    """Enabling writes the Run entry and only then persists the preference."""
    _patch_windows(monkeypatch)
    tray.settings.setValue(APP_CONFIG.AUTO_START_SETTING_KEY, False)
    tray.is_open_at_login = False
    fake_startup_registry.reset()  # the boot's first-run write is not under test

    tray._toggle_open_at_boot(True)

    assert tray.is_open_at_login is True
    assert tray.settings.value(APP_CONFIG.AUTO_START_SETTING_KEY, False, type=bool) is True
    assert fake_startup_registry.writes == [controller_module._startup_executable_value()]
    assert fake_startup_registry.entry_exists is True


def test_toggle_open_at_boot_failure_keeps_setting(tray, fake_startup_registry, monkeypatch):
    """WIN-2: a failed registry write must not flip the application setting."""
    _patch_windows(monkeypatch)
    # Explicit preconditions: booting the tray persists the first-run autostart
    # default whenever the temp settings file starts empty, so neither the stored
    # preference nor the Run entry is guaranteed to be empty by the time the test
    # runs. This test is about what the TOGGLE writes, not what the boot left.
    tray.settings.setValue(APP_CONFIG.AUTO_START_SETTING_KEY, False)
    tray.is_open_at_login = False
    fake_startup_registry.value = None
    fake_startup_registry.reset()
    fake_startup_registry.fail_writes = True

    tray._toggle_open_at_boot(True)

    assert tray.is_open_at_login is False
    assert tray.settings.value(APP_CONFIG.AUTO_START_SETTING_KEY, False, type=bool) is False
    assert fake_startup_registry.entry_exists is False


def test_toggle_open_at_boot_delete_failure_keeps_setting_on(tray, fake_startup_registry, monkeypatch):
    """A failed delete must leave the preference ON, so the checkbox never claims
    a startup state that Windows does not actually have."""
    _patch_windows(monkeypatch)
    fake_startup_registry.value = controller_module._startup_executable_value()
    fake_startup_registry.reset()
    tray.settings.setValue(APP_CONFIG.AUTO_START_SETTING_KEY, True)
    tray.is_open_at_login = True
    fake_startup_registry.fail_deletes = True

    tray._toggle_open_at_boot(False)

    assert tray.is_open_at_login is True
    assert tray.settings.value(APP_CONFIG.AUTO_START_SETTING_KEY, False, type=bool) is True
    assert fake_startup_registry.entry_exists is True


def test_startup_registry_skipped_off_windows(tray, fake_startup_registry, monkeypatch):
    """The platform guard must short-circuit before any registry access.

    sys.platform is forced rather than assumed, so this exercises the real guard
    on every OS - including the Windows dev boxes where it used to fall through
    to the live registry.
    """
    fake_startup_registry.reset()  # ignore the boot's own first-run write
    monkeypatch.setattr(controller_module.sys, "platform", "linux")

    assert tray._set_startup_registry(True) is False
    assert tray._set_startup_registry(False) is False

    assert fake_startup_registry.writes == []
    assert fake_startup_registry.deletes == 0
    assert fake_startup_registry.reads == 0


def test_validate_startup_setting_early_return_off_windows(tray, fake_startup_registry, monkeypatch):
    """Off Windows the whole validation is skipped, with no registry access."""
    fake_startup_registry.reset()
    monkeypatch.setattr(controller_module.sys, "platform", "linux")

    tray._validate_and_apply_startup_setting()  # must not raise

    assert fake_startup_registry.reads == 0


# --- autostart opt-out default (fresh install = ON) --------------------------------------

def _boot_tray(user_data, settings_overrides=None, registry=None):
    """Boot a tray with a fresh (or pre-seeded) settings store.

    Always boots against an in-memory autostart registry: the boot runs the real
    ``_validate_and_apply_startup_setting()`` path, which would otherwise write to
    the developer's real HKCU Run key whenever the platform guard is faked.
    """
    from tests.fake_registry import FakeStartupRegistry
    from utils.json_settings import JsonSettings

    settings = JsonSettings(APP_CONFIG.SETTINGS_FILE_PATH)
    for key, value in (settings_overrides or {}).items():
        settings.setValue(key, value)
    return SystemTrayIcon(
        settings=settings,
        startup_registry=registry if registry is not None else FakeStartupRegistry())


def _patch_windows(monkeypatch):
    """Fake the win32 platform guard so the Windows autostart path runs on any OS.

    The registry behind it is the in-memory fake, so faking the platform can
    never reach the developer's real hive.
    """
    monkeypatch.setattr(controller_module.sys, "platform", "win32")


def _executable_value():
    return controller_module._startup_executable_value()


def test_fresh_install_defaults_autostart_on(user_data, qtbot, monkeypatch, fake_startup_registry):
    """Test A — brand-new install: no saved preference → Run entry written
    first, preference persisted ON, checkbox state ON."""
    _patch_windows(monkeypatch)

    tray = _boot_tray(user_data, registry=fake_startup_registry)

    assert tray._autostart_pref_exists is False
    assert fake_startup_registry.writes == [_executable_value()]
    assert fake_startup_registry.entry_exists is True
    assert tray.is_open_at_login is True
    assert tray.settings.value(APP_CONFIG.AUTO_START_SETTING_KEY, False, type=bool) is True


def test_fresh_install_registry_failure_leaves_preference_unset(user_data, qtbot, monkeypatch, fake_startup_registry):
    """Test D — a failed registry write must not produce a false success:
    the preference stays unset (next launch retries) and the in-memory state
    is honestly OFF so the checkbox can never claim a startup Windows won't do."""
    _patch_windows(monkeypatch)
    fake_startup_registry.fail_writes = True

    tray = _boot_tray(user_data, registry=fake_startup_registry)

    assert tray.is_open_at_login is False
    assert not tray.settings.contains(APP_CONFIG.AUTO_START_SETTING_KEY)
    assert fake_startup_registry.entry_exists is False


def test_existing_disabled_preference_stays_off(user_data, qtbot, monkeypatch, fake_startup_registry):
    """Test E — an explicit OFF must survive the opt-out default untouched."""
    _patch_windows(monkeypatch)

    tray = _boot_tray(user_data, {APP_CONFIG.AUTO_START_SETTING_KEY: False},
                      registry=fake_startup_registry)

    assert tray._autostart_pref_exists is True
    assert tray.is_open_at_login is False
    # No Run entry, so nothing to heal and nothing to write.
    assert fake_startup_registry.writes == []
    assert fake_startup_registry.deletes == 0


def test_existing_disabled_preference_heals_stale_run_entry(user_data, qtbot, monkeypatch, fake_startup_registry):
    """Test E (self-heal) — a leftover Run entry despite an OFF preference is
    removed; the OFF preference is never re-enabled."""
    _patch_windows(monkeypatch)
    fake_startup_registry.value = _executable_value()  # stale entry

    tray = _boot_tray(user_data, {APP_CONFIG.AUTO_START_SETTING_KEY: False},
                      registry=fake_startup_registry)

    assert tray.is_open_at_login is False
    assert fake_startup_registry.deletes == 1
    assert fake_startup_registry.entry_exists is False
    assert fake_startup_registry.writes == []  # only a delete - never a re-enable
    assert tray.settings.value(APP_CONFIG.AUTO_START_SETTING_KEY, True, type=bool) is False


def test_existing_enabled_preference_reapplies_missing_entry(user_data, qtbot, monkeypatch, fake_startup_registry):
    """Existing ON with the Run entry gone (e.g. wiped externally) is repaired."""
    _patch_windows(monkeypatch)
    fake_startup_registry.value = None  # entry missing

    tray = _boot_tray(user_data, {APP_CONFIG.AUTO_START_SETTING_KEY: True},
                      registry=fake_startup_registry)

    assert tray.is_open_at_login is True
    assert fake_startup_registry.writes == [_executable_value()]


def test_existing_enabled_preference_with_correct_entry_is_left_alone(user_data, qtbot, monkeypatch, fake_startup_registry):
    """Existing ON with the Run entry already correct: no registry writes."""
    _patch_windows(monkeypatch)
    fake_startup_registry.value = _executable_value()

    tray = _boot_tray(user_data, {APP_CONFIG.AUTO_START_SETTING_KEY: True},
                      registry=fake_startup_registry)

    assert tray.is_open_at_login is True
    assert fake_startup_registry.writes == []
    assert fake_startup_registry.deletes == 0


def test_existing_enabled_preference_with_drifted_entry_is_repaired(user_data, qtbot, monkeypatch, fake_startup_registry):
    """Existing ON whose Run value points somewhere else is re-applied."""
    _patch_windows(monkeypatch)
    fake_startup_registry.value = '"C:\\Elsewhere\\Other.exe"'

    tray = _boot_tray(user_data, {APP_CONFIG.AUTO_START_SETTING_KEY: True},
                      registry=fake_startup_registry)

    assert tray.is_open_at_login is True
    assert fake_startup_registry.writes == [_executable_value()]
    assert fake_startup_registry.read() == _executable_value()


def test_toggle_then_restart_keeps_disabled_state(user_data, qtbot, monkeypatch, fake_startup_registry):
    """Test B/C — disable via the toggle, then reboot: the preference must
    persist and the boot path must keep it OFF (never re-default it)."""
    _patch_windows(monkeypatch)
    fake_startup_registry.value = _executable_value()

    tray = _boot_tray(user_data, registry=fake_startup_registry)
    assert tray.is_open_at_login is True  # first run defaulted it ON

    tray._toggle_open_at_boot(False)
    assert fake_startup_registry.entry_exists is False
    assert tray.settings.value(APP_CONFIG.AUTO_START_SETTING_KEY, True, type=bool) is False

    writes_before_reboot = list(fake_startup_registry.writes)
    rebooted = _boot_tray(user_data, registry=fake_startup_registry)

    assert rebooted.is_open_at_login is False
    assert fake_startup_registry.writes == writes_before_reboot  # no re-default write


# --- startup executable value ----------------------------------------------------------


def test_startup_executable_value_is_absolute_and_quoted():
    from pathlib import Path

    value = controller_module._startup_executable_value()
    assert value.startswith('"') and value.endswith('"')
    assert Path(value[1:-1]).is_absolute()


def test_startup_executable_value_frozen_uses_executable(monkeypatch):
    monkeypatch.setattr(controller_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(controller_module.sys, "executable", r"C:\Program Files\ShamsiTray\ShamsiTray.exe")
    assert controller_module._startup_executable_value() == '"C:\\Program Files\\ShamsiTray\\ShamsiTray.exe"'


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


def test_open_restores_a_minimized_window(tray, qtbot):
    """A minimized tool window still reports visible, so re-opening it must
    restore it instead of leaving it in the taskbar."""
    tray._open_event_manager()
    window = tray.event_manager_window
    qtbot.addWidget(window)
    window.showMinimized()
    tray._open_event_manager()
    assert not (window.windowState() & Qt.WindowState.WindowMinimized)
    assert window.isVisible()
    window.close()


def test_open_activates_a_background_window(tray, qtbot, monkeypatch):
    """Opening a window that is already up re-raises and re-activates it
    instead of doing nothing (the offscreen platform cannot observe real
    focus, so the opener's calls are spied)."""
    tray._open_holiday_viewer()
    window = tray.holiday_viewer_window
    qtbot.addWidget(window)
    calls = []
    monkeypatch.setattr(window, "raise_", lambda: calls.append("raise"))
    monkeypatch.setattr(window, "activateWindow", lambda: calls.append("activate"))
    tray._open_holiday_viewer()
    assert calls == ["raise", "activate"]
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


# --- always-on-top toggle -------------------------------------------------------------------

def test_calendar_is_pinned_by_default(tray):
    assert tray.always_on_top is True
    assert tray.calendar_widget.windowFlags() & Qt.WindowType.WindowStaysOnTopHint


def test_toggle_always_on_top_applies_and_persists(tray):
    tray._toggle_always_on_top(False)
    assert tray.always_on_top is False
    assert not tray.calendar_widget.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert tray.settings.value(APP_CONFIG.ALWAYS_ON_TOP_SETTING_KEY, None, type=bool) is False

    tray._toggle_always_on_top(True)
    assert tray.calendar_widget.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert tray.settings.value(APP_CONFIG.ALWAYS_ON_TOP_SETTING_KEY, None, type=bool) is True


def test_saved_unpinned_preference_applies_on_boot(user_data, qtbot, fake_startup_registry):
    from utils.json_settings import JsonSettings

    settings = JsonSettings(APP_CONFIG.SETTINGS_FILE_PATH)
    settings.setValue(APP_CONFIG.ALWAYS_ON_TOP_SETTING_KEY, False)
    tray = SystemTrayIcon(settings=settings, startup_registry=fake_startup_registry)

    assert tray.always_on_top is False
    assert not tray.calendar_widget.windowFlags() & Qt.WindowType.WindowStaysOnTopHint


def _always_on_top_widget(tray):
    menu = tray.contextMenu()
    return next(w for w in menu.findChildren(IconCheckboxActionWidget)
                if w.text_label.text() == "تقویم همیشه در بالا")


def test_menu_row_shows_the_current_state(tray):
    assert _always_on_top_widget(tray).isChecked() is True

    tray._toggle_always_on_top(False)
    tray._setup_context_menu()

    assert _always_on_top_widget(tray).isChecked() is False


def test_clicking_the_menu_row_unpins_the_calendar(tray):
    widget = _always_on_top_widget(tray)
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton)

    assert tray.always_on_top is False
    assert tray.settings.value(APP_CONFIG.ALWAYS_ON_TOP_SETTING_KEY, None, type=bool) is False
    assert not tray.calendar_widget.windowFlags() & Qt.WindowType.WindowStaysOnTopHint


# --- auto-update-check toggle row --------------------------------------------------


_AUTO_CHECK_ROW_TEXT = "بررسی خودکار بروزرسانی"


def _auto_check_widget(tray):
    menu = tray.contextMenu()
    return next(w for w in menu.findChildren(IconCheckboxActionWidget)
                if w.text_label.text() == _AUTO_CHECK_ROW_TEXT)


def test_menu_has_the_auto_check_toggle_row(tray):
    widgets = [w for w in tray.contextMenu().findChildren(IconCheckboxActionWidget)
               if w.text_label.text() == _AUTO_CHECK_ROW_TEXT]
    assert len(widgets) == 1
    assert widgets[0].isChecked() is True  # default when never set


def test_menu_auto_check_row_reflects_disabled_preference(tray):
    tray.settings.setValue(APP_CONFIG.UPDATE_CHECK_ENABLED_SETTING_KEY, False)
    tray._setup_context_menu()
    assert _auto_check_widget(tray).isChecked() is False


def test_clicking_the_menu_row_disables_auto_check(tray):
    tray._setup_context_menu()
    widget = _auto_check_widget(tray)
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
    assert tray.settings.value(APP_CONFIG.UPDATE_CHECK_ENABLED_SETTING_KEY, True, type=bool) is False


def test_auto_check_toggle_persists_check_enabled(tray):
    assert tray._auto_check_enabled() is True  # default when never set
    tray._toggle_auto_update_check(False)
    assert tray.settings.value(APP_CONFIG.UPDATE_CHECK_ENABLED_SETTING_KEY, True, type=bool) is False
    assert tray._auto_check_enabled() is False
    tray._toggle_auto_update_check(True)
    assert tray._auto_check_enabled() is True


def test_auto_check_timer_is_recurring_and_hourly(tray):
    """The daily gate is re-asked by an hourly timer, so a machine that sleeps
    instead of rebooting still checks again after launch."""
    timer = tray._auto_check_timer
    assert timer.isActive()
    assert not timer.isSingleShot()
    assert timer.interval() == 60 * 60 * 1000


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


def test_tray_click_completes_a_just_dismissed_popup(tray, monkeypatch):
    """Unpinned: the press half of a tray click already dismissed the popup, so
    the release must finish the toggle instead of reopening it."""
    from PyQt6.QtWidgets import QSystemTrayIcon

    cal = tray.calendar_widget
    shown = []
    monkeypatch.setattr(tray, "show_calendar", lambda: shown.append(1))
    monkeypatch.setattr(tray, "geometry",
                        lambda: QRect(QCursor.pos() - QPoint(4, 4), QSize(8, 8)))

    # The probe reads the tray geometry: this dismissal happened over the icon.
    cal._record_outside_dismissal()
    tray.on_tray_icon_activated(QSystemTrayIcon.ActivationReason.Trigger)
    assert shown == []

    # One-shot marker: the following click opens the calendar again.
    tray.on_tray_icon_activated(QSystemTrayIcon.ActivationReason.Trigger)
    assert shown == [1]


def test_dismissal_far_from_the_tray_icon_still_opens(tray, monkeypatch):
    """The overlap with the icon is judged when the dismissal is recorded: a
    popup dismissed elsewhere must still let the next tray click open it, even
    though the cursor is over the icon by the time that click arrives."""
    from PyQt6.QtWidgets import QSystemTrayIcon

    shown = []
    monkeypatch.setattr(tray, "show_calendar", lambda: shown.append(1))
    monkeypatch.setattr(tray, "geometry",
                        lambda: QRect(QCursor.pos() + QPoint(400, 400), QSize(8, 8)))

    # Away from the icon when the dismissal is recorded...
    tray.calendar_widget._record_outside_dismissal()
    # ... and over it by the time the icon delivers its click. The verdict has
    # to come from the dismissal, or this click would be swallowed.
    monkeypatch.setattr(tray, "geometry",
                        lambda: QRect(QCursor.pos() - QPoint(4, 4), QSize(8, 8)))

    tray.on_tray_icon_activated(QSystemTrayIcon.ActivationReason.Trigger)
    assert shown == [1]


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
    monkeypatch.setattr(controller_module.ConfirmDialog, "notify",
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
    monkeypatch.setattr(controller_module.ConfirmDialog, "notify",
                        staticmethod(lambda *a, **k: errors.append(a)))
    assert tray.import_events_from_dialog() is False
    assert errors


def test_export_events_empty_shows_info(tray, monkeypatch):
    tray.user_events = {}
    boxes = []
    monkeypatch.setattr(controller_module.ConfirmDialog, "notify",
                        staticmethod(lambda *a, **k: boxes.append(a)))
    assert tray.export_events_to_dialog() is False
    assert boxes


def test_export_events_success(tray, monkeypatch, tmp_path):
    tray.add_user_event(jdatetime.date(1405, 9, 10), "export me", "none", False)
    out = tmp_path / "out.json"
    monkeypatch.setattr(controller_module.QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(out), "")))
    boxes = []
    monkeypatch.setattr(controller_module.ConfirmDialog, "notify",
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


# --- prewarm / tray date tracking --------------------------------------------------------


def test_prewarm_skips_when_calendar_is_visible(tray, qtbot):
    """UI-1: prewarming prepares a HIDDEN window; a calendar the user opened
    within the first second must not be yanked off-screen by the timer."""
    tray.show_calendar()
    assert tray.calendar_widget.isVisible()
    position_before = tray.calendar_widget.pos()

    tray._prewarm_calendar()

    assert tray.calendar_widget.isVisible(), "the open calendar must stay open"
    assert tray.calendar_widget.pos() == position_before


def test_prewarm_runs_when_calendar_is_hidden(tray, qtbot):
    assert not tray.calendar_widget.isVisible()
    tray._prewarm_calendar()
    assert not tray.calendar_widget.isVisible()  # parked off-screen again


def test_update_tray_icon_tracks_last_tray_date_and_cleans_expiry(tray):
    """TRAY-4/EVT-9: the tray keeps its own date and a real date change runs
    the expired-event cleanup, so a sleep across midnight self-heals."""
    clean_calls, _ = _spy(tray, "_clean_expired_events")
    tray.update_tray_icon(force=True)
    first_date = tray._last_tray_date
    assert first_date is not None

    # Simulate a day change without force (the minute-tick path).
    tray._last_tray_date = jdatetime.date(first_date.year - 1, 1, 1)
    tray.update_tray_icon(force=False)
    assert len(clean_calls) == 1

    # Same date again: no repeat cleanup, no repaint work.
    tray.update_tray_icon(force=False)
    assert len(clean_calls) == 1


def test_fit_tooltip_caps_at_windows_limit(tray):
    """TRAY-3: the tooltip never exceeds Windows' ~128-char cap."""
    lines = ["شنبه", "1404/05/05", "۵ مرداد ۱۴۰۴"]
    event_text = "رویداد طولانی " * 20
    fitted = tray._fit_tooltip(lines + ["رویداد:"] + event_text.split("\n"))
    assert len(fitted) <= 127
    assert fitted.startswith("شنبه")  # priority lines survive


def test_fit_tooltip_trims_lowest_priority_first(tray):
    lines = ["شنبه", "1404/05/05", "۵ مرداد ۱۴۰۴", "تعطیلی:", "جشن بزرگ"]
    event_text = "y" * 200
    fitted = tray._fit_tooltip(lines + ["رویداد:"] + [event_text])
    assert "جشن بزرگ" in fitted  # holiday reasons outrank the event text
    assert event_text not in fitted  # the oversized event text was trimmed


def test_fit_tooltip_hard_cuts_when_identity_lines_alone_overflow():
    """The fallback branch only trimmed the LAST line; if the first three
    (identity) lines alone exceed the cap the loop could never end."""
    fat_identity = ["ش" * 200, "ش" * 200, "ش" * 200]
    fitted = SystemTrayIcon._fit_tooltip(list(fat_identity))
    assert len(fitted) <= 127


# --- persistence-failure handling (EVT-7) -------------------------------------------------


def test_add_user_event_rolls_back_on_save_failure(tray, monkeypatch):
    # The EventService owns the save (EVT-6), so patch it there.
    monkeypatch.setattr(event_service_module, "save_user_events", lambda events: False)
    monkeypatch.setattr(controller_module.ConfirmDialog, "notify",
                        staticmethod(lambda *a, **k: None))

    date = jdatetime.date(1405, 3, 3)
    tray.user_events = {"1405-03-01": {"text": "keep me", "recurrence": "none",
                                       "remove_after_finish": False}}
    snapshot = dict(tray.user_events)

    tray.add_user_event(date, "will fail to persist")

    assert tray.user_events == snapshot, "in-memory state must roll back"


def test_remove_user_event_rolls_back_on_save_failure(tray, monkeypatch):
    monkeypatch.setattr(event_service_module, "save_user_events", lambda events: False)
    monkeypatch.setattr(controller_module.ConfirmDialog, "notify",
                        staticmethod(lambda *a, **k: None))

    key = "1405-03-01"
    tray.user_events = {key: {"text": "keep me", "recurrence": "none",
                              "remove_after_finish": False}}
    snapshot = dict(tray.user_events)

    tray.remove_user_event(jdatetime.date(1405, 3, 1))

    assert tray.user_events == snapshot


def test_background_cleanup_save_failure_stays_quiet(tray, monkeypatch):
    """EVT-7 revisited: expired-event cleanup runs from timers (startup,
    midnight, time-change, minute tick). A failed save there must roll the
    in-memory state back and LOG, never fire a modal - a modal per minute
    while the disk is down was dialog spam, not UX."""
    monkeypatch.setattr(event_service_module, "save_user_events", lambda events: False)
    notified = []
    monkeypatch.setattr(controller_module.ConfirmDialog, "notify",
                        staticmethod(lambda *a, **k: notified.append(a)))

    expired_key = "1400-01-01"
    tray.user_events = {expired_key: {"text": "old one-shot", "recurrence": "none",
                                      "remove_after_finish": True}}
    snapshot = dict(tray.user_events)

    tray._clean_expired_events()

    assert notified == [], "background cleanup must not raise a modal dialog"
    assert tray.user_events == snapshot  # rolled back, still consistent


def test_interactive_save_failure_notifies(tray, monkeypatch):
    """Interactive mutations keep the themed failure dialog: the save result
    and the UI notification are separated, not removed."""
    monkeypatch.setattr(event_service_module, "save_user_events", lambda events: False)
    notified = []
    monkeypatch.setattr(controller_module.ConfirmDialog, "notify",
                        staticmethod(lambda *a, **k: notified.append(a)))

    tray.add_user_event(jdatetime.date(1405, 3, 3), "interactive add")

    assert len(notified) == 1
    title = notified[0][1]
    assert title == "ذخیره رویدادها"


# --- UPD-6 / UPD-9 controller wiring ------------------------------------------------------


def test_noop_press_does_not_start_a_second_round(tray, monkeypatch):
    """The press lands on a busy checker: no second round starts (the _pending
    guard), but the press is still honoured by marking/queueing - see
    test_press_during_a_full_round_marks_that_round_manual."""
    monkeypatch.setattr(tray.update_checker, "check", lambda: False)
    tray._manual_update_check = False
    started, _ = _spy(tray.update_checker, "check")
    tray._check_for_updates(manual=True)
    assert started == [((), {})]  # check() was called once, and refused


def test_download_update_reuses_verified_existing_installer(tray, monkeypatch, tmp_path):
    """UPD-9: an existing, digest-verified installer skips the download."""
    import hashlib

    # _download_update prefers ~/Downloads when it exists; pin home to the
    # tmp tree so the destination is deterministic.
    monkeypatch.setattr(controller_module.Path, "home", staticmethod(lambda: tmp_path))
    (tmp_path / "Downloads").mkdir()
    destination = tmp_path / "Downloads" / "ShamsiTraySetup-1.4.1.exe"
    payload = b"installer-bytes"
    destination.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()

    download_calls = []
    monkeypatch.setattr(tray.update_checker, "download_installer",
                        lambda url, dest, sha: download_calls.append((url, dest, sha)))
    reuse_offers = []
    monkeypatch.setattr(tray, "_on_installer_downloaded",
                        lambda path: reuse_offers.append(path))

    tray._download_update("1.4.1", "http://x/installer.exe", digest)

    assert download_calls == []            # no re-download
    assert reuse_offers == [str(destination)]


def test_download_update_redownloads_on_digest_mismatch(tray, monkeypatch, tmp_path):
    import hashlib

    monkeypatch.setattr(controller_module.Path, "home", staticmethod(lambda: tmp_path))
    (tmp_path / "Downloads").mkdir()
    destination = tmp_path / "Downloads" / "ShamsiTraySetup-1.4.1.exe"
    destination.write_bytes(b"stale bytes")

    download_calls = []
    monkeypatch.setattr(tray.update_checker, "download_installer",
                        lambda url, dest, sha: download_calls.append((url, dest, sha)))

    tray._download_update("1.4.1", "http://x/installer.exe",
                          hashlib.sha256(b"fresh").hexdigest())

    assert len(download_calls) == 1        # stale file: re-download


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


# --- keyed edits through the calendar's own signals ------------------------------------


def _two_events_today(tray):
    """Today's date carrying a one-time and a monthly event, added the way the app does."""
    today = jdatetime.date.today()
    tray.add_user_event(today, "Doctor", "none", True)
    tray.add_user_event(today, "Pay bills", "monthly", False)
    return today, f"{today.year:04d}-{today.month:02d}-{today.day:02d}", f"0000-00-{today.day:02d}"


def test_editing_one_of_two_events_leaves_the_other_alone(tray):
    """End to end through the calendar: the per-event menu edits ONE of the day's
    events, so the other one must be untouched."""
    today, one_time_key, monthly_key = _two_events_today(tray)

    tray.calendar_widget.event_updated_by_key.emit(monthly_key, today, "Pay bills later",
                                                   "monthly", False, "")

    assert tray.user_events[monthly_key]["text"] == "Pay bills later"
    assert tray.user_events[one_time_key]["text"] == "Doctor"


def test_editing_the_one_time_event_leaves_the_monthly_one_alone(tray):
    """The same edit in the other direction. A one-time event keeps its own key on
    a recurrence-free edit, so it must not disturb the monthly event sharing the
    date - the two are separate entries, not one date-level slot."""
    today, one_time_key, monthly_key = _two_events_today(tray)
    monthly_before = dict(tray.user_events[monthly_key])

    tray.calendar_widget.event_updated_by_key.emit(one_time_key, today, "Doctor checkup",
                                                   "none", False, "")

    assert tray.user_events[one_time_key]["text"] == "Doctor checkup"
    assert tray.user_events[one_time_key]["recurrence"] == "none"
    assert tray.user_events[monthly_key] == monthly_before
    assert set(tray.user_events) == {one_time_key, monthly_key}


def test_an_unconfirmed_merge_leaves_both_events_alone(tray):
    """The user said no, so the calendar emits no merge target at all. The edit
    would land on the monthly event's key, and must be refused rather than
    silently overwriting it."""
    today, one_time_key, monthly_key = _two_events_today(tray)
    before = {key: dict(entry) for key, entry in tray.user_events.items()}

    tray.calendar_widget.event_updated_by_key.emit(one_time_key, today, "Doctor",
                                                   "monthly", False, "")

    assert tray.user_events == before
    assert set(tray.user_events) == {one_time_key, monthly_key}


def test_deleting_one_of_two_events_leaves_the_other_alone(tray):
    _today, one_time_key, monthly_key = _two_events_today(tray)

    tray.calendar_widget.event_removed_by_key.emit(monthly_key)

    assert monthly_key not in tray.user_events
    assert one_time_key in tray.user_events


def test_a_confirmed_merge_lands_as_one_entry(tray):
    """The calendar's merge ask resolves to a single entry carrying both texts."""
    today, one_time_key, monthly_key = _two_events_today(tray)

    tray.calendar_widget.event_updated_by_key.emit(one_time_key, today, "Doctor",
                                                   "monthly", False, monthly_key)

    assert set(tray.user_events) == {monthly_key}
    assert tray.user_events[monthly_key]["text"] == "Pay bills\nDoctor"
    assert tray.user_events[monthly_key]["recurrence"] == "monthly"


def test_a_merge_of_identical_text_never_repeats_the_line(tray):
    """Both events already carry the same text: the merge must land on that one
    line, not on the line twice."""
    today, one_time_key, monthly_key = _two_events_today(tray)
    tray.user_events[one_time_key]["text"] = "Pay bills"

    tray.calendar_widget.event_updated_by_key.emit(one_time_key, today, "Pay bills",
                                                   "monthly", False, monthly_key)

    assert set(tray.user_events) == {monthly_key}
    assert tray.user_events[monthly_key]["text"] == "Pay bills"
    assert "Pay bills\nPay bills" not in tray.user_events[monthly_key]["text"]


def test_a_merge_onto_a_yearly_event_keeps_the_yearly_one(tray):
    """The other reachable merge: a monthly event moved onto a yearly one on the
    same date. The event already sitting on the date survives as the entry, with
    its own recurrence, and the two texts combine."""
    today, one_time_key, monthly_key = _two_events_today(tray)
    tray.add_user_event(today, "Dentist", "yearly", False)
    yearly_key = f"0000-{today.month:02d}-{today.day:02d}"

    tray.calendar_widget.event_updated_by_key.emit(monthly_key, today, "Pay bills + pharmacy",
                                                   "yearly", False, yearly_key)

    assert set(tray.user_events) == {one_time_key, yearly_key}
    assert tray.user_events[yearly_key]["text"] == "Dentist\nPay bills + pharmacy"
    assert tray.user_events[yearly_key]["recurrence"] == "yearly"


def test_update_user_event_by_key_is_safe_for_an_unknown_key(tray):
    """An expired or already-removed key must not raise, and must not refresh."""
    tray.user_events = {}
    tray.update_user_event_by_key("1405-01-01", jdatetime.date(1405, 1, 1), "ghost")
    assert tray.user_events == {}


def test_user_events_setter_survives_assigning_the_store_itself(tray):
    """The setter's contract invites ``tray.user_events = tray.user_events`` -
    the getter hands back the live store - so clearing before updating from that
    same dict would wipe it, and the next save would persist the wipe."""
    tray.user_events = {"1405-01-01": {"text": "keep me", "recurrence": "none",
                                       "remove_after_finish": False}}
    live_store = tray.user_events

    tray.user_events = tray.user_events

    assert tray.user_events is live_store
    assert tray.user_events == {"1405-01-01": {"text": "keep me", "recurrence": "none",
                                               "remove_after_finish": False}}


def test_update_user_event_by_key_rolls_back_on_save_failure(tray, monkeypatch):
    monkeypatch.setattr(event_service_module, "save_user_events", lambda events: False)
    monkeypatch.setattr(controller_module.ConfirmDialog, "notify",
                        staticmethod(lambda *a, **k: None))
    today, _one_time_key, monthly_key = _two_events_today(tray)
    snapshot = dict(tray.user_events)

    tray.calendar_widget.event_updated_by_key.emit(monthly_key, today, "will fail",
                                                   "monthly", False, "")

    assert tray.user_events == snapshot


# --- import collision confirmation (EVT-5 / #1) -----------------------------------------


def _write_import_file(tmp_path, events):
    import json

    from utils.event_io import EVENTS_STORE_VERSION

    path = tmp_path / "import.json"
    path.write_text(json.dumps({"version": EVENTS_STORE_VERSION, "events": events},
                               ensure_ascii=False), encoding="utf-8")
    return str(path)


def _entry(text, recurrence="none", remove_after_finish=False):
    return {"text": text, "recurrence": recurrence, "remove_after_finish": remove_after_finish}


def test_import_warns_and_aborts_on_exact_key_collision(tray, monkeypatch, tmp_path):
    tray.user_events = {"1405-08-01": _entry("existing event")}
    import_file = _write_import_file(tmp_path, {"1405-08-01": _entry("imported event")})
    monkeypatch.setattr(controller_module.QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (import_file, "")))
    asks = []

    def fake_ask(parent, title, message, **kwargs):
        asks.append((title, message, kwargs))
        return False  # user declines

    monkeypatch.setattr(controller_module.ConfirmDialog, "ask", staticmethod(fake_ask))
    assert tray.import_events_from_dialog() is False
    # Nothing changed: the store still holds the original event.
    assert tray.user_events == {"1405-08-01": _entry("existing event")}
    assert len(asks) == 1
    title, message, kwargs = asks[0]
    assert title == "وارد کردن رویدادها"
    assert "جایگزین" in message
    assert kwargs["detail"] == "existing event"


def test_import_confirms_before_replacing_on_exact_collision(tray, monkeypatch, tmp_path):
    tray.user_events = {"1405-08-01": _entry("existing event")}
    import_file = _write_import_file(tmp_path, {"1405-08-01": _entry("imported event")})
    monkeypatch.setattr(controller_module.QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (import_file, "")))
    monkeypatch.setattr(controller_module.ConfirmDialog, "ask", staticmethod(lambda *a, **k: True))
    boxes = []
    monkeypatch.setattr(controller_module.ConfirmDialog, "notify",
                        staticmethod(lambda *a, **k: boxes.append((a[1], a[2]))))
    assert tray.import_events_from_dialog() is True
    assert tray.user_events == {"1405-08-01": _entry("imported event")}
    # Summary mentions both the import and the replacement (Grok's «N جایگزین شد»).
    summary = boxes[0][1]
    assert "وارد شد" in summary and "جایگزین شد" in summary


def test_import_warns_on_cross_representation_collision(tray, monkeypatch, tmp_path):
    """A one-time event and an imported yearly event landing on the same
    visible day used to stack silently: the calendar picked a winner while
    the manager listed both."""
    tray.user_events = {"1405-08-01": _entry("one-time existing")}
    import_file = _write_import_file(tmp_path, {"0000-08-01": _entry("yearly imported", "yearly")})
    monkeypatch.setattr(controller_module.QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (import_file, "")))
    asks = []

    def fake_ask(parent, title, message, **kwargs):
        asks.append((message, kwargs))
        return True

    monkeypatch.setattr(controller_module.ConfirmDialog, "ask", staticmethod(fake_ask))
    boxes = []
    monkeypatch.setattr(controller_module.ConfirmDialog, "notify",
                        staticmethod(lambda *a, **k: boxes.append(a)))
    assert tray.import_events_from_dialog() is True
    # The confirm promised exactly ONE replacement:
    assert len(asks) == 1 and "جایگزین" in asks[0][0]
    assert asks[0][1]["detail"] == "one-time existing"
    # And applying it kept the one-event-per-date invariant: the imported
    # yearly took over, the shadowed one-time is gone everywhere.
    assert tray.user_events == {"0000-08-01": _entry("yearly imported", "yearly")}


def test_import_without_collisions_never_asks(tray, monkeypatch, tmp_path):
    tray.user_events = {"1405-08-01": _entry("existing")}
    import_file = _write_import_file(tmp_path, {"1406-03-05": _entry("imported")})
    monkeypatch.setattr(controller_module.QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (import_file, "")))

    def boom(*a, **k):
        raise AssertionError("confirm dialog must not appear without collisions")

    monkeypatch.setattr(controller_module.ConfirmDialog, "ask", staticmethod(boom))
    monkeypatch.setattr(controller_module.ConfirmDialog, "notify", staticmethod(lambda *a, **k: None))
    assert tray.import_events_from_dialog() is True
    assert set(tray.user_events) == {"1405-08-01", "1406-03-05"}


def test_import_save_failure_leaves_disk_and_memory_untouched(tray, monkeypatch, tmp_path):
    """Review item #2, failure side: with the single atomic save there is no
    half-imported file to outlive the in-memory rollback."""
    import json

    original = {"version": 2, "events": {"1405-08-01": _entry("existing event")}}
    store = APP_CONFIG.USER_EVENTS_FILE_PATH
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
    tray.user_events = {"1405-08-01": _entry("existing event")}

    import_file = _write_import_file(tmp_path, {"1406-01-01": _entry("imported")})
    monkeypatch.setattr(controller_module.QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (import_file, "")))
    errors = []
    monkeypatch.setattr(controller_module.ConfirmDialog, "notify",
                        staticmethod(lambda *a, **k: errors.append(a)))
    monkeypatch.setattr(event_service_module, "save_user_events", lambda events: False)

    assert tray.import_events_from_dialog() is False
    assert tray.user_events == {"1405-08-01": _entry("existing event")}
    assert json.loads(store.read_text(encoding="utf-8")) == original, \
        "the store file must be byte-identical after a failed import"
    assert errors  # themed failure notice shown


# --- download dialog duplicate guard (#3) ------------------------------------------------


def test_download_update_ignored_while_download_in_progress(tray, monkeypatch):
    """(#3) A second download request must not even CREATE a progress dialog:
    the live one owns the progress, and a second card would freeze forever."""
    monkeypatch.setattr(tray.update_checker, "is_downloading", lambda: True)

    class MustNotBuild:
        def __init__(self, *a, **k):
            raise AssertionError("dialog must not be created while a download runs")

    monkeypatch.setattr(controller_module, "DownloadUpdateDialog", MustNotBuild)
    calls = []
    monkeypatch.setattr(tray.update_checker, "download_installer",
                        lambda *a, **k: calls.append(a))

    tray._download_update("1.4.1", "http://x/installer.exe", "a" * 64)

    assert calls == []


def test_download_update_rejected_request_closes_dialog(tray, monkeypatch):
    """Defense in depth: if the request is ever rejected after the dialog was
    built, the freshly opened dialog is dismissed instead of orphaned."""
    canceled_slots = []

    class FakeDialog:
        def __init__(self, version, parent=None):
            self.shown = False
            self.dismissed = False
            self.canceled = type("Signal", (), {
                "connect": staticmethod(lambda slot: canceled_slots.append(slot))})()

        def show(self):
            self.shown = True

        def dismiss(self):
            self.dismissed = True

    dialog = FakeDialog("1.4.1")
    monkeypatch.setattr(controller_module, "DownloadUpdateDialog",
                        lambda version, parent=None: dialog)
    monkeypatch.setattr(tray.update_checker, "is_downloading", lambda: False)
    monkeypatch.setattr(tray.update_checker, "download_installer", lambda *a, **k: False)

    tray._download_update("1.4.1", "http://x/installer.exe", "a" * 64)

    assert dialog.shown and dialog.dismissed
    assert tray._download_dialog is None
