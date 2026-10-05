"""Tests for the new windows: event manager, holiday viewer."""
import datetime

import jdatetime
import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QComboBox, QDialog, QLabel, QWidget

from config import APP_CONFIG
from ui.windows.base_window import BaseFramelessWindow
from ui.windows.calendar_window import PersianCalendarWidget
from ui.widgets.confirm_card import ConfirmCard
from ui.widgets.confirm_dialog import ConfirmDialog
from ui.widgets.confirm_overlay import ConfirmOverlay
from ui.widgets.tooltip import CustomTooltip
from ui.windows.event_manager_window import EventManagerWindow, _event_date_label
from utils.event_io import recurrence_of_key as _event_recurrence
from ui.widgets.checkbox import CustomCheckbox
from ui.widgets.event_input import EventInputWidget
from ui.windows.holiday_viewer_window import HolidayViewerWindow
from ui.windows.converter_window import DateConverterWindow
from utils.date_utils import to_persian_digits
from utils.event_io import (RECURRENCE_MONTHLY, RECURRENCE_NONE,
                            RECURRENCE_YEARLY, make_event_key)


@pytest.fixture(autouse=True)
def _ensure_qapp(qapp):
    """Widget construction requires a QApplication to exist."""
    yield


# --- event manager ---

@pytest.fixture
def manager(tray, qtbot):
    window = EventManagerWindow(tray)
    qtbot.addWidget(window)
    window.show()
    yield window
    window.close()


def test_manager_lists_all_events(manager):
    today = jdatetime.date.today()
    manager.controller.add_user_event(today, "یادداشت امروز", "none", False)
    manager.controller.user_events["0000-05-05"] = {"text": "سالانه", "recurrence": "yearly", "remove_after_finish": False}
    manager.controller.user_events["0000-00-05"] = {"text": "ماهانه", "recurrence": "monthly", "remove_after_finish": False}
    manager.refresh_list()
    rows = manager.rows_layout.count() - 1  # trailing stretch
    assert rows == 3


def test_manager_count_label_reflects_active_filter(manager):
    """EM-1: while a filter narrows the list, the counter shows "X of Y"."""
    manager.controller.user_events["1405-01-01"] = {"text": "نخست", "recurrence": "none", "remove_after_finish": False}
    manager.controller.user_events["1405-02-01"] = {"text": "دوم", "recurrence": "none", "remove_after_finish": False}
    manager.refresh_list()
    # Unfiltered: the plain total.
    assert manager.count_label.text() == to_persian_digits(2) + " رویداد"

    manager.search_input.setText("نخست")
    assert manager.rows_layout.count() - 1 == 1
    assert manager.count_label.text() == f"{to_persian_digits(1)} از {to_persian_digits(2)} رویداد"

    manager.search_input.setText("")
    assert manager.count_label.text() == to_persian_digits(2) + " رویداد"


def test_manager_header_stays_put_when_a_filter_empties_the_list(manager):
    """Hiding the list used to hand its slot to the title row, so the header and
    the filter row slid down whenever a search matched nothing."""
    manager.user_events["1405-01-01"] = {"text": "نخست", "recurrence": RECURRENCE_NONE,
                                         "remove_after_finish": False}
    manager.refresh_list()
    QApplication.processEvents()
    before = (manager.title_label.geometry().y(), manager.search_input.geometry().y())

    manager.search_input.setText("zzzz-nothing-matches")
    QApplication.processEvents()

    assert manager.empty_label.isVisible()
    after = (manager.title_label.geometry().y(), manager.search_input.geometry().y())
    assert after == before


def test_manager_swaps_between_the_list_and_the_empty_label(manager):
    manager.user_events["1405-01-01"] = {"text": "نخست", "recurrence": RECURRENCE_NONE,
                                         "remove_after_finish": False}
    manager.refresh_list()
    assert not manager.empty_label.isVisible()
    assert manager.content_stack.currentWidget() is manager.scroll_area

    manager.search_input.setText("zzzz-nothing-matches")
    assert manager.empty_label.isVisible()
    assert manager.content_stack.currentWidget() is manager.empty_label


def test_manager_search_filters_by_text(manager):
    import datetime
    today = jdatetime.date.today()
    manager.controller.add_user_event(today, "خرید نان", "none", False)
    manager.controller.add_user_event(today - datetime.timedelta(days=1),
                                      "جلسه کاری", "none", False)
    manager.search_input.setText("خرید")
    rows = manager.rows_layout.count() - 1
    assert rows == 1


def test_manager_search_normalizes_digits_and_arabic_letters(manager):
    """A query pasted from elsewhere must match the STORED Persian text.

    Matching normalized only the query with .lower() made «١٢» and «علي»
    match nothing at all, which reads to the user as a missing event."""
    manager.controller.user_events["1404-05-05"] = {
        "text": "کتاب علی", "recurrence": "none", "remove_after_finish": False}

    manager.search_input.setText("كتاب علي")   # Arabic kaf + Arabic yeh
    assert manager.rows_layout.count() - 1 == 1

    manager.search_input.setText("کتاب")         # Persian spelling
    assert manager.rows_layout.count() - 1 == 1


def test_manager_search_matches_arabic_indic_digits_in_event_text(manager):
    manager.controller.user_events["1404-05-05"] = {
        "text": "جلسه ۱۲ نفره", "recurrence": "none", "remove_after_finish": False}
    manager.search_input.setText("١٢")            # Arabic-Indic twelve
    assert manager.rows_layout.count() - 1 == 1


def test_manager_search_also_matches_the_date_label(manager):
    """Typing a year or a month name must find an event whose numeric label
    spells neither («۱۴۰۵/۰۸/۰۱» names no month)."""
    manager.controller.user_events["1404-05-05"] = {
        "text": "مراسم", "recurrence": "none", "remove_after_finish": False}
    manager.search_input.setText("مرداد")
    assert manager.rows_layout.count() - 1 == 1

    manager.search_input.setText("1404")
    assert manager.rows_layout.count() - 1 == 1


def test_manager_count_label_counts_the_hidden_past_filter(manager):
    """Hiding the past IS a narrowing filter, so the counter must not claim
    the full total while expired rows are off screen."""
    manager.controller.add_user_event(
        jdatetime.date.today() - datetime.timedelta(days=1), "گذشته", "none", False)
    manager.controller.add_user_event(jdatetime.date.today(), "امروز", "none", False)
    manager.past_checkbox.setChecked(False)
    assert manager.rows_layout.count() - 1 == 1
    assert "۱" in manager.count_label.text() and "۲" in manager.count_label.text()


def test_manager_filters_by_type(manager):
    manager.controller.user_events["0000-05-05"] = {"text": "سالانه", "recurrence": "yearly", "remove_after_finish": False}
    manager.controller.user_events["1404-05-05"] = {"text": "یک‌بار", "recurrence": "none", "remove_after_finish": False}
    manager.refresh_list()
    manager.type_combo.setCurrentIndex(manager.type_combo.findData(RECURRENCE_YEARLY))
    assert manager.rows_layout.count() - 1 == 1
    manager.type_combo.setCurrentIndex(manager.type_combo.findData(RECURRENCE_NONE))
    assert manager.rows_layout.count() - 1 == 1


def test_manager_filters_by_month(manager):
    manager.controller.user_events["1404-05-05"] = {"text": "مرداد", "recurrence": "none", "remove_after_finish": False}
    manager.controller.user_events["1404-06-06"] = {"text": "شهریور", "recurrence": "none", "remove_after_finish": False}
    manager.controller.user_events["0000-00-07"] = {"text": "ماهانه", "recurrence": "monthly", "remove_after_finish": False}
    manager.refresh_list()
    manager.month_combo.setCurrentIndex(manager.month_combo.findData(5))  # مرداد
    labels = [manager.rows_layout.itemAt(i).widget().text_label.text()
              for i in range(manager.rows_layout.count() - 1)
              if manager.rows_layout.itemAt(i).widget() is not None]
    assert "مرداد" in labels
    assert "ماهانه" in labels          # monthly events match every month
    assert "شهریور" not in labels


