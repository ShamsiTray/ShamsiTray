"""
System Tray Icon Controller
---------------------------

This module contains the `SystemTrayIcon` class, which serves as the main
controller for the application. It manages:
- The system tray icon itself, including its appearance and tooltip.
- The context menu (right-click menu).
- Loading and saving application settings (theme, auto-start) and user data (events).
- Creating and managing the lifecycle of the main application windows (calendar, converter).
- Handling system events like time changes and application activation.
"""
import sys
import json
import datetime
from typing import Dict, List, Optional, Tuple

import jdatetime
from PyQt6.QtCore import QCoreApplication, QSettings, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QApplication, QMenu, QSystemTrayIcon,
                             QWidgetAction)

from config import APP_CONFIG
from ui.windows.calendar_window import PersianCalendarWidget
from ui.windows.converter_window import DateConverterWindow
from ui.widgets.menu_widgets import (MenuActionWidget,
                                       ThemeToggleActionWidget)
from ui.widgets.custom_checkbox import IconCheckboxActionWidget
from utils.date_helpers import (persian_month_name, persian_weekday_name,
                                  to_persian_digits)
from utils.logging_setup import setup_logging
from utils.native_events import TimeChangeEventFilter
from utils.ui_helpers import create_tray_pixmap
from ui.windows.tutorial_window import TutorialWindow

if sys.platform == 'win32':
    import winreg

logger = setup_logging(__name__)

