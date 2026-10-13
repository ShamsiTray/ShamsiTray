"""Tests for ui.widgets.checkbox: the FontAwesome custom checkboxes used in
the tray menu and the event editor."""
from PyQt6.QtCore import Qt

from config import APP_CONFIG
from tests.qt_mousing import press, release
from ui.widgets.checkbox import CustomCheckbox, IconCheckboxActionWidget


def _left_press(widget):
    return press(widget)


def test_custom_checkbox_initial_state(qtbot):
    box = CustomCheckbox("label text", is_checked=False)
    qtbot.addWidget(box)
    assert not box.isChecked()
    box2 = CustomCheckbox("checked", is_checked=True)
    qtbot.addWidget(box2)
    assert box2.isChecked()


def test_custom_checkbox_left_click_toggles_and_emits(qtbot):
    box = CustomCheckbox("toggle me")
    qtbot.addWidget(box)
    seen = []
    box.toggled.connect(seen.append)
    box.mousePressEvent(_left_press(box))
    assert box.isChecked()
    assert seen == [True]
    box.mousePressEvent(_left_press(box))
    assert not box.isChecked()
    assert seen == [True, False]


def test_custom_checkbox_right_click_does_nothing(qtbot):
    box = CustomCheckbox("stay")
    qtbot.addWidget(box)
    seen = []
    box.toggled.connect(seen.append)
    box.mousePressEvent(press(box, button=Qt.MouseButton.RightButton))
    assert not box.isChecked()
    assert seen == []


def test_custom_checkbox_set_checked_only_emits_on_change(qtbot):
    box = CustomCheckbox("set")
    qtbot.addWidget(box)
    seen = []
    box.toggled.connect(seen.append)
    box.setChecked(True)
    box.setChecked(True)  # no change: no duplicate signal
    assert seen == [True]
    box.setChecked(False)
    assert seen == [True, False]


def test_custom_checkbox_disabled_is_greyed_and_inert(qtbot):
    box = CustomCheckbox("disabled")
    qtbot.addWidget(box)
    box.setChecked(True)
    box.setEnabled(False)
    box.update_visuals()
    palette = APP_CONFIG.get_current_palette()
    # Disabled only greys the box: the glyph still has to agree with
    # isChecked(), or a checked box that gets disabled draws an empty square
    # while isChecked() stays True.
    assert box.isChecked() is True
    assert box.icon_label.text() == APP_CONFIG.FAS.FA_SQUARE_CHECK_SOLID
    assert palette["GREY_COLOR"] in box.icon_label.styleSheet()
    assert palette["GREY_COLOR"] in box.text_label.styleSheet()
    assert palette["ACCENT_COLOR"] not in box.icon_label.styleSheet()
    seen = []
    box.toggled.connect(seen.append)
    box.mousePressEvent(_left_press(box))  # click on a disabled checkbox
    assert box.isChecked() is True          # unchanged
    assert seen == []                       # no toggled signal


def test_custom_checkbox_disabled_unchecked_keeps_the_empty_square(qtbot):
    box = CustomCheckbox("disabled")
    qtbot.addWidget(box)
    box.setEnabled(False)
    box.update_visuals()
    assert box.isChecked() is False
    assert box.icon_label.text() == APP_CONFIG.FAS.FA_SQUARE_REGULAR


def test_custom_checkbox_checked_glyph_is_accent(qtbot):
    box = CustomCheckbox("accent")
    qtbot.addWidget(box)
    box.setChecked(True)
    box.update_visuals()
    palette = APP_CONFIG.get_current_palette()
    assert box.icon_label.text() == APP_CONFIG.FAS.FA_SQUARE_CHECK_SOLID
    assert palette["ACCENT_COLOR"] in box.icon_label.styleSheet()


def test_icon_checkbox_action_toggles_and_keeps_menu_open(qtbot):
    """The release must be swallowed: toggling a tray-menu checkbox may not
    activate-and-close the containing context menu."""
    widget = IconCheckboxActionWidget("menu item", is_checked=False)
    qtbot.addWidget(widget)
    seen = []
    widget.toggled.connect(seen.append)

    widget.mousePressEvent(_left_press(widget))
    assert widget.isChecked()
    assert seen == [True]

    release_event = release(widget)
    widget.mouseReleaseEvent(release_event)
    assert release_event.isAccepted()  # swallowed, never propagated to the menu


def test_icon_checkbox_action_set_checked_does_not_emit(qtbot):
    """Unlike CustomCheckbox, the menu variant's setChecked is silent (the
    menu rebuilds its own state when reopened)."""
    widget = IconCheckboxActionWidget("menu item", is_checked=False)
    qtbot.addWidget(widget)
    seen = []
    widget.toggled.connect(seen.append)
    widget.setChecked(True)
    assert widget.isChecked()
    assert seen == []


def test_icon_checkbox_action_disabled_click_inert(qtbot):
    widget = IconCheckboxActionWidget("menu item", is_checked=False)
    qtbot.addWidget(widget)
    widget.setEnabled(False)
    widget.mousePressEvent(_left_press(widget))
    assert widget.isChecked() is False