def test_manager_delete_requires_confirmation(manager, qtbot, monkeypatch):
    today = jdatetime.date.today()
    manager.controller.add_user_event(today, "برای حذف", "none", False)
    key = today.strftime("%Y-%m-%d")
    monkeypatch.setattr(manager, "_confirm_delete", lambda k: True)
    with qtbot.waitSignal(manager.events_changed, timeout=2000):
        manager._on_delete_requested(key)
    assert key not in manager.controller.user_events


def test_manager_delete_declined_keeps_event(manager, monkeypatch):
    today = jdatetime.date.today()
    manager.controller.add_user_event(today, "می‌ماند", "none", False)
    key = today.strftime("%Y-%m-%d")
    monkeypatch.setattr(manager, "_confirm_delete", lambda k: False)
    manager._on_delete_requested(key)
    assert key in manager.controller.user_events


def test_manager_edit_updates_text_and_recurrence(manager):
    today = jdatetime.date.today()
    manager.controller.add_user_event(today, "قدیمی", "none", False)
    key = today.strftime("%Y-%m-%d")
    manager._editing_key = key
    manager._on_edit_saved("ویرایش‌شده", RECURRENCE_YEARLY, False)
    assert key not in manager.controller.user_events
    yearly_key = make_event_key(today, RECURRENCE_YEARLY)
    assert manager.controller.user_events[yearly_key]["text"] == "ویرایش‌شده"


def test_manager_edit_recurring_ignores_auto_delete(manager):
    manager.controller.user_events["0000-05-05"] = {"text": "سالانه", "recurrence": "yearly", "remove_after_finish": False}
    manager._editing_key = "0000-05-05"
    manager._on_edit_saved("به‌روز", RECURRENCE_YEARLY, True)   # flag must be dropped
    assert manager.controller.user_events["0000-05-05"]["remove_after_finish"] is False


def test_manager_asks_before_replacing_an_event_on_the_same_day(manager, monkeypatch):
    """A yearly 0000-08-01 and a one-time 1405-08-01 are two keys for the same
    day, so the new event must ask about the stored one instead of stacking."""
    manager.user_events["0000-08-01"] = {"text": "سالانه", "recurrence": RECURRENCE_YEARLY,
                                         "remove_after_finish": False}
    asked = []
    monkeypatch.setattr(manager, "_confirm_replace", lambda key: asked.append(key) or True)
    manager._editing_key = None
    manager.event_input_widget.event_date = lambda: jdatetime.date(1405, 8, 1)

    manager._on_edit_saved("یک‌بار", RECURRENCE_NONE, False)

    assert asked == ["0000-08-01"]
    assert list(manager.user_events) == ["1405-08-01"]


def test_manager_declining_the_replace_keeps_the_stored_event(manager, monkeypatch):
    manager.user_events["0000-08-01"] = {"text": "سالانه", "recurrence": RECURRENCE_YEARLY,
                                         "remove_after_finish": False}
    monkeypatch.setattr(manager, "_confirm_replace", lambda key: False)
    manager._editing_key = None
    manager.event_input_widget.event_date = lambda: jdatetime.date(1405, 8, 1)

    manager._on_edit_saved("یک‌بار", RECURRENCE_NONE, False)

    assert list(manager.user_events) == ["0000-08-01"]


def test_manager_moving_onto_another_events_day_replaces_it(manager, monkeypatch):
    """An edit that lands on another event's day (under either key shape) still
    has to ask, and the replaced event is dropped from the store."""
    manager.user_events["0000-08-01"] = {"text": "سالانه", "recurrence": RECURRENCE_YEARLY,
                                         "remove_after_finish": False}
    manager.user_events["1404-05-05"] = {"text": "یک‌بار", "recurrence": RECURRENCE_NONE,
                                         "remove_after_finish": False}
    asked = []
    monkeypatch.setattr(manager, "_confirm_replace", lambda key: asked.append(key) or True)
    manager._on_edit_requested("1404-05-05")
    manager.event_input_widget.event_date = lambda: jdatetime.date(1405, 8, 1)

    manager._on_edit_saved("یک‌بار", RECURRENCE_NONE, False)

    assert asked == ["0000-08-01"]
    assert list(manager.user_events) == ["1405-08-01"]


def test_manager_unchanged_save_keeps_a_clamped_anchor(manager):
    """A day-31 monthly event opens on the 30th of a short month; saving the
    edit keeps that anchor instead of moving the event to the shown day."""
    manager.user_events["0000-00-31"] = {"text": "پایان ماه", "recurrence": RECURRENCE_MONTHLY,
                                         "remove_after_finish": False}
    manager._on_edit_requested("0000-00-31")

    manager._on_edit_saved("پایان ماه ویرایش‌شده", RECURRENCE_MONTHLY, False)

    assert list(manager.user_events) == ["0000-00-31"]
    assert manager.user_events["0000-00-31"]["text"] == "پایان ماه ویرایش‌شده"


def test_manager_moving_the_date_reanchors_the_event(manager):
    manager.user_events["0000-00-31"] = {"text": "پایان ماه", "recurrence": RECURRENCE_MONTHLY,
                                         "remove_after_finish": False}
    manager._on_edit_requested("0000-00-31")
    manager.event_input_widget.event_date = lambda: jdatetime.date(1405, 3, 15)

    manager._on_edit_saved("پایان ماه", RECURRENCE_MONTHLY, False)

    assert list(manager.user_events) == ["0000-00-15"]


def test_event_date_labels():
    assert "هر سال" in _event_date_label("0000-05-05")
    assert "هر ماه" in _event_date_label("0000-00-05")
    label = _event_date_label("1404-05-05")
    assert "۱۴۰۴" in label
    assert _event_recurrence("0000-00-05") == RECURRENCE_MONTHLY
    assert _event_recurrence("0000-05-05") == RECURRENCE_YEARLY
    assert _event_recurrence("1404-05-05") == RECURRENCE_NONE


# --- event manager add flow (date picker) ---

def test_manager_add_flow_creates_today_event(manager):
    manager._on_add_requested()
    assert manager.event_input_widget.isVisible()
    assert not manager.event_input_widget.date_row.isHidden()
    assert manager._editing_key is None
    picked = manager.event_input_widget.event_date()
    assert picked == jdatetime.date.today()
    manager._on_edit_saved("رویداد تازه", RECURRENCE_NONE, False)
    key = jdatetime.date.today().strftime("%Y-%m-%d")
    assert manager.controller.user_events[key]["text"] == "رویداد تازه"
    assert not manager.event_input_widget.isVisible()


def test_manager_add_flow_picked_date(manager):
    manager._on_add_requested()
    widget = manager.event_input_widget
    # Pick 1 Farvardin of a neighbouring year by typing it into the year box.
    widget.year_input.setText(to_persian_digits(1403))
    widget.month_combo.setCurrentIndex(widget.month_combo.findData(1))
    widget.day_combo.setCurrentIndex(widget.day_combo.findData(1))
    manager._on_edit_saved("نوروز", RECURRENCE_NONE, False)
    assert manager.controller.user_events["1403-01-01"]["text"] == "نوروز"


