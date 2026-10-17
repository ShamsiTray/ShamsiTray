"""Tests for ui.widgets.tooltip: the custom rounded tooltip that bypasses
Qt6's native tooltip rendering, and the hover mixin that routes widgets to it."""
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QCursor, QEnterEvent
from PyQt6.QtWidgets import QApplication

from config import APP_CONFIG
from tests.qt_mousing import press
from ui.widgets.tooltip import (TOOLTIP_DELAY_MS, CustomTooltip, TooltipButton,
                                TooltipLabel)


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


def test_flash_tooltip_shows_then_auto_hides(qtbot):
    tooltip = CustomTooltip.instance()
    qtbot.addWidget(tooltip)
    tooltip.flash_tooltip("کپی شد", QPoint(200, 200), duration_ms=50)
    assert tooltip.isVisible()
    assert tooltip._auto_hide_timer.isActive()
    qtbot.wait(150)
    assert not tooltip.isVisible()


def test_a_second_flash_gets_its_own_full_window(qtbot):
    """Two copies in a row must not share one deadline.

    The callers used to schedule an uncancellable QTimer.singleShot(600, hide)
    each, so the SECOND confirmation was hidden by the FIRST one's timer - it
    appeared for a fraction of the intended window."""
    tooltip = CustomTooltip.instance()
    qtbot.addWidget(tooltip)
    tooltip.flash_tooltip("کپی شد", QPoint(200, 200), duration_ms=400)
    qtbot.wait(300)                      # 300ms into the first flash's window
    tooltip.flash_tooltip("کپی شد", QPoint(200, 200), duration_ms=400)
    qtbot.wait(300)                      # past where the FIRST timer would fire
    assert tooltip.isVisible(), "the first flash's timer hid the second flash"


def test_a_stale_flash_cannot_hide_a_later_tooltip(qtbot):
    """An explicit show must survive a confirmation still counting down.

    Without stopping the timer, a holiday tooltip arriving just after a copy
    was hidden mid-read by the leftover flash."""
    tooltip = CustomTooltip.instance()
    qtbot.addWidget(tooltip)
    tooltip.flash_tooltip("کپی شد", QPoint(200, 200), duration_ms=100)
    tooltip.show_tooltip("تعطیلی: عید نوروز", QPoint(200, 200))
    qtbot.wait(250)
    assert tooltip.isVisible()
    assert tooltip._label.text() == "تعطیلی: عید نوروز"


def test_show_tooltip_flips_up_near_bottom_edge(qtbot):
    tooltip = CustomTooltip.instance()
    qtbot.addWidget(tooltip)
    tooltip.resize(120, 40)
    screen = QApplication.primaryScreen().availableGeometry()
    pos = QPoint(100, screen.bottom() - 2)
    tooltip.show_tooltip("bottom tooltip", pos)
    assert tooltip.y() + tooltip.height() <= screen.bottom() + 1
    tooltip.hide()


# --- tones: what a tooltip means, coloured by the palette ---

def test_danger_tone_colours_the_border_and_the_text(qtbot):
    """The one destructive action - deleting an event - gets the palette's
    warning colour on both the border and the text, so the warning lands before
    the click does."""
    tooltip = CustomTooltip.instance()
    qtbot.addWidget(tooltip)
    palette = APP_CONFIG.get_current_palette()

    tooltip.show_tooltip("حذف", QPoint(200, 200), tone="danger")

    assert palette["HOLIDAY_COLOR"] in tooltip._label.styleSheet()
    assert palette["BACKGROUND_COLOR"] in tooltip._label.styleSheet()


def test_an_unknown_tone_falls_back_to_neutral(qtbot):
    """A typo must never leave a tooltip unstyled."""
    tooltip = CustomTooltip.instance()
    qtbot.addWidget(tooltip)
    palette = APP_CONFIG.get_current_palette()

    tooltip.show_tooltip("سلام", QPoint(200, 200), tone="ناشناخته")

    assert palette["TEXT_COLOR"] in tooltip._label.styleSheet()
    assert palette["HOLIDAY_COLOR"] not in tooltip._label.styleSheet()


# --- HoverTooltipMixin: the widget half of the themed tooltip ---

def _enter_event(widget):
    """A real QEnterEvent over the widget's centre.

    Offscreen tests cannot move the cursor through the window system, so the
    pointer position is faked with QCursor.setPos and the enter is delivered by
    hand - the same split tests/qt_mousing uses for press/release.
    """
    centre = QPointF(widget.rect().center())
    return QEnterEvent(centre, centre, QPointF(widget.mapToGlobal(widget.rect().center())))


def _hover(widget):
    """Put the real cursor over ``widget`` and deliver the enter event."""
    QCursor.setPos(widget.mapToGlobal(widget.rect().center()))
    widget.enterEvent(_enter_event(widget))


def test_hover_tooltip_shows_the_themed_tooltip_after_the_delay(qtbot):
    button = TooltipButton("x")
    button.TOOLTIP_DELAY_MS = 10
    button.setToolTip("ویرایش")
    qtbot.addWidget(button)
    button.show()

    _hover(button)
    assert button._tooltip_timer.isActive()
    qtbot.wait(80)

    assert CustomTooltip.instance().isVisible()
    assert CustomTooltip.instance()._label.text() == "ویرایش"


