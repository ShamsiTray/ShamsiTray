"""Tests for ui.windows.base_window: the shared frameless window base.

The hover driver these tests exercise lives on ``utils.ui_helpers``
(``HoverDriverMixin``) and reaches this window - and the QDialog hosts
(``ConfirmDialog``, ``DownloadUpdateDialog``) - through the mixins."""
import sys
import time

import pytest

from PyQt6.QtCore import QEvent, QPoint, QSize, Qt
from PyQt6.QtWidgets import QApplication, QWidget

import ui.windows.base_window as base_window_module
import utils.ui_helpers as ui_helpers_module
from config import APP_CONFIG
from ui.windows.base_window import BaseFramelessWindow


def test_default_flags_are_tool_stays_on_top(qtbot):
    window = BaseFramelessWindow()
    qtbot.addWidget(window)
    assert window.windowType() == Qt.WindowType.Tool
    assert window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)


def test_taskbar_opt_in_uses_regular_window_flag(qtbot):
    class TaskbarWindow(BaseFramelessWindow):
        TASKBAR_ICON = True

    window = TaskbarWindow()
    qtbot.addWidget(window)
    # windowType() resolves the Qt6 flag-bit overlap (Tool contains Window).
    assert window.windowType() == Qt.WindowType.Window
    assert not window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    # App icon attached when the bundled icon exists (it does in this repo).
    if APP_CONFIG.ICON_PATH.exists():
        assert not window.windowIcon().isNull()


def test_drag_configuration_matches_tool_window_rules():
    assert BaseFramelessWindow.drag_strip_height == APP_CONFIG.DRAGGABLE_AREA_HEIGHT
    assert BaseFramelessWindow.drag_bottom_keep_visible == 50


def test_paint_event_draws_rounded_card(qtbot):
    window = BaseFramelessWindow()
    qtbot.addWidget(window)
    window.resize(200, 150)
    pixmap = window.grab()
    assert not pixmap.isNull()


def test_paint_event_early_returns_on_empty_rect(qtbot):
    """An empty rect must not even construct the painter."""
    window = BaseFramelessWindow()
    qtbot.addWidget(window)
    window.setFixedSize(0, 0)
    window.paintEvent(None)  # must not raise


def test_paint_event_fills_with_background_color(qtbot):
    window = BaseFramelessWindow()
    qtbot.addWidget(window)
    window.resize(60, 60)
    image = window.grab().toImage()
    center = image.pixelColor(30, 30)
    assert center.alpha() == 255  # the rounded card painted an opaque fill


def test_mouse_events_delegate_to_drag_mixin(qtbot):
    from tests.qt_mousing import press, release

    window = BaseFramelessWindow()
    qtbot.addWidget(window)
    window.resize(200, 300)
    window.show()
    # Press inside the top 40px strip starts a drag (press consumed).
    assert window.handle_drag_press is not None
    event = press(window, local=(10, 10))
    window.mousePressEvent(event)
    assert window._drag_position is not None
    window.mouseReleaseEvent(release(window))
    assert window._drag_position is None


# --- always-on-top flag -----------------------------------------------------------------

def test_set_always_on_top_clears_and_restores_the_flag(qtbot):
    window = BaseFramelessWindow()
    qtbot.addWidget(window)
    assert window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint  # Tool window default

    window.set_always_on_top(False)
    assert not window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    window.set_always_on_top(True)
    assert window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint


def test_set_always_on_top_keeps_a_visible_window_where_it_was(qtbot):
    """Changing window flags hides a native window, so it must be re-shown in place."""
    window = BaseFramelessWindow()
    qtbot.addWidget(window)
    window.setGeometry(140, 110, 200, 150)
    window.show()
    qtbot.waitExposed(window)

    window.set_always_on_top(False)

    assert window.isVisible()
    assert window.geometry().topLeft() == QPoint(140, 110)
    assert window.size() == QSize(200, 150)


