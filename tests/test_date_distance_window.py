"""
Tests for the two-date distance tool window.

The pins that matter: equality answers «دو تاریخ یکسان هستند.» (a fact about
the two picked dates, never the converter's «تاریخ امروز است.»), the
measurement is direction-agnostic (no «مانده/گذشته», the row order never
changes the numbers), every sentence comes from the shared neutral date-distance
helpers rather than a window-local rewrite, each secondary line shows only when
it says more than the lines above it, the calendar switch measures in either
calendar, and every result line copies itself on click or from the keyboard.
"""
import datetime

import jdatetime
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLabel

from config import APP_CONFIG
from ui.widgets.calendar_switch import CALENDAR_JALALI
from ui.widgets.event_input import DateSelectorRow, GregorianDateSelectorRow
from ui.widgets.tooltip import CustomTooltip
from ui.windows.date_distance_window import (CALENDAR_GREGORIAN, COPIED_MESSAGE,
                                             COPY_ALL_CORNER_INSET_PX,
                                             GREGORIAN_YEAR_MAX,
                                             GREGORIAN_YEAR_MIN, HERO_MIN_CONTRAST,
                                             JALALI_YEAR_MAX, JALALI_YEAR_MIN,
                                             DateDistanceWindow, DistanceRowMetrics)
from utils.date_utils import (describe_date_distance, describe_gregorian_distance,
                              format_distance_total_months, format_distance_units,
                              format_distance_weeks, to_persian_digits, year_range_hint)
from utils.ui_helpers import contrast_ratio, legible_on, mix_colors

from tests.qt_mousing import press

LRM = "\u200e"


class _FocusProbe:
    """Stands in for Qt's held-focus query in offscreen builds, where windows
    cannot be activated at all: records every clearFocus() the window issues."""

    def __init__(self):
        self.cleared = 0

    def clearFocus(self):
        self.cleared += 1


@pytest.fixture
def window(qtbot):
    w = DateDistanceWindow()
    qtbot.addWidget(w)
    return w


@pytest.fixture(autouse=True)
def _quiet_tooltip():
    tooltip = CustomTooltip.instance()
    tooltip.hide()
    yield
    tooltip.hide()


def _set_date(row, year, month, day):
    row.year_input.setText(str(year) if isinstance(row, GregorianDateSelectorRow)
                           else to_persian_digits(year))
    row.month_combo.setCurrentIndex(month - 1)
    row.day_combo.setCurrentIndex(day - 1)


def _hero(window):
    return f"{window.result_days.text()} {window.result_unit.text()}".strip()


def _lines(window):
    return (_hero(window), window.result_breakdown.text(), window.result_months.text(),
            window.result_weeks.text())


def _switch_to_gregorian(window):
    window.calendar_switch.gregorian_button.click()


@pytest.fixture
def flashes(monkeypatch):
    """Record every «✓ کپی شد» flash instead of showing it."""
    seen = []
    monkeypatch.setattr(CustomTooltip.instance(), "flash_tooltip",
                        lambda text, pos, *a, **k: seen.append(text))
    return seen


# ---------------------------------------------------------------- results

def test_window_opens_with_both_rows_on_today(window):
    today = jdatetime.date.today()
    assert window.from_row.picked() == today
    assert window.to_row.picked() == today
    assert window.result_message.text() == "دو تاریخ یکسان هستند."
    assert not window.result_message.isHidden()
    assert window.hero_row.isHidden()
    assert window.result_breakdown.isHidden() and window.result_months.isHidden()
    assert window.result_weeks.isHidden() and window.result_divider.isHidden()


def test_equal_dates_say_the_two_dates_are_equal(window):
    _set_date(window.from_row, 1400, 1, 1)
    _set_date(window.to_row, 1400, 1, 1)
    assert window.result_message.text() == "دو تاریخ یکسان هستند."
    assert _lines(window) == ("", "", "", "")


def test_hero_is_the_day_total_without_a_direction_word(window):
    _set_date(window.from_row, 1405, 1, 1)
    _set_date(window.to_row, 1405, 4, 15)
    assert _hero(window) == "۱۰۷ روز"
    assert window.result_message.isHidden() and not window.hero_row.isHidden()
    for text in _lines(window):
        assert "مانده" not in text and "گذشته" not in text


