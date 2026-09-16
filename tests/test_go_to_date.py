"""Tests for ui.widgets.go_to_date: the jump-to-date popup over the calendar."""
import jdatetime
import pytest

from config import APP_CONFIG
from ui.widgets.go_to_date import GoToDateWindow
from utils.date_utils import to_persian_digits
from utils.ui_helpers import DigitsFirstCombo


@pytest.fixture
def popup(qtbot):
    window = GoToDateWindow()
    qtbot.addWidget(window)
    return window


def test_constants_match_documented_range():
    assert GoToDateWindow.MIN_YEAR == 1200
    assert GoToDateWindow.MAX_YEAR == 1600


def test_popup_initial_state(popup):
    today = jdatetime.date.today()
    assert isinstance(popup.month_combo, DigitsFirstCombo)
    assert popup.month_combo.count() == 12
    assert popup.month_combo.currentIndex() == today.month - 1  # opens on today
    assert popup.year_input.text() == to_persian_digits(today.year)
    assert not popup.error_label.isVisible()


def test_month_items_are_digits_first_prefixed(popup):
    first = popup.month_combo.itemText(0)
    assert first.startswith(to_persian_digits("01"))
    assert "فروردین" in first
    last = popup.month_combo.itemText(11)
    assert "اسفند" in last


def test_year_validator_allows_only_four_digits(popup):
    validator = popup.year_input.validator()
    state, _, _ = validator.validate("1404", 0)
    assert state == validator.State.Acceptable
    state, _, _ = validator.validate("14045", 0)
    assert state == validator.State.Intermediate or state == validator.State.Invalid
    state, _, _ = validator.validate("abc", 0)
    assert state == validator.State.Invalid


def test_confirm_emits_year_month_and_closes(popup, qtbot):
    popup.year_input.setText("1403")
    popup.month_combo.setCurrentIndex(4)  # مرداد
    with qtbot.waitSignal(popup.date_selected, timeout=2000) as blocker:
        popup.confirm_button.click()
    assert blocker.args == [1403, 5]
    assert not popup.isVisible()


def test_return_pressed_confirms(popup, qtbot):
    popup.year_input.setText("1500")
    month = popup.month_combo.currentIndex() + 1
    with qtbot.waitSignal(popup.date_selected, timeout=2000) as blocker:
        popup.year_input.returnPressed.emit()
    assert blocker.args == [1500, month]


def test_empty_year_shows_error_and_grows_window(popup):
    popup.show()  # real visibility semantics for the child label
    height_before = popup.height()
    popup.year_input.clear()  # the fixture pre-fills today's year
    popup._on_confirm()
    assert popup.error_label.isVisible()
    assert "سال" in popup.error_label.text()
    assert popup.height() > height_before  # window grew to fit the message


def test_out_of_range_year_lists_bounds(popup):
    popup.show()
    popup.year_input.setText("900")
    popup._on_confirm()
    assert popup.error_label.isVisible()
    assert to_persian_digits("1200") in popup.error_label.text()
    assert to_persian_digits("1600") in popup.error_label.text()


def test_out_of_range_year_does_not_emit(popup, qtbot):
    received = []
    popup.date_selected.connect(lambda y, m: received.append((y, m)))
    popup.year_input.setText("1999")
    popup._on_confirm()
    assert received == []


def test_typing_clears_error_and_restores_size(popup):
    popup.show()
    popup.year_input.setText("900")
    popup._on_confirm()
    assert popup.error_label.isVisible()
    error_height = popup.height()
    popup.year_input.setText("1400")  # textChanged clears the error
    assert not popup.error_label.isVisible()
    assert popup.height() < error_height


def test_year_error_state_restyling(popup):
    palette = APP_CONFIG.get_current_palette()
    popup.year_input.setText("1700")
    assert popup._year_is_out_of_range() is True
    assert popup._year_error is True
    style = popup.year_input.styleSheet()
    assert palette["HOLIDAY_COLOR"] in style  # error style is holiday-red
    popup.year_input.setText("1400")
    assert popup._year_error is False


def test_cancel_button_closes_without_emitting(popup, qtbot):
    received = []
    popup.date_selected.connect(lambda y, m: received.append((y, m)))
    popup.cancel_button.click()
    assert not popup.isVisible()
    assert received == []


def test_out_of_range_flags_use_persian_digits(popup):
    popup.year_input.setText(to_persian_digits("1199"))
    assert popup._year_is_out_of_range() is True
    popup.year_input.setText(to_persian_digits("1200"))
    assert popup._year_is_out_of_range() is False
    popup.year_input.setText(to_persian_digits("1600"))
    assert popup._year_is_out_of_range() is False
    popup.year_input.setText(to_persian_digits("1601"))
    assert popup._year_is_out_of_range() is True


def test_paint_rounded_card_offscreen(popup):
    popup.resize(200, 200)
    pixmap = popup.grab()
    assert not pixmap.isNull()
