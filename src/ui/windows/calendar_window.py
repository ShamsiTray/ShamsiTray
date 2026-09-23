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
from utils.date_utils import days_in_jalali_month, persian_month_name, to_persian_digits
from utils.event_io import RECURRENCE_NONE, events_for_date
from utils.ui_helpers import nav_button_stylesheet
from ui.widgets.calendar_day_cell import ClickableLabel
from ui.widgets.confirm_dialog import ConfirmDialog
from ui.widgets.go_to_date import GoToDateWindow
from ui.widgets.event_input import EventInputWidget
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
    event_added = pyqtSignal(object, str, str, bool)  # jdate, text, recurrence, remove_after_finish
    event_removed = pyqtSignal(object)

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
        self.overlay_blocker.hide()
        self._cancel_day_tooltips()
        super().hideEvent(event)

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
        # Shared builder in ui_helpers: the header buttons keep the calendar's own
        # look, but the style text lives with every other shared stylesheet so a
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

        user_event_text, _, _ = self.get_user_event_for_date(jdate)
        is_user_event = bool(user_event_text)
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
        if is_user_event:
            html_event_text = escape(user_event_text).replace('\n', '<br>')
            tooltip_parts.append(f'<span style="color:{palette["ACCENT_COLOR"]};">{html_event_text}</span>')
        # Tooltips are rendered as rich text to allow color-coded holiday and event info
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
        menu.exec(self.mapToGlobal(pos))

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

    def _show_event_input_widget(self, jdate: jdatetime.date):
        if not jdate or self.event_input_widget.isVisible():
            return
        # The tooltip is a top-level window; without an explicit hide it can
        # keep floating above the editor overlay (right-click opens the menu
        # without ever leaving the cell, so nothing else dismisses it).
        # Pending cell timers are cancelled too: the menu close re-armed one,
        # and it would pop the holiday tooltip over this editor 500ms later.
        self._cancel_day_tooltips()
        self.editing_date = jdate
        matched = events_for_date(self.user_events, jdate)
        if matched is None:
            existing_text, recurrence, remove_after_finish = "", RECURRENCE_NONE, False
        else:
            entry = matched[1]
            existing_text = entry.get("text", "")
            recurrence = entry.get("recurrence", RECURRENCE_NONE)
            remove_after_finish = entry.get("remove_after_finish", False)
        self.event_input_widget.set_data(existing_text, recurrence, remove_after_finish)
        self.overlay_blocker.resize(self.size())
        self.overlay_blocker.show()
        self.overlay_blocker.raise_()
        width = self.width() - 40
        # The original panel was 230px; the added تکرار row costs ~15px more,
        # so 245px keeps the text box at its original size.
        height = 245
        x = (self.width() - width) // 2
        y = (self.height() - height) // 2 + 15
        self.event_input_widget.setGeometry(x, y, width, height)
        self.event_input_widget.show()
        self.event_input_widget.raise_()

    def _handle_event_saved(self, text: str, recurrence: str, remove_after_finish: bool):
        # Save is disabled while the text is empty, so an empty text here is impossible;
        # event deletion goes through the context menu (_remove_event) instead.
        if self.editing_date:
            self.event_added.emit(self.editing_date, text, recurrence, remove_after_finish)
        self._hide_event_input_widget()

    def _handle_event_canceled(self):
        self._hide_event_input_widget()

    def _hide_event_input_widget(self):
        self.editing_date = None
        self.event_input_widget.hide()
        self.overlay_blocker.hide()
        # Both the tooltip (top-level window) and a stale hover flag would
        # outlive the editor otherwise - the former floats above the grid,
        # the latter leaves a cell lit as if the cursor were still on it.
        self._cancel_day_tooltips()
        self.normalize_day_hover()

    def _confirm_remove(self, jdate: jdatetime.date) -> bool:
        """Ask before deleting; a context-menu click must never delete silently.

        Uses the themed in-app dialog (the stock QMessageBox ignored the app
        palette and its long-winded wording read like a system error). The
        dialog is narrower than the default: the calendar is only 305px wide,
        and the 340px default literally overflowed the window on both sides.
        Pending day-cell tooltips are cancelled first: the dialog is a separate
        top-level window and a re-armed timer would otherwise draw the holiday
        reason over it."""
        self._cancel_day_tooltips()
        matched = events_for_date(self.user_events, jdate)
        text = str(matched[1].get("text", "")) if matched else ""
        preview = text if len(text) <= 40 else text[:40] + "…"
        return ConfirmDialog.ask(
            self, "حذف رویداد", "این رویداد حذف شود؟", detail=preview,
            confirm_text="حذف", cancel_text="انصراف", danger=True, width=280)

    def _remove_event(self, jdate: jdatetime.date):
        if not jdate:
            return
        if not self._confirm_remove(jdate):
            return
        self.event_removed.emit(jdate)