def test_manager_add_flow_year_input_beyond_dropdown_range(manager):
    """The year is a free input: any full year is accepted, no ±10 cap."""
    manager._on_add_requested()
    widget = manager.event_input_widget
    widget.year_input.setText(to_persian_digits(1500))
    widget.month_combo.setCurrentIndex(widget.month_combo.findData(1))
    widget.day_combo.setCurrentIndex(widget.day_combo.findData(2))
    assert widget.event_date() == jdatetime.date(1500, 1, 2)
    # A half-typed or cleared year must yield no date rather than crash.
    widget.year_input.setText("")
    assert widget.event_date() is None


def test_manager_add_flow_recurring_drops_auto_delete(manager):
    manager._on_add_requested()
    manager.event_input_widget.recurrence_combo.setCurrentIndex(
        manager.event_input_widget.recurrence_combo.findText("ماهانه"))
    manager._on_edit_saved("ماهانه تازه", RECURRENCE_MONTHLY, True)
    today = jdatetime.date.today()
    key = make_event_key(today, RECURRENCE_MONTHLY)
    assert manager.controller.user_events[key]["remove_after_finish"] is False


def test_manager_add_replace_confirmed(manager, monkeypatch):
    today = jdatetime.date.today()
    key = today.strftime("%Y-%m-%d")
    manager.controller.add_user_event(today, "قدیمی", "none", False)
    manager._on_add_requested()
    monkeypatch.setattr(manager, "_confirm_replace", lambda k: True)
    manager._on_edit_saved("جایگزین", RECURRENCE_NONE, False)
    assert manager.controller.user_events[key]["text"] == "جایگزین"


def test_manager_add_replace_declined(manager, monkeypatch):
    today = jdatetime.date.today()
    key = today.strftime("%Y-%m-%d")
    manager.controller.add_user_event(today, "قدیمی", "none", False)
    manager._on_add_requested()
    monkeypatch.setattr(manager, "_confirm_replace", lambda k: False)
    manager._on_edit_saved("جایگزین", RECURRENCE_NONE, False)
    assert manager.controller.user_events[key]["text"] == "قدیمی"


def test_manager_edit_shows_prefilled_date_selector(manager):
    """Editing now allows changing the date: the selector opens prefilled with
    the event's own anchor (not today) and saving re-anchors the store key."""
    from utils.event_io import make_event_key

    anchor = jdatetime.date.today().replace(year=1404, month=5, day=10)
    key = make_event_key(anchor, "none")
    manager.controller.add_user_event(anchor, "برای ویرایش", "none", False)
    manager._on_edit_requested(key)
    assert manager.event_input_widget.date_row.isVisible()
    assert manager._editing_key == key
    assert manager.event_input_widget.year_input.text() == "۱۴۰۴"
    assert manager.event_input_widget.month_combo.currentData() == 5
    assert manager.event_input_widget.day_combo.currentData() == 10

    # Move the event to day 15 and save; the store key must be re-anchored.
    widget = manager.event_input_widget
    widget.day_combo.setCurrentIndex(14)
    manager._on_edit_saved("برای ویرایش", "none", False)
    new_key = make_event_key(anchor.replace(day=15), "none")
    assert new_key in manager.controller.user_events
    assert key not in manager.controller.user_events


def test_manager_calendar_add_refreshes_open_manager(tray):
    """2.3: adding an event from the calendar must refresh an open manager."""
    from PyQt6.QtWidgets import QApplication
    tray._open_event_manager()
    window = tray.event_manager_window
    try:
        QApplication.processEvents()
        assert window.isVisible()
        today = jdatetime.date.today()
        tray.add_user_event(today, "همگام‌سازی", "none", False)
        QApplication.processEvents()
        labels = [window.rows_layout.itemAt(i).widget().text_label.text()
                  for i in range(window.rows_layout.count() - 1)
                  if window.rows_layout.itemAt(i).widget() is not None]
        assert "همگام‌سازی" in labels
    finally:
        window.close()
        tray.event_manager_window = None


# --- event input widget details (1.1, 1.2, 1.3) ---

def test_event_input_text_edit_has_multi_line_minimum():
    widget = EventInputWidget()
    # Floor only; the real size comes from the host overlay geometry.
    assert widget.text_edit.minimumHeight() >= 40


def test_calendar_event_overlay_restored_to_original_size(tray):
    """The calendar editor overlay is back at the original compact size
    (upstream used 230px; the added recurrence row costs ~15px more)."""
    calendar = tray.calendar_widget
    calendar.show()
    calendar._show_event_input_widget(jdatetime.date.today())
    try:
        assert calendar.event_input_widget.isVisible()
        assert 230 <= calendar.event_input_widget.height() <= 250
        assert calendar.event_input_widget.width() == calendar.width() - 40
    finally:
        calendar._hide_event_input_widget()


def test_event_input_recurrence_combo_sized_to_contents():
    """«بدون تکرار» must never elide - but the width guarantee now comes from
    the measured minimum (fit_combo_width), not from AdjustToContents, which
    every combo in the app dropped in favour of the converter's dead-space-free
    popup sizing."""
    widget = EventInputWidget()
    assert widget.recurrence_combo.sizeAdjustPolicy() != QComboBox.SizeAdjustPolicy.AdjustToContents
    assert widget.recurrence_combo.minimumWidth() > 0


def test_event_input_recurrence_greys_out_auto_delete(qtbot):
    widget = EventInputWidget()
    widget.show()
    widget.recurrence_combo.setCurrentIndex(widget.recurrence_combo.findText("سالانه"))
    assert not widget.remove_after_finish_checkbox.isEnabled()
    assert not widget.remove_after_finish_checkbox.isChecked()
    widget.recurrence_combo.setCurrentIndex(widget.recurrence_combo.findText("بدون تکرار"))
    assert widget.remove_after_finish_checkbox.isEnabled()


def test_custom_checkbox_disabled_state_grey_and_inert():
    box = CustomCheckbox("حذف پس از گذشت تاریخ")
    box.setChecked(True)
    box.show()
    QApplication.processEvents()
    box.setEnabled(False)
    box.update_visuals()
    grey = APP_CONFIG.get_current_palette()['GREY_COLOR']
    assert grey in box.text_label.styleSheet()
    QTest.mouseClick(box, Qt.MouseButton.LeftButton, pos=QPoint(5, 5))
    assert box.isChecked()  # disabled clicks must not toggle


def test_event_input_date_selector_day_clamping():
    widget = EventInputWidget()
    widget.set_date_selector_visible(True)
    widget.year_input.setText(to_persian_digits(1404))
    widget.month_combo.setCurrentIndex(widget.month_combo.findData(7))  # مهر: 30 days
    widget.day_combo.setCurrentIndex(widget.day_combo.findData(30))
    assert widget.event_date() == jdatetime.date(1404, 7, 30)
    # Switching to شهریور (31 days is invalid there) clamps back within range.
    widget.month_combo.setCurrentIndex(widget.month_combo.findData(6))
    widget.day_combo.setCurrentIndex(widget.day_combo.count() - 1)
    assert widget.day_combo.currentData() == 31
    widget.month_combo.setCurrentIndex(widget.month_combo.findData(7))
    assert widget.day_combo.currentData() == 30  # clamped from 31


def test_event_input_date_selector_hidden_by_default():
    widget = EventInputWidget()
    assert widget.date_row.isHidden()
    assert widget.event_date() is None


# --- taskbar presence (2.1) ---

def test_tool_windows_opt_into_taskbar():
    assert DateConverterWindow.TASKBAR_ICON is True
    assert EventManagerWindow.__mro__[1] is BaseFramelessWindow
    for cls in (EventManagerWindow, HolidayViewerWindow, DateConverterWindow):
        assert cls.TASKBAR_ICON is True, cls.__name__
    # The calendar popup keeps the Tool behaviour (no taskbar button).
    assert PersianCalendarWidget.TASKBAR_ICON is False


