"""Tests for ui.windows.calendar_window: grid filling, navigation, day
styling, the event editor overlay and the go-to-date popup."""
import jdatetime
import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import QApplication

from config import APP_CONFIG
from ui.windows.calendar_window import DayStyle, PersianCalendarWidget
from ui.widgets.calendar_day_cell import ClickableLabel
from ui.widgets.go_to_date import GoToDateWindow
from utils.date_utils import to_persian_digits


@pytest.fixture
def calendar(qtbot):
    widget = PersianCalendarWidget({}, {})
    qtbot.addWidget(widget)
    widget.show()  # real visibility semantics for children/overlays
    return widget


# --- construction & grid ---------------------------------------------------------


def test_window_sized_to_config(calendar):
    assert calendar.width() == APP_CONFIG.CALENDAR_WIDTH
    assert calendar.height() == APP_CONFIG.CALENDAR_HEIGHT


def test_grid_has_six_rows_seven_cols(calendar):
    assert len(calendar.day_labels) == PersianCalendarWidget.ROWS
    assert all(len(row) == PersianCalendarWidget.COLS for row in calendar.day_labels)
    assert all(isinstance(cell, ClickableLabel) for row in calendar.day_labels for cell in row)


def test_grid_opens_on_current_month(calendar):
    today = jdatetime.date.today()
    assert calendar.display_date == today
    assert calendar.month_label.text() == APP_CONFIG.PERSIAN_MONTHS[today.month - 1]
    assert calendar.year_label.text() == to_persian_digits(today.year)


def test_grid_cells_carry_jalali_dates_and_persian_digits(calendar):
    calendar.fill_calendar_grid()
    cells = [cell for row in calendar.day_labels for cell in row]
    assert len(cells) == 42
    first = cells[0].jalali_date
    second = cells[1].jalali_date
    assert (second - first).days == 1  # sequential days
    for cell in cells:
        assert cell.text() == to_persian_digits(cell.jalali_date.day)


def test_grid_starts_on_the_first_weekday(calendar):
    calendar.display_date = jdatetime.date(1404, 5, 1)
    calendar.fill_calendar_grid()
    first_cell = calendar.day_labels[0][0]
    first_of_month = jdatetime.date(1404, 5, 1)
    offset = first_of_month.weekday()  # cells back-fill from the week start
    assert first_cell.jalali_date == first_of_month - jdatetime.timedelta(days=offset)


def test_adjacent_month_days_are_greyed(calendar):
    calendar.display_date = jdatetime.date(1404, 5, 15)
    calendar.fill_calendar_grid()
    grey = APP_CONFIG.current_palette["GREY_COLOR"]
    outside_plain_cells = [cell for row in calendar.day_labels for cell in row
                           if cell.jalali_date.month != 5 and cell.jalali_date.weekday() != 6]
    assert outside_plain_cells, "1404-05 never fills a 6x7 grid edge to edge"
    for cell in outside_plain_cells:
        assert grey in cell.styleSheet()


# --- day styling ------------------------------------------------------------------


def test_holiday_day_is_holiday_red(calendar):
    calendar.holidays_cache = {1404: {(5, 3): ["جشن بزرگ"]}}
    style = calendar._determine_day_style(jdatetime.date(1404, 5, 3), True)
    assert style.text_color == APP_CONFIG.current_palette["HOLIDAY_COLOR"]


def test_friday_is_holiday_red(calendar):
    friday = None
    for day in range(1, 29):
        candidate = jdatetime.date(1404, 5, day)
        if candidate.weekday() == 6:
            friday = candidate
            break
    style = calendar._determine_day_style(friday, True)
    assert style.text_color == APP_CONFIG.current_palette["HOLIDAY_COLOR"]


def test_user_event_day_is_accent(calendar):
    calendar.user_events = {"1404-05-04": {"text": "yaddasht", "recurrence": "none",
                                            "remove_after_finish": False}}
    style = calendar._determine_day_style(jdatetime.date(1404, 5, 4), True)
    assert style.text_color == APP_CONFIG.current_palette["ACCENT_COLOR"]


