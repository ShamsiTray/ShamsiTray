"""
App Controller
---------------------------

This module contains the `SystemTrayIcon` class, which serves as the main
controller for the application. It manages:
- The system tray icon itself, including its appearance and tooltip.
- The context menu (right-click menu).
- Loading and saving application settings (theme, auto-start) and user data (events).
- Creating and managing the lifecycle of the main application windows (calendar, converter).
- Handling system events like time changes and application activation.
"""
import os
import sys
import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Optional

import jdatetime
from PyQt6.QtCore import QCoreApplication, QEventLoop, QTimer, QUrl, Qt
from PyQt6.QtGui import QCursor, QDesktopServices, QIcon
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon

from config import APP_CONFIG
from core.event_service import EventService
from ui.windows.calendar_window import PersianCalendarWidget
from ui.windows.converter_window import DateConverterWindow
from ui.windows.event_manager_window import EventManagerWindow
from ui.windows.holiday_viewer_window import HolidayViewerWindow
from ui.widgets.tray_menu import build_tray_menu
from ui.widgets.confirm_dialog import ConfirmDialog
from ui.widgets.download_dialog import DownloadUpdateDialog
from core.update_checker import (
    APP_STATE_CURRENT,
    APP_STATE_FAILED,
    APP_STATE_SKIPPED,
    APP_STATE_UNAVAILABLE,
    APP_STATE_UPDATE_FOUND,
    DAY_MS,
    HOLIDAYS_STATE_CURRENT,
    HOLIDAYS_STATE_FAILED,
    HOLIDAYS_STATE_UPDATED,
    UpdateChecker,
    file_sha256,
    should_notify,
)
from utils.date_utils import ms_until_midnight, persian_month_name, persian_weekday_name, to_persian_digits
from utils.event_io import (
    RECURRENCE_NONE,
    events_on_date,
)
from utils.holiday_io import read_version, resolve_holidays_store
from utils.json_settings import JsonSettings
from utils.logger import setup_logging
from utils.native_events import TimeChangeEventFilter
from utils.startup_registry import RUN_KEY_PATH, StartupRegistry
from utils.windows_theme import WindowsThemeBackend
from utils.ui_helpers import create_tray_pixmap, global_scrollbar_stylesheet

if TYPE_CHECKING:
    from ui.windows.tutorial_window import TutorialWindow

logger = setup_logging(__name__)

# A failed AUTO check is retried on this cadence, at most this many times per
# session (reset on any clean check).
AUTO_CHECK_RETRY_DELAY_MS = 10 * 60 * 1000
AUTO_CHECK_MAX_RETRIES = 3

# The 24h gate is enforced by _auto_check_updates itself; this recurring timer is
# what makes the gate REACHED again: a one-shot timer fires once per session, so
# a machine that sleeps instead of rebooting would never check again after launch.
AUTO_CHECK_REARM_INTERVAL_MS = 60 * 60 * 1000

# A failed HOLIDAY fetch is retried quietly on its own cadence, separate from the
# app verdict: it must never re-pop the update popup or stamp "last checked".
HOLIDAY_RETRY_DELAY_MS = 10 * 60 * 1000
HOLIDAY_RETRY_MAX_ATTEMPTS = 3

# Every manual round report shares one replacement key, so a second result
# rewrites the open notice (and raises it) instead of stacking a second window.
# The update popup outranks these notices and dismisses only this key's notice.
UPDATE_CHECK_NOTICE_KEY = "update-check"

# Windows broadcasts WM_TIMECHANGE to every top-level window, and the time
# service can emit a burst of them while re-syncing. Coalescing them makes a
# burst of any length cost one refresh (expiry cleanup + calendar rebuild + tray
# repaint + midnight reschedule), which runs once the burst has gone quiet for
# this long.
TIME_CHANGE_COALESCE_MS = 300

# Windows silently truncates tray tooltips at ~128 characters. Build the tooltip
# by priority (weekday, date, holidays, then the event text) and trim the
# lowest-priority content ourselves instead of losing the tail mid-line.
WINDOWS_TOOLTIP_MAX_CHARS = 127

# Autostart is OPT-OUT: a brand-new installation has no saved preference yet and
# defaults to ENABLED. An existing explicit False must never be read as "missing"
# and re-enabled, which is why the missing-vs-False distinction is made with
# JsonSettings.contains() instead of a value() default.
AUTOSTART_FIRST_RUN_DEFAULT = True


def _startup_executable_value() -> str:
    """The quoted executable path the autostart Run entry should hold.

    Frozen builds point at the running executable; development runs resolve
    ``sys.argv[0]`` to an ABSOLUTE path first - a bare relative name would make
    the Run entry depend on whatever working directory the process happened to
    be launched from, and the entry would not survive a launch from another
    directory.
    """
    if getattr(sys, 'frozen', False):
        return f'"{sys.executable}"'
    return f'"{Path(sys.argv[0]).resolve()}"'

# Test hook for the holiday updater: pretend the local store has this data
# version instead of the real one. Set to 0 to force the updater to see the
# remote file (currently version 140500) as newer and apply it.
DEBUG_DATA_VERSION_ENV = "SHAMSITRAY_DEBUG_DATA_VERSION"