def test_the_documented_example_shows_all_four_readings(window):
    """2 شهریور 1382 → 22 اردیبهشت 1388."""
    _set_date(window.from_row, 1382, 6, 2)
    _set_date(window.to_row, 1388, 2, 22)
    assert _lines(window) == ("۲۰۸۸ روز", "۵ سال و ۸ ماه و ۲۰ روز",
                              "۶۸ ماه و ۲۰ روز", "۲۹۸ هفته و ۲ روز")
    for line in (window.hero_row, window.result_breakdown, window.result_months,
                 window.result_weeks):
        assert not line.isHidden()
    assert not window.result_divider.isHidden()


def test_secondary_lines_come_from_the_shared_formatters(window):
    first, second = jdatetime.date(1382, 6, 2), jdatetime.date(1388, 2, 22)
    _set_date(window.from_row, 1382, 6, 2)
    _set_date(window.to_row, 1388, 2, 22)
    distance = describe_date_distance(second, today=first)
    assert window.result_breakdown.text() == format_distance_units(distance)
    assert window.result_months.text() == format_distance_total_months(distance)
    assert window.result_weeks.text() == format_distance_weeks(distance)


def test_months_line_needs_a_year_to_say_anything_new(window):
    """Under a year «۳ ماه و ۱۴ روز» already IS the months reading."""
    _set_date(window.from_row, 1405, 1, 1)
    _set_date(window.to_row, 1405, 4, 15)
    assert window.result_breakdown.text() == "۳ ماه و ۱۴ روز"
    assert window.result_months.isHidden() and window.result_months.text() == ""
    assert window.result_weeks.text() == "۱۵ هفته و ۲ روز"


def test_exact_years_still_get_a_months_line(window):
    _set_date(window.from_row, 1400, 1, 1)
    _set_date(window.to_row, 1402, 1, 1)
    assert window.result_breakdown.text() == "۲ سال"
    assert window.result_months.text() == "۲۴ ماه"


def test_under_a_week_shows_only_the_hero(window):
    _set_date(window.from_row, 1405, 1, 1)
    _set_date(window.to_row, 1405, 1, 5)
    assert _hero(window) == "۴ روز"
    assert window.result_breakdown.isHidden() and window.result_months.isHidden()
    assert window.result_weeks.isHidden() and window.result_divider.isHidden()


def test_whole_weeks_without_a_month_show_weeks_only(window):
    _set_date(window.from_row, 1405, 1, 1)
    _set_date(window.to_row, 1405, 1, 21)
    assert _hero(window) == "۲۰ روز"
    assert window.result_breakdown.isHidden() and window.result_months.isHidden()
    assert window.result_weeks.text() == "۲ هفته و ۶ روز"
    assert not window.result_divider.isHidden()


def test_row_order_never_changes_what_is_shown(window):
    _set_date(window.from_row, 1400, 1, 1)
    _set_date(window.to_row, 1402, 3, 2)
    forward = _lines(window)
    _set_date(window.from_row, 1402, 3, 2)
    _set_date(window.to_row, 1400, 1, 1)
    assert _lines(window) == forward
    assert forward[1] and forward[2]  # a multi-year span carries both readings


# -------------------------------------------------------- year validation

def test_incomplete_or_out_of_range_year_clears_results(window):
    _set_date(window.from_row, 1400, 1, 1)
    _set_date(window.to_row, 1400, 1, 10)
    assert _hero(window) == "۹ روز"

    window.to_row.year_input.setText(to_persian_digits(9500))
    assert window.year_hint_label.text() == year_range_hint(JALALI_YEAR_MIN, JALALI_YEAR_MAX)
    assert not window.year_hint_label.isHidden()
    assert _lines(window) == ("", "", "", "")

    window.to_row.year_input.setText(to_persian_digits(1400))
    assert window.year_hint_label.text() == "" and window.year_hint_label.isHidden()
    assert _hero(window) == "۹ روز"


