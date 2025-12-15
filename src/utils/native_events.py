"""
Native Event Filter
-------------------

This module contains the `TimeChangeEventFilter`, which hooks into the
operating system's native event loop to detect system-wide time changes.
This is necessary because Qt's timers may not fire correctly if the system
clock is adjusted manually or by a time synchronization service.

This implementation is specific to Windows (WM_TIMECHANGE).
"""
import ctypes.wintypes

from PyQt5.QtCore import QAbstractNativeEventFilter

from .logging_setup import setup_logging

logger = setup_logging(__name__)

class TimeChangeEventFilter(QAbstractNativeEventFilter):
    """Native event filter to detect system time changes (WM_TIMECHANGE on Windows)."""
    def __init__(self, on_time_change_callback):
        super().__init__()
        self.on_time_change_callback = on_time_change_callback
        logger.debug("TimeChangeEventFilter initialized.")

    def nativeEventFilter(self, eventType, message):
        if eventType in ("windows_generic_MSG", "windows_dispatcher_MSG"):
            if not message:
                return False, 0
            try:
                msg = ctypes.cast(int(message), ctypes.POINTER(ctypes.wintypes.MSG)).contents
                WM_TIMECHANGE = 0x001E
                if msg.message == WM_TIMECHANGE:
                    logger.info("⏰ System time changed (WM_TIMECHANGE detected).")
                    if callable(self.on_time_change_callback):
                        self.on_time_change_callback()
            except Exception as e:
                logger.error(f"Error processing Windows message in native event filter: {e}")
        return False, 0
