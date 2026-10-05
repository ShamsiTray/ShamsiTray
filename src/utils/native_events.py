"""
Native Event Filter
-------------------

This module contains the `TimeChangeEventFilter`, which hooks into the
operating system's native event loop to detect system-wide changes the app
cares about:

- system time changes (WM_TIMECHANGE) - Qt's timers may not fire correctly if
  the system clock is adjusted manually or by a time synchronization service;
- system setting changes (WM_SETTINGCHANGE), filtered to the Windows light/dark
  mode broadcast ("ImmersiveColorSet") so the app can FOLLOW the system theme
  while the user has not picked one of their own.

This implementation is specific to Windows (WM_TIMECHANGE / WM_SETTINGCHANGE).
"""
import ctypes.wintypes

from PyQt6.QtCore import QAbstractNativeEventFilter

from .logger import setup_logging

logger = setup_logging(__name__)

class TimeChangeEventFilter(QAbstractNativeEventFilter):
    """Native event filter for Windows time/setting change broadcasts.

    ``on_time_change_callback`` is called (no arguments) on WM_TIMECHANGE;
    ``on_setting_change_callback`` is called with the setting-change section
    string on WM_SETTINGCHANGE (only when the lParam string can be read).
    """
    def __init__(self, on_time_change_callback, on_setting_change_callback=None):
        super().__init__()
        self.on_time_change_callback = on_time_change_callback
        self.on_setting_change_callback = on_setting_change_callback
        logger.debug("TimeChangeEventFilter initialized.")

    @staticmethod
    def _setting_change_section(lparam: int):
        """The WM_SETTINGCHANGE lParam string ('ImmersiveColorSet', ...), or
        None when it cannot be read. Reading must be fault-isolated: the
        pointer can be null or point at anything a broadcast carries."""
        if not lparam:
            return None
        try:
            return ctypes.cast(lparam, ctypes.c_wchar_p).value
        except Exception as e:  # pragma: no cover - depends on OS payloads
            logger.debug(f"Could not read WM_SETTINGCHANGE lParam string: {e}")
            return None

    def nativeEventFilter(self, eventType, message):
        if eventType in ("windows_generic_MSG", "windows_dispatcher_MSG"):
            if not message:
                return False, 0
            try:
                msg = ctypes.cast(int(message), ctypes.POINTER(ctypes.wintypes.MSG)).contents
                WM_TIMECHANGE = 0x001E
                WM_SETTINGCHANGE = 0x001A
                if msg.message == WM_TIMECHANGE:
                    # DEBUG, not INFO: Windows broadcasts this message to every
                    # top-level window and the time service can emit a burst of
                    # them while re-syncing, so a per-message INFO line floods the
                    # log. The callback coalesces the burst and the controller logs
                    # the single resulting refresh at INFO instead.
                    logger.debug("WM_TIMECHANGE received.")
                    if callable(self.on_time_change_callback):
                        self.on_time_change_callback()
                elif msg.message == WM_SETTINGCHANGE:
                    section = self._setting_change_section(msg.lParam)
                    # Only the theme broadcast matters; every other section
                    # (environment changes, device arrivals, ...) is ignored
                    # without even a debug line - they are frequent.
                    if section == "ImmersiveColorSet":
                        logger.debug("WM_SETTINGCHANGE (ImmersiveColorSet) received.")
                        if callable(self.on_setting_change_callback):
                            self.on_setting_change_callback(section)
            except Exception as e:
                logger.error(f"Error processing Windows message in native event filter: {e}")
        return False, 0