@pytest.mark.parametrize("calendar", [CALENDAR_JALALI, CALENDAR_GREGORIAN])
def test_empty_year_is_an_error_like_a_wrong_one(window, calendar):
    """The shared mixin treats empty as "not out of range"; this window cannot
    answer without a year, so it must say why: red border plus the range."""
    if calendar == CALENDAR_GREGORIAN:
        _switch_to_gregorian(window)
    first, second = window.active_rows()
    second.year_input.setText("")
    assert second._year_error is True and first._year_error is False
    assert not window.year_hint_label.isHidden()
    lo, hi = second._year_bounds()
    assert window.year_hint_label.text() == year_range_hint(
        lo, hi, persian_digits=calendar == CALENDAR_JALALI)
    assert _lines(window) == ("", "", "", "")
    second.year_input.setText(to_persian_digits(1400) if calendar == CALENDAR_JALALI else "2020")
    assert second._year_error is False and window.year_hint_label.isHidden()


def test_year_hint_is_large_enough_to_read(window):
    """Regression: the hint was 12px, smaller than every result line."""
    import re
    size = int(re.search(r"font-size:\s*(\d+)px", window.year_hint_label.styleSheet()).group(1))
    assert size >= 15


def test_event_editor_rows_do_not_flag_an_empty_year(qtbot):
    """flag_empty_year is opt-in: the editor's row keeps the mixin's rule."""
    row = DateSelectorRow()
    qtbot.addWidget(row)
    row.set_date(jdatetime.date(1405, 1, 1))
    row.year_input.setText("")
    assert row._year_is_out_of_range() is False
    assert row._year_error is False


# ------------------------------------------------------------ month labels

def test_jalali_months_are_numbered_like_the_converter(window):
    labels = [window.from_row.month_combo.itemText(i) for i in range(12)]
    assert labels[0] == "۰۱ - فروردین" and labels[5] == "۰۶ - شهریور"
    assert labels[11] == "۱۲ - اسفند"
    assert [window.from_row.month_combo.itemData(i) for i in range(12)] == list(range(1, 13))


def test_gregorian_months_are_numbered_and_read_digits_first(window):
    labels = [window.greg_from_row.month_combo.itemText(i) for i in range(12)]
    # The leading LRM keeps «09 - September» one left-to-right run under the
    # combo's RTL base; without it the label paints as «September - 09».
    assert labels[0] == f"{LRM}01 - January" and labels[8] == f"{LRM}09 - September"
    assert [window.greg_from_row.month_combo.itemData(i) for i in range(12)] == list(range(1, 13))


def test_default_row_keeps_the_editors_bare_month_names(qtbot):
    row = DateSelectorRow()
    qtbot.addWidget(row)
    row.set_date(jdatetime.date(1405, 1, 1))
    assert row.month_combo.itemText(5) == "شهریور"


# --------------------------------------------------------- field layout

def test_fields_read_year_month_day_from_the_left_edge(window):
    window.show()
    for row in (window.from_row, window.to_row):
        x = {name: widget.mapTo(window, widget.rect().topLeft()).x()
             for name, widget in (("label", row.row_label), ("day", row.day_combo),
                                  ("month", row.month_combo), ("year", row.year_input))}
        assert x["year"] < x["month"] < x["day"] < x["label"]


def test_fields_keep_their_proportions_and_fit_their_month_labels(window):
    window.show()
    for row in (window.from_row, window.greg_from_row):
        assert row.row_label.width() == DateSelectorRow.LTR_LABEL_WIDTH_PX
        assert row.day_combo.minimumWidth() == DateSelectorRow.LTR_DAY_WIDTH_PX
        assert row.day_combo.width() >= row.day_combo.minimumWidth()
    # The widest month label must still fit its combo and the row its window.
    for row in (window.from_row, window.greg_from_row):
        assert row.month_combo.width() >= row.month_combo.minimumWidth()
        right_edge = row.year_input.mapTo(window, row.year_input.rect().bottomRight()).x()
        assert right_edge < window.width()


