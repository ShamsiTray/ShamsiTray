"""Tests for ui.widgets.go_to_date: the jump-to-date popup over the calendar."""
import jdatetime
import pytest

from config import APP_CONFIG
from ui.widgets.go_to_date import GoToDateWindow
from utils.date_utils import to_persian_digits
from utils.ui_helpers import DigitsFirstCombo


@pytest.fixture(autouse=True, scope="module")
def _app_fonts(qapp):
    """The production app always starts with its bundled Vazirmatn fonts
    (main.py loads them before any window exists), and this module's
    growth/height assertions are measured against those metrics. Loading is
    idempotent; without it a lone run of this file depends on the accident
    of test_asset_loader (alphabetically earlier) having loaded them.
    Depends on qapp: QFontDatabase needs the QApplication to exist."""
    from utils.asset_loader import load_fonts
    load_fonts()


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


def test_empty_year_direct_confirm_is_silently_ignored(popup, qtbot):
    """A direct _on_confirm() with an empty year is a no-op (the guard):
    no emit, no error surface, no resize — the refusal UX is the greyed
    button itself, not a message that Enter can no longer trigger."""
    received = []
    popup.date_selected.connect(lambda y, m: received.append((y, m)))
    popup.show()
    height_before = popup.height()
    popup.year_input.clear()  # the fixture pre-fills today's year
    popup._on_confirm()
    assert received == []
    assert not popup.error_label.isVisible()
    assert popup.height() == height_before


def test_out_of_range_year_direct_confirm_is_ignored_hint_stays(popup, qtbot):
    """A direct _on_confirm() with an out-of-range year is ignored too; the
    range message on screen is the mixin's LIVE hint (it appeared on typing,
    not on confirm) and stays until the input changes."""
    received = []
    popup.date_selected.connect(lambda y, m: received.append((y, m)))
    popup.show()
    popup.year_input.setText("900")
    popup._on_confirm()
    assert received == []
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


# --- live year-range error (#6) -----------------------------------------------------------


def test_out_of_range_year_shows_range_error_while_typing(popup, qtbot):
    """The red border alone left users guessing which years are valid: while
    the typed year is out of range, the range MESSAGE must stay on screen."""
    popup.show()
    popup.year_input.setText(to_persian_digits(9999))
    assert popup.error_label.isVisible()
    assert to_persian_digits(GoToDateWindow.MAX_YEAR) in popup.error_label.text()
    assert to_persian_digits(GoToDateWindow.MIN_YEAR) in popup.error_label.text()
    # The card grows with the hint (same rule the confirm-time error uses).
    assert popup.height() > popup._initial_height


def test_valid_year_hides_range_error_and_restores_height(popup, qtbot):
    popup.show()
    popup.year_input.setText(to_persian_digits(9999))
    assert popup.error_label.isVisible()
    popup.year_input.setText(to_persian_digits(1400))
    assert not popup.error_label.isVisible()
    assert popup.height() == popup._initial_height


def test_range_error_survives_each_keystroke_of_an_invalid_year(popup, qtbot):
    """Regression guard: _clear_error runs BEFORE the error-state update on
    textChanged; hiding there would flicker the message away on every digit."""
    popup.show()
    popup.year_input.setText("9")
    assert popup.error_label.isVisible()
    popup.year_input.setText("99")
    assert popup.error_label.isVisible()
    popup.year_input.setText("999")
    assert popup.error_label.isVisible()
    popup.year_input.setText("9999")
    assert popup.error_label.isVisible()


def test_enter_on_empty_year_submits_nothing(popup, qtbot):
    """Enter is routed through the تایید button itself, and an empty year
    keeps that button disabled: no submission, no confirm-time error text,
    and the card stays open."""
    received = []
    popup.date_selected.connect(lambda y, m: received.append((y, m)))
    popup.show()
    popup.year_input.clear()
    popup.year_input.returnPressed.emit()
    assert received == []
    assert not popup.error_label.isVisible()
    assert popup.isVisible()  # the refusal is a no-op, not a close


def test_enter_respects_a_disabled_button_even_for_a_valid_year(popup, qtbot):
    """The routing itself must go through the BUTTON: with a submittable
    year but the button forcibly disabled, Enter does nothing — a direct
    returnPressed → _on_confirm wiring would submit here."""
    received = []
    popup.date_selected.connect(lambda y, m: received.append((y, m)))
    popup.show()
    popup.year_input.setText("1404")  # valid → the state keeps it enabled
    popup.confirm_button.setEnabled(False)  # force-disable regardless
    popup.year_input.returnPressed.emit()
    assert received == []
    assert popup.isVisible()


# --- confirm button greyed out while the year is invalid -----------------------------


def test_confirm_button_disabled_while_year_invalid(popup):
    """The تایید button must be greyed out for an out-of-range year and come
    back the moment the year is valid again."""
    popup.year_input.setText("1999")
    assert popup._year_error is True
    assert not popup.confirm_button.isEnabled()
    popup.year_input.setText(to_persian_digits(1400))
    assert popup.confirm_button.isEnabled()


def test_confirm_button_disabled_state_covers_persian_and_english_digits(popup):
    popup.year_input.setText(to_persian_digits("1601"))
    assert not popup.confirm_button.isEnabled()
    popup.year_input.setText("1600")
    assert popup.confirm_button.isEnabled()


def test_invalid_year_return_pressed_does_not_emit(popup, qtbot):
    """Enter with an out-of-range year must refuse the same way a disabled
    button would: no date_selected, live hint stays up."""
    received = []
    popup.date_selected.connect(lambda y, m: received.append((y, m)))
    popup.show()
    popup.year_input.setText(to_persian_digits("1700"))
    popup.year_input.returnPressed.emit()
    assert received == []
    assert popup.error_label.isVisible()


