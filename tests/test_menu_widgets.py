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


def test_arrow_aware_text_zone_trims_the_leading_edge_more():
    """The arrow-aware zone is lopsided by design: 10px off the leading edge,
    4px off the trailing one.

    ``QRect.adjust`` ADDS to each edge, so these trims are the overflow check's
    bound rather than the arrow's box - the arrow is painted in the trailing
    padding gutter, outside the zone - and the extra leading trim is what
    settles the caption's ink on the RTL side of the row. It is not mirrored
    for LTR rows because ShamsiTray never lays one out."""
    from PyQt6.QtCore import QRect
    from ui.widgets.menu_widgets import CenteredTextMenu

    zone = QRect(10, 0, 100, 20)
    inset = CenteredTextMenu._arrow_aware_text_zone(zone)
    assert inset.left() == zone.left() + 10
    assert inset.right() == zone.right() - 4
    assert inset.width() == zone.width() - 14
    # Vertically untouched: only the row's ends carry the indicator.
    assert inset.top() == zone.top() and inset.bottom() == zone.bottom()
    # Lopsided trims move the centre by half their difference, and the caption
    # settles there by design rather than by accident.
    assert inset.center().x() == zone.center().x() + 3


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