def test_hover_tooltip_carries_the_widgets_tone(qtbot):
    """A widget that explains a destructive action is coloured for it: the tone
    travels with the show call, so the widget's own declaration is what counts."""
    button = TooltipButton("x")
    button.setToolTip("حذف")
    button.TOOLTIP_TONE = "danger"
    qtbot.addWidget(button)
    button.show()
    palette = APP_CONFIG.get_current_palette()

    _hover(button)
    button._show_custom_tooltip()

    assert CustomTooltip.instance().isVisible()
    assert palette["HOLIDAY_COLOR"] in CustomTooltip.instance()._label.styleSheet()


def test_hover_delay_comes_from_the_shared_constant(qtbot):
    """The grid and the event manager read one value; a change here is a change
    everywhere rather than a drift between two hardcoded numbers."""
    button = TooltipButton("x")
    button.setToolTip("ویرایش")
    qtbot.addWidget(button)
    button.show()

    _hover(button)

    assert button._tooltip_timer.interval() == TOOLTIP_DELAY_MS


def test_hover_tooltip_without_text_never_arms(qtbot):
    button = TooltipButton("x")
    button.TOOLTIP_DELAY_MS = 10
    qtbot.addWidget(button)
    button.show()

    _hover(button)

    assert not button._tooltip_timer.isActive()


def test_hover_tooltip_is_skipped_when_the_cursor_is_elsewhere(qtbot):
    """A stale timer must not pop a tooltip after a scroll, a menu or an overlay
    broke the enter/leave chain - the cursor position is the source of truth."""
    button = TooltipButton("x")
    button.setToolTip("ویرایش")
    qtbot.addWidget(button)
    button.show()

    QCursor.setPos(0, 0)
    button._show_custom_tooltip()
    assert not CustomTooltip.instance().isVisible()

    QCursor.setPos(button.mapToGlobal(button.rect().center()))
    button._show_custom_tooltip()
    assert CustomTooltip.instance().isVisible()
    CustomTooltip.instance().hide()


def test_setToolTip_never_reaches_qt(qtbot):
    """Qt's own tooltip must stay unset (it renders as an unthemed box on
    Windows), while assistive tech still gets the description."""
    button = TooltipButton("x")
    button.setToolTip("ویرایش")

    assert button.toolTip() == ""
    assert button.accessibleDescription() == "ویرایش"


def test_pressing_a_tooltip_widget_dismisses_its_tooltip(qtbot):
    """Clicking edits or deletes the row, so the tooltip must not linger over
    the editor or the row that is about to be rebuilt."""
    button = TooltipButton("x")
    qtbot.addWidget(button)
    button.show()
    button._tooltip_timer.start(5000)
    CustomTooltip.instance().show_tooltip("ویرایش", QPoint(200, 200), owner=button)

    button.mousePressEvent(press(button))

    assert not button._tooltip_timer.isActive()
    assert not CustomTooltip.instance().isVisible()


def test_hiding_a_tooltip_widget_dismisses_its_tooltip(qtbot):
    label = TooltipLabel("متن")
    label.setToolTip("شرح")
    qtbot.addWidget(label)
    label.show()
    CustomTooltip.instance().show_tooltip("شرح", QPoint(200, 200), owner=label)
    assert CustomTooltip.instance().isVisible()

    label.hide()

    assert not CustomTooltip.instance().isVisible()


def test_one_widgets_dismiss_leaves_another_widgets_flash_alone(qtbot):
    """There is one shared tooltip window: a widget going away must not cut
    short a «کپی شد» flash (or another widget's tooltip) it does not own."""
    tooltip = CustomTooltip.instance()
    qtbot.addWidget(tooltip)
    label = TooltipLabel("متن")
    label.setToolTip("شرح")
    qtbot.addWidget(label)
    label.show()

    tooltip.flash_tooltip("کپی شد", QPoint(200, 200), duration_ms=1000)
    label.cancel_pending_tooltip()

    assert tooltip.isVisible()
    assert tooltip._label.text() == "کپی شد"


def test_cancel_pending_tooltip_is_safe_to_call_redundantly(qtbot):
    """Hosts call it on every row when the list scrolls, shown or not."""
    button = TooltipButton("x")
    button.setToolTip("ویرایش")
    qtbot.addWidget(button)
    button.cancel_pending_tooltip()
    button.cancel_pending_tooltip()
    assert not CustomTooltip.instance().isVisible()


def test_hiding_a_widget_wins_over_a_hover_still_counting_down(qtbot):
    """A tooltip queued by the timer must not pop over a widget that has since
    been hidden (the list rebuilds its rows on every filter change)."""
    label = TooltipLabel("متن")
    label.TOOLTIP_DELAY_MS = 10
    label.setToolTip("شرح")
    qtbot.addWidget(label)
    label.show()
    _hover(label)

    label.hide()
    qtbot.wait(80)

    assert not CustomTooltip.instance().isVisible()