def test_both_pages_read_one_field_width(window):
    """«۰۶ - شهریور» and «09 September» fit the app font differently, and
    the ltr row turns the month fit into the day box's share of the slack:
    the wider fit must bind both pages, or the field columns jump sideways
    on every flip. A hidden stacked page has never been laid out, so each
    page is measured while it is the one showing."""
    window.show()
    measurements = {}
    for calendar in (CALENDAR_JALALI, CALENDAR_GREGORIAN):
        if calendar == CALENDAR_GREGORIAN:
            _switch_to_gregorian(window)
        else:
            window.calendar_switch.jalali_button.click()
        QApplication.processEvents()
        for name in ("month_combo", "day_combo"):
            measurements[name, calendar] = [getattr(row, name).width()
                                            for row in window.active_rows()]
    for name, calendar in measurements:
        assert len(set(measurements[name, calendar])) == 1, (name, calendar)
    for name in ("month_combo", "day_combo"):
        assert measurements[name, CALENDAR_GREGORIAN] == measurements[name, CALENDAR_JALALI], name


def test_distance_rows_use_the_converter_field_metrics(window):
    # The converter's metrics, not the event editor's compact ones: 40px
    # fields and a regular caption behind every row of this window.
    for row in window._all_rows():
        assert row.FIELD_HEIGHT_PX == DistanceRowMetrics.FIELD_HEIGHT_PX == 40
        assert row.year_input.height() == 40
        assert row.month_combo.height() == 40
        assert row.day_combo.height() == 40
        assert "font-size: 14px; font-weight: normal;" in row.row_label.styleSheet()


def test_event_editor_rows_keep_their_compact_metrics():
    # The knobs are opt-in per surface: the distance window copies the
    # converter, the event editor keeps the compact defaults.
    assert (DateSelectorRow.FIELD_HEIGHT_PX, DateSelectorRow.YEAR_WIDTH_PX,
            DateSelectorRow.ROW_LABEL_SIZE_PX, DateSelectorRow.ROW_LABEL_BOLD) == (34, 92, 13, True)
    assert (DateSelectorRow.LTR_LABEL_WIDTH_PX, DateSelectorRow.LTR_DAY_WIDTH_PX) == (56, 68)


def test_clicking_a_no_focus_surface_clears_field_focus(window, monkeypatch):
    window.show()
    probe = _FocusProbe()
    # One physical press reaches the filter once per parent hop as Qt walks it
    # up; the real held-focus query answers None after the first clearFocus.
    monkeypatch.setattr(window, "_query_focused_widget",
                        lambda: probe if probe.cleared == 0 else None)
    # The row caption is a plain QLabel: no click on it can move focus
    # anywhere, so it is on this window to answer the press instead.
    QApplication.sendEvent(window.from_row.row_label, press(window.from_row.row_label))
    assert probe.cleared == 1


def test_clicking_a_focusable_field_is_not_fought(window, monkeypatch):
    window.show()
    probe = _FocusProbe()
    monkeypatch.setattr(window, "_query_focused_widget", lambda: probe)
    # The day combo takes click focus on its own; the clearer must leave that
    # press alone rather than clear the held focus under it.
    QApplication.sendEvent(window.from_row.day_combo, press(window.from_row.day_combo))
    assert probe.cleared == 0


def test_presses_belonging_to_other_windows_are_not_answered(window, monkeypatch, qtbot):
    window.show()
    probe = _FocusProbe()
    monkeypatch.setattr(window, "_query_focused_widget", lambda: probe)
    foreign = QLabel()  # no parent: its own top-level window
    qtbot.addWidget(foreign)
    QApplication.sendEvent(foreign, press(foreign))
    assert probe.cleared == 0


def test_close_removes_the_focus_clearer(window, monkeypatch):
    window.show()
    window.close()
    # A closed window can stay referenced until the next open replaces it;
    # its application-level filter must not keep answering presses meanwhile.
    probe = _FocusProbe()
    monkeypatch.setattr(window, "_query_focused_widget", lambda: probe)
    QApplication.sendEvent(window.from_row.row_label, press(window.from_row.row_label))
    assert not window._focus_clearer_armed
    assert probe.cleared == 0


def test_default_row_keeps_the_editors_field_order(qtbot):
    row = DateSelectorRow()
    qtbot.addWidget(row)
    row.set_date(jdatetime.date(1405, 1, 1))
    row.update_styles()
    row.resize(400, 40)
    row.show()
    x = {name: widget.mapTo(row, widget.rect().topLeft()).x()
         for name, widget in (("day", row.day_combo), ("month", row.month_combo),
                              ("year", row.year_input))}
    assert x["day"] < x["month"] < x["year"]
    assert not row.ltr_date_order