def test_today_and_selected_get_border(calendar):
    target = jdatetime.date(1404, 5, 5)
    calendar.current_date = target
    calendar.selected_date = target
    style = calendar._determine_day_style(target, True)
    assert style.border_style.startswith("1px solid")
    assert style.font_size == 17  # today pops one size up


def test_out_of_month_holiday_is_tinted_not_full_red(calendar):
    calendar.holidays_cache = {1404: {(4, 30): ["جشن ماه قبل"]}}
    style = calendar._determine_day_style(jdatetime.date(1404, 4, 30), False)
    # Out-of-month days carry the holiday tint via rgba(), never the full red.
    assert style.text_color.startswith("rgba(255, 76, 76")
    assert style.border_style == "none"


def test_tooltip_html_escapes_holiday_reasons(calendar):
    calendar.holidays_cache = {1404: {(5, 3): ["<b>恶意</b> title"]}}
    style = calendar._determine_day_style(jdatetime.date(1404, 5, 3), True)
    assert "&lt;b&gt;" in style.tooltip  # escaped, never raw HTML from data
    assert "<b>恶意</b>" not in style.tooltip


def test_tooltip_combines_holiday_and_event_lines(calendar):
    calendar.holidays_cache = {1404: {(5, 3): ["جشن"]}}
    calendar.user_events = {"1404-05-03": {"text": "important!", "recurrence": "none",
                                            "remove_after_finish": False}}
    style = calendar._determine_day_style(jdatetime.date(1404, 5, 3), True)
    assert "جشن" in style.tooltip and "important!" in style.tooltip
    assert style.tooltip.startswith("<qt>")


def test_tooltip_lists_every_event_on_the_date(calendar):
    """A one-time and a monthly event on one date both appear in the tooltip.

    Only the priority winner was listed, so the monthly event looked absent from
    the very surface a user reads to find out what is scheduled."""
    calendar.user_events = {
        "1404-05-03": {"text": "one-time thing", "recurrence": "none",
                       "remove_after_finish": False},
        "0000-00-03": {"text": "monthly thing", "recurrence": "monthly",
                       "remove_after_finish": False},
    }
    style = calendar._determine_day_style(jdatetime.date(1404, 5, 3), True)
    assert "one-time thing" in style.tooltip
    assert "monthly thing" in style.tooltip


def test_plain_day_has_no_tooltip(calendar):
    plain = None
    for day in range(1, 28):
        candidate = jdatetime.date(1404, 6, day)
        if candidate.weekday() != 6:
            plain = candidate
            break
    style = calendar._determine_day_style(plain, True)
    assert style.tooltip == ""


# --- navigation --------------------------------------------------------------------


def test_prev_next_month_navigation(calendar):
    calendar.display_date = jdatetime.date(1404, 5, 15)
    calendar.prev_month()
    assert (calendar.display_date.year, calendar.display_date.month) == (1404, 4)
    calendar.next_month()
    calendar.next_month()
    assert (calendar.display_date.year, calendar.display_date.month) == (1404, 6)


def test_navigation_wraps_year_boundaries(calendar):
    calendar.display_date = jdatetime.date(1404, 1, 15)
    calendar.prev_month()
    assert (calendar.display_date.year, calendar.display_date.month) == (1403, 12)
    calendar.next_month()
    calendar.next_month()
    assert (calendar.display_date.year, calendar.display_date.month) == (1404, 2)


def test_navigation_stops_at_supported_year_bounds(calendar):
    """UI-7: navigation clamps to the app-wide 1200-1600 range."""
    calendar.display_date = jdatetime.date(APP_CONFIG.SUPPORTED_MIN_YEAR, 1, 15)
    calendar.prev_month()
    assert calendar.display_date.year == APP_CONFIG.SUPPORTED_MIN_YEAR

    calendar.display_date = jdatetime.date(APP_CONFIG.SUPPORTED_MAX_YEAR, 12, 15)
    calendar.next_month()
    assert calendar.display_date.year == APP_CONFIG.SUPPORTED_MAX_YEAR


def test_navigation_clamps_day_to_target_month_length(calendar):
    # Jalali months 1-6 have 31 days, 7-11 have 30: 06-31 -> 07-30 clamps.
    calendar.display_date = jdatetime.date(1404, 6, 31)
    calendar.next_month()
    assert (calendar.display_date.year, calendar.display_date.month) == (1404, 7)
    assert calendar.display_date.day == 30


