"""Tests for ui.windows.base_window: the shared frameless window base."""
import time

from PyQt6.QtCore import QEvent, QPoint, QSize, Qt
from PyQt6.QtWidgets import QApplication, QWidget

import ui.windows.base_window as base_window_module
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
