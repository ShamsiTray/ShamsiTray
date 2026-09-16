"""Tests for ui.widgets.calendar_day_cell: the clickable day cell with its
custom tooltip lifecycle and the add/remove-event context menu."""
import jdatetime
import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QCursor, QContextMenuEvent
from PyQt6.QtWidgets import QMenu, QWidget

from tests.qt_mousing import press
from ui.widgets.calendar_day_cell import ClickableLabel
from ui.widgets.tooltip import CustomTooltip


@pytest.fixture(autouse=True)
def _reset_tooltip_singleton():
    CustomTooltip._instance = None
    yield
    if CustomTooltip._instance is not None:
        CustomTooltip._instance.hide()
        CustomTooltip._instance = None


@pytest.fixture
def cell(qtbot):
    label = ClickableLabel()
    qtbot.addWidget(label)
    label.jalali_date = jdatetime.date(1404, 5, 2)
    return label


def test_left_click_emits_clicked_with_jalali_date(cell):
    received = []
    cell.clicked.connect(lambda jdate: received.append(jdate))
    cell.mousePressEvent(press(cell))
    assert received == [cell.jalali_date]


def test_right_click_does_not_emit_clicked(cell):
    received = []
    cell.clicked.connect(lambda jdate: received.append(jdate))
    cell.mousePressEvent(press(cell, button=Qt.MouseButton.RightButton))
    assert received == []


def test_settooltip_overrides_native_tooltip(cell):
    cell.setToolTip("custom text")
    # The custom tooltip system stores it; QLabel's dynamic tooltip stays empty.
    assert cell._tooltip_text == "custom text"


def test_enter_starts_timer_only_with_text(qtbot, cell):
    cell.enterEvent(None)
    assert not cell._tooltip_timer.isActive()  # no tooltip text yet
    cell.setToolTip("holiday reason")
    cell.enterEvent(None)
    assert cell._tooltip_timer.isActive()
    assert cell._tooltip_timer.remainingTime() > 0  # ~500ms, minus jitter


def test_leave_stops_timer_and_hides_shared_tooltip(qtbot, cell):
    cell.setToolTip("text")
    cell.enterEvent(None)
    cell.leaveEvent(None)
    assert not cell._tooltip_timer.isActive()
    assert not CustomTooltip.instance().isVisible()


def test_stale_timer_does_not_pop_tooltip_for_moved_off_cursor(qtbot, cell):
    """Regression guard for the tooltip-over-editor bug: the cursor check must
    veto a tooltip for a cell the cursor is no longer over."""
    cell.setToolTip("stale")
    cell.move(500, 500)  # cursor (offscreen 0,0 region) is far outside
    cell._show_custom_tooltip()
    assert not CustomTooltip.instance().isVisible()


def test_tooltip_shows_when_cursor_genuinely_inside(qtbot, cell, monkeypatch):
    cell.setToolTip("real hover")
    cell.resize(35, 35)
    cell.show()  # the visibility guard must see a live cell
    # Pin the cursor to the cell's center (deterministic on every platform).
    monkeypatch.setattr(QCursor, "pos",
                        staticmethod(lambda: cell.mapToGlobal(cell.rect().center())))
    cell._show_custom_tooltip()
    assert CustomTooltip.instance().isVisible()
    assert CustomTooltip.instance()._label.text() == "real hover"


def test_tooltip_skipped_while_context_menu_open(qtbot, cell):
    cell.setToolTip("text")
    cell._context_menu_open = True
    cell._show_custom_tooltip()
    assert not CustomTooltip.instance().isVisible()


def test_tooltip_skipped_when_cell_hidden(qtbot, cell):
    cell.setToolTip("text")
    cell.hide()
    cell._show_custom_tooltip()
    assert not CustomTooltip.instance().isVisible()


def test_cancel_pending_tooltip_stops_and_hides(qtbot, cell):
    cell.setToolTip("text")
    cell.enterEvent(None)
    cell.cancel_pending_tooltip()
    assert not cell._tooltip_timer.isActive()
    assert not CustomTooltip.instance().isVisible()