def test_go_to_today_resets_all_dates(calendar):
    calendar.display_date = jdatetime.date(1403, 1, 1)
    calendar.selected_date = jdatetime.date(1403, 1, 1)
    calendar.go_to_today()
    today = jdatetime.date.today()
    assert calendar.display_date == today
    assert calendar.selected_date == today
    assert calendar.current_date == today


def test_go_to_date_moves_and_hides_overlay(calendar):
    calendar.go_to_date(1403, 5)
    assert (calendar.display_date.year, calendar.display_date.month) == (1403, 5)
    assert not calendar.overlay_blocker.isVisible()


def test_go_to_date_clamps_day(calendar):
    calendar.display_date = jdatetime.date(1404, 6, 31)
    calendar.go_to_date(1404, 7)  # 30-day month
    assert calendar.display_date.day == 30


def test_go_to_date_invalid_input_is_swallowed(calendar):
    calendar.go_to_date("bogus", "data")  # must not raise
    assert calendar.overlay_blocker.isHidden()


def test_day_click_selects_and_moves_display(calendar):
    calendar.display_date = jdatetime.date(1404, 5, 15)
    target = jdatetime.date(1404, 4, 20)  # previous-month cell
    calendar._on_day_clicked(target)
    assert calendar.selected_date == target
    assert calendar.display_date == target


def test_day_click_ignored_while_editor_open(calendar, monkeypatch):
    monkeypatch.setattr(calendar.event_input_widget, "isVisible", lambda: True)
    before = calendar.selected_date
    calendar._on_day_clicked(jdatetime.date(1404, 8, 8))
    assert calendar.selected_date == before


def test_gregorian_format_toggle(calendar):
    before = calendar.gregorian_date_label.text()
    calendar._toggle_gregorian_format(None)
    after = calendar.gregorian_date_label.text()
    assert before != after
    # One format is m/d/Y, the other 'Mon DD, YYYY'.
    import re
    assert bool(re.match(r"^\d{2}/\d{2}/\d{4}$", before)) != bool(re.match(r"^[A-Z][a-z]{2} \d{2}, \d{4}$", before))


# --- event editor overlay ---------------------------------------------------------


def test_show_event_input_opens_overlay_for_new_event(calendar):
    jdate = jdatetime.date(1404, 5, 10)
    calendar._show_event_input_widget(jdate)
    assert calendar.event_input_widget.isVisible()
    assert calendar.editing_date == jdate
    assert calendar.overlay_blocker.isVisible()


def test_show_event_input_prefills_existing_event(calendar):
    jdate = jdatetime.date(1404, 5, 10)
    calendar.user_events = {"1404-05-10": {"text": "existing", "recurrence": "none",
                                            "remove_after_finish": True}}
    calendar._show_event_input_widget(jdate)
    editor = calendar.event_input_widget
    assert editor.text_edit.toPlainText() == "existing"
    assert editor.remove_after_finish_checkbox.isChecked()


def test_show_event_input_ignored_when_already_open(calendar, monkeypatch):
    jdate = jdatetime.date(1404, 5, 10)
    calendar._show_event_input_widget(jdate)
    monkeypatch.setattr(calendar.event_input_widget, "isVisible", lambda: True)
    calendar.editing_date = None
    calendar._show_event_input_widget(jdatetime.date(1404, 6, 6))
    assert calendar.editing_date is None  # second request rejected


def test_saved_event_emits_and_closes(calendar, qtbot):
    received = []
    calendar.event_added.connect(lambda j, t, r, a: received.append((j, t, r, a)))
    calendar._show_event_input_widget(jdatetime.date(1404, 5, 10))
    calendar._handle_event_saved("the text", "none", True)
    assert received == [(jdatetime.date(1404, 5, 10), "the text", "none", True)]
    assert not calendar.event_input_widget.isVisible()
    assert calendar.editing_date is None
    assert calendar.overlay_blocker.isHidden()


def test_canceled_event_only_closes(calendar):
    received = []
    calendar.event_added.connect(lambda *a: received.append(a))
    calendar._show_event_input_widget(jdatetime.date(1404, 5, 10))
    calendar._handle_event_canceled()
    assert received == []
    assert calendar.editing_date is None