# ---------------------------------------------------- the calendar switch

def test_switch_opens_on_jalali_and_both_segments_are_choosable(window):
    switch = window.calendar_switch
    assert switch.calendar == CALENDAR_JALALI
    assert switch.jalali_button.isChecked() and not switch.gregorian_button.isChecked()
    assert switch.gregorian_button.isEnabled()
    assert window.rows_stack.currentIndex() == 0


def test_clicking_میلادی_changes_the_mode_and_back(window, qtbot):
    switch = window.calendar_switch
    with qtbot.waitSignal(switch.calendar_changed) as blocker:
        switch.gregorian_button.click()
    assert blocker.args == [CALENDAR_GREGORIAN]
    assert switch.calendar == CALENDAR_GREGORIAN
    assert switch.gregorian_button.isChecked() and not switch.jalali_button.isChecked()
    assert window.rows_stack.currentIndex() == 1
    assert window.active_rows() == (window.greg_from_row, window.greg_to_row)
    with qtbot.waitSignal(switch.calendar_changed) as blocker:
        switch.jalali_button.click()
    assert blocker.args == [CALENDAR_JALALI]
    assert window.active_rows() == (window.from_row, window.to_row)


def test_clicking_the_chosen_segment_keeps_it_chosen(window, qtbot):
    with qtbot.assertNotEmitted(window.calendar_switch.calendar_changed):
        window.calendar_switch.jalali_button.click()
    assert window.calendar_switch.jalali_button.isChecked()


def test_switching_carries_the_same_two_days_across(window):
    _set_date(window.from_row, 1382, 6, 2)
    _set_date(window.to_row, 1388, 2, 22)
    jalali_days = window.result_days.text()
    _switch_to_gregorian(window)
    assert window.greg_from_row.picked() == jdatetime.date(1382, 6, 2).togregorian()
    assert window.greg_to_row.picked() == jdatetime.date(1388, 2, 22).togregorian()
    # The same days apart whichever calendar measures them.
    assert window.result_days.text() == jalali_days == "۲۰۸۸"
    window.calendar_switch.jalali_button.click()
    assert window.from_row.picked() == jdatetime.date(1382, 6, 2)
    assert window.to_row.picked() == jdatetime.date(1388, 2, 22)


def test_gregorian_mode_measures_in_gregorian_units(window):
    _switch_to_gregorian(window)
    _set_date(window.greg_from_row, 2026, 3, 21)
    _set_date(window.greg_to_row, 2026, 7, 6)
    distance = describe_gregorian_distance(datetime.date(2026, 7, 6),
                                           today=datetime.date(2026, 3, 21))
    assert _hero(window) == "۱۰۷ روز"
    # Gregorian months differ from Jalali ones: 3 months 15 days, not 14.
    assert window.result_breakdown.text() == format_distance_units(distance) == "۳ ماه و ۱۵ روز"
    assert window.result_months.isHidden()
    assert window.result_weeks.text() == "۱۵ هفته و ۲ روز"


def test_gregorian_equal_dates_and_row_order(window):
    _switch_to_gregorian(window)
    _set_date(window.greg_from_row, 2020, 5, 5)
    _set_date(window.greg_to_row, 2020, 5, 5)
    assert window.result_message.text() == "دو تاریخ یکسان هستند."
    _set_date(window.greg_to_row, 2024, 2, 29)
    forward = _lines(window)
    _set_date(window.greg_from_row, 2024, 2, 29)
    _set_date(window.greg_to_row, 2020, 5, 5)
    assert _lines(window) == forward


def test_gregorian_leap_day_row_follows_gregorian_month_lengths(window):
    _switch_to_gregorian(window)
    row = window.greg_from_row
    _set_date(row, 2024, 2, 1)
    assert row.day_combo.count() == 29
    row.year_input.setText("2023")
    assert row.day_combo.count() == 28


