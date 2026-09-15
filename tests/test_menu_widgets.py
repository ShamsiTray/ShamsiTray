"""Widget tests for the tray-menu action widgets (offscreen platform)."""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMenu, QWidgetAction

from ui.widgets.checkbox import IconCheckboxActionWidget
from ui.widgets.menu_widgets import MenuActionWidget


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


def _click(target, x, y):
    QTest.mouseMove(target, target.rect().center())
    QTest.mouseClick(target, Qt.MouseButton.LeftButton, pos=QPoint(x, y))


@pytest.fixture()
def checkbox_menu(qapp):
    menu = QMenu()
    action = QWidgetAction(menu)
    widget = IconCheckboxActionWidget("راه اندازی همراه با سیستم", False, parent=menu)
    action.setDefaultWidget(widget)
    menu.addAction(action)
    menu.popup(QPoint(0, 0))
    yield menu, widget
    menu.close()


def test_checkbox_toggle_keeps_menu_open(checkbox_menu):
    menu, widget = checkbox_menu
    _click(widget, 10, 10)
    assert widget.isChecked()
    assert menu.isVisible()


def test_checkbox_toggle_updates_and_stays_open(checkbox_menu):
    menu, widget = checkbox_menu
    _click(widget, 10, 10)
    assert widget.isChecked()
    _click(widget, 10, 10)
    assert not widget.isChecked()
    assert menu.isVisible()


def test_hover_clears_when_hidden(qapp):
    widget = MenuActionWidget("تبدیل تاریخ")
    widget.resize(120, 40)
    widget.show()
    widget._is_hovered = True
    widget.update()
    widget.hide()
    assert widget._is_hovered is False