def test_remove_event_requires_confirmation(calendar):
    """A context-menu click must never delete silently: the overlay comes up and
    only answering «حذف» removes anything."""
    received = []
    calendar.event_removed.connect(lambda j: received.append(j))
    calendar._remove_event(jdatetime.date(1404, 5, 10))
    assert received == []
    assert calendar._remove_overlay.isVisible()
    assert calendar.overlay_blocker.isVisible()
    assert calendar._pending_remove == jdatetime.date(1404, 5, 10)
    calendar._remove_overlay.cancel_button.click()
    assert received == []


def test_confirmed_remove_emits_event_removed(calendar):
    received = []
    calendar.event_removed.connect(lambda j: received.append(j))
    calendar._remove_event(jdatetime.date(1404, 5, 10))
    calendar._remove_overlay.confirm_button.click()
    assert received == [jdatetime.date(1404, 5, 10)]


def test_delete_confirmation_is_an_in_calendar_overlay(calendar):
    """The question is part of the popup: dimmed grid behind it, no separate
    window, and nothing to drag away."""
    calendar._remove_event(jdatetime.date(1404, 5, 10))
    overlay = calendar._remove_overlay
    assert overlay.parent() is calendar
    assert not overlay.isWindow()
    assert overlay.width() <= calendar.width()   # the calendar is 305px wide
    assert overlay.title_label.text() == "حذف رویداد"
    assert overlay._danger


def test_delete_question_stays_out_of_the_preview_box(calendar):
    """The description line states what is about to happen; the box holds the
    event being acted on, so the two can never blur into one another."""
    calendar.user_events = {"1404-05-10": {"text": "یادداشت مهم", "recurrence": "none",
                                           "remove_after_finish": False}}
    calendar._remove_event(jdatetime.date(1404, 5, 10))
    overlay = calendar._remove_overlay
    assert overlay.message_label.text() == "این رویداد حذف شود؟"
    assert overlay.detail_label.text() == "یادداشت مهم"
    assert "حذف شود" not in overlay.detail_label.text()


def test_delete_confirmation_without_event_text_shows_no_box(calendar):
    calendar._remove_event(jdatetime.date(1404, 5, 10))
    overlay = calendar._remove_overlay
    overlay.show()
    assert overlay.message_label.text() == "این رویداد حذف شود؟"
    assert not overlay.detail_label.isVisible()


def test_answering_the_delete_confirmation_tears_it_down(calendar):
    calendar._remove_event(jdatetime.date(1404, 5, 10))
    calendar._remove_overlay.confirm_button.click()
    assert not calendar._remove_overlay.isVisible()
    assert calendar._active_overlay is None
    assert calendar._pending_remove is None
    assert not calendar.overlay_blocker.isVisible()


def test_delete_confirmation_emits_only_once_per_confirmation(calendar):
    """The pending date is cleared before the emit, so a second answer - or a
    re-entrant one - cannot delete twice."""
    received = []
    calendar.event_removed.connect(lambda j: received.append(j))
    calendar._remove_event(jdatetime.date(1404, 5, 10))
    overlay = calendar._remove_overlay
    overlay.confirm_button.click()
    overlay.confirm_button.click()
    assert received == [jdatetime.date(1404, 5, 10)]


def test_a_second_delete_request_cannot_replace_the_pending_one(calendar):
    """Two context-menu clicks in a row: the first confirmation owns the answer,
    so the second date can never be the one deleted."""
    received = []
    calendar.event_removed.connect(lambda j: received.append(j))
    calendar._remove_event(jdatetime.date(1404, 5, 10))
    calendar._remove_event(jdatetime.date(1404, 5, 20))
    assert calendar._pending_remove == jdatetime.date(1404, 5, 10)
    calendar._remove_overlay.confirm_button.click()
    assert received == [jdatetime.date(1404, 5, 10)]