def test_set_always_on_top_before_first_show_does_not_show_it(qtbot):
    """Applying the preference during startup must not pop the window up."""
    window = BaseFramelessWindow()
    qtbot.addWidget(window)
    window.set_always_on_top(False)
    assert not window.isVisible()


def test_taskbar_window_is_not_pinned_by_default(qtbot):
    class TaskbarWindow(BaseFramelessWindow):
        TASKBAR_ICON = True

    window = TaskbarWindow()
    qtbot.addWidget(window)
    assert window._always_on_top is False
    window.set_always_on_top(True)
    assert window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint


def test_screen_clamp_semantics_documented():
    """The 50px keep-visible rule must equal the historical tool-window rule."""
    from utils.ui_helpers import FramelessDragMixin

    assert issubclass(BaseFramelessWindow, FramelessDragMixin)
    screen = QApplication.primaryScreen().availableGeometry()
    # For a 395px-tall calendar the bottom clamp leaves the top 50 visible.
    assert screen.bottom() - 50 > screen.top()


# --- popup dismissal ----------------------------------------------------------------------

class _Popup(BaseFramelessWindow):
    """A window configured like the calendar popup."""
    CLOSE_ON_OUTSIDE_CLICK_WHEN_UNPINNED = True


def _visible_window(qtbot, *, pinned=True, window=None):
    window = window if window is not None else _Popup()
    qtbot.addWidget(window)
    if not pinned:
        # Before the first show, so the unpinning itself does not dismiss it.
        window.set_always_on_top(False)
    window.show()
    qtbot.waitExposed(window)
    return window


def _lose_activation(window, monkeypatch, active=None):
    """Deliver the activation change Qt sends when focus moves off the window."""
    class _App:
        @staticmethod
        def activeWindow():
            return active

    monkeypatch.setattr(base_window_module, "QApplication", _App)
    monkeypatch.setattr(window, "isActiveWindow", lambda: False)
    window.changeEvent(QEvent(QEvent.Type.ActivationChange))


def test_unpinned_popup_closes_when_it_loses_activation(qtbot, monkeypatch):
    window = _visible_window(qtbot, pinned=False)
    _lose_activation(window, monkeypatch)
    assert not window.isVisible()


def test_pinned_popup_stays_open_when_it_loses_activation(qtbot, monkeypatch):
    window = _visible_window(qtbot)
    _lose_activation(window, monkeypatch)
    assert window.isVisible()


def test_ordinary_window_stays_open_when_it_loses_activation(qtbot, monkeypatch):
    """Tool windows are forms, not flyouts: focus loss must not close them."""
    window = _visible_window(qtbot, pinned=False, window=BaseFramelessWindow())
    _lose_activation(window, monkeypatch)
    assert window.isVisible()


def test_popup_stays_open_when_its_own_dialog_takes_focus(qtbot, monkeypatch):
    """A confirm dialog this popup opened is not an outside click."""
    window = _visible_window(qtbot, pinned=False)
    dialog = QWidget(window)
    _lose_activation(window, monkeypatch, active=dialog)
    assert window.isVisible()


def test_outside_dismissal_marker_is_consumed_once(qtbot, monkeypatch):
    window = _visible_window(qtbot, pinned=False)
    _lose_activation(window, monkeypatch)

    assert window.consume_outside_click_dismissal() is True
    assert window.consume_outside_click_dismissal() is False   # cleared on read


def test_dismissal_freezes_the_tray_probe_verdict_at_dismissal_time(qtbot, monkeypatch):
    """The verdict the tray click later consumes is the probe taken when the
    dismissal was recorded: a cursor that has moved on by click time must not
    change it."""
    window = _visible_window(qtbot, pinned=False)
    verdicts = [True]
    window.cursor_over_tray_probe = lambda: verdicts[-1]

    _lose_activation(window, monkeypatch)
    verdicts[-1] = False  # the cursor has moved on by the time the click lands

    assert window.consume_outside_click_dismissal() is True