def test_manager_window_has_no_tool_flag(manager):
    type_mask = manager.windowFlags() & Qt.WindowType.WindowType_Mask
    assert type_mask == Qt.WindowType.Window


# --- calendar delete confirmation (2.2) ---

def test_calendar_remove_event_asks_confirmation(tray):
    calendar = tray.calendar_widget
    today = jdatetime.date.today()
    tray.add_user_event(today, "رویداد تقویم", "none", False)
    emitted = []
    calendar.event_removed.connect(lambda jd: emitted.append(jd))

    # Decline: nothing is removed.
    calendar._remove_event(today)
    calendar._remove_overlay.cancel_button.click()
    assert not emitted

    # Confirm: the removal signal fires.
    calendar._remove_event(today)
    calendar._remove_overlay.confirm_button.click()
    assert emitted == [today]


# --- tray click closes the whole calendar (1.5) ---

def test_tray_click_hides_whole_calendar_even_with_editor_open(tray):
    from PyQt6.QtWidgets import QSystemTrayIcon
    calendar = tray.calendar_widget
    today = jdatetime.date.today()
    calendar.show()
    calendar._show_event_input_widget(today)
    assert calendar.event_input_widget.isVisible()
    tray.on_tray_icon_activated(QSystemTrayIcon.ActivationReason.Trigger)
    assert not calendar.isVisible()
    assert not calendar.event_input_widget.isVisible()
    assert calendar.editing_date is None


# --- holiday viewer ---

def test_holiday_viewer_groups_by_month():
    holidays = {
        1403: {(1, 1): ["جشن نوروز"], (1, 2): ["عیدنوروز"], (5, 5): ["تعطیل تست"]},
        1404: {(2, 10): ["چیز دیگر"]},
    }
    window = HolidayViewerWindow(holidays)
    window.year_combo.setCurrentIndex(window.year_combo.findData(1403))
    labels = [child.text() for child in window.list_container.findChildren(type(window.empty_label))
              if child.objectName() in ("MonthHeader", "HolidayRow")]
    month_headers = [t for t in labels if t and "-" in t and "تعطیلی" in t]
    rows = [t for t in labels if t and t not in month_headers]
    assert any("فروردین" in h for h in month_headers)
    assert any("مرداد" in h for h in month_headers)
    assert any("جشن نوروز" in r for r in rows)
    assert any("۵ مرداد" in r for r in rows)
    window.close()


def test_holiday_viewer_empty_state():
    window = HolidayViewerWindow({})
    window.show()
    try:
        assert window.empty_label.isVisible()
        assert not window.scroll_area.isVisible()
    finally:
        window.close()


def test_holiday_viewer_year_switch():
    holidays = {1403: {(1, 1): ["عید"]}, 1404: {(3, 3): ["دیگری"]}}
    window = HolidayViewerWindow(holidays)
    window.year_combo.setCurrentIndex(window.year_combo.findData(1404))
    labels = [child.text() for child in window.list_container.findChildren(type(window.empty_label))]
    assert any("خرداد" in t for t in labels if "-" in t)
    window.close()


def test_holiday_viewer_opens_on_current_year():
    """The viewer opens on today's year even when the store lacks its data."""
    holidays = {1403: {(1, 1): ["عید"]}}
    window = HolidayViewerWindow(holidays)
    current_year = jdatetime.date.today().year
    assert window.year_combo.currentData() == current_year
    assert window.year_combo.count() == 2  # current year + 1403
    window.close()


def test_holiday_viewer_year_stepper_buttons():
    """«❯» steps to older years, «❮» to newer ones, dimming at the ends."""
    holidays = {1403: {(1, 1): ["عید"]}, 1404: {(3, 3): ["دیگری"]}}
    window = HolidayViewerWindow(holidays)
    current_year = jdatetime.date.today().year
    years = sorted({1403, 1404, current_year}, reverse=True)
    assert window.year_combo.currentData() == current_year
    assert not window.next_year_btn.isEnabled()      # already at the newest
    window._go_to_prev_year()
    assert window.year_combo.currentData() == years[1]
    window._go_to_prev_year()
    assert window.year_combo.currentData() == years[2]
    assert not window.prev_year_btn.isEnabled()      # already at the oldest
    window._go_to_next_year()
    assert window.year_combo.currentData() == years[1]
    window.close()


def test_holiday_viewer_count_label_shows_days_only():
    """The summary counts distinct holiday days; the occasion tally is gone."""
    holidays = {1403: {(1, 1): ["عید", "جشن"], (1, 2): ["دیگری"]}}
    window = HolidayViewerWindow(holidays)
    window.year_combo.setCurrentIndex(window.year_combo.findData(1403))
    text = window.count_label.text()
    assert "۲ روز تعطیل" in text      # two distinct dates
    assert "مناسبت" not in text       # occasions no longer shown (by design)
    assert "۱۴۰۳" in text
    window.close()


# --- past-events filter (event manager) ---

def test_manager_hides_past_events_when_filter_off(manager):
    today = jdatetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    manager.controller.add_user_event(yesterday, "گذشته", "none", False)
    manager.controller.add_user_event(today, "امروز", "none", False)

    manager.past_checkbox.setChecked(False)   # hide passed dates
    labels = [manager.rows_layout.itemAt(i).widget().text_label.text()
              for i in range(manager.rows_layout.count() - 1)
              if manager.rows_layout.itemAt(i).widget() is not None]
    assert "گذشته" not in labels
    assert "امروز" in labels

    manager.past_checkbox.setChecked(True)    # back to showing everything
    labels = [manager.rows_layout.itemAt(i).widget().text_label.text()
              for i in range(manager.rows_layout.count() - 1)
              if manager.rows_layout.itemAt(i).widget() is not None]
    assert "گذشته" in labels


def test_manager_past_filter_shows_recurring_even_when_hiding_past(manager):
    """Recurring events never "pass", so they survive the hidden-past filter."""
    manager.controller.user_events["0000-05-05"] = {"text": "سالانه", "recurrence": "yearly", "remove_after_finish": False}
    manager.past_checkbox.setChecked(False)
    labels = [manager.rows_layout.itemAt(i).widget().text_label.text()
              for i in range(manager.rows_layout.count() - 1)
              if manager.rows_layout.itemAt(i).widget() is not None]
    assert "سالانه" in labels


# --- themed confirmation dialog ---

def test_confirm_card_is_a_mixin_not_a_widget(qtbot):
    """The card must stay free of any QWidget base, or mixing it into QDialog
    would give that class two QWidget branches and an ambiguous super()."""
    assert ConfirmCard.__bases__ == (object,)
    dialog_mro = ConfirmDialog.__mro__
    assert dialog_mro.index(ConfirmCard) < dialog_mro.index(QDialog)
    # Exactly one QWidget-derived base on the dialog: no QWidget of its own.
    assert sum(c.__name__ == "QWidget" for c in dialog_mro) == 1
    assert not issubclass(ConfirmDialog, ConfirmOverlay)


def test_confirm_dialog_still_paints_translucent_corners(qtbot):
    """WA_TranslucentBackground moved into the shared card; without it the rounded
    card gets square corners (invisible on a dialog, wrong over the calendar)."""
    dialog = ConfirmDialog(None, "حذف رویداد", "متن", confirm_text="حذف")
    qtbot.addWidget(dialog)
    assert dialog.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)