def test_hiding_the_calendar_drops_a_pending_deletion(calendar):
    """The popup closing mid-question must not leave a date waiting to be
    deleted: reopening and answering later would remove an event the user was no
    longer looking at."""
    received = []
    calendar.event_removed.connect(lambda j: received.append(j))
    calendar._remove_event(jdatetime.date(1404, 5, 10))
    calendar.hide()
    assert calendar._pending_remove is None
    assert calendar._active_overlay is None
    assert not calendar._remove_overlay.isVisible()
    assert not calendar.overlay_blocker.isVisible()
    # And a late answer to the dismissed card does nothing.
    calendar._on_remove_choice(calendar._remove_overlay.confirm_button.text())
    assert received == []


def test_reopening_the_calendar_leaves_no_stale_overlay(calendar):
    calendar._show_date_distance(jdatetime.date(1404, 8, 20))
    calendar.hide()
    calendar.show()
    assert not calendar.overlay_blocker.isVisible()
    assert not calendar._distance_overlay.isVisible()
    assert not calendar._remove_overlay.isVisible()
    assert calendar._active_overlay is None


def test_remove_event_ignores_none(calendar):
    calendar._remove_event(None)  # must not raise


def test_editor_open_cancels_day_tooltips(calendar, monkeypatch):
    killed = []

    class SpyCell(ClickableLabel):
        def cancel_pending_tooltip(self):
            killed.append(1)

    # Swap the grid cells for spies.
    for row in range(calendar.ROWS):
        for col in range(calendar.COLS):
            spy = SpyCell()
            spy.jalali_date = calendar.day_labels[row][col].jalali_date
            calendar.day_labels[row][col] = spy
    calendar._show_event_input_widget(jdatetime.date(1404, 5, 10))
    assert len(killed) == 42


# --- go-to-date popup ---------------------------------------------------------------


def test_open_go_to_date_window_shows_overlay(calendar, qtbot):
    calendar._open_go_to_date_window()
    qtbot.addWidget(calendar.go_to_window)
    assert isinstance(calendar.go_to_window, GoToDateWindow)
    assert calendar.overlay_blocker.isVisible()
    calendar.go_to_window.close()


def test_go_to_date_selection_moves_calendar(calendar, qtbot):
    calendar._open_go_to_date_window()
    window = calendar.go_to_window
    qtbot.addWidget(window)
    window.date_selected.emit(1402, 3)
    assert (calendar.display_date.year, calendar.display_date.month) == (1402, 3)
    assert not calendar.overlay_blocker.isVisible()
    window.close()


def test_go_to_window_destroyed_clears_overlay(calendar, qtbot):
    calendar._open_go_to_date_window()
    window = calendar.go_to_window
    window.close()
    qtbot.waitUntil(lambda: calendar.go_to_window is None, timeout=3000)
    assert calendar.overlay_blocker.isHidden()


def test_calendar_teardown_with_popup_open_is_safe(qtbot):
    # The popup is a child window, so Qt deletes it from the calendar's own
    # destructor, after the siblings it would touch. Raising out of that slot
    # aborts the process instead of failing the test, so this one guards the
    # handler's shutdown path. The widget is not registered with qtbot: it is
    # deleted here, and qtbot would re-close it at teardown.
    calendar = PersianCalendarWidget({}, {})
    calendar.show()
    calendar._open_go_to_date_window()
    gone = []
    calendar.destroyed.connect(lambda: gone.append(True))
    calendar.deleteLater()
    qtbot.waitUntil(lambda: bool(gone), timeout=3000)


def test_stale_go_to_window_is_replaced(calendar, qtbot):
    stale = GoToDateWindow(calendar)  # hidden, parented: "stale" instance
    calendar.go_to_window = stale
    calendar._open_go_to_date_window()
    qtbot.addWidget(calendar.go_to_window)
    assert calendar.go_to_window is not stale
    assert calendar.go_to_window.isVisible()
    calendar.go_to_window.close()
    stale.deleteLater()  # the stale one was already deleteLater'd by the app


def test_stale_go_to_window_destruction_keeps_current(calendar, qtbot):
    # A window opened by the app is wired to the destroyed handler; replacing
    # a hidden instance must not let its deferred destruction clear the new one.
    calendar._open_go_to_date_window()
    first = calendar.go_to_window
    first.hide()  # hidden, not yet destroyed: like a close pending deleteLater
    stale_destroyed = []
    first.destroyed.connect(lambda *_: stale_destroyed.append(True))
    calendar._open_go_to_date_window()
    current = calendar.go_to_window
    qtbot.addWidget(current)
    assert current is not first
    assert calendar.overlay_blocker.isVisible()
    qtbot.waitUntil(lambda: bool(stale_destroyed), timeout=3000)
    assert calendar.go_to_window is current
    assert calendar.overlay_blocker.isVisible()