def test_dismissal_recorded_away_from_the_tray_does_not_count(qtbot, monkeypatch):
    """A popup dismissed by a click elsewhere must not swallow a later tray
    click: the overlay with the icon is judged when the dismissal is recorded."""
    window = _visible_window(qtbot, pinned=False)
    window.cursor_over_tray_probe = lambda: False

    _lose_activation(window, monkeypatch)

    assert window.consume_outside_click_dismissal() is False


def test_stale_outside_dismissal_marker_expires(qtbot):
    window = _visible_window(qtbot, pinned=False)
    window._outside_dismissed_at = time.monotonic() - 5
    assert window.consume_outside_click_dismissal() is False


def test_unpinning_a_popup_that_lost_activation_dismisses_it(qtbot, monkeypatch):
    """The tray menu that flips the setting is itself an outside click, so an
    unpinned popup must not be left on screen where no later click can close it."""
    window = _visible_window(qtbot)
    monkeypatch.setattr(window, "isActiveWindow", lambda: False)

    window.set_always_on_top(False)

    assert not window.isVisible()
    assert not window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint


def test_unpinning_an_active_popup_keeps_it_up_and_activated(qtbot, monkeypatch):
    window = _visible_window(qtbot)
    activated = []
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    monkeypatch.setattr(window, "activateWindow", lambda: activated.append(1))

    window.set_always_on_top(False)

    assert window.isVisible()
    # setWindowFlags drops activation, and an inactive popup is the state no
    # click can dismiss, so the window is activated again.
    assert activated == [1]


def test_unpinning_an_ordinary_window_never_dismisses_it(qtbot, monkeypatch):
    window = _visible_window(qtbot, window=BaseFramelessWindow())
    monkeypatch.setattr(window, "isActiveWindow", lambda: False)

    window.set_always_on_top(False)

    assert window.isVisible()


# --- hover driver ---------------------------------------------------------------------------

def _fake_qapp(monkeypatch, *, under=None, buttons=Qt.MouseButton.NoButton):
    """Stand in for the module's QApplication on the driver's tick path."""
    class _App:
        @staticmethod
        def widgetAt(_pos):
            return under

        @staticmethod
        def mouseButtons():
            return buttons

        @staticmethod
        def screens():
            return ()  # the capture sweep is out of scope for hover tests

    monkeypatch.setattr(ui_helpers_module, "QApplication", _App)


def _fake_cursor(monkeypatch, pos):
    monkeypatch.setattr(ui_helpers_module.QCursor, "pos", staticmethod(lambda: pos))


def _hover_window(qtbot, position=None):
    """A shown window whose driver ticks only when the test calls for them."""
    window = BaseFramelessWindow()
    qtbot.addWidget(window)
    if position is not None:
        window.move(*position)
    window._hover_timer.setInterval(10 ** 9)  # ticks are driven by hand
    window.show()
    qtbot.waitExposed(window)
    return window


class _FakeUnder:
    """A widget under the cursor with controllable hover state."""

    def __init__(self, host):
        self._host = host
        self.hovered = False

    def window(self):
        return self._host

    def underMouse(self):
        return self.hovered


def test_show_arms_and_hide_disarms_the_hover_driver(qtbot):
    window = _hover_window(qtbot)
    assert window._hover_timer.isActive()
    window.hide()
    assert not window._hover_timer.isActive()


def test_next_show_resets_leftover_driver_bookkeeping(qtbot):
    """Every open starts fresh: the prewarm show must never hand the real open
    spent budgets or hover verdicts left over from the previous one."""
    window = _hover_window(qtbot)
    window._stale_repairs = 3
    window._capture_checks = 17
    window._was_inside = True
    window._healthy_ticks = 4

    window.hide()
    window.show()

    assert window._hover_timer.isActive()
    assert window._stale_repairs == 0
    assert window._capture_checks == 0
    assert not window._was_inside
    assert window._healthy_ticks == 0