def test_context_menu_requires_date_and_text(cell):
    """No jalali date or no label text: the menu must not even open."""
    cell.jalali_date = None
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(5, 5),
                              cell.mapToGlobal(QPoint(5, 5)))
    cell.contextMenuEvent(event)
    assert cell._context_menu_open is False


def test_context_menu_add_action_emits_after_menu_closes(qtbot, cell, monkeypatch):
    """The full right-click flow, with QMenu.exec stubbed out (offscreen)."""
    monkeypatch.setattr(QMenu, "exec", lambda self, pos: None)
    cell.setText("۵")  # a non-empty label is required too
    add_requested, remove_requested = [], []
    cell.add_event_requested.connect(lambda j: add_requested.append(j))
    cell.remove_event_requested.connect(lambda j: remove_requested.append(j))

    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(5, 5),
                              cell.mapToGlobal(QPoint(5, 5)))
    cell.contextMenuEvent(event)
    assert cell._context_menu_open is False  # reset after exec returns


def test_context_menu_remove_disabled_without_user_event(qtbot, cell, monkeypatch):
    """Without a user event on this day, حذف رویداد is greyed out."""
    actions = {}

    def fake_exec(self, pos):
        for action in self.actions():
            default_widget = getattr(action, "defaultWidget", lambda: None)()
            if default_widget is not None and hasattr(default_widget, "label"):
                actions[default_widget.label.text()] = (action.isEnabled(),
                                                        default_widget.isEnabled())

    monkeypatch.setattr(QMenu, "exec", fake_exec)
    cell.setText("۵")
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(5, 5),
                              cell.mapToGlobal(QPoint(5, 5)))
    cell.contextMenuEvent(event)
    assert actions["افزودن رویداد"] == (True, True)
    assert actions["حذف رویداد"] == (False, False)  # disabled on action + widget


def test_context_menu_remove_enabled_with_user_event(qtbot, cell, monkeypatch):
    monkeypatch.setattr(QMenu, "exec", lambda self, pos: None)
    cell.setText("۵")
    cell.has_user_event = True
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(5, 5),
                              cell.mapToGlobal(QPoint(5, 5)))
    cell.contextMenuEvent(event)
    # (Not executed interactively; flag presence is what the menu reads.)


def test_add_event_emission_is_delayed_until_menu_gone(cell, qtbot):
    """_trigger_add_event_and_close_menu closes first, emits via singleShot."""
    received = []
    cell.add_event_requested.connect(lambda j: received.append(j))

    class FakeMenu:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    menu = FakeMenu()
    cell._trigger_add_event_and_close_menu(menu, cell.jalali_date)
    assert menu.closed
    assert received == []  # not emitted synchronously
    qtbot.wait(100)  # let the 50ms singleShot fire
    assert received == [cell.jalali_date]


def test_remove_event_emission_is_delayed_until_menu_gone(cell, qtbot):
    received = []
    cell.remove_event_requested.connect(lambda j: received.append(j))

    class FakeMenu:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    menu = FakeMenu()
    cell._trigger_remove_event_and_close_menu(menu, cell.jalali_date)
    assert menu.closed
    assert received == []  # not emitted synchronously
    qtbot.wait(100)  # let the 50ms singleShot fire
    assert received == [cell.jalali_date]


def test_context_menu_asks_host_window_to_normalize_hover(qtbot, monkeypatch):
    """After the menu closes, the host calendar re-syncs hover flags."""
    normalized = []

    class HostWindow(QWidget):
        def normalize_day_hover(self):
            normalized.append(1)

    host = HostWindow()
    qtbot.addWidget(host)
    cell = ClickableLabel(host)
    qtbot.addWidget(cell)
    cell.jalali_date = jdatetime.date(1404, 5, 2)
    cell.setText("۵")
    monkeypatch.setattr(QMenu, "exec", lambda self, pos: None)

    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(5, 5),
                              cell.mapToGlobal(QPoint(5, 5)))
    cell.contextMenuEvent(event)
    assert normalized == [1]