def test_hide_event_tears_down_overlay_and_go_to(calendar):
    calendar._open_go_to_date_window()
    calendar._show_event_input_widget(jdatetime.date(1404, 5, 10))
    calendar.hide()
    assert not calendar.event_input_widget.isVisible()
    assert calendar.overlay_blocker.isHidden()
    assert calendar.editing_date is None
    # Closing the calendar also closed the go-to-date child.
    assert calendar.go_to_window is None or not calendar.go_to_window.isVisible()


# --- hover normalization -------------------------------------------------------------


def test_normalize_day_hover_clears_stale_flag(calendar):
    calendar.show()
    cell = calendar.day_labels[0][0]
    cell.setAttribute(Qt.WidgetAttribute.WA_UnderMouse, True)
    # The offscreen cursor cannot be inside a cell far from (0,0).
    cell.move(1000, 1000)
    calendar.normalize_day_hover()
    assert not cell.underMouse()
    cell.move(0, 0)
    calendar.hide()


# --- popup semantics -----------------------------------------------------------------


def test_calendar_opts_into_popup_dismissal():
    """Tray-triggered flyout, not a form: unpinned, an outside click closes it."""
    assert PersianCalendarWidget.CLOSE_ON_OUTSIDE_CLICK_WHEN_UNPINNED is True


# --- dataclass -----------------------------------------------------------------------


def test_day_style_defaults():
    style = DayStyle(text_color="#ffffff")
    assert style.background_color == "transparent"
    assert style.border_style == "none"
    assert style.font_size == APP_CONFIG.FONT_SIZE_LABEL
    assert style.tooltip == ""


# --- فاصله تا امروز notice ------------------------------------------------------------


def notice_lines(calendar):
    """The notice is an in-calendar overlay now, so read the live card's own text
    instead of intercepting a static call: what the user sees is the widget."""
    return calendar._distance_overlay.detail_label.text().splitlines()


def test_distance_notice_leads_with_the_day_total_and_direction(calendar):
    calendar.current_date = jdatetime.date(1404, 5, 10)
    calendar._show_date_distance(jdatetime.date(1404, 8, 20))
    lines = notice_lines(calendar)
    assert lines[0].endswith("مانده")   # a future day
    assert "روز" in lines[0]


def test_distance_notice_names_a_past_day_as_گذشته(calendar):
    calendar.current_date = jdatetime.date(1404, 5, 10)
    calendar._show_date_distance(jdatetime.date(1403, 2, 1))
    assert notice_lines(calendar)[0].endswith("گذشته")


def test_distance_notice_box_carries_total_breakdown_and_date(calendar):
    calendar.current_date = jdatetime.date(1404, 5, 10)
    calendar._show_date_distance(jdatetime.date(1404, 8, 20))
    lines = notice_lines(calendar)
    assert len(lines) == 3
    assert lines[0].endswith("مانده") and "سال" not in lines[0]   # day total
    assert lines[1].endswith("مانده") and "ماه" in lines[1]      # breakdown
    assert "آبان" in lines[2] and "۱۴۰۴" in lines[2]              # the day's date


def test_distance_notice_omits_the_breakdown_under_one_month(calendar):
    """Under a month the breakdown is the total restated - same days, same
    direction word - so printing both would show one line twice."""
    calendar.current_date = jdatetime.date(1404, 5, 10)
    calendar._show_date_distance(jdatetime.date(1404, 5, 20))   # +10 days
    lines = notice_lines(calendar)
    assert len(lines) == 2
    assert lines[0] == "۱۰ روز مانده"
    assert "۱۰ روز مانده" not in lines[1]      # not repeated
    assert "مرداد" in lines[1]                # the day's own date