class SystemTrayIcon(QSystemTrayIcon):
    """The main application controller, managing the tray icon, windows, and settings."""

    def __init__(self):
        super().__init__()
        self.settings = QSettings(APP_CONFIG.COMPANY_NAME, APP_CONFIG.APP_NAME)
        self.holidays_cache = self._load_holidays_from_file()
        self.user_events = self._load_user_events()
        self._clean_expired_events()
        
        self.calendar_widget = PersianCalendarWidget(self.holidays_cache, self.user_events)
        self.calendar_widget.event_added.connect(self.add_user_event)
        self.calendar_widget.event_removed.connect(self.remove_user_event)

        self.converter_window: Optional[DateConverterWindow] = None
        self.tutorial_window: Optional["TutorialWindow"] = None

        self._load_settings() 
        self._validate_and_apply_startup_setting()
        self._apply_theme()
        self.activated.connect(self.on_tray_icon_activated)
        self._setup_timers()
        self.update_tray_icon(force=True)

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
        self.is_open_at_login = self.settings.value(APP_CONFIG.AUTO_START_SETTING_KEY, False, type=bool)
        
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
        if self.converter_window and self.converter_window.isVisible():
            self.converter_window.update_styles()
        if self.tutorial_window and self.tutorial_window.isVisible():
            self.tutorial_window.update_styles()
    
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
        self.calendar_widget.go_to_today()
        self.update_tray_icon(force=True)
        self.schedule_next_midnight_check()

    def schedule_next_midnight_check(self):
        now = datetime.datetime.now()
        tomorrow = now + datetime.timedelta(days=1)
        midnight = datetime.datetime(tomorrow.year, tomorrow.month, tomorrow.day)
        millis_until_midnight = int((midnight - now).total_seconds() * 1000)
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
        self.calendar_widget.go_to_today()
        self.update_tray_icon(force=True)
        self.schedule_next_midnight_check()

    def _build_global_stylesheet(self) -> str:
        palette = APP_CONFIG.get_current_palette()
        return (f"QScrollBar:vertical {{ border: none; background: {palette['SCROLLBAR_GROOVE_COLOR']}; width: 10px; margin: 0px; border-radius: 5px;}}"
                f"QScrollBar::handle:vertical {{ background: {palette['SCROLLBAR_HANDLE_COLOR']}; border-radius: 5px; min-height: 20px;}}"
                f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}"
                f"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}")
    
    def _load_holidays_from_file(self) -> Dict[int, Dict[Tuple[int, int], List[str]]]:
        try:
            with open(APP_CONFIG.HOLIDAYS_FILE_PATH, 'r', encoding='utf-8') as f:
                raw_data = json.load(f).get('holidays', {})
            holidays_data = {}
            for year_str, events in raw_data.items():
                year_int = int(year_str)
                holidays_data[year_int] = {}
                for month_day_str, desc in events.items():
                    month, day = map(int, month_day_str.split('-'))
                    holidays_data[year_int][(month, day)] = [desc] if isinstance(desc, str) else desc
            logger.info("Holidays loaded successfully.")
            return holidays_data
        except (IOError, json.JSONDecodeError, ValueError) as e:
            # If holidays fail to load, continue without them rather than blocking the app
            logger.error(f"Failed to load or parse holidays file: {e}")
            return {}

    def _load_user_events(self) -> Dict[str, dict]:
        """Loads user events from QSettings and ensures they are in the new format."""
        events = self.settings.value(APP_CONFIG.USER_EVENTS_SETTING_KEY, {}, type=dict)
        migrated = False
        for key, value in list(events.items()):
            if isinstance(value, str):
                events[key] = {"text": value, "yearly": False, "remove_after_finish": False}
                migrated = True
            elif isinstance(value, dict) and "remove_after_finish" not in value:
                value["remove_after_finish"] = False
                migrated = True
        if migrated:
            logger.info("Migrated old event format to new format.")
            self.settings.setValue(APP_CONFIG.USER_EVENTS_SETTING_KEY, events)
        logger.info(f"Loaded {len(events)} user events.")
        return events

    def _save_user_events(self):
        self.settings.setValue(APP_CONFIG.USER_EVENTS_SETTING_KEY, self.user_events)
        logger.info(f"Saved {len(self.user_events)} user events.")

    def add_user_event(self, jdate: jdatetime.date, text: str, is_yearly: bool, remove_after_finish: bool):
        if not jdate:
            return
        self.remove_user_event(jdate, save=False)
        
        if is_yearly:
        # Yearly events are stored with year "0000" so they match the same month/day across all years when rendering and cleaning events.
            remove_after_finish = False
            key = jdate.strftime("0000-%m-%d")
        else:
            key = jdate.strftime("%Y-%m-%d")

        self.user_events[key] = {"text": text, "yearly": is_yearly, "remove_after_finish": remove_after_finish}
        self._save_user_events()
        self.calendar_widget.set_user_events(self.user_events)
        self.update_tray_icon(force=True)

    def remove_user_event(self, jdate: jdatetime.date, save: bool = True):
        if not jdate:
            return
        specific_key = jdate.strftime("%Y-%m-%d")
        yearly_key = jdate.strftime("0000-%m-%d")
        event_removed = False
        if specific_key in self.user_events:
            del self.user_events[specific_key]
            event_removed = True
        if yearly_key in self.user_events:
            del self.user_events[yearly_key]
            event_removed = True
        if event_removed and save:
            self._save_user_events()
            self.calendar_widget.set_user_events(self.user_events)
            self.update_tray_icon(force=True)
    
    def _clean_expired_events(self):
        today = jdatetime.date.today()
        events_to_remove = []
        for date_str, event_data in list(self.user_events.items()):
            if not event_data.get("yearly", False) and event_data.get("remove_after_finish", False):
                try:
                    event_date = jdatetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                    if event_date < today:
                        events_to_remove.append(date_str)
                except (ValueError, TypeError):
                    logger.warning(f"Could not parse event date for removal: {date_str}")
                    continue

        if events_to_remove:
            logger.info(f"Removing {len(events_to_remove)} expired events.")
            for key in events_to_remove:
                del self.user_events[key]
            self._save_user_events()
            if self.calendar_widget:
                self.calendar_widget.set_user_events(self.user_events)

    def update_tray_icon(self, force: bool = False):
        new_date = jdatetime.date.today()
        if not force and hasattr(self.calendar_widget, 'current_date') and new_date == self.calendar_widget.current_date:
            return

        logger.info(f"Updating tray icon for new date: {new_date}")
        self.calendar_widget.current_date = new_date
        if self.calendar_widget.isVisible():
            self.calendar_widget.fill_calendar_grid()

        day_str_persian = to_persian_digits(new_date.day)
        
        user_event_text, _, _ = self.calendar_widget._get_user_event_for_date(new_date)
        is_user_event = bool(user_event_text)
        is_holiday = new_date.weekday() == 6 or self.holidays_cache.get(new_date.year, {}).get((new_date.month, new_date.day))
        
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
                
        self.setToolTip("\n".join(tooltip_lines))

    def _setup_context_menu(self):
        menu = QMenu()
        palette = APP_CONFIG.get_current_palette()
        menu.setStyleSheet(
            f"QMenu {{ background-color: {palette['BACKGROUND_COLOR']}; border: 1px solid {palette['MENU_BORDER_COLOR']}; border-radius: 8px; padding: 5px; }}"
            f"QMenu::separator {{ height: 1px; background-color: {palette['MENU_BORDER_COLOR']}; margin: 5px 0px; }}"
        )
        self._add_menu_action(menu, "تبدیل تاریخ", self._open_date_converter)
        menu.addSeparator()
        self._add_theme_toggle_action(menu)
        menu.addSeparator()
        self._add_startup_action(menu)
        menu.addSeparator()
        self._add_menu_action(menu, "خروج", QApplication.quit)
        self.setContextMenu(menu)
    
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
            if self.calendar_widget.isVisible():
                if self.calendar_widget.event_input_widget.isVisible():
                    self.calendar_widget._hide_event_input_widget()
                else:
                    self.calendar_widget.hide()
            else:
                self.show_calendar()

    def show_calendar(self):
        if self.calendar_widget.selected_date != jdatetime.date.today():
             self.calendar_widget.go_to_today()
        
        self.calendar_widget.fill_calendar_grid()
        self.calendar_widget.update_styles()
        
        screen = QApplication.primaryScreen().availableGeometry()
        tray_geom = self.geometry()
        widget_size = self.calendar_widget.size()
        x = screen.right() - widget_size.width() - 10 # Small gap so the widget doesn't touch the tray icon
        y = screen.bottom() - widget_size.height() - 45 # Fallback offset to keep widget above taskbar
        if tray_geom.isValid():
            x = tray_geom.center().x() - widget_size.width() // 2
            y = tray_geom.top() - widget_size.height() - 5
            x = max(screen.left(), min(x, screen.right() - widget_size.width()))
            y = max(screen.top(), min(y, screen.bottom() - widget_size.height()))
        self.calendar_widget.move(int(x), int(y))
        self.calendar_widget.show()
        self.calendar_widget.activateWindow()

    def _toggle_theme(self):
        self.current_theme = APP_CONFIG.Theme.LIGHT if self.current_theme == APP_CONFIG.Theme.DARK else APP_CONFIG.Theme.DARK
        self.settings.setValue(APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY, self.current_theme)
        logger.info(f"Theme toggled to: {self.current_theme}")
        self._apply_theme()

    def _set_startup_registry(self, enable: bool):
        if not sys.platform.startswith('win'):
            logger.warning("Auto-start is only supported on Windows.")
            return
        try:
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
            if enable:
                executable_path = sys.executable if getattr(sys, 'frozen', False) else sys.argv[0]
                # Path must be quoted to support spaces when the app is frozen or installed in Program Files
                winreg.SetValueEx(key, APP_CONFIG.APP_NAME, 0, winreg.REG_SZ, f'"{executable_path}"')
                logger.info(f"Set startup registry key to: {executable_path}")
            else:
                winreg.DeleteValue(key, APP_CONFIG.APP_NAME)
                logger.info("Removed startup registry key.")
            winreg.CloseKey(key)
        except FileNotFoundError:
            if not enable:
                logger.warning("Could not remove startup key (it may not exist).")
            else:
                logger.error(f"Could not find registry key path: {key_path}")
        except Exception as e:
            logger.error(f"Error modifying Windows registry: {e}")

    def _toggle_open_at_boot(self, checked: bool):
        self.is_open_at_login = checked
        self.settings.setValue(APP_CONFIG.AUTO_START_SETTING_KEY, checked)
        logger.info(f"Setting 'Open at Login' to {checked}.")
        self._set_startup_registry(checked)

    def _validate_and_apply_startup_setting(self):
        if not sys.platform.startswith('win') or not self.is_open_at_login:
            return
        logger.info("Validating startup registry key...")
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        executable_path = sys.executable if getattr(sys, 'frozen', False) else sys.argv[0]
        expected_value = f'"{executable_path}"'
        needs_update = True
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
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

    def _open_date_converter(self):
        if self.converter_window is None or not self.converter_window.isVisible():
            self.converter_window = DateConverterWindow()
            self.converter_window.show()
            self.converter_window.activateWindow()
        else:
            self.converter_window.activateWindow()