def test_year_bounds_span_each_librarys_true_edges(window):
    """The pages are not the app's support span - that is the event editor's
    constraint - but each calendar's own representable truth."""
    assert window.from_row._year_bounds() == (JALALI_YEAR_MIN, JALALI_YEAR_MAX)
    assert window.greg_from_row._year_bounds() == (GREGORIAN_YEAR_MIN, GREGORIAN_YEAR_MAX)
    _switch_to_gregorian(window)
    window.greg_to_row.year_input.setText("15000")
    assert window.year_hint_label.text() == year_range_hint(
        GREGORIAN_YEAR_MIN, GREGORIAN_YEAR_MAX, persian_digits=False)
    assert window.greg_to_row._year_error is True
    assert _lines(window) == ("", "", "", "")


def test_a_jalali_year_beyond_the_last_twin_is_out_of_range(window):
    """Typing 9378 (or past it) is an ordinary out-of-range year: red border
    plus the range message, no quiet blank."""
    _set_date(window.from_row, 1400, 1, 1)
    window.to_row.year_input.setText(to_persian_digits(9378))
    assert window.to_row._year_error is True
    assert window.year_hint_label.text() == year_range_hint(JALALI_YEAR_MIN, JALALI_YEAR_MAX)
    assert _lines(window) == ("", "", "", "")


def test_the_jalali_edge_carries_across_the_flip(window):
    """Jalali 9377 is the last year with a Gregorian twin: the flip into
    Gregorian must carry it (9998), not silently restart it."""
    _set_date(window.from_row, 9377, 1, 1)
    _switch_to_gregorian(window)
    assert window.greg_from_row.picked() == jdatetime.date(9377, 1, 1).togregorian()


def test_gregorian_years_before_the_converter_floor_measure(window):
    """The measurement is Gregorian-native: a Christ-era gap needs Jalali for
    nothing and answers it, although the converter itself rejects year 500."""
    _switch_to_gregorian(window)
    _set_date(window.greg_from_row, 500, 1, 1)
    _set_date(window.greg_to_row, 600, 1, 1)
    distance = describe_gregorian_distance(datetime.date(600, 1, 1),
                                           today=datetime.date(500, 1, 1))
    assert _hero(window) == f"{to_persian_digits(abs(distance.total_days))} روز"
    assert window.result_breakdown.text() == format_distance_units(distance) == "۱۰۰ سال"


def test_switching_an_invalid_row_restarts_it_from_today(window):
    window.from_row.year_input.setText("")
    _switch_to_gregorian(window)
    assert window.greg_from_row.picked() == datetime.date.today()


def test_a_gregorian_date_with_no_jalali_twin_restarts_from_today(window):
    """Gregorian before 622-03-21 predates Jalali year 1: the carry cannot
    convert it, so the flip uses the restart recovery - while a date the
    Jalali calendar can represent is carried as ever."""
    _switch_to_gregorian(window)
    _set_date(window.greg_from_row, 1900, 1, 1)  # Jalali twin exists
    _set_date(window.greg_to_row, 500, 1, 1)     # no Jalali twin at all
    window.calendar_switch.jalali_button.click()
    assert window.from_row.picked() == jdatetime.date.fromgregorian(date=datetime.date(1900, 1, 1))
    assert window.to_row.picked() == jdatetime.date.today()


# ------------------------------------------------------------------ copy

def _clipboard():
    return QApplication.clipboard()


def test_clicking_each_line_copies_it_and_flashes_copied(window, qtbot, flashes):
    _set_date(window.from_row, 1382, 6, 2)
    _set_date(window.to_row, 1388, 2, 22)
    cases = ((window.hero_row, "2088 روز"),
             (window.result_breakdown, "5 سال و 8 ماه و 20 روز"),
             (window.result_months, "68 ماه و 20 روز"),
             (window.result_weeks, "298 هفته و 2 روز"))
    for widget, expected in cases:
        _clipboard().clear()
        qtbot.mouseClick(widget, Qt.MouseButton.LeftButton)
        assert _clipboard().text() == expected
    assert flashes == [COPIED_MESSAGE] * 4 and COPIED_MESSAGE == "✓ کپی شد"


def test_clicking_the_hero_number_or_unit_copies_the_whole_hero(window, qtbot, flashes):
    _set_date(window.from_row, 1405, 1, 1)
    _set_date(window.to_row, 1405, 4, 15)
    for child in (window.result_days, window.result_unit):
        _clipboard().clear()
        qtbot.mouseClick(child, Qt.MouseButton.LeftButton)
        assert _clipboard().text() == "107 روز"
    assert len(flashes) == 2


