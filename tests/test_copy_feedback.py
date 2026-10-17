"""Tests for the copy submenu's in-place copied-row confirmation."""
import jdatetime
import pytest
from PyQt6.QtCore import QEvent, QPoint, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QMenu, QWidget, QWidgetAction

from tests.qt_mousing import release
from utils.date_utils import (
    format_gregorian_long,
    format_gregorian_numeric,
    format_jalali_long,
    format_jalali_numeric,
)
from ui.widgets.calendar_day_cell import ClickableLabel, CopyDateMenu
from ui.widgets.tooltip import CustomTooltip


@pytest.fixture(autouse=True)
def _hide_tooltip():
    tooltip = CustomTooltip.instance()
    tooltip.hide()
    yield
    tooltip.hide()


@pytest.fixture
def calendar(qtbot):
    window = QWidget()
    window.resize(305, 395)
    cell = ClickableLabel(window)
    cell.setGeometry(20, 20, 35, 35)
    cell.setText("۵")
    cell.jalali_date = jdatetime.date(1404, 5, 2)
    qtbot.addWidget(window)
    window.show()
    return window, cell


def _menus(cell):
    parent = QMenu(cell)
    copy_menu = cell._build_copy_date_menu(parent)
    assert isinstance(copy_menu, CopyDateMenu)
    return parent, copy_menu


def _copy_rows(menu):
    return [action for action in menu.actions() if not action.isSeparator()]


def _expected_payloads(date):
    jalali = format_jalali_numeric(date)
    gregorian = format_gregorian_numeric(date)
    jalali_full = format_jalali_long(date, persian_digits=False)
    gregorian_full = format_gregorian_long(date.togregorian(), persian_digits=False)
    return {
        "jalali": jalali,
        "jalali_full": jalali_full,
        "gregorian": gregorian,
        "gregorian_full": gregorian_full,
        "both": f"{jalali}\n{gregorian}",
        "both_full": f"{jalali_full}\n{gregorian_full}",
    }


@pytest.mark.parametrize(
    "mode", ["jalali", "jalali_full", "gregorian", "gregorian_full", "both", "both_full"]
)
def test_all_copy_modes_keep_their_clipboard_payload(calendar, mode):
    _window, cell = calendar
    parent, copy_menu = _menus(cell)
    action = next(action for action in _copy_rows(copy_menu) if action.data() == mode)
    clipboard = QApplication.clipboard()
    before = clipboard.text()

    action.trigger()

    assert clipboard.text() == _expected_payloads(cell.jalali_date)[mode]
    copy_menu._finish_copy()
    clipboard.setText(before)
    parent.close()


@pytest.mark.parametrize(
    ("x", "y"),
    [(12, 12), (258, 12), (258, 345)],
)
def test_copy_submenu_uses_normal_qt_placement(calendar, qtbot, x, y):
    """No geometry hijack anywhere in the class: Qt places the submenu as any
    native one, including when that means it extends past the calendar window
    (the feedback travels with the row, so placement need not be controlled)."""
    window, cell = calendar
    window.move(100, 100)
    cell.move(x, y)
    parent, copy_menu = _menus(cell)
    parent.popup(window.mapToGlobal(QPoint(5, 5)))
    copy_menu.popup(window.mapToGlobal(QPoint(window.width() - 3, window.height() - 20)))
    qtbot.wait(20)

    assert "showEvent" not in CopyDateMenu.__dict__
    assert copy_menu.frameGeometry().right() > window.frameGeometry().right()

    copy_menu.close()
    parent.close()


def test_mouse_release_morphs_the_row_without_closing_either_menu(calendar, qtbot):
    _window, cell = calendar
    parent, copy_menu = _menus(cell)
    parent.popup(QPoint(20, 20))
    copy_menu.popup(QPoint(60, 60))
    qtbot.wait(20)
    action = _copy_rows(copy_menu)[0]
    row = copy_menu.actionGeometry(action)

    copy_menu.mouseReleaseEvent(
        release(copy_menu, (row.center().x(), row.center().y())))

    assert copy_menu.isVisible()
    assert parent.isVisible()
    assert action.text() == "✓ کپی شد"
    assert action.data() == "copy_done"
    assert all(not other.isEnabled() for other in _copy_rows(copy_menu)
               if other is not action)
    assert all(not isinstance(other, QWidgetAction) for other in copy_menu.actions())
    copy_menu._finish_copy()


@pytest.mark.parametrize("key", [Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space])
def test_keyboard_activation_morphs_active_row(calendar, key):
    _window, cell = calendar
    _parent, copy_menu = _menus(cell)
    action = _copy_rows(copy_menu)[1]
    copy_menu.setActiveAction(action)

    copy_menu.keyPressEvent(
        QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))

    assert action.text() == "✓ کپی شد"
    assert action.data() == "copy_done"
    copy_menu._finish_copy()


def test_repeat_copy_restarts_the_delay_without_adding_rows(calendar, qtbot):
    _window, cell = calendar
    parent, copy_menu = _menus(cell)
    parent.popup(QPoint(20, 20))
    copy_menu.popup(QPoint(60, 60))
    qtbot.wait(20)
    action = _copy_rows(copy_menu)[0]
    original_row_count = len(copy_menu.actions())
    row = copy_menu.actionGeometry(action)

    copy_menu.mouseReleaseEvent(
        release(copy_menu, (row.center().x(), row.center().y())))
    qtbot.wait(250)
    copy_menu.mouseReleaseEvent(
        release(copy_menu, (row.center().x(), row.center().y())))

    assert copy_menu._reset_timer.isActive()
    assert copy_menu._reset_timer.remainingTime() > 400
    assert len(copy_menu.actions()) == original_row_count
    assert copy_menu.isVisible()
    copy_menu._finish_copy()


def test_copy_row_restores_after_delay(calendar, qtbot):
    _window, cell = calendar
    parent, copy_menu = _menus(cell)
    parent.popup(QPoint(20, 20))
    copy_menu.popup(QPoint(60, 60))
    qtbot.wait(20)
    action = _copy_rows(copy_menu)[0]
    copy_menu.mouseReleaseEvent(
        release(copy_menu, (copy_menu.actionGeometry(action).center().x(),
                            copy_menu.actionGeometry(action).center().y())))

    qtbot.wait(500)

    assert not copy_menu.isVisible()
    assert not parent.isVisible()
    assert action.text() == "تاریخ شمسی"
    assert action.isEnabled()


def test_row_feedback_does_not_change_shared_holiday_tooltip(calendar):
    _window, cell = calendar
    tooltip = CustomTooltip.instance()
    tooltip.show_tooltip("تعطیلی: نوروز", QPoint(20, 20))
    _parent, copy_menu = _menus(cell)

    _copy_rows(copy_menu)[0].trigger()

    assert tooltip.isVisible()
    assert tooltip._label.text() == "تعطیلی: نوروز"
    copy_menu._finish_copy()