def test_hover_tick_feeds_a_move_at_the_real_cursor(qtbot, monkeypatch):
    window = _hover_window(qtbot)
    pos = window.mapToGlobal(QPoint(60, 60))
    _fake_cursor(monkeypatch, pos)
    _fake_qapp(monkeypatch, under=window)
    monkeypatch.setattr(window, "_query_os_buttons", lambda: False)
    fed = []
    monkeypatch.setattr(window, "_feed_mouse_move", lambda local: fed.append(local))

    window._sync_hover()

    assert fed == [window.mapFromGlobal(pos)]
    assert window._was_inside


def test_stationary_hovered_widget_is_not_refed(qtbot, monkeypatch):
    """Once the widget under a still cursor carries hover state, feeding is
    done - the driver never spams moves while nothing changes."""
    window = _hover_window(qtbot)
    under = _FakeUnder(window)
    _fake_cursor(monkeypatch, window.mapToGlobal(QPoint(60, 60)))
    _fake_qapp(monkeypatch, under=under)
    monkeypatch.setattr(window, "_query_os_buttons", lambda: False)
    fed = []
    monkeypatch.setattr(window, "_feed_mouse_move", lambda local: fed.append(local))

    window._sync_hover()
    under.hovered = True
    window._sync_hover()

    assert len(fed) == 1


def test_cursor_leaving_the_window_parks_the_hover(qtbot, monkeypatch):
    """Qt ignores moves outside the window, so the parked move on the inert
    corner is what clears the hover the cursor just walked out of."""
    window = _hover_window(qtbot)
    _fake_cursor(monkeypatch, window.mapToGlobal(QPoint(60, 60)))
    _fake_qapp(monkeypatch, under=window)
    monkeypatch.setattr(window, "_query_os_buttons", lambda: False)
    fed = []
    monkeypatch.setattr(window, "_feed_mouse_move", lambda local: fed.append(local))

    window._sync_hover()  # establish "inside"
    outside = window.mapToGlobal(QPoint(60, 60)) + QPoint(400, 0)
    _fake_cursor(monkeypatch, outside)
    _fake_qapp(monkeypatch, under=None)
    window._sync_hover()

    assert fed[-1] == ui_helpers_module._INERT_FEED_POS
    assert not window._was_inside

    window._sync_hover()  # already parked: leaving again sends nothing
    assert len(fed) == 2


def test_foreign_toplevel_under_the_cursor_is_not_fed(qtbot, monkeypatch):
    """A menu, tooltip or dialog of this process under the cursor serves its
    own hover; the driver must not steal events it needs."""
    window = _hover_window(qtbot)
    _fake_cursor(monkeypatch, window.mapToGlobal(QPoint(60, 60)))
    _fake_qapp(monkeypatch, under=QWidget())
    monkeypatch.setattr(window, "_query_os_buttons", lambda: False)
    fed = []
    monkeypatch.setattr(window, "_feed_mouse_move", lambda local: fed.append(local))

    window._sync_hover()

    assert fed == []
    assert not window._was_inside


def test_physically_held_button_pauses_the_driver(qtbot, monkeypatch):
    """While a real button is down (a drag mid-flight) the driver must not
    touch Qt's mouse bookkeeping at all."""
    window = _hover_window(qtbot)
    _fake_cursor(monkeypatch, window.mapToGlobal(QPoint(60, 60)))
    _fake_qapp(monkeypatch, under=window, buttons=Qt.MouseButton.LeftButton)
    monkeypatch.setattr(window, "_query_os_buttons", lambda: True)
    touched = []
    for name in ("_release_stray_capture", "_feed_mouse_move", "_reset_stale_qt_buttons"):
        monkeypatch.setattr(window, name, lambda *a, _n=name: touched.append(_n))

    window._sync_hover()

    assert touched == []
    assert not window._was_inside


