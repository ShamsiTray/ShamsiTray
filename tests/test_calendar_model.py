"""Calendar model tests: grid layout, navigation, event matching, day styling."""
import pytest

import jdatetime

from config import APP_CONFIG
from utils.date_utils import to_persian_digits
from ui.windows.calendar_window import PersianCalendarWidget


@pytest.fixture(autouse=True)
def _ensure_qapp(qapp):
    """Widget construction requires a QApplication to exist."""
    yield


def make_calendar(holidays=None, events=None):
    return PersianCalendarWidget(holidays or {}, events or {})


# --- grid shape ---

def test_grid_has_six_weeks_of_seven_days():
    calendar = make_calendar()
    assert len(calendar.day_labels) == PersianCalendarWidget.ROWS == 6
    assert all(len(row) == PersianCalendarWidget.COLS == 7 for row in calendar.day_labels)


def test_grid_starts_on_saturday_of_the_week():
    calendar = make_calendar()
    first_of_month = calendar.display_date.replace(day=1)
    first_cell_date = calendar.day_labels[0][0].jalali_date
    assert first_cell_date.weekday() == 0          # Saturday
    assert (first_of_month - first_cell_date).days == first_of_month.weekday()


def test_grid_cells_are_consecutive_days():
    calendar = make_calendar()
    cells = [cell for row in calendar.day_labels for cell in row]
    dates = [cell.jalali_date for cell in cells]
    for earlier, later in zip(dates, dates[1:]):
        assert (later - earlier).days == 1
    assert all(to_persian_digits(d.day) == cell.text() for d, cell in zip(dates, cells))


def test_day_cells_carry_dates_and_event_flag():
    event_date = jdatetime.date.today().replace(day=10)
    calendar = make_calendar(events={})
    calendar.set_user_events({})
    calendar.display_date = event_date
    calendar.fill_calendar_grid()
    target = [cell for row in calendar.day_labels for cell in row
              if cell.jalali_date == event_date]
    assert target and not target[0].has_user_event

    key = event_date.strftime("%Y-%m-%d")
    calendar.set_user_events({key: {"text": "event", "recurrence": "none", "remove_after_finish": False}})
    assert target[0].has_user_event


# --- navigation ---

def test_next_prev_month_navigation():
    calendar = make_calendar()
    calendar.display_date = jdatetime.date(1404, 5, 15)
    calendar.next_month()
    assert (calendar.display_date.year, calendar.display_date.month) == (1404, 6)
    calendar.prev_month()
    calendar.prev_month()
    assert (calendar.display_date.year, calendar.display_date.month) == (1404, 4)


def test_navigation_wraps_years():
    calendar = make_calendar()
    calendar.display_date = jdatetime.date(1404, 12, 29)
    calendar.next_month()
    assert (calendar.display_date.year, calendar.display_date.month) == (1405, 1)
    calendar.display_date = jdatetime.date(1404, 1, 15)
    calendar.prev_month()
    assert (calendar.display_date.year, calendar.display_date.month) == (1403, 12)


def test_navigation_clamps_day_to_target_month():
    calendar = make_calendar()
    calendar.display_date = jdatetime.date(1404, 6, 31)   # month 6 has 31 days
    calendar.next_month()                                  # month 7 has 30
    assert calendar.display_date == jdatetime.date(1404, 7, 30)


def test_go_to_date_and_invalid_dates_are_safe():
    calendar = make_calendar()
    calendar.go_to_date(1402, 3)
    assert (calendar.display_date.year, calendar.display_date.month) == (1402, 3)
    calendar.go_to_date(9999, 12)   # out of widget range must not raise
    calendar.go_to_date(0, 0)


def test_go_to_today_resets_selection():
    calendar = make_calendar()
    calendar.display_date = jdatetime.date(1402, 3, 1)
    calendar.go_to_today()
    assert calendar.display_date == calendar.current_date == jdatetime.date.today()


# --- event matching through the widget API ---

def test_widget_event_lookup_priorities():
    jdate = jdatetime.date(1404, 5, 5)
    calendar = make_calendar(events={
        "1404-05-05": {"text": "specific", "recurrence": "none", "remove_after_finish": True},
        "0000-05-05": {"text": "yearly", "recurrence": "yearly", "remove_after_finish": False},
        "0000-00-05": {"text": "monthly", "recurrence": "monthly", "remove_after_finish": False},
    })
    text, repeats, remove = calendar.get_user_event_for_date(jdate)
    assert text == "specific" and not repeats and remove

    del calendar.user_events["1404-05-05"]
    text, repeats, remove = calendar.get_user_event_for_date(jdate)
    assert text == "yearly" and repeats and not remove

    del calendar.user_events["0000-05-05"]
    text, repeats, remove = calendar.get_user_event_for_date(jdate)
    assert text == "monthly" and repeats and not remove

    text, repeats, remove = calendar.get_user_event_for_date(jdatetime.date(1404, 5, 6))
    assert text is None and not repeats and not remove


def test_holiday_tooltips_and_styling():
    today = jdatetime.date.today()
    year = today.year
    month, day = 7, 15
    holidays = {year: {(month, day): ["عید تست"]}}
    calendar = make_calendar(holidays=holidays)
    calendar.display_date = today.replace(month=month, day=1)
    calendar.fill_calendar_grid()

    cell = next(c for row in calendar.day_labels for c in row if c.jalali_date == jdatetime.date(year, month, day))
    assert "عید تست" in cell._tooltip_text
    assert APP_CONFIG.current_palette['HOLIDAY_COLOR'].lower() in cell.styleSheet().lower()


def test_friday_cells_are_styled_as_holiday():
    calendar = make_calendar()
    calendar.fill_calendar_grid()
    friday_cells = [cell for row in calendar.day_labels for cell in row
                    if cell.jalali_date and cell.jalali_date.weekday() == 6
                    and cell.jalali_date.month == calendar.display_date.month]
    assert friday_cells
    holiday_color = APP_CONFIG.current_palette['HOLIDAY_COLOR'].lower()
    assert all(holiday_color in cell.styleSheet().lower() for cell in friday_cells)


def test_today_cell_gets_border():
    calendar = make_calendar()
    calendar.fill_calendar_grid()
    today = jdatetime.date.today()
    cell = next(c for row in calendar.day_labels for c in row if c.jalali_date == today)
    assert "solid" in cell.styleSheet()
    assert "17px" in cell.styleSheet()  # today renders in a larger font


def test_event_saved_signal_payload(qtbot):
    calendar = make_calendar()
    target = jdatetime.date(1404, 6, 15)
    with qtbot.waitSignal(calendar.event_added, timeout=2000) as blocker:
        calendar.editing_date = target
        calendar._handle_event_saved("یادداشت", "yearly", True)
    assert blocker.args == [target, "یادداشت", "yearly", True]
    assert calendar.editing_date is None
    assert not calendar.event_input_widget.isVisible()


def test_event_removed_signal(qtbot):
    calendar = make_calendar()
    target = jdatetime.date(1404, 6, 15)
    # The user is asked before every deletion; answer the in-calendar overlay.
    with qtbot.waitSignal(calendar.event_removed, timeout=2000) as blocker:
        calendar._remove_event(target)
        calendar._remove_overlay.confirm_button.click()
    assert blocker.args == [target]


def test_event_removed_declined_does_not_emit(qtbot):
    calendar = make_calendar()
    target = jdatetime.date(1404, 6, 15)
    with qtbot.assertNotEmitted(calendar.event_removed, wait=200):
        calendar._remove_event(target)
        calendar._remove_overlay.cancel_button.click()
