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


def test_arrow_aware_text_zone_insets_instead_of_shifting():
    """QRect.adjust ADDS to each edge, so adjusting +4 on left AND right shifts
    the zone - and the centred caption drawn in it - to the right. The
    arrow-aware zone must be an inset: narrower, same centre."""
    from PyQt6.QtCore import QRect

    from ui.widgets.menu_widgets import CenteredTextMenu

    zone = QRect(10, 0, 100, 20)
    inset = CenteredTextMenu._arrow_aware_text_zone(zone)
    assert inset.left() == zone.left() + 4
    assert inset.right() == zone.right() - 4
    assert inset.center().x() == zone.center().x()
    assert inset.width() == zone.width() - 8


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


def test_theme_row_labels_all_three_choices(qapp):
    """The theme row cycles system -> light -> dark, and labels every stop of
    the cycle - including «هماهنگ با سیستم», which the old two-state toggle had
    no representation for."""
    from config import APP_CONFIG
    from ui.widgets.menu_widgets import ThemeToggleActionWidget

    expected = {
        APP_CONFIG.Theme.SYSTEM: "تم برنامه: هماهنگ با سیستم",
        APP_CONFIG.Theme.LIGHT: "تم برنامه: روشن",
        APP_CONFIG.Theme.DARK: "تم برنامه: تاریک",
    }
    for choice, label in expected.items():
        widget = ThemeToggleActionWidget(lambda c=choice: c)
        assert widget.label.text() == label
        widget.deleteLater()

    # An unknown value degrades to the system label, never a crash.
    widget = ThemeToggleActionWidget(lambda: "nonsense")
    assert widget.label.text() == expected[APP_CONFIG.Theme.SYSTEM]
    widget.deleteLater()