def test_stale_qt_buttons_are_repaired_on_the_third_tick(qtbot, monkeypatch):
    """The tray click's release never reaches Qt: after three ticks of
    Qt-says-down / OS-says-none the driver sends the synthetic releases."""
    window = _hover_window(qtbot)
    _fake_qapp(monkeypatch, under=None, buttons=Qt.MouseButton.LeftButton)
    monkeypatch.setattr(window, "_query_os_buttons", lambda: False)
    repairs = []
    monkeypatch.setattr(window, "_reset_stale_qt_buttons", lambda: repairs.append(1))

    window._sync_hover()
    window._sync_hover()
    assert repairs == []

    window._sync_hover()
    assert repairs == [1]
    assert window._stale_repairs == 1


def test_repair_attempts_are_capped_and_the_driver_then_converges(qtbot, monkeypatch):
    """Synthetic releases that never unstick Qt must not run forever: after
    the repair budget is spent, the driver accepts the state and stops."""
    window = _hover_window(qtbot)
    _fake_qapp(monkeypatch, under=None, buttons=Qt.MouseButton.LeftButton)
    monkeypatch.setattr(window, "_query_os_buttons", lambda: False)
    repairs = []
    monkeypatch.setattr(window, "_reset_stale_qt_buttons", lambda: repairs.append(1))

    for _ in range(100):
        window._sync_hover()

    assert len(repairs) == window.HOVER_STALE_REPAIR_MAX
    assert not window._hover_timer.isActive()


def test_clean_ticks_converge_the_driver(qtbot, monkeypatch):
    """Enough clean ticks prove Qt's mouse state is healed; ordinary OS mouse
    moves carry hover from there, so the driver stops polling."""
    window = _hover_window(qtbot)
    under = _FakeUnder(window)
    under.hovered = True
    _fake_cursor(monkeypatch, window.mapToGlobal(QPoint(60, 60)))
    _fake_qapp(monkeypatch, under=under)
    monkeypatch.setattr(window, "_query_os_buttons", lambda: False)
    fed = []
    monkeypatch.setattr(window, "_feed_mouse_move", lambda local: fed.append(local))

    for _ in range(window.HOVER_CONVERGE_TICKS):
        window._sync_hover()

    assert not window._hover_timer.isActive()
    # The open's initial feed, then nothing: a stationary hovered widget is
    # not refed, and every tick still counts clean toward convergence.
    assert fed == [window.mapFromGlobal(QPoint(60, 60))]


def test_capture_sweep_is_gated_by_budget(qtbot):
    """After HOVER_CAPTURE_TICKS the sweep stops checking entirely."""
    window = _hover_window(qtbot)
    window._capture_checks = window.HOVER_CAPTURE_TICKS

    window._release_stray_capture()

    assert window._capture_checks == window.HOVER_CAPTURE_TICKS


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only Win32 capture")
def test_offscreen_prewarm_show_never_spends_the_capture_budget(qtbot):
    """The controller pre-warms a hidden copy of the calendar far off-screen;
    its capture sweep must stay untouched for the later real open."""
    window = _hover_window(qtbot, position=(-10000, -10000))

    for _ in range(20):
        window._release_stray_capture()

    assert window._capture_checks == 0


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only Win32 capture")
def test_capture_release_is_scoped_to_this_window(qtbot, monkeypatch):
    """Only the window's own capture is dropped - a menu's modal loop holding
    the capture must survive the sweep."""
    window = _hover_window(qtbot)
    releases = []
    monkeypatch.setattr(ui_helpers_module, "_win32_capture_hwnd", lambda: 1234)
    monkeypatch.setattr(ui_helpers_module, "_win32_release_capture",
                        lambda: releases.append(1))

    window._release_stray_capture()
    assert window._capture_checks == 1
    assert releases == []

    ours = int(window.winId())
    monkeypatch.setattr(ui_helpers_module, "_win32_capture_hwnd", lambda: ours)
    window._release_stray_capture()
    assert releases == [1]
