"""Date-converter UI tests: conversion both ways, validation, day-dropdown rebuild."""
import datetime

import jdatetime
import pytest

from ui.windows.converter_window import DateConverterWindow
from utils.date_utils import (describe_date_distance, format_distance_breakdown,
                              to_persian_digits)


@pytest.fixture
def window(qtbot):
    """A shown converter window: visibility assertions need a top-level window."""
    converter = DateConverterWindow()
    qtbot.addWidget(converter)
    converter.show()
    yield converter
    converter.close()


def make_converter():
    return DateConverterWindow()


def set_jalali_input(window, year_text, month_index, day_text):
    window.conversion_type_combo.setCurrentIndex(0)          # «شمسی به میلادی»
    window.month_combo.setCurrentIndex(month_index)
    window.year_input.setText(year_text)
    window.day_combo.setCurrentText(day_text)


def test_default_state_is_today_jalali_to_gregorian(window):
    today = jdatetime.date.today()
    assert window.conversion_type_combo.currentText() == "شمسی به میلادی"
    assert window.year_input.text() == to_persian_digits(str(today.year))
    assert window.month_combo.currentIndex() == today.month - 1
    assert window.day_combo.currentText() == to_persian_digits(str(today.day))


def test_open_does_not_focus_the_year_field(window, qtbot):
    """Like the app's other windows, the converter opens with no field claiming
    focus; the prefilled year stays inert until the user actually clicks it."""
    qtbot.wait(150)  # the old steal fired 100 ms after show - outlast it
    assert window.focusWidget() is not window.year_input


def test_convert_known_jalali_date(window):
    set_jalali_input(window, "۱۴۰۳", 0, "۱")
    window._convert_date()
    assert window.gregorian_date_value_1.text() == "2024-03-20"
    assert window.jalali_date_value_1.text() == to_persian_digits("1403/01/01")
    assert window.output_widget.isVisible()
    assert window.leap_year_status.text() != ""


def test_convert_known_gregorian_date(window):
    window.conversion_type_combo.setCurrentIndex(1)          # «میلادی به شمسی»
    window.month_combo.setCurrentIndex(2)                    # March
    window.year_input.setText("2024")
    window.day_combo.setCurrentText("20")
    window._convert_date()
    assert window.jalali_date_value_1.text() == to_persian_digits("1403/01/01")
    assert window.gregorian_date_value_1.text() == "2024-03-20"


def test_convert_today_shows_is_today_message(window):
    window._convert_date()
    assert window.elapsed_text.text() == "تاریخ امروز است."


def test_empty_year_shows_error(window):
    window.year_input.clear()
    window._convert_date()
    assert window.status_message.isVisible()
    assert "سال" in window.status_message.text()


def test_out_of_range_jalali_year_shows_error(window):
    set_jalali_input(window, "1700", 0, "۱")
    window._convert_date()
    assert window.status_message.isVisible()
    assert "۱۶۰۰" in window.status_message.text()


def test_invalid_day_for_month_shows_error(window):
    # 1404 Esfand has 29 days; force day 30 into the combo and convert.
    set_jalali_input(window, "۱۴۰۴", 11, "۲۹")
    window._update_day_dropdown()
    window.day_combo.setCurrentIndex(window.day_combo.count() - 1)  # 29, valid
    window.year_input.setText("۱۴۰۴")
    window._convert_date()   # valid; should not raise
    assert not window.status_message.isVisible()


def test_day_dropdown_respects_jalali_month_lengths(window):
    set_jalali_input(window, "۱۴۰۳", 11, "۱")     # Esfand of leap year 1403
    window._update_day_dropdown()
    assert window.day_combo.count() == 30
    set_jalali_input(window, "۱۴۰۴", 11, "۱")     # Esfand of 1404
    window._update_day_dropdown()
    assert window.day_combo.count() == 29


def test_day_dropdown_respects_gregorian_feb(window):
    window.conversion_type_combo.setCurrentIndex(1)
    window.month_combo.setCurrentIndex(1)          # February
    window.year_input.setText("2024")
    window._update_day_dropdown()
    assert window.day_combo.count() == 29
    window.year_input.setText("2023")
    window._update_day_dropdown()
    assert window.day_combo.count() == 28


def test_changing_inputs_hides_results(window):
    set_jalali_input(window, "۱۴۰۳", 0, "۱")
    window._convert_date()
    assert window.output_widget.isVisible()
    window.year_input.setText("۱۴۰۲")
    assert not window.output_widget.isVisible()
    assert not window.middle_divider.isVisible()


def test_conversion_type_switch_resets_to_today(window):
    window.conversion_type_combo.setCurrentIndex(1)
    today = datetime.date.today()
    assert window.year_input.text() == str(today.year)
    assert window.month_combo.currentIndex() == today.month - 1
    window.conversion_type_combo.setCurrentIndex(0)
    jtoday = jdatetime.date.today()
    assert window.year_input.text() == to_persian_digits(str(jtoday.year))