def test_only_a_left_click_copies(window, qtbot, flashes):
    _set_date(window.from_row, 1405, 1, 1)
    _set_date(window.to_row, 1405, 4, 15)
    _clipboard().setText("untouched")
    qtbot.mouseClick(window.result_breakdown, Qt.MouseButton.RightButton)
    qtbot.mouseClick(window.hero_row, Qt.MouseButton.RightButton)
    assert _clipboard().text() == "untouched" and flashes == []


def test_copy_payload_is_latin_digits_while_the_label_shows_persian(window, qtbot, flashes):
    _set_date(window.from_row, 1405, 1, 1)
    _set_date(window.to_row, 1405, 4, 15)
    qtbot.mouseClick(window.result_breakdown, Qt.MouseButton.LeftButton)
    assert window.result_breakdown.text() == "۳ ماه و ۱۴ روز"
    assert _clipboard().text() == "3 ماه و 14 روز"


def test_gregorian_lines_copy_too(window, qtbot, flashes):
    _switch_to_gregorian(window)
    _set_date(window.greg_from_row, 2026, 3, 21)
    _set_date(window.greg_to_row, 2026, 7, 6)
    qtbot.mouseClick(window.result_breakdown, Qt.MouseButton.LeftButton)
    assert _clipboard().text() == "3 ماه و 15 روز"


def test_lines_are_clickable_looking(window):
    for widget in (window.hero_row, window.result_breakdown, window.result_months,
                   window.result_weeks):
        assert widget.cursor().shape() == Qt.CursorShape.PointingHandCursor


def test_result_lines_copy_from_the_keyboard(window, qtbot, flashes):
    """The copy lines answer the keyboard like the pointer: each line takes
    tab focus (TabFocus, like the «کپی همه» button) and Enter or Space copies
    that line; keys that mean nothing here stay on the superclass path."""
    _set_date(window.from_row, 1382, 6, 2)
    _set_date(window.to_row, 1388, 2, 22)
    window.show()
    cases = ((window.hero_row, "2088 روز"),
             (window.result_breakdown, "5 سال و 8 ماه و 20 روز"),
             (window.result_months, "68 ماه و 20 روز"),
             (window.result_weeks, "298 هفته و 2 روز"))
    for widget, expected in cases:
        assert widget.focusPolicy() == Qt.FocusPolicy.TabFocus
        for key in (Qt.Key.Key_Return, Qt.Key.Key_Space):
            widget.setFocus()
            _clipboard().clear()
            QTest.keyClick(widget, key)
            assert _clipboard().text() == expected
    assert flashes == [COPIED_MESSAGE] * 8
    _clipboard().setText("stays")
    QTest.keyClick(window.result_breakdown, Qt.Key.Key_A)
    assert _clipboard().text() == "stays" and flashes == [COPIED_MESSAGE] * 8


def test_a_keyboard_copy_flashes_on_its_own_widget(window, qtbot, monkeypatch):
    """A keyboard activation has no cursor truth to ride: its flash anchors
    to the widget the copy was launched from."""
    _set_date(window.from_row, 1405, 1, 1)
    _set_date(window.to_row, 1405, 4, 15)
    window.show()
    seen = []
    monkeypatch.setattr(CustomTooltip.instance(), "flash_tooltip",
                        lambda text, at, *a, **k: seen.append(at))
    window.result_breakdown.setFocus()
    QTest.keyClick(window.result_breakdown, Qt.Key.Key_Space)
    assert seen == [window.result_breakdown.mapToGlobal(
        window.result_breakdown.rect().center())]


def test_focused_copy_lines_paint_their_ring(window, qtbot):
    """The ring rides a :focus clause the base style must not swallow: a
    focused line renders differently from the same line at rest."""
    _set_date(window.from_row, 1405, 1, 1)
    _set_date(window.to_row, 1405, 4, 15)
    window.show()
    for widget in (window.hero_row, window.result_breakdown):
        widget.clearFocus()
        QTest.qWait(50)
        at_rest = widget.grab().toImage()
        widget.setFocus()
        qtbot.waitUntil(lambda w=widget: w.grab().toImage() != at_rest)
        widget.clearFocus()


