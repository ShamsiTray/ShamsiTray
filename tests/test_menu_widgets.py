"""Widget tests for the tray-menu action widgets (offscreen platform)."""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMenu, QWidgetAction

from ui.widgets.menu_widgets import EventsActionWidget


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def events_menu(qapp):
    menu = QMenu()
    action = QWidgetAction(menu)
    widget = EventsActionWidget(menu)
    action.setDefaultWidget(widget)
    menu.addAction(action)
    menu.popup(QPoint(0, 0))
    yield menu, widget
    menu.close()


def _click(target, x, y):
    QTest.mouseMove(target, target.rect().center())
    QTest.mouseClick(target, Qt.MouseButton.LeftButton, pos=QPoint(x, y))


def test_clicking_header_keeps_menu_open(events_menu):
    menu, widget = events_menu
    _click(widget.header_label, 5, 5)
    assert menu.isVisible()


def test_clicking_divider_keeps_menu_open(events_menu):
    menu, widget = events_menu
    _click(widget.h_divider, 5, 5)
    assert menu.isVisible()


def test_clicking_container_padding_keeps_menu_open(events_menu):
    menu, widget = events_menu
    _click(widget, widget.width() // 2, widget.height() - 3)
    assert menu.isVisible()


def test_import_and_export_buttons_still_fire(events_menu):
    _menu, widget = events_menu
    fired = []
    widget.import_triggered.connect(lambda: fired.append('import'))
    widget.export_triggered.connect(lambda: fired.append('export'))
    _click(widget.import_button, 5, 5)
    _click(widget.export_button, 5, 5)
    assert fired == ['import', 'export']
