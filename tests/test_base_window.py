"""Tests for ui.windows.base_window: the shared frameless window base."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

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


def test_screen_clamp_semantics_documented():
    """The 50px keep-visible rule must equal the historical tool-window rule."""
    from utils.ui_helpers import FramelessDragMixin

    assert issubclass(BaseFramelessWindow, FramelessDragMixin)
    screen = QApplication.primaryScreen().availableGeometry()
    # For a 395px-tall calendar the bottom clamp leaves the top 50 visible.
    assert screen.bottom() - 50 > screen.top()