# --- confirm button follows the input's actual submittability -------------------------


@pytest.mark.parametrize("year_text, expected_enabled", [
    ("", False),        # empty: nothing to confirm
    ("abc", False),     # non-numeric
    ("1199", False),    # just below the range
    ("1601", False),    # just above the range
    ("1200", True),     # range start
    ("1600", True),     # range end
    ("1404", True),     # comfortably inside
])
def test_confirm_button_enabled_only_for_submittable_year(popup, year_text, expected_enabled):
    """The تایید button derives from whether the CURRENT input is submittable:
    empty / non-numeric / out of range all keep it greyed out; a year inside
    1200–1600 enables it. (Empty is distinct from out-of-range on purpose —
    the shared mixin must not flag an empty field with the red-border hint.)"""
    popup.year_input.setText(to_persian_digits(year_text) if year_text.isdigit() else year_text)
    assert popup.confirm_button.isEnabled() is expected_enabled


def test_confirm_button_start_disabled_when_year_empty(popup):
    """The button state must derive from the actual input, not sit stale: an
    empty year field — the state before any valid year is present — keeps
    تایید greyed out from the very first keystroke state."""
    popup.year_input.clear()
    assert not popup.confirm_button.isEnabled()


def test_confirm_button_tracks_each_edit_transition(popup):
    """Valid → empty → valid: the button greys and un-greys on every change,
    including the empty state the out-of-range flip never reports."""
    popup.year_input.setText("1404")
    assert popup.confirm_button.isEnabled()
    popup.year_input.clear()  # valid → empty: must disable, not stay stale
    assert not popup.confirm_button.isEnabled()
    popup.year_input.setText(to_persian_digits(1500))
    assert popup.confirm_button.isEnabled()


def test_empty_year_is_not_reported_out_of_range(popup):
    """The mixin keeps its meaning (a COMPLETE year outside the bounds) — an
    empty field greys the button via submittability, not via the error flag."""
    popup.year_input.clear()
    assert popup._year_is_out_of_range() is False
    assert popup._year_error is False
    assert not popup.error_label.isVisible()


def test_invalid_year_return_pressed_with_empty_year_does_not_emit(popup, qtbot):
    """Enter on an empty field does nothing at all: the disabled button
    swallows the key and _on_confirm's own guard would refuse too."""
    received = []
    popup.date_selected.connect(lambda y, m: received.append((y, m)))
    popup.show()
    popup.year_input.clear()
    popup.confirm_button.click()  # disabled button: click() must not emit
    popup.year_input.returnPressed.emit()
    assert received == []


# --- direct _on_confirm() can never submit an invalid year ---------------------------


@pytest.mark.parametrize("year_text", [
    "",                                  # empty
    "abc",                               # non-numeric
    "1199", "1601",                      # just outside the range
    to_persian_digits("1700"),           # out of range, Persian digits
])
def test_direct_on_confirm_ignores_unsubmittable_years(popup, qtbot, year_text):
    """_year_is_submittable is the single source of truth: any path into
    _on_confirm (a direct call included) refuses an un-submittable year
    silently and leaves the card open."""
    received = []
    popup.date_selected.connect(lambda y, m: received.append((y, m)))
    popup.show()
    popup.year_input.setText(year_text)
    popup._on_confirm()
    assert received == []
    assert popup.isVisible()


# --- dead space under the error message ----------------------------------------------


def test_error_card_grows_exactly_to_the_message(popup, qtbot):
    """The dead-space regression: the card grows by the label's REAL wrapped
    height (heightForWidth at the card's inner width) — the old sizeHint
    measurement over-estimated word-wrapped labels and left a band of empty
    space between the hint and the button row."""
    popup.show()
    qtbot.wait(20)  # let the layout polish the stylesheet font
    popup.year_input.setText(to_persian_digits(9999))
    assert popup.error_label.isVisible()
    label_h = popup.error_label.heightForWidth(popup.width() - 30)
    assert label_h > 0
    # The label is pinned to its measured height — the layout can't inflate it.
    assert popup.error_label.minimumHeight() == label_h
    assert popup.error_label.maximumHeight() == label_h
    # The card is at most base + message + one spacing gap: no extra band.
    assert popup.height() <= popup._initial_height + label_h + 20


def test_error_card_restores_base_size_when_error_clears(popup, qtbot):
    popup.show()
    popup.year_input.setText(to_persian_digits(9999))
    assert popup.height() > popup._initial_height
    popup.year_input.setText(to_persian_digits(1400))
    assert popup.height() == popup._initial_height
    assert not popup.error_label.isVisible()


def test_show_error_fits_a_long_wrapped_message(popup, qtbot):
    """A message long enough to wrap on the 200px card must neither clip nor
    inflate the card: the window covers the layout's own minimum and never
    exceeds base + measured message + spacing."""
    popup.show()
    qtbot.wait(20)
    long_message = ("این پیام خطای طولانی عمداً برای آزمودن شکستن خط در عرض "
                    "کارت ارسال می‌شود تا اندازه‌گیری دقیق بررسی شود")
    popup._show_error(long_message)
    label_h = popup.error_label.heightForWidth(popup.width() - 30)
    assert popup.error_label.minimumHeight() == label_h
    # No clipping: the window covers everything the layout minimally needs.
    assert popup.height() >= popup.layout().minimumSize().height()
    # No inflation: at most the base card plus the message plus two gaps.
    assert popup.height() <= popup._initial_height + label_h + 20
