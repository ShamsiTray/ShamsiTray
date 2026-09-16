"""Tests for ui.widgets.tooltip: the custom rounded tooltip that bypasses
Qt6's native tooltip rendering."""
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import QApplication

from config import APP_CONFIG
from ui.widgets.tooltip import CustomTooltip


def setup_function(function):
    # The tooltip is a process-wide singleton; reset between tests.
    CustomTooltip._instance = None


def teardown_function(function):
    if CustomTooltip._instance is not None:
        CustomTooltip._instance.hide()
        CustomTooltip._instance = None


def test_instance_is_a_singleton(qtbot):
    first = CustomTooltip.instance()
    second = CustomTooltip.instance()
    assert first is second
    assert first.windowType() == Qt.WindowType.ToolTip


def test_show_tooltip_with_text_shows_and_styles(qtbot):
    tooltip = CustomTooltip.instance()
    qtbot.addWidget(tooltip)
    palette = APP_CONFIG.get_current_palette()
    tooltip.show_tooltip("hello tooltip", QPoint(200, 200))
    assert tooltip.isVisible()
    assert tooltip._label.text() == "hello tooltip"
    # Rich text + themed styling from the current palette.
    assert tooltip._label.textFormat() == Qt.TextFormat.RichText
    assert palette["BACKGROUND_COLOR"] in tooltip._label.styleSheet()
    assert palette["TEXT_COLOR"] in tooltip._label.styleSheet()


def test_show_tooltip_with_empty_text_hides(qtbot):
    tooltip = CustomTooltip.instance()
    qtbot.addWidget(tooltip)
    tooltip.show_tooltip("temp", QPoint(200, 200))
    tooltip.show_tooltip("", QPoint(200, 200))
    assert not tooltip.isVisible()


def test_show_tooltip_flips_left_near_right_edge(qtbot):
    tooltip = CustomTooltip.instance()
    qtbot.addWidget(tooltip)
    tooltip.resize(200, 40)
    screen = QApplication.primaryScreen().availableGeometry()
    # Cursor so close to the right edge that +4 would push the tip off-screen.
    pos = QPoint(screen.right() - 2, 100)
    tooltip.show_tooltip("long tooltip text near the edge", pos)
    assert tooltip.x() + tooltip.width() <= screen.right() + 1
    tooltip.hide()


def test_show_tooltip_flips_up_near_bottom_edge(qtbot):
    tooltip = CustomTooltip.instance()
    qtbot.addWidget(tooltip)
    tooltip.resize(120, 40)
    screen = QApplication.primaryScreen().availableGeometry()
    pos = QPoint(100, screen.bottom() - 2)
    tooltip.show_tooltip("bottom tooltip", pos)
    assert tooltip.y() + tooltip.height() <= screen.bottom() + 1
    tooltip.hide()