def test_no_message_or_hint_is_a_copy_target(window, qtbot, flashes):
    """Equality and the range hint are explanations, not results."""
    _clipboard().setText("untouched")
    qtbot.mouseClick(window.result_message, Qt.MouseButton.LeftButton)
    assert _clipboard().text() == "untouched" and flashes == []


def test_copy_all_hides_with_the_results(window):
    """The «کپی همه» control is shown and hidden with the results: equality
    and the range message leave nothing to copy, so no button either."""
    window.show()
    assert not window.copy_all_button.isVisible()
    _set_date(window.from_row, 1405, 1, 1)
    _set_date(window.to_row, 1405, 4, 15)
    assert window.copy_all_button.isVisible()
    _set_date(window.to_row, 1405, 1, 1)   # equal again
    assert not window.copy_all_button.isVisible()


def test_copy_all_copies_every_shown_line_in_one_block(window, qtbot, flashes):
    window.show()
    _set_date(window.from_row, 1382, 6, 2)
    _set_date(window.to_row, 1388, 2, 22)
    qtbot.mouseClick(window.copy_all_button, Qt.MouseButton.LeftButton)
    assert _clipboard().text() == "\n".join(("2088 روز",
                                             "5 سال و 8 ماه و 20 روز",
                                             "68 ماه و 20 روز",
                                             "298 هفته و 2 روز"))
    assert flashes == [COPIED_MESSAGE]


def test_copy_all_skips_lines_the_short_span_hides(window, qtbot, flashes):
    """Two days: only the hero says anything, so the block is one line."""
    window.show()
    _set_date(window.from_row, 1405, 1, 1)
    _set_date(window.to_row, 1405, 1, 3)
    qtbot.mouseClick(window.copy_all_button, Qt.MouseButton.LeftButton)
    assert _clipboard().text() == "2 روز"
    assert flashes == [COPIED_MESSAGE]


def test_copy_all_button_pinned_inside_the_card_corner(window):
    """The corner control costs the layout nothing: an absolute child of the
    card, it sits at the card's top-right (RTL reading-start) corner inside
    the pinned inset whenever the results show, however tall the result stack
    gets."""
    window.show()
    _set_date(window.from_row, 1400, 1, 1)
    _set_date(window.to_row, 1405, 7, 20)
    assert window.copy_all_button.isVisible()
    for line in (window.result_breakdown, window.result_months, window.result_weeks):
        assert line.isVisible()
    button, card = window.copy_all_button, window.result_card
    in_card = button.mapTo(card, button.rect().topLeft())
    assert in_card.x() == card.width() - button.width() - COPY_ALL_CORNER_INSET_PX
    assert in_card.y() == COPY_ALL_CORNER_INSET_PX
    assert card.rect().contains(button.geometry())
    assert (window.width(), window.height()) == (window.WINDOW_WIDTH, window.INITIAL_HEIGHT)


# --------------------------------------------------------- size and theme

def test_window_is_a_fixed_size_independent_of_the_result(window):
    size = (window.width(), window.height())
    assert size == (window.WINDOW_WIDTH, window.INITIAL_HEIGHT)
    _set_date(window.from_row, 1400, 1, 1)
    _set_date(window.to_row, 1405, 7, 20)
    window.to_row.year_input.setText("")
    _switch_to_gregorian(window)
    assert (window.width(), window.height()) == size


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_hero_colour_clears_large_text_contrast_in_both_themes(theme):
    palette = APP_CONFIG.DARK_PALETTE if theme == "dark" else APP_CONFIG.LIGHT_PALETTE
    card = mix_colors(palette["BACKGROUND_COLOR"], palette["INPUT_BG_COLOR"], 0.5)
    hero = legible_on(palette["ACCENT_COLOR"], card)
    assert contrast_ratio(QColor(hero), QColor(card)) >= HERO_MIN_CONTRAST


def test_legible_on_leaves_a_readable_colour_alone():
    assert legible_on("#1a6fa8", "#ffffff") == "#1a6fa8"


def test_theme_update_restyles_every_part(window):
    window.update_styles()
    for row in (window.from_row, window.greg_from_row):
        assert row.year_input.styleSheet()
    assert window.result_days.styleSheet() and window.result_months.styleSheet()
    assert window.calendar_switch.styleSheet()
