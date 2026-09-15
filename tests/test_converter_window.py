"""Date-converter UI tests: conversion both ways, validation, day-dropdown rebuild."""
import datetime

import jdatetime
import pytest

from ui.windows.converter_window import DateConverterWindow
from utils.date_utils import to_persian_digits


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
