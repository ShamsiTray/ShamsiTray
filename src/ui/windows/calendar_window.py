"""
Persian Calendar Widget
-----------------------

This module defines `PersianCalendarWidget`, the main calendar view of the
application. It displays a month grid of Jalali dates and handles user
interaction for navigation, date selection, and event management.
"""
import datetime
from dataclasses import dataclass
from html import escape
from typing import List, Optional, Tuple

import jdatetime
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFont
from PyQt6.QtWidgets import QBoxLayout, QGridLayout, QHBoxLayout, QLabel, QPushButton, QWidgetAction, QVBoxLayout, QWidget, QMenu

from config import APP_CONFIG
from utils.date_utils import (describe_date_distance, days_in_jalali_month,
                              format_distance_breakdown, format_distance_total,
                              format_jalali_long, persian_month_name,
                              to_persian_digits)
from utils.event_io import (RECURRENCE_MODES, RECURRENCE_NONE, events_for_date,
                            events_on_date, make_event_key, recurrence_of_key,
                            recurrences_on_date)
from utils.ui_helpers import clamp_popup_to_work_area, nav_button_stylesheet
from ui.widgets.calendar_day_cell import ClickableLabel
from ui.widgets.confirm_overlay import ConfirmOverlay
from ui.widgets.go_to_date import GoToDateWindow
from ui.widgets.event_input import EventInputWidget, recurrence_label
from ui.widgets.menu_widgets import MenuActionWidget
from .base_window import BaseFramelessWindow

@dataclass
class DayStyle:
    """A data class to hold styling properties for a calendar day label."""
    text_color: str
    background_color: str = "transparent"
    hover_background_color: str = "transparent"
    border_style: str = "none"
    font_size: int = APP_CONFIG.FONT_SIZE_LABEL
    tooltip: str = ""