def test_confirm_dialog_ask_returns_button_choice(qtbot, monkeypatch):
    widget = EventInputWidget()
    monkeypatch.setattr(ConfirmDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    assert ConfirmDialog.ask(widget, "حذف رویداد", "این رویداد حذف شود؟", confirm_text="حذف") is True
    monkeypatch.setattr(ConfirmDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    assert ConfirmDialog.ask(widget, "حذف رویداد", "این رویداد حذف شود؟") is False


def test_confirm_dialog_wiring(qtbot):
    dialog = ConfirmDialog(None, "حذف رویداد", "متن", confirm_text="حذف")
    qtbot.addWidget(dialog)
    QTest.mouseClick(dialog.confirm_button, Qt.MouseButton.LeftButton)
    assert dialog.result() == int(QDialog.DialogCode.Accepted)
    dialog2 = ConfirmDialog(None, "حذف رویداد", "متن")
    qtbot.addWidget(dialog2)
    QTest.mouseClick(dialog2.cancel_button, Qt.MouseButton.LeftButton)
    assert dialog2.result() == int(QDialog.DialogCode.Rejected)


def test_confirm_dialog_shows_detail_box_and_centers_content():
    """The preview gets its own box; without a detail the box stays hidden."""
    dialog = ConfirmDialog(None, "حذف رویداد", "این رویداد حذف شود؟", detail="جلسه پروژه")
    assert dialog.detail_label.isVisible() is False  # parent not shown yet
    assert "جلسه پروژه" in dialog.detail_label.text()
    assert dialog.detail_label.isVisibleTo(dialog) is True
    assert dialog.title_label.alignment() & Qt.AlignmentFlag.AlignHCenter
    assert dialog.message_label.alignment() & Qt.AlignmentFlag.AlignHCenter
    plain = ConfirmDialog(None, "حذف رویداد", "متن")
    assert plain.detail_label.isVisibleTo(plain) is False


def test_confirm_dialog_message_uses_readable_text_color():
    """The main reason/message line must read as normal text — the muted grey
    is reserved for secondary metadata and disabled rows, not for the one
    sentence that explains why the dialog opened."""
    palette = APP_CONFIG.get_current_palette()
    dialog = ConfirmDialog(None, "برنامه در حال اجراست",
                           "یک نسخه دیگر از برنامه در حال اجرا است.")
    assert palette["TEXT_COLOR"] in dialog.message_label.styleSheet()
    assert palette["GREY_COLOR"] not in dialog.message_label.styleSheet()
    # The title keeps its own (already readable) style.
    assert palette["TEXT_COLOR"] in dialog.title_label.styleSheet()


def test_confirm_dialog_short_message_leaves_no_dead_space(qtbot):
    """Spacing regression: the word-wrapped message label's sizeHint badly
    over-estimated short one-line messages, and the surplus height was
    smeared across the title and message rows — a visible empty band
    between the header and the reason text. The label is pinned to its real
    heightForWidth need, so both rows sit at their exact height."""
    dialog = ConfirmDialog(None, "برنامه در حال اجراست",
                           "یک نسخه دیگر از برنامه در حال اجرا است.")
    qtbot.addWidget(dialog)
    dialog.adjustSize()
    dialog.show()
    margins = dialog.layout().contentsMargins()
    inner_width = dialog.width() - margins.left() - margins.right()
    needed = dialog.message_label.heightForWidth(inner_width)
    assert needed > 0
    # The message occupies exactly its wrapped height (no dead band around it)…
    assert dialog.message_label.height() == needed
    # …and the title gets exactly its own one-line height (no surplus to smear).
    assert dialog.title_label.height() == dialog.title_label.sizeHint().height()


def test_confirm_dialog_wrapped_message_still_fits(qtbot):
    """A message that wraps to several lines keeps fitting: the pin uses the
    same heightForWidth measurement the layout grants, so nothing clips."""
    dialog = ConfirmDialog(None, "عنوان",
                           "این پیام نسبتاً طولانی برای آزمودن شکستن خط در عرض کارت محاوره "
                           "عمداً نوشته شده است تا رفتار چیدمان در حالت دو یا سه خطی بررسی شود")
    qtbot.addWidget(dialog)
    dialog.adjustSize()
    dialog.show()
    margins = dialog.layout().contentsMargins()
    inner_width = dialog.width() - margins.left() - margins.right()
    needed = dialog.message_label.heightForWidth(inner_width)
    assert dialog.message_label.height() == needed
    assert dialog.height() >= dialog.layout().minimumSize().height()


# --- event year cap and greyed-out year field ---

def test_event_year_input_rejects_years_beyond_calendar_range(manager):
    """Years the calendar UI cannot reach (go-to-date allows 1200..1600)
    must not produce an event date."""
    from ui.widgets.event_input import MAX_EVENT_YEAR, MIN_EVENT_YEAR
    manager._on_add_requested()
    widget = manager.event_input_widget
    widget.month_combo.setCurrentIndex(widget.month_combo.findData(1))
    widget.day_combo.setCurrentIndex(widget.day_combo.findData(1))
    widget.year_input.setText(to_persian_digits(3213))
    assert widget.event_date() is None
    assert widget._year_is_out_of_range() is True
    widget.year_input.setText(to_persian_digits(MIN_EVENT_YEAR))
    assert widget._year_is_out_of_range() is False
    assert widget.event_date() == jdatetime.date(MIN_EVENT_YEAR, 1, 1)
    widget.year_input.setText(to_persian_digits(MAX_EVENT_YEAR))
    assert widget.event_date() == jdatetime.date(MAX_EVENT_YEAR, 1, 1)
    widget.year_input.setText(to_persian_digits(MIN_EVENT_YEAR - 1))
    assert widget.event_date() is None


def test_event_save_blocked_for_out_of_range_year(manager, qtbot):
    """Saving with an unreachable year flags the error and keeps the editor open."""
    manager._on_add_requested()
    widget = manager.event_input_widget
    widget.text_edit.setPlainText("دور از دسترس")
    widget.year_input.setText(to_persian_digits(3213))
    widget._on_save()
    assert widget.isVisible()                    # editor stays open
    assert widget._year_error is True            # red error border is on
    assert manager.controller.user_events == {}


def test_event_year_field_greyed_for_recurring_events(manager):
    """Monthly/yearly events need no year: the field disables and re-enables."""
    manager._on_add_requested()
    widget = manager.event_input_widget
    assert widget.year_input.isEnabled()         # one-time: editable
    widget.recurrence_combo.setCurrentIndex(widget.recurrence_combo.findText("سالانه"))
    assert not widget.year_input.isEnabled()
    widget.recurrence_combo.setCurrentIndex(widget.recurrence_combo.findText("ماهانه"))
    assert not widget.year_input.isEnabled()
    widget.recurrence_combo.setCurrentIndex(widget.recurrence_combo.findText("بدون تکرار"))
    assert widget.year_input.isEnabled()


def test_event_recurring_saves_even_with_unusable_year(manager):
    """Recurring keys drop the year, so a greyed/leftover year must not block."""
    manager._on_add_requested()
    widget = manager.event_input_widget
    widget.recurrence_combo.setCurrentIndex(widget.recurrence_combo.findText("ماهانه"))
    widget.year_input.setText(to_persian_digits(9999))  # greyed, out of range
    manager._on_edit_saved("روز ماه", RECURRENCE_MONTHLY, False)
    today = jdatetime.date.today()
    assert manager.controller.user_events[make_event_key(today, RECURRENCE_MONTHLY)]["text"] == "روز ماه"


# --- centered combo items ---

def test_manager_filter_combo_items_are_centered(manager):
    """Every dropdown row of the filter combos carries the centered role.

    The role combines the horizontal and vertical alignment bits: a
    horizontal-only value paints an empty band under the last popup option.
    """
    from PyQt6.QtCore import Qt as QtCoreQt
    expected = QtCoreQt.AlignmentFlag.AlignHCenter | QtCoreQt.AlignmentFlag.AlignVCenter
    for combo in (manager.month_combo, manager.type_combo):
        assert combo.count() > 1
        for i in range(combo.count()):
            role = combo.itemData(i, QtCoreQt.ItemDataRole.TextAlignmentRole)
            assert role == expected


def test_event_input_date_combos_are_centered(manager):
    manager._on_add_requested()
    widget = manager.event_input_widget
    expected = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
    for combo in (widget.month_combo, widget.day_combo, widget.recurrence_combo):
        for i in range(combo.count()):
            role = combo.itemData(i, Qt.ItemDataRole.TextAlignmentRole)
            assert role == expected


def test_holiday_viewer_year_combo_items_are_centered():
    window = HolidayViewerWindow({1403: {(1, 1): ["عید"]}})
    expected = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
    for i in range(window.year_combo.count()):
        role = window.year_combo.itemData(i, Qt.ItemDataRole.TextAlignmentRole)
        assert role == expected
    window.close()


# --- «گذشته» type filter ---

def test_manager_past_type_filter_shows_only_expired_one_time_events(manager):
    """Choosing «گذشته» lists just the already-passed one-time events."""
    today = jdatetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    manager.controller.add_user_event(yesterday, "گذشته", "none", False)
    manager.controller.add_user_event(today, "امروز", "none", False)
    manager.controller.user_events["0000-05-05"] = {"text": "سالانه", "recurrence": "yearly", "remove_after_finish": False}

    manager.type_combo.setCurrentIndex(manager.type_combo.findData("past"))
    labels = [manager.rows_layout.itemAt(i).widget().text_label.text()
              for i in range(manager.rows_layout.count() - 1)
              if manager.rows_layout.itemAt(i).widget() is not None]
    assert labels == ["گذشته"]

    # The show-past checkbox stays irrelevant while «گذشته» is selected.
    manager.past_checkbox.setChecked(False)
    labels = [manager.rows_layout.itemAt(i).widget().text_label.text()
              for i in range(manager.rows_layout.count() - 1)
              if manager.rows_layout.itemAt(i).widget() is not None]
    assert labels == ["گذشته"]


# --- modal editor overlay ---

def test_manager_add_flow_blocks_background_while_open(manager):
    """The scrim covers the window while the editor is open and closes with it."""
    manager.show()
    manager._on_add_requested()
    assert manager.overlay_blocker.isVisible()
    assert manager.overlay_blocker.geometry() == manager.rect()
    manager._hide_event_input_widget()
    assert not manager.overlay_blocker.isVisible()


def test_manager_hide_window_tears_down_overlay(manager):
    """Reopening after hiding must not leave a stale click-eating scrim."""
    manager.show()
    manager._on_add_requested()
    assert manager.overlay_blocker.isVisible()
    manager.hide()
    assert not manager.overlay_blocker.isVisible()
    assert not manager.event_input_widget.isVisible()
    manager.show()
    assert not manager.overlay_blocker.isVisible()


# --- text-only import/export buttons, short search placeholder ---

def test_manager_import_export_buttons_are_text_only(manager):
    """Two rounds of footer icons (inline FA glyphs, then pre-rendered
    QIcons) both looked bad on the user's machine; the buttons now carry
    their clear Persian labels alone."""
    assert manager.export_button.icon().isNull()
    assert manager.import_button.icon().isNull()
    assert manager.export_button.text() == "خروجی گرفتن"
    assert manager.import_button.text() == "وارد کردن"


def test_manager_search_placeholder_is_short_enough_to_fit(manager):
    """The filter row shares its width with two combos and a checkbox; the
    long placeholder elided to a stub, the short one must stay whole."""
    assert manager.search_input.placeholderText() == "جستجو…"


def test_manager_search_placeholder_pins_to_physical_right_edge(manager):
    """The manager window is RTL, where a bare AlignRight reads as
    "trailing" = the visual LEFT edge - the misplaced «جستجو…» the user
    saw. AlignAbsolute opts out of the mirroring so the placeholder, the
    text and the caret all sit on the physical right."""
    alignment = manager.search_input.alignment()
    assert alignment & Qt.AlignmentFlag.AlignRight
    assert alignment & Qt.AlignmentFlag.AlignAbsolute


# --- month combo greyed out for monthly events ---

def test_event_month_combo_greyed_for_monthly_events(manager):
    """Monthly keys anchor to the day only, so the month combo joins the year
    field in the disabled state; yearly and one-time keep it enabled."""
    manager._on_add_requested()
    widget = manager.event_input_widget
    assert widget.month_combo.isEnabled()            # one-time: month matters
    widget.recurrence_combo.setCurrentIndex(widget.recurrence_combo.findText("سالانه"))
    assert widget.month_combo.isEnabled()            # yearly still needs the month
    widget.recurrence_combo.setCurrentIndex(widget.recurrence_combo.findText("ماهانه"))
    assert not widget.month_combo.isEnabled()        # monthly: day is the anchor
    widget.recurrence_combo.setCurrentIndex(widget.recurrence_combo.findText("بدون تکرار"))
    assert widget.month_combo.isEnabled()


# --- year range hint next to the red border ---

def test_year_range_hint_appears_only_for_out_of_range_year(manager):
    """The red border says 'wrong'; the hint label states the 1200..1600
    range and disappears again for a valid year."""
    manager._on_add_requested()
    widget = manager.event_input_widget
    widget.year_input.setText(to_persian_digits(1404))
    assert widget.year_hint_label.isHidden()
    widget.year_input.setText(to_persian_digits(3213))
    assert not widget.year_hint_label.isHidden()
    assert "۱۲۰۰" in widget.year_hint_label.text() and "۱۶۰۰" in widget.year_hint_label.text()
    widget.year_input.setText(to_persian_digits(1200))
    assert widget.year_hint_label.isHidden()
    widget.year_input.setText(to_persian_digits(1601))
    assert not widget.year_hint_label.isHidden()
    widget.year_input.setText(to_persian_digits(1600))
    assert widget.year_hint_label.isHidden()


def test_editing_flow_never_inherits_year_hint(manager):
    """Opening the editor without the date picker resets any stale error,
    so an invalid year from a cancelled add attempt never leaks into edit."""
    manager._on_add_requested()
    widget = manager.event_input_widget
    widget.year_input.setText(to_persian_digits(3213))
    assert widget.year_hint_label.isVisibleTo(widget)
    manager._hide_event_input_widget()           # user cancels the add flow
    key = make_event_key(jdatetime.date.today(), RECURRENCE_NONE)
    manager.controller.user_events[key] = {
        "text": "موجود", "recurrence": RECURRENCE_NONE, "remove_after_finish": False}
    manager._on_edit_requested(key)
    assert widget.year_hint_label.isHidden()


# --- plain converter-style combos (no dead space under the last option) ---

def test_manager_and_viewer_combos_match_the_working_converter_recipe(manager):
    """The two windows the user reported use plain QComboBox with no
    size-adjust policy - exactly the configuration of the date converter
    and go-to-date combos, whose dropdowns render without dead space.
    (The previous TightPopupCombo subclass pinned the view height from
    pre-popup metrics, which itself re-created the dead-space band.)"""
    from PyQt6.QtWidgets import QComboBox
    for combo in (manager.month_combo, manager.type_combo):
        assert type(combo) is QComboBox
        assert combo.sizeAdjustPolicy() != QComboBox.SizeAdjustPolicy.AdjustToContents
    window = HolidayViewerWindow({1403: {(1, 1): ["عید"]}})
    try:
        assert type(window.year_combo) is QComboBox
        assert (window.year_combo.sizeAdjustPolicy()
                != QComboBox.SizeAdjustPolicy.AdjustToContents)
    finally:
        window.close()


# --- auto-delete badge on rows flagged to remove after their date ---

def test_manager_rows_mark_auto_delete_events(manager):
    today = jdatetime.date.today()
    key = make_event_key(today, RECURRENCE_NONE)
    manager.controller.add_user_event(today, "یک‌بار مصرف", "none", False)
    manager.controller.user_events[key]["remove_after_finish"] = True
    manager.controller.add_user_event(today - datetime.timedelta(days=1),
                                      "معمولی", "none", False)
    manager.refresh_list()
    rows = [manager.rows_layout.itemAt(i).widget()
            for i in range(manager.rows_layout.count() - 1)
            if manager.rows_layout.itemAt(i).widget() is not None]
    badges = [row.findChild(QLabel, "EventAutoDeleteBadge") for row in rows]
    assert len(rows) == 2
    assert [badge is not None for badge in badges].count(True) == 1


# --- confirmation dialog: quotes, choose/notify ---

def test_confirm_dialog_detail_box_keeps_text_verbatim():
    """No decorative «» around the preview - the rounded box already sets
    the text apart."""
    dialog = ConfirmDialog(None, "حذف رویداد", "این رویداد حذف شود؟", detail="جلسه پروژه")
    assert dialog.detail_label.text() == "جلسه پروژه"


def test_confirm_dialog_choose_returns_clicked_action(qtbot):
    """A three-way ask records the clicked label; ghost buttons still reject
    so Esc-style semantics survive, accent/danger buttons accept."""
    dialog = ConfirmDialog(
        None, "بروزرسانی جدید", "متن",
        actions=[("دانلود", "accent"), ("نادیده گرفتن", "danger"), ("بعداً یادآوری کن", "ghost")])
    qtbot.addWidget(dialog)
    QTest.mouseClick(dialog.buttons[1], Qt.MouseButton.LeftButton)
    assert dialog.choice == "نادیده گرفتن"
    assert dialog.result() == int(QDialog.DialogCode.Accepted)

    ghost = ConfirmDialog(
        None, "بروزرسانی جدید", "متن",
        actions=[("دانلود", "accent"), ("نادیده گرفتن", "danger"), ("بعداً یادآوری کن", "ghost")])
    qtbot.addWidget(ghost)
    QTest.mouseClick(ghost.buttons[2], Qt.MouseButton.LeftButton)
    assert ghost.choice == "بعداً یادآوری کن"
    assert ghost.result() == int(QDialog.DialogCode.Rejected)


def test_confirm_dialog_choose_returns_none_when_dismissed(qtbot, monkeypatch):
    """Closing the dialog without a button yields None, not the first action."""
    widget = EventInputWidget()
    monkeypatch.setattr(ConfirmDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    assert ConfirmDialog.choose(widget, "عنوان", "متن",
                                actions=[("دانلود", "accent"), ("بعداً", "ghost")]) is None


def test_confirm_dialog_notify_shows_single_button(qtbot, monkeypatch):
    """The single-button notice reports acceptance and carries one button."""
    dialogs = []
    real_init = ConfirmDialog.__init__

    def capturing_init(self, *args, **kwargs):
        real_init(self, *args, **kwargs)
        dialogs.append(self)

    monkeypatch.setattr(ConfirmDialog, "__init__", capturing_init)
    monkeypatch.setattr(ConfirmDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    ConfirmDialog.notify(None, "بروز است", "برنامه و فایل تعطیلات بروز است.")
    assert len(dialogs) == 1
    assert len(dialogs[0].buttons) == 1


def test_confirm_dialog_notify_forwards_detail_to_the_dialog(qtbot, monkeypatch):
    """notify() is the only flow that had no detail line, so a notice could not
    show a breakdown under its headline. The detail must reach the dialog rather
    than be silently dropped on the way through choose()."""
    seen = {}

    def fake_choose(parent, title, message, **kwargs):
        seen.update(kwargs)
        seen["message"] = message

    monkeypatch.setattr(ConfirmDialog, "choose", staticmethod(fake_choose))
    ConfirmDialog.notify(None, "فاصله تا امروز", "۶۹ روز مانده",
                         detail="۲ ماه و ۹ روز مانده")
    assert seen["detail"] == "۲ ماه و ۹ روز مانده"
    assert seen["message"] == "۶۹ روز مانده"


def test_confirm_dialog_notify_without_detail_keeps_the_box_hidden(qtbot, monkeypatch):
    """The default stays empty so the existing notices keep their current height."""
    dialogs = []
    real_init = ConfirmDialog.__init__

    def capturing_init(self, *args, **kwargs):
        real_init(self, *args, **kwargs)
        dialogs.append(self)

    monkeypatch.setattr(ConfirmDialog, "__init__", capturing_init)
    monkeypatch.setattr(ConfirmDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    ConfirmDialog.notify(None, "بروز است", "برنامه و فایل تعطیلات بروز است.")
    assert not dialogs[0].detail_label.isVisible()
    assert dialogs[0].detail_label.text() == ""


# --- update checker uses the themed dialogs ---

def test_update_popup_download_choice_starts_download(tray, monkeypatch):
    picked = {}
    monkeypatch.setattr(ConfirmDialog, "choose", lambda *a, **k: "دانلود")
    monkeypatch.setattr(tray, "_download_update",
                        lambda version, url, sha: picked.update(version=version))
    tray._show_update_popup("1.4.1", "http://example.com/setup.exe", "abc")
    assert picked == {"version": "1.4.1"}


def test_update_popup_ignore_choice_records_version(tray, monkeypatch):
    monkeypatch.setattr(ConfirmDialog, "choose", lambda *a, **k: "نادیده گرفتن")
    tray._show_update_popup("1.4.1", "http://example.com/setup.exe", "abc")
    assert tray.settings.value(APP_CONFIG.IGNORED_UPDATE_VERSION_SETTING_KEY) == "1.4.1"


def test_update_popup_remind_choice_does_nothing(tray, monkeypatch):
    monkeypatch.setattr(ConfirmDialog, "choose", lambda *a, **k: "بعداً یادآوری کن")
    picked = {}
    monkeypatch.setattr(tray, "_download_update", lambda *a: picked.update(any=True))
    tray._show_update_popup("1.4.1", "http://example.com/setup.exe", "abc")
    assert picked == {}
    assert tray.settings.value(APP_CONFIG.IGNORED_UPDATE_VERSION_SETTING_KEY) in (None, "")


# --- day-cell hover residue and tooltip z-order ---

@pytest.fixture
def calendar(qtbot):
    window = PersianCalendarWidget({}, {})
    qtbot.addWidget(window)
    window.show()
    yield window


def test_normalize_day_hover_clears_stale_flag(calendar):
    """A cell whose under-mouse flag went stale (menus/overlays interrupt the
    enter/leave chain) is cleared when the cursor is genuinely elsewhere."""
    cell = calendar.day_labels[0][0]
    QCursor.setPos(cell.mapToGlobal(cell.rect().center()))
    cell.setAttribute(Qt.WidgetAttribute.WA_UnderMouse, True)
    calendar.normalize_day_hover()
    assert cell.underMouse()                       # cursor really is inside

    cell.setAttribute(Qt.WidgetAttribute.WA_UnderMouse, True)
    QCursor.setPos(0, 0)
    calendar.normalize_day_hover()
    assert not cell.underMouse()                   # stale flag cleared


def test_cancel_editor_clears_stale_day_hover(calendar):
    """The reported flow: right-click -> add event -> cancel must not leave
    a cell lit as if the cursor were still on it."""
    cell = calendar.day_labels[0][0]
    cell.setAttribute(Qt.WidgetAttribute.WA_UnderMouse, True)
    QCursor.setPos(0, 0)
    calendar._show_event_input_widget(jdatetime.date.today())
    calendar._hide_event_input_widget()
    assert not calendar.event_input_widget.isVisible()
    assert not cell.underMouse()


def test_day_cell_tooltip_skipped_when_cursor_is_elsewhere(calendar):
    """A stale tooltip timer must not pop a floating tooltip (it would even
    hover above the modal event editor) when the cursor has moved off."""
    cell = calendar.day_labels[0][0]
    cell.setToolTip("مناسبت")
    QCursor.setPos(0, 0)
    cell._show_custom_tooltip()
    assert not CustomTooltip.instance().isVisible()

    QCursor.setPos(cell.mapToGlobal(cell.rect().center()))
    cell._show_custom_tooltip()
    assert CustomTooltip.instance().isVisible()
    CustomTooltip.instance().hide()


# --- failure notices style their OK button as an error (#5) --------------------------


def test_notify_danger_styles_ok_button_as_danger(qtbot, monkeypatch):
    """(#5) A failed-operation notice must not look like a success: with
    danger=True the single OK button uses the destructive (holiday-red)
    style instead of the accent blue."""
    captured = {}

    def fake_choose(parent, title, message, *, actions, danger, glyph, width, **kwargs):
        captured['actions'] = actions
        captured['danger'] = danger
        return None

    monkeypatch.setattr(ConfirmDialog, "choose", staticmethod(fake_choose))
    ConfirmDialog.notify(None, "ذخیره رویدادها", "ذخیره رویدادها ناموفق بود.", danger=True)
    assert captured['actions'] == [("باشه", "danger")]
    ConfirmDialog.notify(None, "خروجی گرفتن از رویدادها", "موفق بود.")  # default danger=False
    assert captured['actions'] == [("باشه", "accent")]


def test_danger_notify_button_gets_danger_stylesheet(qtbot):
    """End-to-end visual check: the built dialog's OK button really carries
    the danger stylesheet (holiday red), not the accent one."""
    from config import APP_CONFIG
    from utils.ui_helpers import danger_button_stylesheet

    dialog = ConfirmDialog(None, "ذخیره رویدادها", "ناموفق", danger=True,
                           actions=[("باشه", "danger")])
    qtbot.addWidget(dialog)
    assert dialog.buttons[0].styleSheet() == danger_button_stylesheet(APP_CONFIG.get_current_palette())


# --- in-calendar confirm overlay ---

@pytest.fixture
def host(qtbot):
    """A plain widget to parent an overlay to; the calendar is only one host."""
    widget = QWidget()
    widget.resize(APP_CONFIG.CALENDAR_WIDTH, APP_CONFIG.CALENDAR_HEIGHT)
    qtbot.addWidget(widget)
    widget.show()
    return widget


def test_overlay_is_a_child_card_not_a_window(qtbot, host):
    overlay = ConfirmOverlay(host, "حذف رویداد", detail="این رویداد حذف شود؟")
    overlay.show()
    assert overlay.parent() is host
    assert not overlay.isWindow()
    assert not isinstance(overlay, QDialog)
    # A child has no window flags of its own and must not be draggable.
    assert not hasattr(overlay, "handle_drag_press")


def test_overlay_reports_and_hides_on_choice(qtbot, host):
    overlay = ConfirmOverlay(host, "حذف رویداد", detail="x")
    overlay.show()
    seen = []
    overlay.chosen.connect(seen.append)
    QTest.mouseClick(overlay.confirm_button, Qt.MouseButton.LeftButton)
    assert seen == [overlay.confirm_button.text()]
    assert not overlay.isVisible()
    assert overlay.choice == overlay.confirm_button.text()


def test_overlay_ask_shape_has_a_cancel_button(qtbot, host):
    overlay = ConfirmOverlay(host, "حذف رویداد", confirm_text="حذف", cancel_text="انصراف")
    seen = []
    overlay.chosen.connect(seen.append)
    QTest.mouseClick(overlay.cancel_button, Qt.MouseButton.LeftButton)
    assert seen == ["انصراف"]


def test_overlay_notice_shape_is_single_button(qtbot, host):
    """The read-only notice shape has no cancel; `cancel_button` is None rather
    than a missing attribute a host could trip over."""
    overlay = ConfirmOverlay(host, "فاصله تا امروز", notice=True, danger=False)
    assert len(overlay.buttons) == 1
    assert overlay.cancel_button is None
    assert overlay.confirm_button is overlay.buttons[0]


def test_overlay_carries_no_message_line(qtbot, host):
    """An overlay starts with no description line, so a box-only notice leaves no
    dead air above it; a host that wants one raises it per use."""
    overlay = ConfirmOverlay(host, "حذف رویداد", detail="متن")
    overlay.show()
    assert overlay.message_label.text() == ""
    assert not overlay.message_label.isVisible()
    assert overlay.detail_label.isVisible()


def test_overlay_set_message_raises_the_description_line(qtbot, host):
    overlay = ConfirmOverlay(host, "حذف رویداد", detail="یادداشت")
    overlay.show()
    overlay.set_message("این رویداد حذف شود؟")
    assert overlay.message_label.isVisible()
    # Pinned to its real wrapped height, not Qt's inflated word-wrap hint.
    assert overlay.message_label.height() > 0
    assert overlay.message_label.height() < 60


def test_overlay_set_message_clears_the_line_for_the_next_use(qtbot, host):
    """Overlays are persistent: a stale question or a stale height pinned for the
    previous wording must not survive into the next card."""
    overlay = ConfirmOverlay(host, "حذف رویداد")
    overlay.show()
    overlay.set_message("این رویداد حذف شود؟")
    overlay.set_message("")
    assert overlay.message_label.text() == ""
    assert not overlay.message_label.isVisible()


def test_overlay_set_message_resets_the_choice(qtbot, host):
    """Refilling a reused card must not leave the previous answer behind, or a
    host could act on a click the user never made."""
    overlay = ConfirmOverlay(host, "حذف رویداد", detail="یادداشت")
    overlay.show()
    overlay.confirm_button.click()
    assert overlay.choice is not None
    overlay.set_message("این رویداد حذف شود؟")
    assert overlay.choice is None



def test_overlay_width_never_exceeds_its_host(qtbot, host):
    """The calendar is 305px; a caption that would push the card wider must not
    be able to overflow the popup."""
    overlay = ConfirmOverlay(host, "حذف رویداد", confirm_text="حذف", cancel_text="انصراف")
    overlay.show()
    assert overlay.width() <= host.width()


def test_overlay_reuse_refills_the_box_and_resets_the_choice(qtbot, host):
    """The overlay is persistent, so stale text or a stale choice from a previous
    question must not leak into the next one."""
    overlay = ConfirmOverlay(host, "حذف رویداد", detail="اولی")
    overlay.show()
    overlay.confirm_button.click()
    overlay.set_detail("دومی")
    assert overlay.detail_label.text() == "دومی"
    assert overlay.choice is None
    overlay.set_detail("")
    assert not overlay.detail_label.isVisible()


def test_overlay_centers_over_its_host(qtbot, host):
    overlay = ConfirmOverlay(host, "حذف رویداد", detail="متن")
    overlay.show()
    overlay.center_in(host)
    assert abs(overlay.x() - (host.width() - overlay.width()) // 2) <= 1
    assert abs(overlay.y() - (host.height() - overlay.height()) // 2) <= 1