class SystemTrayIcon(QSystemTrayIcon):
    """The main application controller, managing the tray icon, windows, and settings."""

    def __init__(self, settings: Optional[JsonSettings] = None,
                 startup_registry: Optional[StartupRegistry] = None,
                 theme_backend: Optional[WindowsThemeBackend] = None):
        super().__init__()
        self.settings = settings if settings is not None else JsonSettings()
        # Every autostart registry operation goes through this seam, so the
        # policy below can be driven against an in-memory backend in tests
        # without touching the real HKCU hive.
        self.startup_registry = startup_registry if startup_registry is not None else StartupRegistry()
        # The 'system' theme mode's winreg read works the same way: a backend
        # that can stand in for the real unreadable host in tests.
        self.theme_backend = theme_backend if theme_backend is not None else WindowsThemeBackend()
        self.holidays_cache = resolve_holidays_store()
        # The bundled data covers a limited year range, and a missing current
        # year is a silent cliff - Fridays still render red while official
        # holidays quietly vanish. Say so in the log.
        _current_year = jdatetime.date.today().year
        if not self.holidays_cache.get(_current_year):
            logger.warning(
                f"No holiday data for the current Jalali year {_current_year}; "
                f"official holidays will be missing until the holiday data is updated.")
        # The store is owned by the EventService, named here as the public
        # attribute the UI layers reach: every mutation and every save goes
        # through it, so the calendar, the tray and the disk can never
        # disagree. ``user_events`` below is a live view of its dict.
        self.event_service = EventService()
        # The service stays Qt-free; the application supplies the themed failure
        # dialog for interactive saves (background cleanup passes notify=False
        # inside the service and never calls this) and the one post-save refresh
        # for the calendar, tray and manager.
        self.event_service.on_save_error = self._notify_save_failed
        self.event_service.on_store_changed = self._refresh_after_events_changed
        # Window references are created lazily; they must exist (as None) before
        # _clean_expired_events can run, because it refreshes the calendar when
        # events expire.
        self.calendar_widget: Optional[PersianCalendarWidget] = None
        self.converter_window: Optional[DateConverterWindow] = None
        self.event_manager_window: Optional[EventManagerWindow] = None
        self.holiday_viewer_window: Optional[HolidayViewerWindow] = None
        self.tutorial_window: Optional["TutorialWindow"] = None

        self._clean_expired_events()

        self.calendar_widget = PersianCalendarWidget(self.holidays_cache, self.user_events)
        # Evaluated when the calendar records an outside-click dismissal, so
        # the tray click that follows can tell its own press from a separate
        # tray click inside the marker's age window.
        self.calendar_widget.cursor_over_tray_probe = self._cursor_is_over_tray
        self.calendar_widget.event_added.connect(self.add_user_event)
        self.calendar_widget.event_removed.connect(self.remove_user_event)
        self.calendar_widget.event_removed_by_key.connect(self.remove_user_event_by_key)
        self.calendar_widget.event_updated_by_key.connect(self.update_user_event_by_key)

        QTimer.singleShot(1000, self._prewarm_calendar)

        self._load_settings()
        self._validate_and_apply_startup_setting()
        self._apply_theme()
        self.activated.connect(self.on_tray_icon_activated)
        self._setup_timers()
        self._setup_update_checker()
        self.update_tray_icon(force=True)

    # --- user-event store (live view of the EventService state) -----------------

    @property
    def user_events(self) -> Dict[str, dict]:
        """The live event store (the EventService's own dict object).

        A property, not a plain attribute: rebinding it would orphan the
        reference the calendar widget holds. The setter syncs IN PLACE for the
        same reason, so external holders always read current state.
        """
        return self.event_service.events

    @user_events.setter
    def user_events(self, value: Dict[str, dict]):
        # Snapshot first: ``value`` may be the live store itself, and
        # clear-then-update against that same dict leaves it empty - which the
        # next save would then persist.
        snapshot = dict(value)
        self.event_service.events.clear()
        self.event_service.events.update(snapshot)

    def _get_windows_theme(self) -> str:
        """Detects if Windows is in light or dark mode. Defaults to dark if detection fails.

        The read goes through the injectable ``theme_backend`` (the backend
        owns the rule: off Windows too, the verdict is dark).
        """
        return self.theme_backend.theme()

    def _theme_choice(self) -> str:
        """The stored appearance preference: "system", "light" or "dark".

        A missing key reads as "system" (follow Windows) - the behaviour a
        fresh install has always had - and an unknown value falls back to
        "system" instead of breaking theme resolution. Read live like the
        other preference gates: the tray menu writes the key behind this
        method's back.
        """
        saved = self.settings.value(APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY, None)
        return saved if saved in APP_CONFIG.THEME_CHOICES else APP_CONFIG.Theme.SYSTEM

    def _load_settings(self):
        # contains(), not a value() default: a missing preference is not an
        # explicit "off" (see AUTOSTART_FIRST_RUN_DEFAULT).
        self._autostart_pref_exists = self.settings.contains(APP_CONFIG.AUTO_START_SETTING_KEY)
        if self._autostart_pref_exists:
            self.is_open_at_login = self.settings.value(APP_CONFIG.AUTO_START_SETTING_KEY, False, type=bool)
        else:
            self.is_open_at_login = AUTOSTART_FIRST_RUN_DEFAULT

        self.always_on_top = self.settings.value(APP_CONFIG.ALWAYS_ON_TOP_SETTING_KEY, True, type=bool)
        self.calendar_widget.set_always_on_top(self.always_on_top)

        choice = self._theme_choice()
        if choice == APP_CONFIG.Theme.SYSTEM:
            self.current_theme = self._get_windows_theme()
            logger.info(f"No pinned theme; following the system theme: {self.current_theme}")
        else:
            self.current_theme = choice
            logger.info(f"Loaded user-preferred theme: {self.current_theme}")

    def _apply_theme(self):
        APP_CONFIG.set_theme(self.current_theme)
        QApplication.instance().setStyleSheet(self._build_global_stylesheet())
        self.update_tray_icon(force=True)
        self._setup_context_menu()
        if self.calendar_widget:
            self.calendar_widget.update_styles()
        for window in (self.converter_window, self.event_manager_window,
                       self.holiday_viewer_window, self.tutorial_window):
            if window and window.isVisible():
                window.update_styles()

    def _setup_timers(self):
        self.minute_timer = QTimer(self)
        self.minute_timer.timeout.connect(lambda: self.update_tray_icon(force=False))
        self.minute_timer.start(60 * 1000)
        self._time_change_messages = 0
        self._time_change_timer = QTimer(self)
        self._time_change_timer.setSingleShot(True)
        self._time_change_timer.timeout.connect(self._handle_system_time_change)
        # Windows theme changes (WM_SETTINGCHANGE / ImmersiveColorSet) get the
        # same coalescing treatment - they can also arrive as bursts.
        self._theme_change_timer = QTimer(self)
        self._theme_change_timer.setSingleShot(True)
        self._theme_change_timer.timeout.connect(self._handle_system_theme_change)
        self.event_filter = TimeChangeEventFilter(
            self._on_system_time_change,
            on_setting_change_callback=self._on_system_setting_change)
        QCoreApplication.instance().installNativeEventFilter(self.event_filter)
        self.schedule_next_midnight_check()

    def _on_midnight_timer_triggered(self):
        logger.info("Midnight timer triggered. Updating tray icon for new day.")
        self._clean_expired_events()
        if self.calendar_widget:
            self.calendar_widget.go_to_today()
        self.update_tray_icon(force=True)
        self.schedule_next_midnight_check()

    def schedule_next_midnight_check(self):
        millis_until_midnight = ms_until_midnight(datetime.datetime.now())
        buffer_ms = 500 # Small buffer to ensure we pass midnight even if the timer fires slightly early
        if hasattr(self, '_midnight_timer') and self._midnight_timer.isActive():
            self._midnight_timer.stop()
            del self._midnight_timer
        self._midnight_timer = QTimer(self)
        self._midnight_timer.setSingleShot(True)
        self._midnight_timer.timeout.connect(self._on_midnight_timer_triggered)
        self._midnight_timer.start(millis_until_midnight + buffer_ms)
        logger.debug(f"Next midnight check scheduled in {millis_until_midnight + buffer_ms} ms.")

    def _on_system_time_change(self):
        """A WM_TIMECHANGE arrived: (re)arm the coalescing timer.

        Windows broadcasts this message to every top-level window and the time
        service can emit a burst while re-syncing, so the refresh is debounced
        instead of run once per message. Restarting the single-shot timer on each
        message means a burst of ANY length costs exactly one refresh, and that
        refresh runs after the burst has gone quiet - so it reads the settled
        clock value rather than an intermediate one, and a genuine one-off change
        is never lost (it just lands a fraction of a second later).
        """
        self._time_change_messages += 1
        self._time_change_timer.start(TIME_CHANGE_COALESCE_MS)

    def _handle_system_time_change(self):
        """The coalesced refresh for a system-clock change (manual, DST, sync).

        Reached once per burst via the coalescing timer, and directly by tests.
        System time changes can invalidate the current date and the scheduled
        midnight timer, so this forces a full refresh and reschedules.
        """
        coalesced = self._time_change_messages
        self._time_change_messages = 0
        logger.info(f"System time change detected ({coalesced} message(s) coalesced); "
                    f"refreshing tray icon and midnight schedule.")
        self._clean_expired_events()
        if self.calendar_widget:
            self.calendar_widget.go_to_today()
        self.update_tray_icon(force=True)
        self.schedule_next_midnight_check()

    def _on_system_setting_change(self, section: str):
        """A WM_SETTINGCHANGE arrived: debounce by section."""
        if section == "ImmersiveColorSet":
            self._theme_change_timer.start(TIME_CHANGE_COALESCE_MS)

    def _handle_system_theme_change(self):
        """Re-read the Windows theme after a light/dark switch.

        Applies while the stored preference is "system" (or absent) - an
        explicit "light"/"dark" choice always wins, and the tray menu's theme
        row is what sets either.
        """
        if self._theme_choice() != APP_CONFIG.Theme.SYSTEM:
            return
        if not sys.platform == 'win32':
            return
        detected = self._get_windows_theme()
        if detected == self.current_theme:
            return
        logger.info(f"Windows theme changed to {detected}; the theme "
                    f"preference is \"system\", following it.")
        self.current_theme = detected
        self._apply_theme()

    # --- Update checks ---

    def _setup_update_checker(self):
        self._manual_update_check = False
        # Round bookkeeping consumed by the popup and the end-of-round message:
        # set in _on_round_finished (which always fires before the deferred
        # popup opens), so the popup knows whether the round was manual and
        # whether holidays were refreshed during it.
        self._round_was_manual = False
        self._round_holidays_state = HOLIDAYS_STATE_CURRENT
        # A manual press that lands during the quiet holidays-only refresh
        # cannot mark THAT round manual (a skipped round never messages), so the
        # full check is queued here and released by _on_round_finished when the
        # refresh concludes.
        self._queued_full_check_after_holidays = False
        self._update_dialog_open = False
        # The open update popup itself, so a manual check that lands while it is
        # up can RAISE it instead of dropping the result silently.
        self._active_update_popup = None
        # True between the scheduling of a deferred popup and the popup actually
        # opening; closes the one-tick window in which a second
        # app_update_available could schedule a duplicate dialog.
        self._update_popup_pending = False
        self._download_dialog = None
        self._auto_check_retries = 0
        # Quiet holiday-refetch retries; reset whenever a holiday fetch succeeds.
        self._holiday_retries = 0
        data_version = read_version(APP_CONFIG.HOLIDAYS_STORE_PATH)
        # The debug override is a development/test hook: frozen (installed)
        # builds ignore it.
        debug_version = ""
        if not getattr(sys, 'frozen', False):
            debug_version = os.environ.get(DEBUG_DATA_VERSION_ENV, "").strip()
        if debug_version:
            try:
                data_version = int(debug_version)
                logger.info(f"Debug holiday data version override active: {data_version}")
            except ValueError:
                logger.warning(f"Ignoring invalid {DEBUG_DATA_VERSION_ENV}={debug_version!r}.")
        self.update_checker = UpdateChecker(current_data_version=data_version, parent=self)
        self.update_checker.app_update_available.connect(self._on_app_update_available)
        self.update_checker.holidays_updated.connect(self._on_holidays_updated)
        self.update_checker.no_updates.connect(self._on_no_updates)
        self.update_checker.check_failed.connect(self._on_check_failed)
        self.update_checker.round_finished.connect(self._on_round_finished)
        self.update_checker.check_concluded.connect(self._on_check_concluded)
        self.update_checker.download_progress.connect(self._on_download_progress)
        self.update_checker.installer_downloaded.connect(self._on_installer_downloaded)
        self.update_checker.download_failed.connect(self._on_download_failed)
        QTimer.singleShot(30000, self._auto_check_updates)
        # Re-arm the auto check hourly. The method still enforces the enabled
        # flag and the 24h gate itself, and check() refuses to overlap a running
        # round, so the timer only ever re-ASKS the gate.
        self._auto_check_timer = QTimer(self)
        self._auto_check_timer.setInterval(AUTO_CHECK_REARM_INTERVAL_MS)
        self._auto_check_timer.timeout.connect(self._auto_check_updates)
        self._auto_check_timer.start()

    def _auto_check_enabled(self) -> bool:
        """The Updates/CheckEnabled preference; default ON when never set."""
        return self.settings.value(APP_CONFIG.UPDATE_CHECK_ENABLED_SETTING_KEY, True, type=bool)

    def _auto_check_updates(self):
        if not self._auto_check_enabled():
            return
        last_check_ms = self.settings.value(APP_CONFIG.LAST_UPDATE_CHECK_SETTING_KEY, 0, type=int) or 0
        now_ms = int(datetime.datetime.now().timestamp() * 1000)
        if now_ms - last_check_ms < DAY_MS:
            logger.debug("Skipping automatic update check (last check was less than 24h ago).")
            return
        self._check_for_updates(manual=False)

    def _check_for_updates(self, manual: bool):
        # No "last checked" stamp here: only _on_check_concluded writes it, after
        # a round reached a real answer. The manual flag follows check()'s return
        # value for the same reason - it must never mark an AUTO round as manual.
        started = self.update_checker.check()
        if started:
            self._manual_update_check = manual
            logger.info(f"Checking for updates ({'manual' if manual else 'automatic'}).")
        elif manual:
            # A manual press during a running round marks that round as manual,
            # so it reports to the user when it concludes - UNLESS the busy
            # round is the quiet holidays-only refresh, which must never
            # message: there the full check is queued and starts the moment
            # the refresh concludes.
            if self.update_checker.round_kind == "holidays":
                self._queued_full_check_after_holidays = True
                logger.info("Manual update check requested during the quiet "
                            "holiday refresh; a full check will run when it concludes.")
            else:
                self._manual_update_check = True
                logger.info("Manual update check requested while a round is already "
                            "running; the running round will report to the user.")

    def _on_check_concluded(self, failed: bool):
        """End of one check round: stamp success, schedule retries on failure."""
        if not failed:
            self._auto_check_retries = 0
            now_ms = int(datetime.datetime.now().timestamp() * 1000)
            self.settings.setValue(APP_CONFIG.LAST_UPDATE_CHECK_SETTING_KEY, now_ms)
            return
        # Manual-ness is read from the round snapshot, not the live flag: the
        # checker emits round_finished BEFORE check_concluded, and
        # _on_round_finished has already consumed _manual_update_check into
        # _round_was_manual by the time this runs, so the live flag is always
        # False here.
        if not self._round_was_manual and self._auto_check_retries < AUTO_CHECK_MAX_RETRIES:
            self._auto_check_retries += 1
            logger.warning(
                f"Automatic update check failed; retry "
                f"{self._auto_check_retries}/{AUTO_CHECK_MAX_RETRIES} in {AUTO_CHECK_RETRY_DELAY_MS // 60000} minutes.")
            QTimer.singleShot(AUTO_CHECK_RETRY_DELAY_MS, self._auto_check_updates)

    def _on_app_update_available(self, version: str, installer_url: str, sha256: str):
        if not self._manual_update_check:
            ignored = self.settings.value(APP_CONFIG.IGNORED_UPDATE_VERSION_SETTING_KEY, None)
            if not should_notify(version, ignored):
                logger.info(f"Skipping update notification for ignored version {version}.")
                return
        # Defer the popup out of the checker's signal path: _conclude() must still
        # emit check_concluded after this signal, and a modal dialog in between
        # blocks that conclusion while a concurrent check resets the round state.
        if self._update_dialog_open or self._update_popup_pending:
            if self._manual_update_check and self._active_update_popup is not None:
                # A manual result arriving while the popup is already up must
                # not vanish - bring the popup forward. (The popup is showing
                # the same /releases/latest answer in every realistic race;
                # re-offering a second modal would stack.)
                logger.info("Manual update offer arrived while the popup is already open; raising it.")
                self._active_update_popup.raise_()
                self._active_update_popup.activateWindow()
            return
        self._update_popup_pending = True
        QTimer.singleShot(0, lambda: self._show_update_popup(version, installer_url, sha256))

    def _show_update_popup(self, version: str, installer_url: str, sha256: str):
        self._update_popup_pending = False
        # The popup outranks the round notices: any open update-check notice is
        # answered by the popup now, so it must not sit underneath it.
        ConfirmDialog.dismiss_active_notice(UPDATE_CHECK_NOTICE_KEY)
        if self._update_dialog_open:
            return
        self._update_dialog_open = True
        try:
            # Themed three-way ask (the stock QMessageBox ignored the palette):
            # download = accent, ignore = red (it silences this version),
            # remind later = quiet ghost. Rotate glyph marks it as an update.
            # Detail line for a manual round that also refreshed the holiday
            # file, so the popup covers the whole round.
            detail = ("فایل تعطیلات نیز به‌روزرسانی شد."
                      if self._round_was_manual and self._round_holidays_state == HOLIDAYS_STATE_UPDATED
                      else "")
            # Built directly (not via ConfirmDialog.choose) so the reference is
            # retained and a manual arrival can raise the open popup.
            dialog = ConfirmDialog(
                QApplication.activeWindow(), "بروزرسانی جدید",
                f"نسخه جدید {APP_CONFIG.APP_NAME} ({version}) موجود است.",
                detail=detail, glyph=APP_CONFIG.FAS.FA_ARROWS_ROTATE,
                actions=[("دانلود", "accent"),
                         ("نادیده گرفتن", "danger"),
                         ("بعداً یادآوری کن", "ghost")])
            self._active_update_popup = dialog
            # The shared present-tail; the reference above is what lets a
            # manual arrival raise the open popup while it runs.
            dialog.exec_centered(QApplication.activeWindow())
            choice = dialog.choice
        finally:
            self._update_dialog_open = False
            self._active_update_popup = None
        if choice == "دانلود":
            self._download_update(version, installer_url, sha256)
        elif choice == "نادیده گرفتن":
            self.settings.setValue(APP_CONFIG.IGNORED_UPDATE_VERSION_SETTING_KEY, version)
            logger.info(f"Update to {version} will no longer be announced automatically.")

    def _download_update(self, version: str, installer_url: str, sha256: str):
        # A download request arriving while ANOTHER download runs must not build
        # a second progress card: the live dialog owns the real progress, and a
        # second one would sit frozen forever (its request rejected). Check
        # BEFORE creating the dialog at all.
        if self.update_checker.is_downloading():
            logger.warning("Download request ignored: a download is already in progress.")
            return
        downloads_dir = Path.home() / 'Downloads'
        destination = (downloads_dir if downloads_dir.exists() else APP_CONFIG.USER_DATA_DIR) / f"ShamsiTraySetup-{version}.exe"
        # Reuse an already-downloaded installer when its digest matches the
        # release. Without a digest there is nothing to verify against, so the
        # safe path is a fresh download.
        if sha256 and destination.exists():
            existing_digest = file_sha256(destination)
            if existing_digest is not None and existing_digest.lower() == sha256.lower():
                logger.info(f"Installer for {version} already downloaded and verified: {destination}")
                self._on_installer_downloaded(str(destination))
                return
        dialog = DownloadUpdateDialog(version, QApplication.activeWindow())
        dialog.canceled.connect(self.update_checker.cancel_download)
        self._download_dialog = dialog
        dialog.show()
        logger.info(f"Downloading update {version} to {destination}")
        if not self.update_checker.download_installer(installer_url, destination, sha256):
            # Defense in depth: the dialog opened here has no download behind it
            # and would freeze on screen if the guard ever races, so it is never
            # left orphaned.
            logger.warning("Installer download request rejected; a download is already in progress.")
            self._close_download_dialog()

    def _on_download_progress(self, received: int, total: int):
        if self._download_dialog is not None:
            self._download_dialog.set_progress(received, total)

    def _close_download_dialog(self):
        if self._download_dialog is not None:
            dialog = self._download_dialog
            self._download_dialog = None  # clear first: close() re-enters reject paths
            # dismiss() skips the overridden reject(), so closing after a SUCCESS
            # or a failure does not re-emit `canceled` (Qt's default
            # closeEvent -> reject() chain would have fired it every time).
            dialog.dismiss()

    def _on_installer_downloaded(self, path: str):
        self._close_download_dialog()
        # The installer is never run unless the user asks for it here.
        run_requested = ConfirmDialog.ask(
            QApplication.activeWindow(), "دانلود کامل شد", "نصب‌کننده اجرا شود؟",
            glyph=APP_CONFIG.FAS.FA_ARROWS_ROTATE, danger=False,
            confirm_text="اجرا", cancel_text="بعداً")
        if run_requested:
            logger.info(f"Launching installer {path}")
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            logger.info(f"Installer saved to {path}")

    def _on_download_failed(self, reason: str):
        self._close_download_dialog()
        if reason == "canceled":
            logger.info("Update download canceled.")
            return
        logger.error(f"Update download failed: {reason}")
        # No automatic redirect: a checksum failure deserves the user's attention
        # instead of a browser window quietly opening on the releases page.
        ConfirmDialog.notify(
            QApplication.activeWindow(), "دانلود بروزرسانی",
            "دانلود بروزرسانی ناموفق بود.",
            detail="می‌توانید نصب‌کننده را به‌صورت دستی از صفحه Releases دریافت کنید.",
            danger=True, glyph=APP_CONFIG.FAS.FA_CIRCLE_EXCLAMATION)

    def _on_holidays_updated(self):
        logger.info("Holiday data updated; refreshing calendar and tray icon.")
        self.holidays_cache = resolve_holidays_store()
        self.calendar_widget.set_holidays(self.holidays_cache)
        # Refresh an open Holiday Viewer too, so it never keeps showing the
        # previous holiday cache.
        if self.holiday_viewer_window is not None and self.holiday_viewer_window.isVisible():
            self.holiday_viewer_window.set_holidays(self.holidays_cache)
        self.update_tray_icon(force=True)

    def _on_no_updates(self):
        # Manual-check messages live in _on_round_finished, so one end-of-round
        # handler can cover every app/holidays combination; this signal only
        # logs.
        logger.info("No updates available (app and holiday data current).")

    def _on_check_failed(self, reason: str):
        # Only bookkeeping here: the offline dialog lives in _on_round_finished
        # so the holiday outcome can choose the right wording.
        logger.warning(f"Update check failed: {reason}")

    def _on_round_finished(self, app_state: str, holidays_state: str):
        """End-of-round reporting.

        Automatic rounds stay quiet and only log. Manual rounds get exactly ONE
        message covering both outcomes, from the matrix:

        | app          | holidays | message                                        |
        |--------------|----------|------------------------------------------------|
        | current      | updated  | holiday file refreshed                         |
        | current      | current  | both up to date                                |
        | current      | failed   | app current, holiday check failed              |
        | unavailable  | any      | newer release exists, safe download impossible |
        | failed       | updated  | holidays refreshed, app check failed           |
        | failed       | other    | existing offline dialog                        |
        | update found | any      | the update popup (+ line if holidays new)      |

        A failed holiday fetch also arms the quiet holidays-only retry for
        automatic rounds while the auto-check toggle is on - it never touches the
        app verdict.
        """
        self._round_was_manual = self._manual_update_check
        self._manual_update_check = False  # consumed: the round is over
        self._round_holidays_state = holidays_state

        if app_state == APP_STATE_SKIPPED:
            # A quiet holidays-only refresh (the retry path): never message.
            self._handle_holidays_round_bookkeeping(holidays_state)
            # A manual press that arrived DURING this refresh queued a full
            # check - release it now, with the manual flag set, so it reports
            # to the user like any manual round.
            if self._queued_full_check_after_holidays:
                self._queued_full_check_after_holidays = False
                logger.info("Running the full update check queued behind the holiday refresh.")
                self._check_for_updates(manual=True)
            return

        if holidays_state == HOLIDAYS_STATE_UPDATED:
            self._holiday_retries = 0
        else:
            self._handle_holidays_round_bookkeeping(holidays_state)

        if not self._round_was_manual:
            return
        if app_state == APP_STATE_UPDATE_FOUND:
            # The deferred popup carries the report (and the extra holiday line).
            return
        # The update popup outranks every notice: a manual result arriving while
        # the popup is open (or already scheduled) must never stack a notice on
        # top of the user's decision. Bring the popup forward instead. This
        # guards UNAVAILABLE, every CURRENT wording and both FAILED wordings.
        if self._update_dialog_open or self._update_popup_pending:
            if self._active_update_popup is not None:
                self._active_update_popup.raise_()
                self._active_update_popup.activateWindow()
            return
        if app_state == APP_STATE_UNAVAILABLE:
            # A newer release EXISTS but cannot be offered safely (no installer
            # asset, no valid sha256 digest, untrusted URL). Answering «بروز
            # است» would be false; the release needs fixing upstream, and no
            # clean "last checked" is stamped so it is re-checked instead of
            # waiting out the 24h gate.
            ConfirmDialog.notify(
                QApplication.activeWindow(), "بررسی بروزرسانی",
                "نسخه جدید موجود است اما دانلود امن آن ممکن نیست.",
                danger=True, glyph=APP_CONFIG.FAS.FA_CIRCLE_EXCLAMATION,
                key=UPDATE_CHECK_NOTICE_KEY)
            return
        if app_state == APP_STATE_CURRENT:
            if holidays_state == HOLIDAYS_STATE_UPDATED:
                ConfirmDialog.notify(
                    QApplication.activeWindow(), "بررسی بروزرسانی",
                    "فایل تعطیلات به‌روزرسانی شد.",
                    glyph=APP_CONFIG.FAS.FA_ARROWS_ROTATE,
                    key=UPDATE_CHECK_NOTICE_KEY)
            elif holidays_state == HOLIDAYS_STATE_CURRENT:
                ConfirmDialog.notify(
                    QApplication.activeWindow(), "بررسی بروزرسانی",
                    "برنامه و فایل تعطیلات بروز است.",
                    glyph=APP_CONFIG.FAS.FA_ARROWS_ROTATE,
                    key=UPDATE_CHECK_NOTICE_KEY)
            else:
                ConfirmDialog.notify(
                    QApplication.activeWindow(), "بررسی بروزرسانی",
                    "برنامه بروز است؛ بررسی فایل تعطیلات ناموفق بود.",
                    glyph=APP_CONFIG.FAS.FA_ARROWS_ROTATE,
                    key=UPDATE_CHECK_NOTICE_KEY)
        elif app_state == APP_STATE_FAILED:
            if holidays_state == HOLIDAYS_STATE_UPDATED:
                ConfirmDialog.notify(
                    QApplication.activeWindow(), "بررسی بروزرسانی",
                    "فایل تعطیلات به‌روزرسانی شد، اما بررسی برنامه ناموفق بود.",
                    danger=True, glyph=APP_CONFIG.FAS.FA_WIFI,
                    key=UPDATE_CHECK_NOTICE_KEY)
            else:
                ConfirmDialog.notify(
                    QApplication.activeWindow(), "بررسی بروزرسانی",
                    "بررسی بروزرسانی ناموفق بود. اتصال اینترنت را بررسی کنید.",
                    danger=True, glyph=APP_CONFIG.FAS.FA_WIFI,
                    key=UPDATE_CHECK_NOTICE_KEY)

    def _handle_holidays_round_bookkeeping(self, holidays_state: str):
        """Retry bookkeeping for the quiet holiday fetch.

        A quiet retry is BACKGROUND network traffic, so it is armed only after
        an AUTOMATIC round while the auto-check toggle is on. A manual round
        already reported the failure to the user (they can press again), and a
        user who switched «بررسی خودکار بروزرسانی» off opted out of background
        checks entirely. Skipped rounds are themselves automatic retry rounds,
        so they can re-arm the next attempt up to the session cap.
        """
        if holidays_state != HOLIDAYS_STATE_FAILED:
            self._holiday_retries = 0
            return
        if self._round_was_manual:
            return
        if not self._auto_check_enabled():
            logger.info("Holiday refresh failed; quiet retry suppressed "
                        "(automatic checks are disabled).")
            return
        if self._holiday_retries >= HOLIDAY_RETRY_MAX_ATTEMPTS:
            logger.warning(
                f"Holiday refresh failed; retry cap "
                f"({HOLIDAY_RETRY_MAX_ATTEMPTS}) reached for this session.")
            return
        self._holiday_retries += 1
        delay_min = HOLIDAY_RETRY_DELAY_MS // 60000
        logger.warning(
            f"Holiday refresh failed; quiet retry "
            f"{self._holiday_retries}/{HOLIDAY_RETRY_MAX_ATTEMPTS} in {delay_min} minutes.")
        QTimer.singleShot(HOLIDAY_RETRY_DELAY_MS, self._retry_holiday_check)

    def _retry_holiday_check(self):
        """The quiet holidays-only refetch; reports via round_finished(skipped).

        The toggle is re-checked here too, so a retry armed before the user
        switched «بررسی خودکار بروزرسانی» off is dropped instead of firing
        background traffic anyway.
        """
        if not self._auto_check_enabled():
            logger.info("Holiday retry dropped: automatic checks are disabled.")
            return
        if not self.update_checker.check_holidays():
            logger.info("Holiday retry skipped: another check round is in flight.")

    @staticmethod
    def _build_global_stylesheet() -> str:
        return global_scrollbar_stylesheet(APP_CONFIG.get_current_palette())

    def _notify_save_failed(self):
        """Themed failure notice for interactive event saves.

        The EventService calls this via ``on_save_error`` after restoring the
        in-memory state, so the message can honestly claim the current data was
        kept.
        """
        ConfirmDialog.notify(
            QApplication.activeWindow(), "ذخیره رویدادها",
            "ذخیره رویدادها ناموفق بود؛ تغییرات فعلی حفظ شده است.",
            danger=True, glyph=APP_CONFIG.FAS.FA_SAVE)

    def _refresh_after_events_changed(self):
        """Push a committed store change to the calendar, tray and manager.

        Subscribed as the service's ``on_store_changed`` hook, so this one
        composition refreshes every mutation path: the wrappers below, the
        event manager's own edit/delete/import, the calendar's context menu.
        A committed save can itself introduce an expired event (a past-dated
        auto-delete add), so the expiry cleanup rides along quietly first;
        the commit it makes is announced by this already-running composition
        (the service swallows re-entrant announcements), and the steps below
        run once on the settled store."""
        if self.calendar_widget is None:
            # The store is built and cleaned before the calendar exists: the
            # calendar reads the settled store straight from its constructor
            # and the tray refreshes on its own init path.
            return
        self.event_service.clean_expired(notify=False)
        self.calendar_widget.set_user_events(self.user_events)
        self.update_tray_icon(force=True)
        self._refresh_event_manager()

    def add_user_event(self, jdate: jdatetime.date, text: str, recurrence: str = RECURRENCE_NONE,
                       remove_after_finish: bool = False):
        """Add an event on ``jdate``; an event of the same recurrence is replaced.

        Keyed, not date-scoped: a date may show several events with different
        recurrences, and adding one never removes the others. All store rules,
        the transactional save and the post-save refresh live in the service
        and its ``on_store_changed`` hook; this is only the request API the
        calendar's signals and tests call.
        """
        self.event_service.add(jdate, text, recurrence, remove_after_finish)

    def update_user_event_by_key(self, key: str, jdate: jdatetime.date, text: str,
                                 recurrence: str = RECURRENCE_NONE,
                                 remove_after_finish: bool = False,
                                 merge_into: str = ""):
        """Edit the event stored under ``key``, leaving every other event alone.

        The by-key path exists because a day can hold several events with
        different keys, and editing one of them must not touch the rest. A
        non-empty ``merge_into`` carries the key the user confirmed folding this
        edit into, for the case where the new recurrence would otherwise land on
        an event that already exists. The store's own save transaction decides
        the outcome, so there is no second (fallible) path to roll back.
        """
        self.event_service.update_key(key, jdate, text, recurrence, remove_after_finish,
                                      merge_into or None)

    def remove_user_event_by_key(self, key: str):
        """Remove one store entry by its key.

        The by-key path exists because a day can hold several events with
        DIFFERENT keys: deleting by date would take the whole day's set with
        the one the user pointed at. The store's own save transaction decides
        the outcome, so there is no second (fallible) path to roll back.
        """
        self.event_service.delete_key(key)

    def remove_user_event(self, jdate: jdatetime.date, save: bool = True):
        """Remove every event variant matching ``jdate`` (specific, yearly, monthly)."""
        self.event_service.remove_for_date(jdate, commit=save)

    def _clean_expired_events(self):
        # Background cleanup (startup / midnight / time-change / minute tick):
        # the service logs quietly instead of raising a modal from a timer, and
        # any committed cleanup refreshes the surfaces through the store hook.
        self.event_service.clean_expired(notify=False)

    def _refresh_event_manager(self):
        """Keep an open event-manager window in sync with store mutations that
        happen elsewhere (calendar context menu, import, expiry cleanup)."""
        if self.event_manager_window is not None and self.event_manager_window.isVisible():
            self.event_manager_window.refresh_list()

    def update_tray_icon(self, force: bool = False):
        new_date = jdatetime.date.today()
        last_date = getattr(self, '_last_tray_date', None)
        if not force and new_date == last_date:
            return
        date_changed = new_date != last_date
        # The tray tracks its own date rather than reading it back from the
        # calendar widget, so the icon never depends on widget state.
        self._last_tray_date = new_date

        if date_changed and self.calendar_widget is not None:
            # The minute tick notices a date change too, so a sleep across
            # midnight still cleans expired events (no WM_TIMECHANGE involved).
            self._clean_expired_events()

        # jdatetime renders itself as an empty string under an empty format
        # spec, so the date is stringified explicitly instead of logged blank.
        logger.info(f"Updating tray icon for new date: {str(new_date)}")
        self.calendar_widget.current_date = new_date
        if self.calendar_widget.isVisible():
            self.calendar_widget.fill_calendar_grid()

        day_str_persian = to_persian_digits(new_date.day)

        # Every event occurring today, not just the winner: the tray tooltip is the
        # only always-visible surface for a day with several events, and silently
        # dropping the monthly one behind a one-time entry made it look absent.
        day_events = events_on_date(self.user_events, new_date)
        is_user_event = bool(day_events)
        is_holiday = bool(new_date.weekday() == 6 or self.holidays_cache.get(new_date.year, {}).get((new_date.month, new_date.day)))

        color = APP_CONFIG.TRAY_ICON_DARK_COLOR if self.current_theme == APP_CONFIG.Theme.DARK else APP_CONFIG.TRAY_ICON_LIGHT_COLOR
        if is_user_event:
            color = APP_CONFIG.current_palette['ACCENT_COLOR']
        elif is_holiday:
            color = APP_CONFIG.current_palette['HOLIDAY_COLOR']

        pixmap = create_tray_pixmap(day_str_persian, color)
        self.setIcon(QIcon(pixmap))

        weekday_name = persian_weekday_name(new_date.weekday())
        month_name = persian_month_name(new_date.month)

        date_str = f"{new_date.year}/{new_date.month:02d}/{new_date.day:02d}"
        month_written_persian = f"\u200F{new_date.day:02d} {month_name} {new_date.year}"

        tooltip_lines = [weekday_name, date_str, month_written_persian]

        if is_holiday:
            holiday_reasons = self.holidays_cache.get(new_date.year, {}).get((new_date.month, new_date.day), [])
            if holiday_reasons:
                tooltip_lines.append("تعطیلی:")
                tooltip_lines.extend(holiday_reasons)
        if is_user_event:
            # The header is plural once more than one event occurs today, so the
            # plural form reads as a section rather than a label on one line.
            tooltip_lines.append("رویدادها:" if len(day_events) > 1 else "رویداد:")
            for _key, entry in day_events:
                tooltip_lines.extend(str(entry.get("text", "")).split('\n'))

        self.setToolTip(self._fit_tooltip(tooltip_lines))

    @staticmethod
    def _fit_tooltip(lines: list) -> str:
        """Trim a tooltip to Windows' ~128-char cap, lowest priority first.

        Lines are already built highest-priority-first (weekday, date, holiday
        reasons, then the event text), so dropping from the end sacrifices the
        event before it ever touches the identity lines; if even the identity
        lines overflow, the last one is ellipsis-trimmed instead - and if even
        THAT cannot shrink the total (pathological first lines), the joined
        text is hard-cut rather than looping forever: the fallback branch only
        ever trims the last line, so overflow coming from the earlier lines
        alone would otherwise never terminate.
        """
        while len("\n".join(lines)) > WINDOWS_TOOLTIP_MAX_CHARS:
            if len(lines) > 3:
                lines.pop()
            else:
                trimmed = lines[-1][:max(WINDOWS_TOOLTIP_MAX_CHARS - 1, 0)].rstrip() + "…"
                if trimmed == lines[-1]:
                    # The last line cannot shrink further and the total still
                    # overflows: the earlier identity lines are the problem.
                    return "\n".join(lines)[:WINDOWS_TOOLTIP_MAX_CHARS]
                lines[-1] = trimmed
        return "\n".join(lines)

    def _setup_context_menu(self):
        # The menu's composition lives beside the menu widgets (tray_menu.py);
        # the state its rows drive stays owned here (the _toggle_* callbacks).
        self.setContextMenu(build_tray_menu(self))

    def _toggle_always_on_top(self, checked: bool):
        self.always_on_top = checked
        self.settings.setValue(APP_CONFIG.ALWAYS_ON_TOP_SETTING_KEY, checked)
        self.calendar_widget.set_always_on_top(checked)
        logger.info(f"Calendar always-on-top {'enabled' if checked else 'disabled'}.")

    def _toggle_auto_update_check(self, checked: bool):
        self.settings.setValue(APP_CONFIG.UPDATE_CHECK_ENABLED_SETTING_KEY, checked)
        logger.info(f"Automatic update check {'enabled' if checked else 'disabled'}.")
        # No timer stop/start: the recurring auto-check timer consults this
        # setting on every firing, so the next hourly tick simply obeys it.

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            # Toggle the whole calendar. Any open event editor is a child of
            # the calendar (and hideEvent dismisses it), so a tray click must
            # never just close the editor and leave the calendar up.
            if self.calendar_widget.isVisible():
                self.calendar_widget.hide()
            elif self._tray_click_dismissed_the_popup():
                # The press half of this very click already dismissed the
                # unpinned popup; its release completes the toggle instead of
                # reopening what the same click just closed.
                pass
            else:
                self.show_calendar()

    def _cursor_is_over_tray(self) -> bool:
        """Whether the cursor is over the tray icon right now - an unknown tray
        geometry counts as over the icon, the way it always has."""
        tray_geometry = self.geometry()
        return not tray_geometry.isValid() or tray_geometry.contains(QCursor.pos())

    def _tray_click_dismissed_the_popup(self) -> bool:
        """True when this tray click's own press dismissed the unpinned popup.

        The verdict comes from the dismissal itself, not from a cursor check at
        click time: the press hides the popup and the icon's click is only
        delivered on the release, up to a second later, so a separate tray
        click inside that window has the cursor over the icon just the same.
        A dismissal recorded away from the icon leaves the marker False, so
        dismissing the popup elsewhere and then clicking the icon still opens.
        """
        return self.calendar_widget.consume_outside_click_dismissal()

    def show_calendar(self):
        # Stay on the month the user was browsing; the calendar snaps back to today
        # automatically on day changes (midnight timer / system time change).
        self.calendar_widget.fill_calendar_grid()
        self.calendar_widget.update_styles()

        # Position on the monitor that actually hosts the tray icon (not blindly
        # the primary), and guard the no-screen case (RDP disconnect).
        tray_geom = self.geometry()
        screen = QApplication.screenAt(tray_geom.center()) if tray_geom.isValid() else None
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is None:
            screens = QApplication.screens()
            screen = screens[0] if screens else None
        if screen is None:
            logger.error("No screen available; showing the calendar without positioning.")
            self.calendar_widget.show()
            return
        screen_geo = screen.availableGeometry()
        widget_size = self.calendar_widget.size()
        x = screen_geo.right() - widget_size.width() - 10 # Small gap so the widget doesn't touch the tray icon
        y = screen_geo.bottom() - widget_size.height() - 45 # Fallback offset to keep widget above taskbar
        if tray_geom.isValid():
            x = tray_geom.center().x() - widget_size.width() // 2
            y = tray_geom.top() - widget_size.height() - 5
            x = max(screen_geo.left(), min(x, screen_geo.right() - widget_size.width()))
            y = max(screen_geo.top(), min(y, screen_geo.bottom() - widget_size.height()))
        self.calendar_widget.move(int(x), int(y))
        self.calendar_widget.show()
        self.calendar_widget.activateWindow()

    def _prewarm_calendar(self):
        # Prewarming prepares a HIDDEN window for its first real open; if the
        # user beat the 1s timer to it, the calendar is legitimately visible and
        # must not be yanked off-screen.
        if self.calendar_widget.isVisible():
            return
        self.calendar_widget.move(-10000, -10000)
        self.calendar_widget.show()
        # A bare processEvents() dispatches USER INPUT too, so a tray click
        # landing inside this tick saw the (hidden, off-screen) calendar as
        # visible and only hid it again - the first click after launch was
        # swallowed. Excluding input events keeps the prewarm to paint/layout
        # delivery; the click is handled after the calendar is hidden and the
        # toggle logic sees the real state.
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
        self.calendar_widget.hide()

    def _cycle_theme_choice(self):
        """Cycle the appearance preference: system → light → dark → system.

        Every stop of the cycle is persisted explicitly - including "system",
        which re-detects Windows and keeps following it via
        ``_handle_system_theme_change``: that persistence is what lets the
        cycle return to following Windows.
        """
        order = APP_CONFIG.THEME_CHOICES
        next_choice = order[(order.index(self._theme_choice()) + 1) % len(order)]
        self.settings.setValue(APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY, next_choice)
        self.current_theme = (self._get_windows_theme()
                              if next_choice == APP_CONFIG.Theme.SYSTEM else next_choice)
        logger.info(f"Theme preference set to {next_choice}.")
        self._apply_theme()

    def _set_startup_registry(self, enable: bool) -> bool:
        """Write/remove the autostart Run key; True only when the registry now
        matches ``enable`` (the UI setting is only updated after this succeeds)."""
        if not sys.platform.startswith('win'):
            logger.warning("Auto-start is only supported on Windows.")
            return False
        if enable:
            # The path must be quoted to support spaces when the app is frozen
            # or installed in Program Files.
            executable_path = _startup_executable_value()
            if not self.startup_registry.write(executable_path):
                logger.error(f"Could not write the startup registry key ({RUN_KEY_PATH}).")
                return False
            logger.info(f"Set startup registry key to: {executable_path}")
            return True
        if not self.startup_registry.delete():
            logger.warning("Could not remove startup key (it may not exist).")
            return False
        # delete() also reports success for an already-absent value, so the log
        # says both: a stale entry left by a failed delete is still healable.
        logger.info("Startup registry key removed (or already absent).")
        return True

    def _startup_entry_exists(self) -> bool:
        """True when the HKCU Run key currently holds a ShamsiTray value.

        Read-only probe used to reconcile a disabled preference with a stale
        entry; unknown states (unreadable registry) conservatively report False
        so healing never fights a registry it cannot read.
        """
        if not sys.platform.startswith('win'):
            return False
        return self.startup_registry.read() is not None

    def _toggle_open_at_boot(self, checked: bool):
        # The application setting and the menu checkbox may only claim the new
        # state AFTER the registry write is known to have succeeded; otherwise a
        # failed write left settings.json saying "enabled" while Windows never
        # started the app.
        if not self._set_startup_registry(checked):
            logger.error("Autostart registry update failed; application setting left unchanged.")
            self._setup_context_menu()  # rebuild so the checkbox shows the real state
            return
        self.is_open_at_login = checked
        self.settings.setValue(APP_CONFIG.AUTO_START_SETTING_KEY, checked)
        logger.info(f"Setting 'Open at Login' to {checked}.")

    def _validate_and_apply_startup_setting(self):
        """Align the Windows Run entry with the autostart preference.

        Opt-out behaviour, three states:
        - Missing preference (first initialization of the setting / fresh
          install): the Run entry is created FIRST and the preference is
          persisted only after the registry write succeeded. A failed write
          leaves the preference unset (next launch retries the default) and the
          in-memory state honestly OFF, so the checkbox can never claim a
          startup that Windows will not do.
        - Existing preference OFF: stays OFF - never re-enabled - and a stale Run
          entry (e.g. left behind by a failed delete once) is healed away so
          Windows and the app agree.
        - Existing preference ON: the Run value is validated to point at this
          executable and re-applied when it drifted.
        """
        if not sys.platform.startswith('win'):
            return
        if not self._autostart_pref_exists:
            logger.info("No autostart preference saved yet; applying the first-run default (enabled).")
            if self._set_startup_registry(True):
                self.is_open_at_login = True
                self.settings.setValue(APP_CONFIG.AUTO_START_SETTING_KEY, True)
            else:
                # Do not pretend the preference was applied: keep the app state
                # consistent with the registry result and leave the setting unset
                # so the next launch retries the default.
                self.is_open_at_login = False
                logger.error("Autostart registry write failed; preference left unset and shown as disabled.")
            return
        if not self.is_open_at_login:
            # Existing explicit OFF: remain OFF. Only heal a stale Run entry.
            if self._startup_entry_exists():
                logger.warning("Startup Run entry exists despite a disabled preference; removing it.")
                self._set_startup_registry(False)
            return
        logger.info("Validating startup registry key...")
        expected_value = _startup_executable_value()
        current_value = self.startup_registry.read()
        if current_value == expected_value:
            logger.info("Startup registry key is correct.")
            return
        if current_value is None:
            logger.warning("Startup registry key not found.")
        else:
            logger.warning(f"Startup registry key is incorrect. Found: '{current_value}', Expected: '{expected_value}'")
        logger.info("Re-applying startup registry key.")
        self._set_startup_registry(True)

    def _show_or_raise(self, window_attr: str, factory):
        """Shared window-opener: create+show the window stored on ``window_attr``,
        or raise/activate the existing one. Returns the window."""
        window = getattr(self, window_attr)
        if window is None or not window.isVisible():
            window = factory()
            setattr(self, window_attr, window)
            window.show()
        elif window.windowState() & Qt.WindowState.WindowMinimized:
            # A minimized window still reports visible; activateWindow alone
            # never restores it on Windows.
            window.showNormal()
        window.raise_()
        window.activateWindow()
        return window

    def _open_date_converter(self):
        self._show_or_raise("converter_window", DateConverterWindow)

    def _open_event_manager(self):
        self._show_or_raise("event_manager_window",
                            lambda: EventManagerWindow(self))

    def _open_holiday_viewer(self):
        self._show_or_raise("holiday_viewer_window",
                            lambda: HolidayViewerWindow(self.holidays_cache))