def test_elapsed_time_for_a_past_date(window):
    set_jalali_input(window, "۱۴۰۰", 0, "۱")      # 1400/01/01 is in the past
    window._convert_date()
    assert "گذشته" in window.elapsed_text.text()
    assert "مانده" not in window.elapsed_text.text()


def _convert_jalali(window, target: jdatetime.date):
    set_jalali_input(window, to_persian_digits(str(target.year)),
                     target.month - 1, to_persian_digits(str(target.day)))
    window._convert_date()


def test_elapsed_line_is_the_shared_jalali_decomposition(window):
    """The converter's line and the calendar's «فاصله تا امروز» notice must not be
    able to disagree, so the line comes from the same helper rather than a second
    decomposition."""
    target = jdatetime.date.today() + datetime.timedelta(days=800)
    _convert_jalali(window, target)
    expected = describe_date_distance(target, today=jdatetime.date.today())
    assert window.elapsed_text.text() == \
        f"فاصله زمانی: {format_distance_breakdown(expected)}"


def test_elapsed_line_breaks_the_units_down_in_jalali_not_gregorian(window):
    """A Persian calendar app means Jalali years and months here. The two calendars
    disagree on where the year boundary falls, so a span that crosses one lands on
    different month counts depending on which calendar is asked."""
    target = jdatetime.date.today() + datetime.timedelta(days=400)
    _convert_jalali(window, target)
    jalali = describe_date_distance(target, today=jdatetime.date.today())
    gregorian_years = target.togregorian().year - jdatetime.date.today().togregorian().year
    assert (jalali.years, jalali.months) != (gregorian_years, 0)
    assert f"{to_persian_digits(jalali.years)} سال" in window.elapsed_text.text() \
        or f"{to_persian_digits(jalali.months)} ماه" in window.elapsed_text.text()


def test_elapsed_line_reads_units_with_and(window):
    """The old line space-joined the units («۲ سال ۵ روز»); the shared formatter
    puts «و» between them."""
    target = jdatetime.date.today() + datetime.timedelta(days=760)
    _convert_jalali(window, target)
    distance = describe_date_distance(target, today=jdatetime.date.today())
    assert sum(1 for n in (distance.years, distance.months, distance.days) if n) >= 2
    assert " و " in window.elapsed_text.text()


def test_elapsed_line_for_today_is_unchanged(window):
    _convert_jalali(window, jdatetime.date.today())
    assert window.elapsed_text.text() == "تاریخ امروز است."


# --- live year-range error (#6) -----------------------------------------------------------


def test_out_of_range_year_keeps_range_message_visible(window):
    """Changing any input clears the results strip; while the year is out of
    range the strip must immediately re-show WHAT range is valid (#6)."""
    window.show()
    window.year_input.setText(to_persian_digits(3000))
    assert window.status_message.isVisible()
    assert to_persian_digits(DateConverterWindow.MAX_JALALI_YEAR) in window.status_message.text()
    assert window.height() > window._initial_height


def test_valid_year_hides_the_range_message(window):
    window.show()
    window.year_input.setText(to_persian_digits(3000))
    assert window.status_message.isVisible()
    window.year_input.setText(to_persian_digits(1400))
    assert not window.status_message.isVisible()
    assert window.height() == window._initial_height


def test_range_message_follows_the_calendar_mode(window):
    window.show()
    window.conversion_type_combo.setCurrentIndex(1)  # «میلادی به شمسی»
    window.year_input.setText("3000")
    assert window.status_message.isVisible()
    assert str(DateConverterWindow.MAX_GREGORIAN_YEAR) in window.status_message.text()
    assert str(DateConverterWindow.MIN_GREGORIAN_YEAR) in window.status_message.text()


# --- تبدیل button follows the input's actual submittability -------------------------


@pytest.mark.parametrize("year_text, expected_enabled", [
    ("", False),          # empty: nothing to convert
    ("abc", False),       # the validator blocks letters, but the predicate must not assume it
    ("0", False),         # below the Jalali floor
    ("1601", False),      # above the Jalali ceiling
    ("1", True),          # Jalali range start
    ("1600", True),       # Jalali range end
    ("1404", True),       # comfortably inside
])
def test_convert_button_enabled_only_for_submittable_jalali_year(window, year_text, expected_enabled):
    """In «شمسی به میلادی» the تبدیل button tracks the Jalali bounds: empty /
    non-numeric / out of range grey it out, a year inside 1–1600 enables it."""
    window.conversion_type_combo.setCurrentIndex(0)
    window.year_input.setText(to_persian_digits(year_text) if year_text.isdigit() else year_text)
    assert window.convert_button.isEnabled() is expected_enabled


def test_convert_button_uses_gregorian_bounds_in_the_other_mode(window):
    """The bounds are mode-dependent, so the same text can be valid under one
    calendar and not the other: 1601 is out of range for Jalali but perfectly
    valid for Gregorian."""
    window.conversion_type_combo.setCurrentIndex(1)  # «میلادی به شمسی»
    window.year_input.setText("1601")
    assert window.convert_button.isEnabled()

    window.conversion_type_combo.setCurrentIndex(0)  # back to Jalali
    window.year_input.setText("1601")                 # mode switch resets the year to today
    assert not window.convert_button.isEnabled()