def test_distance_notice_for_today_has_no_breakdown(calendar):
    """There is no distance to break down, so the plain literal and the date line
    are all there is."""
    today = jdatetime.date(1404, 5, 10)
    calendar.current_date = today
    calendar._show_date_distance(today)
    lines = notice_lines(calendar)
    assert lines[0] == "تاریخ امروز است."
    assert not any("مانده" in line or "گذشته" in line for line in lines)
    assert len(lines) == 2


def test_distance_notice_is_measured_from_the_calendriers_own_today(calendar):
    """current_date is what the calendar drew today as, so the notice agrees with
    the grid even if the wall clock has moved since the popup opened."""
    calendar.current_date = jdatetime.date(1404, 5, 10)
    calendar._show_date_distance(jdatetime.date(1404, 5, 11))
    lines = notice_lines(calendar)
    assert lines[0] == "۱ روز مانده"
    assert lines.count("۱ روز مانده") == 1


def test_distance_notice_is_an_in_calendar_overlay(calendar):
    """It dims the grid and lives inside the popup - no separate window, and not
    draggable."""
    calendar.current_date = jdatetime.date(1404, 5, 10)
    calendar._show_date_distance(jdatetime.date(1404, 8, 20))
    overlay = calendar._distance_overlay
    assert overlay.parent() is calendar
    assert not overlay.isWindow()
    assert overlay.isVisible()
    assert calendar.overlay_blocker.isVisible()
    assert calendar._active_overlay is overlay
    assert overlay.width() <= calendar.width()   # the calendar is only 305px wide
    assert overlay.icon_badge.text() == APP_CONFIG.FAS.FA_CLOCK
    assert not overlay._danger


def test_distance_notice_dismissal_frees_the_grid(calendar):
    """Answering the notice must lower the dimmer, not just the card.

    The overlay only ever hides itself; the blocker is the calendar's own widget,
    so without a teardown handler the black sheet stayed over a notice that was
    already gone and swallowed every click on the grid.
    """
    calendar.current_date = jdatetime.date(1404, 5, 10)
    calendar._show_date_distance(jdatetime.date(1404, 8, 20))
    assert calendar.overlay_blocker.isVisible()
    # A point in the calendar's left margin: clear of the centred card, so the
    # widget answering there is the dimmer itself and not something inside it.
    probe = calendar.mapToGlobal(QPoint(6, calendar.rect().center().y()))
    assert QApplication.widgetAt(probe) is calendar.overlay_blocker

    calendar._distance_overlay.confirm_button.click()

    assert not calendar._distance_overlay.isVisible()
    assert not calendar.overlay_blocker.isVisible()
    assert calendar._active_overlay is None
    # The real proof the grid is live again: the same point now reaches the grid.
    assert QApplication.widgetAt(probe) is not calendar.overlay_blocker


def test_distance_notice_ignores_a_request_while_another_overlay_is_up(calendar):
    calendar._remove_event(jdatetime.date(1404, 5, 10))
    pending = calendar._pending_remove
    calendar._show_date_distance(jdatetime.date(1404, 8, 20))
    assert calendar._active_overlay is calendar._remove_overlay
    assert calendar._pending_remove == pending


def test_distance_notice_ignores_a_missing_date(calendar):
    calendar._show_date_distance(None)
    assert not calendar._distance_overlay.isVisible()
    assert calendar._active_overlay is None


def test_distance_notice_cancels_pending_day_tooltips(calendar, monkeypatch):
    """The tooltip is a separate top-level window; a re-armed tooltip timer would
    otherwise draw the holiday reason over the overlay."""
    killed = []
    monkeypatch.setattr(calendar, "_cancel_day_tooltips", lambda: killed.append(True))
    calendar.current_date = jdatetime.date(1404, 5, 10)
    calendar._show_date_distance(jdatetime.date(1404, 8, 20))
    assert killed == [True]


def test_day_cells_are_wired_to_the_distance_action(calendar):
    """Emitting from a real cell must reach the calendar, not just exist on it."""
    calendar.current_date = jdatetime.date(1404, 5, 10)
    target = calendar.day_labels[0][0]
    target.jalali_date = jdatetime.date(1404, 8, 20)
    target.distance_requested.emit(target.jalali_date)
    assert calendar._distance_overlay.isVisible()
    assert notice_lines(calendar)[0].endswith("مانده")
