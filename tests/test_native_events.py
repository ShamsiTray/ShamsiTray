"""Tests for utils.native_events: the WM_TIMECHANGE native event filter.

The filter runs on every platform (it is installed unconditionally), so the
parsing path can be exercised on Linux by feeding it hand-built MSG structs.
"""
import ctypes
import ctypes.wintypes

import pytest

from utils.native_events import TimeChangeEventFilter

WM_TIMECHANGE = 0x001E
WM_NOTHING = 0x0200  # WM_USER: an unrelated message id


def _win_msg(message_id: int) -> int:
    """Build a real Windows MSG struct and return its address."""
    msg = ctypes.wintypes.MSG()
    msg.message = message_id
    return ctypes.addressof(msg)


def test_non_windows_events_are_ignored():
    seen = []
    filt = TimeChangeEventFilter(lambda: seen.append(1))
    result = filt.nativeEventFilter("some_other_BUS", 1234)
    assert result == (False, 0)
    assert seen == []


def test_null_message_is_handled():
    filt = TimeChangeEventFilter(lambda: pytest.fail("must not fire"))
    assert filt.nativeEventFilter("windows_generic_MSG", None) == (False, 0)


def test_timechange_message_fires_callback():
    seen = []
    filt = TimeChangeEventFilter(lambda: seen.append(1))
    assert filt.nativeEventFilter("windows_generic_MSG", _win_msg(WM_TIMECHANGE)) == (False, 0)
    assert seen == [1]


def test_other_windows_messages_do_not_fire():
    filt = TimeChangeEventFilter(lambda: pytest.fail("must not fire"))
    assert filt.nativeEventFilter("windows_generic_MSG", _win_msg(WM_NOTHING)) == (False, 0)


def test_dispatcher_message_type_is_also_watched():
    seen = []
    filt = TimeChangeEventFilter(lambda: seen.append(1))
    filt.nativeEventFilter("windows_dispatcher_MSG", _win_msg(WM_TIMECHANGE))
    assert seen == [1]


def test_zeroed_message_buffer_is_safe():
    """A pointer to an unexpected/zeroed buffer reads message=0: no fire.

    (A truly wild pointer cannot be guarded in userspace - ctypes deref
    would fault the process - so the reachable safety boundary is the null
    check plus benign parses of whatever memory a real OS hands over.)
    """
    seen = []
    filt = TimeChangeEventFilter(lambda: seen.append(1))
    buf = ctypes.create_string_buffer(512)  # zeroed, readable, MSG-sized+
    result = filt.nativeEventFilter("windows_generic_MSG", ctypes.addressof(buf))
    assert result == (False, 0)
    assert seen == []


def test_non_callable_callback_is_safe():
    filt = TimeChangeEventFilter(None)
    assert filt.nativeEventFilter("windows_generic_MSG", _win_msg(WM_TIMECHANGE)) == (False, 0)


def test_raising_callback_is_contained():
    """A failing callback must be logged and swallowed, never crash the loop."""
    import logging

    def boom():
        raise RuntimeError("callback exploded")

    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    module_logger = logging.getLogger("utils.native_events")
    capture = Capture()
    module_logger.addHandler(capture)
    try:
        filt = TimeChangeEventFilter(boom)
        result = filt.nativeEventFilter("windows_generic_MSG", _win_msg(WM_TIMECHANGE))
    finally:
        module_logger.removeHandler(capture)

    assert result == (False, 0)
    assert any("native event filter" in r for r in records)