def test_convert_button_state_recomputes_on_mode_switch(window):
    """The mode switch must leave the button judged by the NEW bounds.

    Switching modes refills the year field with today's date, which is inside
    both ranges, so today the visible outcome is the same either way - this
    pins the invariant (a valid year never leaves the button greyed out) rather
    than a specific verdict.
    """
    window.conversion_type_combo.setCurrentIndex(0)
    window.year_input.setText(to_persian_digits(1601))
    assert not window.convert_button.isEnabled()

    window.conversion_type_combo.setCurrentIndex(1)
    assert window.convert_button.isEnabled()

    window.conversion_type_combo.setCurrentIndex(0)
    assert window.convert_button.isEnabled()


def test_year_bounds_actually_differ_per_mode(window):
    """The mode-dependence the button relies on: the two calendars have
    different supported ranges, so a year can pass one and fail the other."""
    window.conversion_type_combo.setCurrentIndex(0)  # Jalali input
    assert window._year_bounds() == (DateConverterWindow.MIN_JALALI_YEAR,
                                     DateConverterWindow.MAX_JALALI_YEAR)
    window.conversion_type_combo.setCurrentIndex(1)  # Gregorian input
    assert window._year_bounds() == (DateConverterWindow.MIN_GREGORIAN_YEAR,
                                     DateConverterWindow.MAX_GREGORIAN_YEAR)


def test_convert_button_starts_enabled_for_today(window):
    """The window opens prefilled with today's year, which is always inside both
    ranges, so the button must not come up greyed out."""
    assert window.year_input.text()
    assert window.convert_button.isEnabled()


def test_convert_button_tracks_clearing_the_year(window):
    """Valid → empty → valid greys and un-greys on every edit, including the
    empty state the out-of-range flip never reports."""
    window.year_input.setText(to_persian_digits(1404))
    assert window.convert_button.isEnabled()
    window.year_input.clear()
    assert not window.convert_button.isEnabled()
    window.year_input.setText(to_persian_digits(1404))
    assert window.convert_button.isEnabled()


def test_empty_year_is_not_reported_out_of_range(window):
    """The mixin keeps its meaning (a COMPLETE year outside the bounds) — an
    empty field greys the button via submittability, not via the error flag."""
    window.year_input.clear()
    assert window._year_is_out_of_range() is False


def test_enter_does_not_convert_while_the_button_is_disabled(window):
    """Enter is routed through the BUTTON so a disabled one swallows it; a
    direct _convert_date must therefore never run for an unusable year."""
    window.year_input.clear()
    assert not window.convert_button.isEnabled()

    window.convert_button.click()          # disabled: click() must not emit
    window.year_input.returnPressed.emit()

    assert not window.status_message.isVisible()
    assert not window.output_widget.isVisible()


def test_copy_payloads_use_latin_digits_while_labels_show_persian(window):
    """Copying a converter row must match the calendar's «کپی تاریخ» convention.

    Copying label.text() put the Persian-digit DISPLAY text on the clipboard,
    so the same day copied to Latin digits from the calendar and to Persian
    digits from here."""
    from PyQt6.QtWidgets import QApplication
    from utils.date_utils import (format_gregorian_long, format_gregorian_numeric,
                                   format_jalali_long, format_jalali_numeric)

    set_jalali_input(window, "۱۴۰۳", 0, "۱")
    window._convert_date()
    j_date = jdatetime.date(1403, 1, 1)
    g_date = j_date.togregorian()
    clipboard = QApplication.clipboard()

    for label, expected in (
        (window.jalali_date_value_1, format_jalali_numeric(j_date)),
        (window.jalali_date_value_2, format_jalali_long(j_date, persian_digits=False)),
        (window.gregorian_date_value_1, format_gregorian_numeric(j_date)),
        (window.gregorian_date_value_2,
         format_gregorian_long(g_date, persian_digits=False)),
    ):
        window._copy_to_clipboard(label)
        assert clipboard.text() == expected

    # The visible Jalali rows still read in Persian digits - only the clipboard
    # payload is Latin, which is the whole point.
    assert window.jalali_date_value_1.text() == "۱۴۰۳/۰۱/۰۱"


def test_copy_payloads_are_rebuilt_on_every_conversion(window):
    """A second conversion must replace the payloads, not merge into them."""
    from PyQt6.QtWidgets import QApplication
    from utils.date_utils import format_jalali_numeric

    set_jalali_input(window, "۱۴۰۳", 0, "۱")
    window._convert_date()
    set_jalali_input(window, "۱۴۰۴", 5, "۱۵")
    window._convert_date()
    window._copy_to_clipboard(window.jalali_date_value_1)
    assert QApplication.clipboard().text() == format_jalali_numeric(jdatetime.date(1404, 6, 15))


def test_enter_converts_through_the_button_when_submittable(window):
    """The routing must not swallow Enter for a valid year — it goes through the
    button and still converts."""
    window.year_input.setText(to_persian_digits(1404))
    assert window.convert_button.isEnabled()

    window.year_input.returnPressed.emit()

    assert window.output_widget.isVisible()