class PersianCalendarWidget(BaseFramelessWindow):
    """Main calendar widget displaying a month of Persian (Jalali) dates."""
    ROWS, COLS = 6, 7
    # Opened from the tray, this is a flyout rather than a form: with
    # always-on-top switched off, a click outside it dismisses it.
    CLOSE_ON_OUTSIDE_CLICK_WHEN_UNPINNED = True
    event_added = pyqtSignal(object, str, str, bool)  # jdate, text, recurrence, remove_after_finish
    # key-scoped edit: key, jdate, text, recurrence, remove_after_finish, merge_into
    # (merge_into is empty unless the user confirmed folding this edit into the
    # event already living on the key the edit would land on)
    event_updated_by_key = pyqtSignal(str, object, str, str, bool, str)
    event_removed = pyqtSignal(object)
    event_removed_by_key = pyqtSignal(str)

    def __init__(self, holidays_cache: dict, user_events: dict):
        super().__init__()
        self.holidays_cache = holidays_cache
        self.user_events = user_events

        self.current_date = jdatetime.date.today()
        self.display_date = self.current_date
        self.selected_date = self.current_date
        self.editing_date: Optional[jdatetime.date] = None
        self.go_to_window: Optional[GoToDateWindow] = None
        # Qt emits this object's destroyed() before it deletes the children, so this
        # flag lets the go-to handler tell "that window died" from "we are all going
        # away". It is a lambda on purpose: a bound method whose receiver is the
        # object being destroyed is not called, a free function is.
        self._is_being_destroyed = False
        self.destroyed.connect(lambda *_: setattr(self, "_is_being_destroyed", True))

        self.day_labels: List[List[ClickableLabel]] = []
        self._show_gregorian_mdy = True

        self._setup_ui()
        self.update_styles()
        self.fill_calendar_grid()

    def hideEvent(self, event):
        """Override hideEvent to also close the 'Go To Date' window and its overlay,
        so a stale overlay can never eat mouse input after the calendar reopens.
        Any open event editor and the custom tooltip are dismissed as well:
        both outlive their parent window otherwise (the tooltip is a separate
        top-level window and would keep floating over other applications)."""
        if self.go_to_window and self.go_to_window.isVisible():
            self.go_to_window.close()
        if self.event_input_widget.isVisible():
            self.event_input_widget.hide()
            self.editing_date = None
            # The key decides which event a save touches, so it must not outlive
            # the editor it belongs to.
            self._editing_event_key = None
        # A confirmation in flight dies with the popup, and its pending deletion
        # with it: leaving the date set would let a later choice remove an event
        # the user was no longer looking at.
        self._dismiss_active_overlay()
        self.overlay_blocker.hide()
        self._cancel_day_tooltips()
        super().hideEvent(event)

    def _dismiss_active_overlay(self):
        """Hide whichever confirm overlay is up and forget any pending action.

        Idempotent, and the single teardown path: a hidden calendar must never
        come back with a dimmed grid or a confirmation waiting for an answer.
        Relies on an overlay being the only thing that dims the grid, so the
        blocker goes down with it.
        """
        overlay, self._active_overlay = self._active_overlay, None
        self._pending_remove = None
        self._pending_merge = None
        if overlay is not None:
            overlay.hide()
            self.overlay_blocker.hide()

    def _present_overlay(self, overlay: ConfirmOverlay):
        """Dim the grid and raise ``overlay`` in the middle of the popup."""
        self._active_overlay = overlay
        self.overlay_blocker.resize(self.size())
        self.overlay_blocker.show()
        self.overlay_blocker.raise_()
        overlay.center_in(self)
        overlay.show()
        overlay.raise_()

    def _cancel_day_tooltips(self):
        """Kill every pending cell tooltip (and hide the shared tooltip window).

        Closing a day-cell context menu re-arms the cell under the cursor, and
        500ms later its tooltip would pop on top of whatever opened in between
        - reported floating over the event editor (holiday reason over the
        add-event panel) and over the delete confirmation alike. Called whenever
        a modal surface opens over the grid and when the window itself hides."""
        for row in self.day_labels:
            for cell in row:
                cell.cancel_pending_tooltip()

    def set_user_events(self, user_events: dict):
        self.user_events = user_events
        self.fill_calendar_grid()

    def set_holidays(self, holidays_cache: dict):
        self.holidays_cache = holidays_cache
        self.fill_calendar_grid()

    def _setup_ui(self):
        self.setFixedSize(APP_CONFIG.CALENDAR_WIDTH, APP_CONFIG.CALENDAR_HEIGHT)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 10, 15, 10)
        main_layout.setSpacing(0)
        main_layout.addLayout(self._create_header())
        main_layout.addLayout(self._create_gregorian_bar())
        self.weekdays_layout = self._create_weekdays_header()
        main_layout.addLayout(self.weekdays_layout)
        self.calendar_grid_layout = self._create_calendar_grid()
        main_layout.addLayout(self.calendar_grid_layout)

        self.overlay_blocker = QWidget(self)
        self.overlay_blocker.setStyleSheet("background-color: rgba(0, 0, 0, 75); border-radius: 26px; margin: 1px;")
        self.overlay_blocker.hide()

        # Confirmation surfaces are part of the popup, not windows over it: no
        # drag, no separate top-level card, and the dimmed blocker behind them.
        # One persistent instance per shape (single-button notice, two-button
        # ask), shown and hidden, so nothing has to track a destroyed widget.
        self._active_overlay: Optional[ConfirmOverlay] = None
        self._editing_event_key: Optional[str] = None
        self._pending_remove: Optional[jdatetime.date] = None
        self._pending_remove_key: Optional[str] = None
        # key, jdate, target_key, text, recurrence, remove_after_finish
        self._pending_merge: Optional[Tuple[str, jdatetime.date, str, str, str, bool]] = None
        self._distance_overlay = ConfirmOverlay(
            self, "فاصله تا امروز", danger=False,
            glyph=APP_CONFIG.FAS.FA_CLOCK, notice=True)
        # Both overlays must answer back: an overlay only hides itself, so without
        # this the dimmer would stay up over a notice that is already gone and the
        # grid would refuse every click.
        self._distance_overlay.chosen.connect(self._on_distance_choice)
        self._distance_overlay.hide()
        self._remove_overlay = ConfirmOverlay(
            self, "حذف رویداد", confirm_text="حذف", cancel_text="انصراف",
            danger=True)
        self._remove_overlay.chosen.connect(self._on_remove_choice)
        self._remove_overlay.hide()
        self._merge_overlay = ConfirmOverlay(
            self, "ادغام رویداد", confirm_text="ادغام", cancel_text="انصراف",
            danger=False)
        self._merge_overlay.chosen.connect(self._on_merge_choice)
        self._merge_overlay.hide()

        self.event_input_widget = EventInputWidget(self)
        self.event_input_widget.saved.connect(self._handle_event_saved)
        self.event_input_widget.canceled.connect(self._handle_event_canceled)
        self.event_input_widget.hide()

    def _create_header(self) -> QHBoxLayout:
        self.left_arrow_btn = QPushButton("❮")
        self.left_arrow_btn.clicked.connect(self.next_month)
        self.right_arrow_btn = QPushButton("❯")
        self.right_arrow_btn.clicked.connect(self.prev_month)
        self.year_label = QLabel()
        self.month_label = QLabel()
        month_year_layout = QHBoxLayout()
        month_year_layout.setSpacing(5)
        month_year_layout.setContentsMargins(0, 0, 0, 0)
        month_year_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        month_year_layout.addWidget(self.year_label)
        month_year_layout.addWidget(self.month_label)

        month_year_container = QWidget()
        month_year_container.setLayout(month_year_layout)
        month_year_container.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        month_year_container.customContextMenuRequested.connect(self._show_go_to_date_menu)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, -5)
        header_layout.setSpacing(10)
        header_layout.addWidget(self.left_arrow_btn)
        header_layout.addStretch(1)
        header_layout.addWidget(month_year_container)
        header_layout.addStretch(1)
        header_layout.addWidget(self.right_arrow_btn)
        return header_layout

    def _create_gregorian_bar(self) -> QHBoxLayout:
        self.gregorian_date_label = ClickableLabel()
        self.gregorian_date_label.clicked.connect(self._toggle_gregorian_format)
        self.today_btn = QPushButton("امروز")
        self.today_btn.clicked.connect(self.go_to_today)
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 10)
        layout.addWidget(self.gregorian_date_label)
        layout.addStretch()
        layout.addWidget(self.today_btn)
        return layout

    def _create_weekdays_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(5)
        layout.setContentsMargins(0, 0, 0, 10)
        layout.setDirection(QBoxLayout.Direction.RightToLeft)
        for day_name in APP_CONFIG.PERSIAN_WEEKDAYS_SHORT:
            label = QLabel(day_name)
            label.setObjectName("WeekdayLabel")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setFixedSize(APP_CONFIG.DAY_LABEL_SIZE, APP_CONFIG.DAY_LABEL_SIZE)
            layout.addWidget(label)
        return layout

    def _create_calendar_grid(self):
        grid_layout = QGridLayout()
        grid_layout.setSpacing(5)
        grid_layout.setOriginCorner(Qt.Corner.TopRightCorner)
        for row in range(self.ROWS):
            week_labels = []
            for col in range(self.COLS):
                label = ClickableLabel()
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label.setFixedSize(APP_CONFIG.DAY_LABEL_SIZE, APP_CONFIG.DAY_LABEL_SIZE)
                label.clicked.connect(self._on_day_clicked)
                label.add_event_requested.connect(self._show_event_input_widget)
                label.remove_event_requested.connect(self._remove_event)
                label.edit_event_requested_specific.connect(self._show_event_input_for_specific)
                label.remove_event_requested_specific.connect(self._remove_event_by_key)
                label.distance_requested.connect(self._show_date_distance)
                grid_layout.addWidget(label, row, col)
                week_labels.append(label)
            self.day_labels.append(week_labels)
        return grid_layout

    def resizeEvent(self, event):
        self.overlay_blocker.resize(self.size())
        super().resizeEvent(event)

    def normalize_day_hover(self):
        """Re-align every day cell's hover flag with the real cursor position.

        Popup menus and overlay panels interrupt Qt's enter/leave chain, so a
        cell can keep its under-mouse flag - and with it the QSS :hover look -
        long after the cursor moved behind the editor (the report: hover stuck
        on the right-clicked date after cancelling the add-event panel, cleared
        only by hovering the cell again). :hover resolves from that flag at
        paint time, so clearing it for cells the cursor is genuinely not inside
        and repainting puts the grid back in sync once an overlay is gone.
        """
        cursor = QCursor.pos()
        for row in self.day_labels:
            for cell in row:
                if cell.underMouse() and not cell.rect().contains(cell.mapFromGlobal(cursor)):
                    cell.setAttribute(Qt.WidgetAttribute.WA_UnderMouse, False)
                    cell.update()

    def _get_nav_button_style(self, bg_color: str, is_today_button: bool = False) -> str:
        # Shared builder: the style text lives with the other stylesheets so a
        # theme tweak cannot drift.
        return nav_button_stylesheet(APP_CONFIG.get_current_palette(), bg_color,
                                     is_today_button=is_today_button)

    def update_styles(self):
        palette = APP_CONFIG.get_current_palette()
        text_color, accent_color = palette['TEXT_COLOR'], palette['ACCENT_COLOR']
        nav_button_font = QFont(APP_CONFIG.FONT_FAMILY, 12, QFont.Weight.Bold)
        today_button_font = QFont(APP_CONFIG.FONT_FAMILY, 12, QFont.Weight.Bold)
        self.left_arrow_btn.setFont(nav_button_font)
        self.right_arrow_btn.setFont(nav_button_font)
        self.left_arrow_btn.setStyleSheet(self._get_nav_button_style("transparent"))
        self.right_arrow_btn.setStyleSheet(self._get_nav_button_style("transparent"))
        self.left_arrow_btn.setFixedSize(30, 30)
        self.right_arrow_btn.setFixedSize(30, 30)
        self.today_btn.setFont(today_button_font)
        self.today_btn.setStyleSheet(self._get_nav_button_style(accent_color, is_today_button=True))
        self.today_btn.setFixedSize(60, 30)
        header_style = f"color: {text_color}; font-size: {APP_CONFIG.FONT_SIZE_HEADER}px; font-weight: bold; font-family: '{APP_CONFIG.FONT_FAMILY}';"
        self.year_label.setStyleSheet(header_style)
        self.month_label.setStyleSheet(header_style)
        self.gregorian_date_label.setStyleSheet(f"QLabel {{ color: {text_color}; font-size: {APP_CONFIG.FONT_SIZE_LABEL}px; background-color: {palette['HOVER_BG']}; font-family: '{APP_CONFIG.GREGORIAN_FONT_FAMILY}'; font-weight: bold; border-radius: 8px; padding: 3px 6px; }} QLabel:hover {{ background-color: {palette['GREGORIAN_DATE_HOVER_BG']}; }}")
        for i in range(self.weekdays_layout.count()):
            day_label = self.weekdays_layout.itemAt(i).widget()
            if isinstance(day_label, QLabel):
                is_friday = day_label.text() == 'ج'
                color = palette['HOLIDAY_COLOR'] if is_friday else palette['WEEKDAY_NAMES_COLOR']
                day_label.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 16px; background: transparent; font-family: '{APP_CONFIG.FONT_FAMILY}';")

        if self.event_input_widget:
            self.event_input_widget.update_styles()
        if self.go_to_window:
            self.go_to_window.update_styles()
        self.fill_calendar_grid()

    def get_user_event_for_date(self, jdate: jdatetime.date) -> Tuple[Optional[str], bool, bool]:
        """Checks for a matching event (specific, yearly or monthly), returning the
        text, whether it repeats (recurrence != none), and its auto-delete flag."""
        matched = events_for_date(self.user_events, jdate)
        if matched is None:
            return None, False, False
        _, entry = matched
        recurrence = entry.get("recurrence", RECURRENCE_NONE)
        return entry.get("text"), recurrence != RECURRENCE_NONE, entry.get("remove_after_finish", False)

    def fill_calendar_grid(self):
        self._update_header()
        self._fill_grid_cells()

    def _fill_grid_cells(self):
        first_day = self.display_date.replace(day=1)
        start_day_of_week = first_day.weekday()

        current_day = first_day - datetime.timedelta(days=start_day_of_week)
        for row in range(self.ROWS):
            for col in range(self.COLS):
                label = self.day_labels[row][col]
                label.jalali_date = current_day
                label.setText(to_persian_digits(current_day.day))

                user_event_text, _, _ = self.get_user_event_for_date(current_day)
                label.has_user_event = bool(user_event_text)

                is_in_display_month = (current_day.month == self.display_date.month)
                stylesheet, tooltip = self._get_day_style(current_day, is_in_display_month)
                label.setStyleSheet(stylesheet)
                label.setToolTip(tooltip)
                current_day += datetime.timedelta(days=1)

    def _update_header(self):
        self.month_label.setText(persian_month_name(self.display_date.month))
        self.year_label.setText(to_persian_digits(self.display_date.year))
        greg_date = self.selected_date.togregorian()
        self.gregorian_date_label.setText(greg_date.strftime("%m/%d/%Y") if self._show_gregorian_mdy else greg_date.strftime("%b %d, %Y"))

    def _get_rgba_string(self, color_hex: str, alpha: float) -> str:
        color = QColor(color_hex)
        return f"rgba({color.red()}, {color.green()}, {color.blue()}, {int(alpha * 255)})"

    def _determine_day_style(self, jdate: jdatetime.date, is_in_month: bool) -> DayStyle:
        """Determines visual styling for a calendar cell based on: current day, selected day,
        holidays (official + Fridays), user-defined events and whether the day belongs to the displayed month
        his function intentionally centralizes all day-state logic to keep rendering consistent across the grid.
        """
        palette = APP_CONFIG.get_current_palette()
        style = DayStyle(text_color=palette['TEXT_COLOR'], hover_background_color=palette['HOVER_BG'])

        # Every event occurring on the day, not just the one the grid highlights: the
        # tooltip is where a user reads what is scheduled, so listing only the
        # priority winner hid a monthly event behind a one-time one on the same
        # date. The single winner still drives the cell's colour and indicator.
        day_events = events_on_date(self.user_events, jdate)
        is_user_event = bool(day_events)
        is_today = (jdate == self.current_date)
        is_selected = (jdate == self.selected_date)
        is_friday = jdate.weekday() == 6

        year_holidays = self.holidays_cache.get(jdate.year, {})
        holiday_reasons = year_holidays.get((jdate.month, jdate.day))
        is_holiday = bool(holiday_reasons)
        is_special_day = is_user_event or is_holiday or is_friday

        tooltip_parts = []
        if holiday_reasons:
            html_reasons = "<br>".join(escape(r) for r in holiday_reasons)
            tooltip_parts.append(f'<span style="white-space: nowrap; color:{palette["HOLIDAY_COLOR"]};">{html_reasons}</span>')
        for _key, entry in day_events:
            html_event_text = escape(str(entry.get("text", ""))).replace('\n', '<br>')
            tooltip_parts.append(f'<span style="color:{palette["ACCENT_COLOR"]};">{html_event_text}</span>')
        if tooltip_parts:
            style.tooltip = f"<qt>{'<br>'.join(tooltip_parts)}</qt>"

        base_color_hex = palette['TEXT_COLOR']
        if is_in_month:
            if is_user_event:
                base_color_hex = palette['ACCENT_COLOR']
            elif is_holiday or is_friday:
                base_color_hex = palette['HOLIDAY_COLOR']
            style.text_color = base_color_hex

            if is_today and is_selected:
                alpha = 0.6 if is_special_day else 0.35
                style.background_color = self._get_rgba_string(base_color_hex, alpha)
                style.hover_background_color = self._get_rgba_string(base_color_hex, alpha + 0.1)
            elif is_selected:
                if is_special_day:
                    style.background_color = self._get_rgba_string(base_color_hex, 0.45)
                    style.hover_background_color = self._get_rgba_string(base_color_hex, 0.55)
                else:
                    style.background_color = palette['CALENDAR_SELECTED_BG_COLOR']
                    style.hover_background_color = palette['CALENDAR_SELECTED_HOVER_BG_COLOR']
            elif is_today:
                alpha = 0.35 if is_special_day else 1.0
                bg_hex = base_color_hex if alpha != 1.0 else palette['CALENDAR_TODAY_BG_COLOR']
                style.background_color = self._get_rgba_string(bg_hex, alpha) if alpha != 1.0 else bg_hex
                style.hover_background_color = self._get_rgba_string(base_color_hex, alpha + 0.1) if alpha != 1.0 else palette['CALENDAR_TODAY_HOVER_BG_COLOR']
            elif is_special_day:
                style.background_color = self._get_rgba_string(base_color_hex, 0.15)
                style.hover_background_color = self._get_rgba_string(base_color_hex, 0.3)

            if is_today or is_selected:
                style.border_style = f"1px solid {base_color_hex}"
            if is_today:
                style.font_size = 17
        else:
            style.text_color = palette['GREY_COLOR']
            if is_user_event:
                style.text_color = self._get_rgba_string(palette['ACCENT_COLOR'], 0.45)
                style.background_color = self._get_rgba_string(palette['ACCENT_COLOR'], 0.05)
                style.hover_background_color = self._get_rgba_string(palette['ACCENT_COLOR'], 0.10)
            elif is_holiday or is_friday:
                style.text_color = self._get_rgba_string(palette['HOLIDAY_COLOR'], 0.45)
                style.background_color = self._get_rgba_string(palette['HOLIDAY_COLOR'], 0.05)
                style.hover_background_color = self._get_rgba_string(palette['HOLIDAY_COLOR'], 0.10)

        return style

    def _get_day_style(self, jdate: jdatetime.date, is_in_month: bool) -> Tuple[str, str]:
        style = self._determine_day_style(jdate, is_in_month)

        base_style = (f"background-color: {style.background_color}; color: {style.text_color}; border: {style.border_style}; border-radius: 8px; font-size: {style.font_size}px; font-weight: bold; font-family: '{APP_CONFIG.FONT_FAMILY}';")

        stylesheet = f"QLabel {{ {base_style} }} QLabel:hover {{ background-color: {style.hover_background_color}; }}"
        return stylesheet, style.tooltip

    def _navigate(self, months: int):
        year = self.display_date.year
        month = self.display_date.month + months
        while month < 1:
                month += 12
                year -= 1
        while month > 12:
                month -= 12
                year += 1

        # Navigation stops at the app's supported year range, the same clamp
        # go-to-date and the event editor already enforce, instead of drifting
        # below year 1200 where the rest of the UI cannot follow.
        if not APP_CONFIG.SUPPORTED_MIN_YEAR <= year <= APP_CONFIG.SUPPORTED_MAX_YEAR:
            return

        day = min(self.display_date.day, days_in_jalali_month(year, month))
        self.display_date = jdatetime.date(year, month, day)
        self.fill_calendar_grid()

    def prev_month(self): self._navigate(-1)
    def next_month(self): self._navigate(1)

    def go_to_today(self):
        self.current_date = jdatetime.date.today()
        self.display_date = self.current_date
        self.selected_date = self.current_date
        self.fill_calendar_grid()

    def go_to_date(self, year, month):
        try:
            day = min(self.display_date.day, days_in_jalali_month(year, month))
            self.display_date = jdatetime.date(year, month, day)
            self.fill_calendar_grid()
        except (ValueError, TypeError):
            pass
        self.overlay_blocker.hide()

    def _on_day_clicked(self, jdate: Optional[jdatetime.date]):
        if jdate and not self.event_input_widget.isVisible():
            self.selected_date = jdate
            if jdate.month != self.display_date.month:
                self.display_date = jdate
            self.fill_calendar_grid()

    def _toggle_gregorian_format(self, _):
        self._show_gregorian_mdy = not self._show_gregorian_mdy
        self._update_header()

    def _show_go_to_date_menu(self, pos):
        menu = QMenu(self)
        palette = APP_CONFIG.get_current_palette()
        menu.setStyleSheet(f"QMenu {{ background-color: {palette['BACKGROUND_COLOR']}; border: 1px solid {palette['MENU_BORDER_COLOR']}; border-radius: 8px; padding: 5px; }}")
        go_to_action = MenuActionWidget("برو به تاریخ", menu)

        def _open_after_menu_close():
            # Close the menu first and open the popup once it has fully
            # dismissed - the same sequencing the tray menu uses, avoiding
            # focus/platform weirdness of dialogs over open menus.
            menu.close()
            QTimer.singleShot(50, self._open_go_to_date_window)

        go_to_action.triggered.connect(_open_after_menu_close)
        action = QWidgetAction(self)
        action.setDefaultWidget(go_to_action)
        menu.addAction(action)
        menu.exec(clamp_popup_to_work_area(menu, self.mapToGlobal(pos)))

    def _open_go_to_date_window(self):
        if self.go_to_window is not None and not self.go_to_window.isVisible():
            # Stale hidden instance from a previous open - discard it.
            self.go_to_window.deleteLater()
            self.go_to_window = None
        if self.go_to_window is None:
            self.overlay_blocker.setGeometry(self.rect())
            self.overlay_blocker.show()
            self.overlay_blocker.raise_()
            window = GoToDateWindow(self)
            self.go_to_window = window
            # Delete on close so the destroyed signal always tears the overlay down,
            # no matter which close path (cancel, confirm, calendar hidden) is taken.
            window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            window.date_selected.connect(self.go_to_date)
            # By the time destroyed fires, sender() is a fresh wrapper for the dying
            # object, so it can never be identity-checked against the stored window.
            # Capture the window here instead: a stale instance that died after being
            # replaced still cannot clear the current one.
            window.destroyed.connect(
                lambda *_, dying=window: self._on_go_to_window_destroyed(dying)
            )
            window.cancel_button.clicked.connect(self.overlay_blocker.hide)
            parent_size = self.size()
            child_size = window.size()
            x = (parent_size.width() - child_size.width()) // 2
            y = (parent_size.height() - child_size.height()) // 2
            window.move(x, y)
            window.show()
            window.raise_()

    def _on_go_to_window_destroyed(self, window: GoToDateWindow):
        if window is not self.go_to_window:
            # A stale instance finished dying after a newer one replaced it.
            return
        self.go_to_window = None
        if self._is_being_destroyed:
            # Qt is already deleting the siblings (the overlay and the day cells), so
            # there is nothing left to hide or restyle - and touching them here would
            # raise out of a slot, which PyQt turns into a fatal abort.
            return
        self.overlay_blocker.hide()
        self.normalize_day_hover()

    def _show_event_input_for_specific(self, jdate: jdatetime.date, key: str, entry: dict):
        if not jdate or self.event_input_widget.isVisible():
            return
        self._cancel_day_tooltips()
        self.editing_date = jdate
        self._editing_event_key = key
        existing_text = entry.get("text", "")
        recurrence = entry.get("recurrence", RECURRENCE_NONE)
        remove_after_finish = entry.get("remove_after_finish", False)
        # Editing may change the recurrence, so nothing is greyed out here; the
        # widget is shared with the add path and would keep its disabled rows.
        self.event_input_widget.set_disabled_recurrences(())
        self.event_input_widget.set_data(existing_text, recurrence, remove_after_finish)
        self.overlay_blocker.resize(self.size())
        self.overlay_blocker.show()
        self.overlay_blocker.raise_()
        width = self.width() - 40
        height = 245
        x = (self.width() - width) // 2
        y = (self.height() - height) // 2 + 15
        self.event_input_widget.setGeometry(x, y, width, height)
        self.event_input_widget.show()
        self.event_input_widget.raise_()

    def _show_event_input_widget(self, jdate: jdatetime.date):
        if not jdate or self.event_input_widget.isVisible():
            return
        # This row means "add a new event". The modes already used on the date
        # are greyed out rather than silently replacing what is there, and a
        # date holding all three modes has nothing left to add - the day menu
        # drops the row, and this guard keeps the editor unreachable anyway.
        taken = recurrences_on_date(self.user_events, jdate)
        if len(taken) == len(RECURRENCE_MODES):
            return
        # The tooltip is a top-level window; without an explicit hide it can
        # keep floating above the editor overlay (right-click opens the menu
        # without ever leaving the cell, so nothing else dismisses it).
        # Pending cell timers are cancelled too: the menu close re-armed one,
        # and it would pop the holiday tooltip over this editor 500ms later.
        self._cancel_day_tooltips()
        self.editing_date = jdate
        self._editing_event_key = None
        self.event_input_widget.set_disabled_recurrences(taken)
        self.event_input_widget.set_data("", RECURRENCE_NONE, False)
        self.overlay_blocker.resize(self.size())
        self.overlay_blocker.show()
        self.overlay_blocker.raise_()
        width = self.width() - 40
        # 245px = the panel height the text box is sized for (230px) plus the
        # ~15px تکرار row.
        height = 245
        x = (self.width() - width) // 2
        y = (self.height() - height) // 2 + 15
        self.event_input_widget.setGeometry(x, y, width, height)
        self.event_input_widget.show()
        self.event_input_widget.raise_()

    def _handle_event_saved(self, text: str, recurrence: str, remove_after_finish: bool):
        # Save is disabled while the text is empty, so an empty text here is impossible;
        # event deletion goes through the context menu (_remove_event) instead.
        jdate, key = self.editing_date, self._editing_event_key
        if not jdate:
            self._hide_event_input_widget()
            return
        # An edit that would move the event onto a key another event already owns
        # is not applied: the store refuses such an overwrite, and merging two
        # events is a decision only the user can make.
        target_key = self._edited_target_key(jdate, key, recurrence)
        collision = (key is not None and target_key != key
                     and target_key in self.user_events)
        if collision:
            self._pending_merge = (key, jdate, target_key, text, recurrence,
                                   remove_after_finish)
        elif key is not None:
            self.event_updated_by_key.emit(key, jdate, text, recurrence,
                                           remove_after_finish, "")
        else:
            self.event_added.emit(jdate, text, recurrence, remove_after_finish)
        # Teardown first: hiding the editor takes the blocker down with it, so the
        # merge overlay has to be presented after, not before.
        self._hide_event_input_widget()
        if collision:
            self._present_merge_confirmation(target_key, recurrence)

    def _edited_target_key(self, jdate: jdatetime.date, key: Optional[str],
                           recurrence: str) -> Optional[str]:
        """Where an edit of ``key`` would land, mirroring the service's own rule.

        Mirrored rather than asked for because the collision has to be known
        BEFORE the store is touched: an unchanged recurrence keeps the entry's own
        key (a clamped occurrence must not walk a recurring event's anchor), and
        anything else is re-derived from the occurrence the user was shown.
        """
        if key is None or recurrence_of_key(key) == recurrence:
            return key
        return make_event_key(jdate, recurrence)

    def _present_merge_confirmation(self, target_key: str, recurrence: str):
        """Ask before folding the edited event into the one already on ``target_key``.

        A recurrence change can land an event on a key another event owns, and
        overwriting it would silently destroy that event. The ask names the
        recurrence and previews the text that would be kept, as the delete card
        splits question and event text.
        """
        self._cancel_day_tooltips()
        existing = str(self.user_events.get(target_key, {}).get("text", ""))
        preview = existing if len(existing) <= 40 else existing[:40] + "…"
        self._merge_overlay.set_message(
            f"رویدادی با تکرار {recurrence_label(recurrence)} از قبل روی این تاریخ وجود دارد؛ ادغام شود؟")
        self._merge_overlay.set_detail(preview)
        self._present_overlay(self._merge_overlay)

    def _on_merge_choice(self, text: str):
        """Apply or drop the parked merge.

        The pending request is cleared *before* anything else, exactly like the
        delete ask, so cancel and confirm share this path and the overlay can
        never be answered twice.
        """
        pending, self._pending_merge = self._pending_merge, None
        self._dismiss_active_overlay()
        self.normalize_day_hover()
        if pending is None or text != self._merge_overlay.confirm_button.text():
            return
        key, jdate, target_key, merged_text, recurrence, remove_after_finish = pending
        self.event_updated_by_key.emit(key, jdate, merged_text, recurrence,
                                       remove_after_finish, target_key)

    def _handle_event_canceled(self):
        self._hide_event_input_widget()

    def _hide_event_input_widget(self):
        self.editing_date = None
        self._editing_event_key = None
        self.event_input_widget.hide()
        self.overlay_blocker.hide()
        # Both the tooltip (top-level window) and a stale hover flag would
        # outlive the editor otherwise - the former floats above the grid,
        # the latter leaves a cell lit as if the cursor were still on it.
        self._cancel_day_tooltips()
        self.normalize_day_hover()

    def _request_remove_confirmation(self, jdate: jdatetime.date):
        """Ask before deleting; a context-menu click must never delete silently.

        Asks with the in-calendar overlay rather than a top-level dialog, so the
        question is part of the popup: it cannot be dragged away, it dims the grid
        like the editor and Go-To-Date do, and it disappears with the calendar.
        The date is parked in ``_pending_remove`` for ``_on_remove_choice`` to
        consume: an overlay answers asynchronously, unlike a modal ask that
        answered inline. Pending day-cell tooltips are cancelled because the
        tooltip is its own top-level window and would float over the overlay.
        """
        self._cancel_day_tooltips()
        matched = events_for_date(self.user_events, jdate)
        text = str(matched[1].get("text", "")) if matched else ""
        preview = text if len(text) <= 40 else text[:40] + "…"
        self._pending_remove = jdate
        # The question is the card's description line, the event text is what the
        # box is for - the same split the event manager's dialog uses. An event
        # with no text simply has no box.
        self._remove_overlay.set_message("این رویداد حذف شود؟")
        self._remove_overlay.set_detail(preview)
        self._present_overlay(self._remove_overlay)

    def _on_remove_choice(self, text: str):
        """Act on the delete overlay's answer.

        The pending date is cleared *before* anything else, so cancel and confirm
        share this path, the overlay can never be answered twice, and a
        re-entrant emit cannot see a stale date.
        """
        target, self._pending_remove = self._pending_remove, None
        target_key, self._pending_remove_key = getattr(self, '_pending_remove_key', None), None
        self._dismiss_active_overlay()
        self.normalize_day_hover()
        if target_key is not None:
            if text == self._remove_overlay.confirm_button.text():
                self.event_removed_by_key.emit(target_key)
            return
        if target is None:
            return
        if text == self._remove_overlay.confirm_button.text():
            self.event_removed.emit(target)

    def _on_distance_choice(self, text: str):
        """Dismiss the read-only distance notice.

        There is nothing to answer, so this only tears the surface down: the
        overlay already hid itself, and the dimmer is the calendar's to lower.
        Hover is re-synced for the same reason the delete path does it - the
        blocker was swallowing enter/leave for as long as it was up.
        """
        self._dismiss_active_overlay()
        self.normalize_day_hover()

    def _remove_event_by_key(self, key: str):
        if not key:
            return
        if self._active_overlay is not None:
            return
        self._pending_remove_key = key
        from utils.event_io import events_for_key
        entry = events_for_key(self.user_events, key)
        text = str(entry.get("text", "")) if entry else ""
        preview = text if len(text) <= 40 else text[:40] + "…"
        self._remove_overlay.set_message("این رویداد حذف شود؟")
        self._remove_overlay.set_detail(preview)
        self._present_overlay(self._remove_overlay)

    def _remove_event(self, jdate: jdatetime.date):
        if not jdate:
            return
        # A second request while a confirmation is up would overwrite the pending
        # date, so the first one owns the answer.
        if self._active_overlay is not None:
            return
        self._pending_remove_key = None
        self._request_remove_confirmation(jdate)

    def _show_date_distance(self, jdate: jdatetime.date):
        """Show how far the clicked day sits from today, in the popup.

        The distance is measured from ``current_date`` rather than a fresh
        ``date.today()``, so it cannot disagree with the ring the calendar drew
        around today.

        Everything lives in the card's box rather than splitting across a
        headline and a detail line: the day total leads, the breakdown follows
        only when it adds something, and the day's own date closes the box. Under
        a month the breakdown *is* the total in different words - same days, same
        direction word - so ``has_calendar_units`` suppresses it instead of
        printing one line twice. Today keeps its own literal, since there is no
        distance to state and both formatters are undefined for it.

        Pending day-cell tooltips are cancelled because the tooltip is a separate
        top-level window and would otherwise draw over this overlay.
        """
        if not jdate:
            return
        # The blocker already covers the grid, so this only guards programmatic
        # callers: a second request would orphan the pending state of whatever is
        # already up.
        if self._active_overlay is not None:
            return
        self._cancel_day_tooltips()
        distance = describe_date_distance(jdate, today=self.current_date)
        # The shared long formatter, also used by the copy menu and the converter.
        date_line = format_jalali_long(jdate)
        if distance.is_today:
            lines = ["تاریخ امروز است.", date_line]
        else:
            lines = [format_distance_total(distance)]
            if distance.has_calendar_units:
                lines.append(format_distance_breakdown(distance))
            lines.append(date_line)
        self._distance_overlay.set_detail("\n".join(lines))
        self._present_overlay(self._distance_overlay)
