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
from PyQt6.QtCore import QCoreApplication, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices, QIcon
from PyQt6.QtWidgets import QApplication, QFileDialog, QSystemTrayIcon, QWidgetAction

from config import APP_CONFIG
from core.event_service import EventService
from ui.windows.calendar_window import PersianCalendarWidget
from ui.windows.converter_window import DateConverterWindow
from ui.windows.event_manager_window import EventManagerWindow
from ui.windows.holiday_viewer_window import HolidayViewerWindow
from ui.widgets.menu_widgets import MenuActionWidget, ThemeToggleActionWidget, TrayMenu
from ui.widgets.checkbox import IconCheckboxActionWidget
from ui.widgets.confirm_dialog import ConfirmDialog
from ui.widgets.download_dialog import DownloadUpdateDialog
from core.update_checker import DAY_MS, UpdateChecker, file_sha256, should_notify
from utils.date_utils import ms_until_midnight, persian_month_name, persian_weekday_name, to_persian_digits
from utils.event_io import (
    RECURRENCE_NONE,
    events_for_date,
    export_events_to_file,
    import_events_from_file,
)
from utils.holiday_io import read_version, resolve_holidays_store
from utils.json_settings import JsonSettings
from utils.logger import setup_logging
from utils.native_events import TimeChangeEventFilter
from utils.ui_helpers import create_tray_pixmap, global_scrollbar_stylesheet

if TYPE_CHECKING:
    from ui.windows.tutorial_window import TutorialWindow

if sys.platform == 'win32':
    import winreg

logger = setup_logging(__name__)

# A failed AUTO check no longer black-holes for 24h: it is retried on this
# cadence, at most this many times per session (reset on any clean check).
AUTO_CHECK_RETRY_DELAY_MS = 10 * 60 * 1000
AUTO_CHECK_MAX_RETRIES = 3

# Windows silently truncates tray tooltips at ~128 characters. Build the tooltip
# by priority (weekday, date, holidays, then the event text) and trim the
# lowest-priority content ourselves instead of losing the tail mid-line.
WINDOWS_TOOLTIP_MAX_CHARS = 127

# Autostart is OPT-OUT: a brand-new installation has no saved preference yet and
# defaults to ENABLED. An existing explicit False must never be read as "missing"
# and re-enabled, which is why the missing-vs-False distinction is made with
# JsonSettings.contains() instead of a value() default.
AUTOSTART_FIRST_RUN_DEFAULT = True

_RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


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

    def __init__(self, settings: Optional[JsonSettings] = None):
        super().__init__()
        self.settings = settings if settings is not None else JsonSettings()
        self.holidays_cache = resolve_holidays_store()
        # The event store is owned by the EventService: every mutation and every
        # save goes through it, so the calendar, the tray and the disk can never
        # disagree. ``user_events`` below is a live view of ``self._events.events``.
        self._events = EventService()
        # The service stays Qt-free; the application supplies the themed failure
        # dialog for interactive saves (background cleanup passes notify=False
        # inside the service and never calls this).
        self._events.on_save_error = self._notify_save_failed
        # Window references are created lazily; they must exist (as None) before
        # _clean_expired_events can run, because it refreshes the calendar when
        # events expire. Previously this raised AttributeError on startup whenever
        # an expired auto-delete event was pending.
        self.calendar_widget: Optional[PersianCalendarWidget] = None
        self.converter_window: Optional[DateConverterWindow] = None
        self.event_manager_window: Optional[EventManagerWindow] = None
        self.holiday_viewer_window: Optional[HolidayViewerWindow] = None
        self.tutorial_window: Optional["TutorialWindow"] = None

        self._clean_expired_events()

        self.calendar_widget = PersianCalendarWidget(self.holidays_cache, self.user_events)
        self.calendar_widget.event_added.connect(self.add_user_event)
        self.calendar_widget.event_removed.connect(self.remove_user_event)

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
        return self._events.events

    @user_events.setter
    def user_events(self, value: Dict[str, dict]):
        self._events.events.clear()
        self._events.events.update(value)

    def _get_windows_theme(self) -> str:
        """Detects if Windows is in light or dark mode. Defaults to dark if detection fails."""
        if not sys.platform == 'win32':
            return APP_CONFIG.Theme.DARK
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return APP_CONFIG.Theme.LIGHT if value == 1 else APP_CONFIG.Theme.DARK
        except Exception as e:
            logger.warning(f"Could not detect Windows theme, defaulting to dark: {e}")
            return APP_CONFIG.Theme.DARK

    def _load_settings(self):
        # Autostart is opt-out (AUTOSTART_FIRST_RUN_DEFAULT): a MISSING
        # preference means the setting has never been initialized (fresh install)
        # and defaults to enabled - it must NOT be read as "the user disabled
        # it". contains() makes the missing-vs-False distinction; the preference
        # is only persisted after the registry agrees.
        self._autostart_pref_exists = self.settings.contains(APP_CONFIG.AUTO_START_SETTING_KEY)
        if self._autostart_pref_exists:
            self.is_open_at_login = self.settings.value(APP_CONFIG.AUTO_START_SETTING_KEY, False, type=bool)
        else:
            self.is_open_at_login = AUTOSTART_FIRST_RUN_DEFAULT

        saved_theme = self.settings.value(APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY, None)
        if saved_theme:
            self.current_theme = saved_theme
            logger.info(f"Loaded user-preferred theme: {self.current_theme}")
        else:
            self.current_theme = self._get_windows_theme()
            logger.info(f"No user theme preference found. Detected system theme: {self.current_theme}")

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
        self.event_filter = TimeChangeEventFilter(self._handle_system_time_change)
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

    def _handle_system_time_change(self):
        # System time changes (manual adjustment, DST) can invalidate the current date and scheduled midnight timers, so we force a full refresh and reschedule.
        logger.info("System time change detected. Forcing tray icon update and rescheduling midnight check.")
        self._clean_expired_events()
        if self.calendar_widget:
            self.calendar_widget.go_to_today()
        self.update_tray_icon(force=True)
        self.schedule_next_midnight_check()

    # --- Update checks ---

    def _setup_update_checker(self):
        self._manual_update_check = False
        self._update_dialog_open = False
        # True between the scheduling of a deferred popup and the popup actually
        # opening; closes the one-tick window in which a second
        # app_update_available could schedule a duplicate dialog.
        self._update_popup_pending = False
        self._download_dialog = None
        self._auto_check_retries = 0
        data_version = read_version(APP_CONFIG.HOLIDAYS_STORE_PATH)
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
        self.update_checker.check_concluded.connect(self._on_check_concluded)
        self.update_checker.download_progress.connect(self._on_download_progress)
        self.update_checker.installer_downloaded.connect(self._on_installer_downloaded)
        self.update_checker.download_failed.connect(self._on_download_failed)
        QTimer.singleShot(30000, self._auto_check_updates)

    def _auto_check_updates(self):
        if not self.settings.value(APP_CONFIG.UPDATE_CHECK_ENABLED_SETTING_KEY, True, type=bool):
            return
        last_check_ms = self.settings.value(APP_CONFIG.LAST_UPDATE_CHECK_SETTING_KEY, 0, type=int) or 0
        now_ms = int(datetime.datetime.now().timestamp() * 1000)
        if now_ms - last_check_ms < DAY_MS:
            logger.debug("Skipping automatic update check (last check was less than 24h ago).")
            return
        self._check_for_updates(manual=False)

    def _check_for_updates(self, manual: bool):
        # No "last checked" stamp here: writing it up front is how a failed
        # check used to count as done and silence auto-checks for a day. The
        # stamp moves to _on_check_concluded, where a real answer arrived.
        #
        # The manual flag moves behind check()'s return value: setting it
        # unconditionally mis-flagged an in-flight AUTO round as manual when a
        # manual check arrived while one was already running.
        started = self.update_checker.check()
        if started:
            self._manual_update_check = manual
            logger.info(f"Checking for updates ({'manual' if manual else 'automatic'}).")

    def _on_check_concluded(self, failed: bool):
        """End of one check round: stamp success, schedule retries on failure."""
        if not failed:
            self._auto_check_retries = 0
            now_ms = int(datetime.datetime.now().timestamp() * 1000)
            self.settings.setValue(APP_CONFIG.LAST_UPDATE_CHECK_SETTING_KEY, now_ms)
            return
        if not self._manual_update_check and self._auto_check_retries < AUTO_CHECK_MAX_RETRIES:
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
        # Defer the popup out of the checker's signal path: _conclude() emits
        # this signal and must still emit check_concluded afterwards. Running a
        # modal dialog in between blocked the conclusion mid-flight, and a check
        # started while the dialog was open reset the shared round state under
        # it - the re-entrancy behind the phantom "check failed; retry in 10
        # minutes" right after answering the popup.
        if self._update_dialog_open or self._update_popup_pending:
            return
        self._update_popup_pending = True
        QTimer.singleShot(0, lambda: self._show_update_popup(version, installer_url, sha256))

    def _show_update_popup(self, version: str, installer_url: str, sha256: str):
        self._update_popup_pending = False
        if self._update_dialog_open:
            return
        self._update_dialog_open = True
        try:
            # Themed three-way ask (the stock QMessageBox ignored the palette):
            # download = accent, ignore = red (it silences this version),
            # remind later = quiet ghost. Rotate glyph marks it as an update.
            choice = ConfirmDialog.choose(
                QApplication.activeWindow(), "بروزرسانی جدید",
                f"نسخه جدید {APP_CONFIG.APP_NAME} ({version}) موجود است.",
                glyph=APP_CONFIG.FAS.FA_ARROWS_ROTATE,
                actions=[("دانلود", "accent"),
                         ("نادیده گرفتن", "danger"),
                         ("بعداً یادآوری کن", "ghost")])
        finally:
            self._update_dialog_open = False
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
        # release: the user may have run the update before, declined to install,
        # and asked again later - re-downloading the same file was pure waste.
        # Without a digest there is nothing to verify against, so the safe path
        # is a fresh download.
        if sha256 and destination.exists():
            existing_digest = file_sha256(destination)
            if existing_digest is not None and existing_digest.lower() == sha256.lower():
                logger.info(f"Installer for {version} already downloaded and verified: {destination}")
                self._on_installer_downloaded(str(destination))
                return
        # Themed progress card matching the rest of the update flow; the
        # stock QProgressDialog ignored the palette entirely.
        dialog = DownloadUpdateDialog(version, QApplication.activeWindow())
        dialog.canceled.connect(self.update_checker.cancel_download)
        self._download_dialog = dialog
        dialog.show()
        logger.info(f"Downloading update {version} to {destination}")
        if not self.update_checker.download_installer(installer_url, destination, sha256):
            # Defense in depth for the rejected-request case: the dialog we just
            # opened has no download behind it and would freeze on screen, so
            # close it immediately (the pre-check above makes this path
            # unreachable today, but the dialog must never be left orphaned if
            # the guard ever races).
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
        # Themed ask matching the rest of the update flow; the installer is
        # not run unless the user asks for it here.
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
        # No automatic redirect: a checksum failure especially deserves a moment
        # of the user's attention ("this file failed verification") instead of a
        # browser window quietly opening on the releases page. Dialogs are titled
        # for the action they belong to, not the app name.
        ConfirmDialog.notify(
            QApplication.activeWindow(), "دانلود بروزرسانی",
            "دانلود بروزرسانی ناموفق بود.",
            detail="می‌توانید نصب‌کننده را به‌صورت دستی از صفحه Releases دریافت کنید.",
            danger=True, glyph=APP_CONFIG.FAS.FA_CIRCLE_EXCLAMATION)

    def _on_holidays_updated(self):
        logger.info("Holiday data updated; refreshing calendar and tray icon.")
        self.holidays_cache = resolve_holidays_store()
        self.calendar_widget.set_holidays(self.holidays_cache)
        # An open Holiday Viewer used to keep showing the old cache until it was
        # closed and reopened.
        if self.holiday_viewer_window is not None and self.holiday_viewer_window.isVisible():
            self.holiday_viewer_window.set_holidays(self.holidays_cache)
        self.update_tray_icon(force=True)

    def _on_no_updates(self):
        logger.info("No updates available.")
        if self._manual_update_check:
            ConfirmDialog.notify(
                QApplication.activeWindow(), "بررسی بروزرسانی",
                "برنامه و فایل تعطیلات بروز است.",
                glyph=APP_CONFIG.FAS.FA_ARROWS_ROTATE)

    def _on_check_failed(self, reason: str):
        logger.warning(f"Update check failed: {reason}")
        # A failure arriving while the update popup is already up must never
        # stack a second dialog on top of the user's decision: "remind later"
        # would otherwise appear to summon an unrelated offline error.
        if self._update_dialog_open or self._update_popup_pending:
            return
        if self._manual_update_check:
            ConfirmDialog.notify(
                QApplication.activeWindow(), "بررسی بروزرسانی",
                "بررسی بروزرسانی ناموفق بود. اتصال اینترنت را بررسی کنید.",
                danger=True,
                glyph=APP_CONFIG.FAS.FA_WIFI)

    @staticmethod
    def _build_global_stylesheet() -> str:
        # Shared builder in ui_helpers: no per-controller QSS inline.
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
        """Push a successful store mutation to the calendar, tray and manager."""
        self.calendar_widget.set_user_events(self.user_events)
        self.update_tray_icon(force=True)
        self._refresh_event_manager()

    def add_user_event(self, jdate: jdatetime.date, text: str, recurrence: str = RECURRENCE_NONE,
                       remove_after_finish: bool = False):
        """Add (or replace) the event shown for ``jdate`` (one event per date).

        All store rules and the transactional save live in the EventService;
        this wrapper only refreshes the UI on success.
        """
        if self._events.add(jdate, text, recurrence, remove_after_finish):
            self._refresh_after_events_changed()

    def remove_user_event(self, jdate: jdatetime.date, save: bool = True):
        """Remove every event variant matching ``jdate`` (specific, yearly, monthly)."""
        if self._events.remove_for_date(jdate, commit=save):
            self._refresh_after_events_changed()

    def _clean_expired_events(self):
        # Background cleanup (startup / midnight / time-change / minute tick):
        # the service logs quietly instead of raising a modal from a timer.
        if not self._events.clean_expired(notify=False):
            return
        if self.calendar_widget is not None:
            self.calendar_widget.set_user_events(self.user_events)
        self._refresh_event_manager()

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
        # The tray tracks its own date: piggy-backing on the calendar widget's
        # current_date was fragile, and the hasattr guard was always true after
        # __init__ anyway.
        self._last_tray_date = new_date

        if date_changed and self.calendar_widget is not None:
            # A sleep across midnight without a WM_TIMECHANGE left expired events
            # uncleaned until the next manual refresh - the minute tick now
            # notices the date change and runs the cleanup.
            self._clean_expired_events()

        logger.info(f"Updating tray icon for new date: {new_date}")
        self.calendar_widget.current_date = new_date
        if self.calendar_widget.isVisible():
            self.calendar_widget.fill_calendar_grid()

        day_str_persian = to_persian_digits(new_date.day)

        matched = events_for_date(self.user_events, new_date)
        user_event_text = matched[1].get("text") if matched else None
        is_user_event = bool(user_event_text)
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
            tooltip_lines.append("رویداد:")
            tooltip_lines.extend(user_event_text.split('\n'))

        self.setToolTip(self._fit_tooltip(tooltip_lines))

    @staticmethod
    def _fit_tooltip(lines: list) -> str:
        """Trim a tooltip to Windows' ~128-char cap, lowest priority first.

        Lines are already built highest-priority-first (weekday, date, holiday
        reasons, then the event text), so dropping from the end sacrifices the
        event before it ever touches the identity lines; if even the identity
        lines overflow, the last one is ellipsis-trimmed instead.
        """
        while len("\n".join(lines)) > WINDOWS_TOOLTIP_MAX_CHARS:
            if len(lines) > 3:
                lines.pop()
            else:
                lines[-1] = lines[-1][:max(WINDOWS_TOOLTIP_MAX_CHARS - 1, 0)].rstrip() + "…"
        return "\n".join(lines)

    def _setup_context_menu(self):
        menu = TrayMenu()
        palette = APP_CONFIG.get_current_palette()
        # Separator rows only provide spacing; TrayMenu paints the actual divider
        # lines with the same thickness everywhere: ceil(scale) full device rows,
        # matching how a native separator renders on a well-aligned position.
        menu.setStyleSheet(
            f"QMenu {{ background-color: {palette['BACKGROUND_COLOR']}; border: 1px solid {palette['MENU_BORDER_COLOR']}; border-radius: 8px; padding: 5px; }}"
            f"QMenu::separator {{ height: 11px; background-color: transparent; }}"
        )
        self._add_menu_action(menu, "تبدیل تاریخ", lambda: self._close_menu_then(self._open_date_converter))
        menu.add_divider()
        self._add_theme_toggle_action(menu)
        menu.add_divider()
        self._add_startup_action(menu)
        menu.add_divider()
        self._add_menu_action(menu, "مدیریت رویدادها", lambda: self._close_menu_then(self._open_event_manager))
        self._add_menu_action(menu, "مشاهده تعطیلات", lambda: self._close_menu_then(self._open_holiday_viewer))
        menu.add_divider()
        self._add_menu_action(menu, "بررسی بروزرسانی", lambda: self._close_menu_then(lambda: self._check_for_updates(manual=True)))
        menu.add_divider()
        self._add_menu_action(menu, "خروج", QApplication.quit)
        self.setContextMenu(menu)

    def _close_menu_then(self, callback):
        """Close the popup menu, then run callback once it has fully dismissed.
        Windows refuses to show modal dialogs (e.g. native file dialogs) while a
        popup menu is still tracking, so dialogs must be opened after the close."""
        menu = self.contextMenu()
        if menu:
            menu.close()
        QTimer.singleShot(50, callback)

    def _add_menu_action(self, menu, text, slot):
        action = QWidgetAction(self)
        widget = MenuActionWidget(text, parent=menu)
        widget.triggered.connect(slot)
        action.setDefaultWidget(widget)
        menu.addAction(action)

    def _add_theme_toggle_action(self, menu):
        action = QWidgetAction(self)
        widget = ThemeToggleActionWidget(lambda: self.current_theme, parent=menu)
        widget.triggered.connect(self._toggle_theme)
        action.setDefaultWidget(widget)
        menu.addAction(action)

    def _add_startup_action(self, menu):
        if not sys.platform.startswith('win'):
            return
        action = QWidgetAction(self)
        widget = IconCheckboxActionWidget("راه اندازی همراه با سیستم", self.is_open_at_login, parent=menu)
        widget.toggled.connect(self._toggle_open_at_boot)
        action.setDefaultWidget(widget)
        menu.addAction(action)

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            # Toggle the whole calendar. Any open event editor is a child of
            # the calendar (and hideEvent dismisses it), so a tray click must
            # never just close the editor and leave the calendar up.
            if self.calendar_widget.isVisible():
                self.calendar_widget.hide()
            else:
                self.show_calendar()

    def show_calendar(self):
        # Stay on the month the user was browsing; the calendar snaps back to today
        # automatically on day changes (midnight timer / system time change).
        self.calendar_widget.fill_calendar_grid()
        self.calendar_widget.update_styles()

        # Position on the monitor that actually hosts the tray icon (not blindly
        # the primary), and guard the no-screen case (RDP disconnect) that used
        # to dereference primaryScreen() unguarded.
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
        QApplication.processEvents()
        self.calendar_widget.hide()

    def _toggle_theme(self):
        self.current_theme = APP_CONFIG.Theme.LIGHT if self.current_theme == APP_CONFIG.Theme.DARK else APP_CONFIG.Theme.DARK
        self.settings.setValue(APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY, self.current_theme)
        logger.info(f"Theme toggled to: {self.current_theme}")
        self._apply_theme()

    def _set_startup_registry(self, enable: bool) -> bool:
        """Write/remove the autostart Run key; True only when the registry now
        matches ``enable`` (the UI setting is only updated after this succeeds)."""
        if not sys.platform.startswith('win'):
            logger.warning("Auto-start is only supported on Windows.")
            return False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, 0, winreg.KEY_ALL_ACCESS) as key:
                if enable:
                    executable_path = _startup_executable_value()
                    # Path must be quoted to support spaces when the app is frozen or installed in Program Files
                    winreg.SetValueEx(key, APP_CONFIG.APP_NAME, 0, winreg.REG_SZ, executable_path)
                    logger.info(f"Set startup registry key to: {executable_path}")
                else:
                    try:
                        winreg.DeleteValue(key, APP_CONFIG.APP_NAME)
                        logger.info("Removed startup registry key.")
                    except FileNotFoundError:
                        # The value is already gone: the desired state holds.
                        logger.warning("Could not remove startup key (it may not exist).")
            return True
        except FileNotFoundError:
            if not enable:
                logger.warning("Could not remove startup key (it may not exist).")
                return True
            logger.error(f"Could not find registry key path: {_RUN_KEY_PATH}")
            return False
        except Exception as e:
            logger.error(f"Error modifying Windows registry: {e}")
            return False

    def _startup_entry_exists(self) -> bool:
        """True when the HKCU Run key currently holds a ShamsiTray value.

        Read-only probe used to reconcile a disabled preference with a stale
        entry; unknown states (unreadable registry) conservatively report False
        so healing never fights a registry it cannot read.
        """
        if not sys.platform.startswith('win'):
            return False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
                winreg.QueryValueEx(key, APP_CONFIG.APP_NAME)
                return True
        except FileNotFoundError:
            return False
        except OSError as e:
            logger.warning(f"Could not read startup registry key: {e}")
            return False

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
        needs_update = True
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, 0, winreg.KEY_READ)
            current_value, _ = winreg.QueryValueEx(key, APP_CONFIG.APP_NAME)
            if current_value == expected_value:
                logger.info("Startup registry key is correct.")
                needs_update = False
            else:
                logger.warning(f"Startup registry key is incorrect. Found: '{current_value}', Expected: '{expected_value}'")
            winreg.CloseKey(key)
        except FileNotFoundError:
            logger.warning("Startup registry key not found.")
        except Exception as e:
            logger.error(f"Error reading startup registry key: {e}")
        if needs_update:
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
        window.activateWindow()
        return window

    def _open_date_converter(self):
        self._show_or_raise("converter_window", DateConverterWindow)

    def _open_event_manager(self):
        def _factory():
            window = EventManagerWindow(self)
            window.events_changed.connect(self._on_events_changed_by_manager)
            return window
        self._show_or_raise("event_manager_window", _factory)

    def _open_holiday_viewer(self):
        self._show_or_raise("holiday_viewer_window",
                            lambda: HolidayViewerWindow(self.holidays_cache))

    def _on_events_changed_by_manager(self):
        """The event manager mutated self.user_events; refresh calendar + tray."""
        self._clean_expired_events()
        self.calendar_widget.set_user_events(self.user_events)
        self.update_tray_icon(force=True)

    def import_events_from_dialog(self, parent=None) -> bool:
        """Reusable import flow for the event manager window. Returns True when events changed.

        The import is reconciled against the store by *visible date* before
        anything is applied. When it would replace existing events (exact-key
        overwrites, or same-date collisions across recurrence forms - e.g. an
        imported yearly «0000-08-01» taking over a stored one-time
        «1405-08-01»), a themed confirm lists the count first.

        The whole new state (merge + replaced-event removal + expiry cleanup) is
        computed in memory and saved EXACTLY ONCE, so a failed save can never
        leave a half-imported file on disk.
        """
        path, _ = QFileDialog.getOpenFileName(parent, "وارد کردن رویدادها", "", "JSON (*.json)")
        if not path:
            return False
        result = import_events_from_file(path)
        if result is None:
            ConfirmDialog.notify(parent, "وارد کردن رویدادها",
                                 "خواندن فایل رویدادها ناموفق بود.",
                                 danger=True, glyph=APP_CONFIG.FAS.FA_CIRCLE_EXCLAMATION)
            return False
        imported, skipped = result
        # Pure planning: nothing is mutated until the user confirms.
        plan = self._events.plan_import(imported)
        if plan.replaced_existing:
            detail = self._import_collision_detail(plan)
            count = to_persian_digits(len(plan.replaced_existing))
            confirmed = ConfirmDialog.ask(
                parent, "وارد کردن رویدادها",
                f"این فایل {count} رویداد موجود را جایگزین می‌کند.",
                detail=detail, confirm_text="جایگزینی", cancel_text="انصراف",
                danger=True, glyph=APP_CONFIG.FAS.FA_DOWNLOAD)
            if not confirmed:
                logger.info("Import canceled at the collision confirmation.")
                return False
        if not self._events.apply_import(plan):
            # The themed failure notice fires via the service's on_save_error;
            # in-memory state was rolled back to the pre-import store.
            return False
        if plan.internal_replaced:
            logger.info(f"Import folded {plan.internal_replaced} same-date duplicate "
                        f"entr{'y' if plan.internal_replaced == 1 else 'ies'} from the file (later entry won).")
        summary = f"{to_persian_digits(len(plan.applied))} رویداد وارد شد."
        if plan.replaced_existing:
            summary += f"\n{to_persian_digits(len(plan.replaced_existing))} رویداد جایگزین شد."
        if skipped:
            summary += f"\n{to_persian_digits(skipped)} ورودی نامعتبر نادیده گرفته شد."
        ConfirmDialog.notify(parent, "وارد کردن رویدادها", summary,
                             glyph=APP_CONFIG.FAS.FA_DOWNLOAD)
        self._refresh_after_events_changed()
        return True

    @staticmethod
    def _import_collision_detail(plan) -> str:
        """Preview of the existing events the import would replace.

        Text-only lines (the same style the delete confirmation uses), capped so
        a bulk import cannot build an endless dialog.
        """
        lines = []
        for _key, entry in list(plan.replaced_existing.items())[:6]:
            text = str(entry.get("text", ""))
            preview = text if len(text) <= 40 else text[:40] + "…"
            lines.append(preview)
        remaining = len(plan.replaced_existing) - len(lines)
        if remaining > 0:
            lines.append(f"… و {to_persian_digits(remaining)} مورد دیگر")
        return "\n".join(lines)

    def export_events_to_dialog(self, parent=None) -> bool:
        """Reusable export flow for the event manager window. Returns True on success."""
        if not self.user_events:
            ConfirmDialog.notify(parent, "خروجی گرفتن از رویدادها",
                                 "هیچ رویدادی برای خروجی گرفتن وجود ندارد.",
                                 glyph=APP_CONFIG.FAS.FA_UPLOAD)
            return False
        default_name = f"ShamsiTrayEvents-{jdatetime.date.today().strftime('%Y-%m-%d')}.json"
        path, _ = QFileDialog.getSaveFileName(parent, "خروجی گرفتن از رویدادها", default_name, "JSON (*.json)")
        if not path:
            return False
        if export_events_to_file(self.user_events, Path(path)):
            logger.info(f"Exported {len(self.user_events)} user events to {path}")
            ConfirmDialog.notify(parent, "خروجی گرفتن از رویدادها",
                                 "رویدادها با موفقیت خروجی گرفته شدند.",
                                 glyph=APP_CONFIG.FAS.FA_UPLOAD)
            return True
        ConfirmDialog.notify(parent, "خروجی گرفتن از رویدادها",
                             "خروجی گرفتن از رویدادها ناموفق بود.",
                             danger=True, glyph=APP_CONFIG.FAS.FA_CIRCLE_EXCLAMATION)
        return False
