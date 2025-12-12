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
from typing import Dict, List, Optional, Tuple

import jdatetime
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (QBoxLayout, QGridLayout, QHBoxLayout, QLabel,
                             QPushButton, QWidgetAction, QVBoxLayout, QWidget, QMenu)

from config import APP_CONFIG
from utils.date_helpers import (is_jalali_leap_year, persian_month_name,
                                   to_persian_digits)
from ui.widgets.clickable_label import ClickableLabel
from ui.widgets.dialogs import GoToDateWindow
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
    event_added = pyqtSignal(object, str, bool, bool)
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
        
        self.day_labels: List[List[ClickableLabel]] = []
        self._show_gregorian_mdy = True
        
        self._setup_ui()
        self.update_styles()
        self.fill_calendar_grid()

    def hideEvent(self, event):
        """Override hideEvent to also close the 'Go To Date' window."""
        if self.go_to_window and self.go_to_window.isVisible():
            self.go_to_window.close()
        super().hideEvent(event)

    def set_user_events(self, user_events: dict):
        self.user_events = user_events
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
        month_year_layout.setAlignment(Qt.AlignCenter)
        month_year_layout.addWidget(self.year_label)
        month_year_layout.addWidget(self.month_label)
        
        month_year_container = QWidget()
        month_year_container.setLayout(month_year_layout)
        month_year_container.setContextMenuPolicy(Qt.CustomContextMenu)
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
        layout.setDirection(QBoxLayout.RightToLeft)
        for day_name in APP_CONFIG.PERSIAN_WEEKDAYS_SHORT:
            label = QLabel(day_name)
            label.setObjectName("WeekdayLabel")
            label.setAlignment(Qt.AlignCenter)
            label.setFixedSize(APP_CONFIG.DAY_LABEL_SIZE, APP_CONFIG.DAY_LABEL_SIZE)
            layout.addWidget(label)
        return layout

    def _create_calendar_grid(self):
        grid_layout = QGridLayout()
        grid_layout.setSpacing(5)
        grid_layout.setOriginCorner(Qt.TopRightCorner)
        for row in range(self.ROWS):
            week_labels = []
            for col in range(self.COLS):
                label = ClickableLabel()
                label.setAlignment(Qt.AlignCenter)
                label.setFixedSize(APP_CONFIG.DAY_LABEL_SIZE, APP_CONFIG.DAY_LABEL_SIZE)
                label.clicked.connect(self._on_day_clicked)
                label.add_event_requested.connect(self._show_event_input_widget)
                label.remove_event_requested.connect(self._remove_event)
                grid_layout.addWidget(label, row, col)
                week_labels.append(label)
            self.day_labels.append(week_labels)
        return grid_layout
    
    def _get_nav_button_style(self, bg_color: str, is_today_button: bool = False) -> str:
        palette = APP_CONFIG.get_current_palette()
        text_color = palette['TEXT_COLOR']
        if is_today_button:
            base_color = QColor(bg_color)
            hover_color = base_color.lighter(120).name()
            pressed_color = base_color.darker(120).name()
            return (f"QPushButton {{ background-color: {base_color.name()}; color: white; border: none; border-radius: 8px; }}"
                    f"QPushButton:hover {{ background-color: {hover_color}; }}"
                    f"QPushButton:pressed {{ background-color: {pressed_color}; }}")
        else:
            hover_color = QColor(bg_color).darker(120).name() if bg_color != "transparent" else palette['HOVER_BG']
            return (f"QPushButton {{ background-color: {bg_color}; color: {text_color}; border: none; border-radius: 8px; }}"
                    f"QPushButton:hover {{ background-color: {hover_color}; }}")

    def update_styles(self):
        palette = APP_CONFIG.get_current_palette()
        text_color, accent_color = palette['TEXT_COLOR'], palette['ACCENT_COLOR']
        nav_button_font = QFont(APP_CONFIG.FONT_FAMILY, 12, QFont.Bold)
        today_button_font = QFont(APP_CONFIG.FONT_FAMILY, 12, QFont.Bold)
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
        
        if self.event_input_widget: self.event_input_widget.update_styles()
        if self.go_to_window: self.go_to_window.update_styles()
        self.fill_calendar_grid()

    def _get_user_event_for_date(self, jdate: jdatetime.date) -> Tuple[Optional[str], bool, bool]:
        """Checks for a specific or yearly event, returning the text, if it was yearly, and if it's set to be removed after finishing."""
        specific_key = jdate.strftime("%Y-%m-%d")
        if specific_key in self.user_events:
            event_data = self.user_events[specific_key]
            return event_data.get("text"), event_data.get("yearly", False), event_data.get("remove_after_finish", False)

        yearly_key = jdate.strftime("0000-%m-%d")
        if yearly_key in self.user_events:
            event_data = self.user_events[yearly_key]
            return event_data.get("text"), True, event_data.get("remove_after_finish", False)
            
        return None, False, False

    def fill_calendar_grid(self):
        self._update_header()
        first_day = self.display_date.replace(day=1)
        start_day_of_week = first_day.weekday()

        current_day = first_day - datetime.timedelta(days=start_day_of_week)
        for row in range(self.ROWS):
            for col in range(self.COLS):
                label = self.day_labels[row][col]
                label.jalali_date = current_day
                label.setText(to_persian_digits(current_day.day))
                
                user_event_text, _, _ = self._get_user_event_for_date(current_day)
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
        palette = APP_CONFIG.get_current_palette()
        style = DayStyle(text_color=palette['TEXT_COLOR'], hover_background_color=palette['HOVER_BG'])

        user_event_text, _, _ = self._get_user_event_for_date(jdate)
        is_user_event = bool(user_event_text)
        is_today = (jdate == self.current_date)
        is_selected = (jdate == self.selected_date)
        is_friday = jdate.weekday() == 6
        
        year_holidays = self.holidays_cache.get(jdate.year, {})
        holiday_reasons = year_holidays.get((jdate.month, jdate.day))
        is_holiday = bool(holiday_reasons)
        is_special_day = is_user_event or is_holiday or is_friday

        # Build tooltip
        tooltip_parts = []
        if holiday_reasons:
            html_reasons = "<br>".join(escape(r) for r in holiday_reasons)
            tooltip_parts.append(f'<span style="white-space: nowrap; color:{palette["HOLIDAY_COLOR"]};">{html_reasons}</span>')
        if is_user_event:
            html_event_text = escape(user_event_text).replace('\n', '<br>')
            tooltip_parts.append(f'<span style="color:{palette["ACCENT_COLOR"]};">{html_event_text}</span>')
        if tooltip_parts:
            style.tooltip = f"<qt>{'<br>'.join(tooltip_parts)}</qt>"

        # Determine colors and styles
        base_color_hex = palette['TEXT_COLOR']
        if is_in_month:
            if is_user_event: base_color_hex = palette['ACCENT_COLOR']
            elif is_holiday or is_friday: base_color_hex = palette['HOLIDAY_COLOR']
            style.text_color = base_color_hex

            if is_today and is_selected:
                alpha = 0.6 if is_special_day else 0.35
                style.background_color = self._get_rgba_string(base_color_hex, alpha)
                style.hover_background_color = self._get_rgba_string(base_color_hex, alpha + 0.1)
            elif is_selected:
                if is_special_day:
                    style.background_color = self._get_rgba_string(base_color_hex, 0.45)
                    style.hover_background_color = self._get_rgba_string(base_color_hex, 0.55)
                else: # BUG FIX: Use direct palette values for normal selected days
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

            if is_today or is_selected: style.border_style = f"1px solid {base_color_hex}"
            if is_today: style.font_size = 17
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
        
        base_style = (f"background-color: {style.background_color}; color: {style.text_color}; border: {style.border_style}; "
                      f"border-radius: 8px; font-size: {style.font_size}px; font-weight: bold; font-family: '{APP_CONFIG.FONT_FAMILY}';")
        
        stylesheet = f"QLabel {{ {base_style} }} QLabel:hover {{ background-color: {style.hover_background_color}; }}"
        return stylesheet, style.tooltip

    def _navigate(self, months: int):
        new_year, new_month = self.display_date.year, self.display_date.month + months
        while new_month < 1: new_month += 12; new_year -= 1
        while new_month > 12: new_month -= 12; new_year += 1
        try:
            self.display_date = jdatetime.date(new_year, new_month, self.display_date.day)
        except ValueError:
            last_day = 31 if 1 <= new_month <= 6 else (30 if 7 <= new_month <= 11 else (30 if is_jalali_leap_year(new_year) else 29))
            self.display_date = jdatetime.date(new_year, new_month, last_day)
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
            day = min(self.display_date.day, 29)
            self.display_date = jdatetime.date(year, month, day)
            self.fill_calendar_grid()
        except (ValueError, TypeError):
            try:
                self.display_date = jdatetime.date(year, month, 1)
                self.fill_calendar_grid()
            except (ValueError, TypeError):
                pass

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
        go_to_action.triggered.connect(self._open_go_to_date_window)
        action = QWidgetAction(self)
        action.setDefaultWidget(go_to_action)
        menu.addAction(action)
        menu.exec_(self.mapToGlobal(pos))
    
    def _open_go_to_date_window(self):
        if self.go_to_window is None or not self.go_to_window.isVisible():
            self.go_to_window = GoToDateWindow(self)
            self.go_to_window.date_selected.connect(self.go_to_date)
            parent_pos = self.pos()
            parent_size = self.size()
            child_size = self.go_to_window.size()
            x = parent_pos.x() + (parent_size.width() - child_size.width()) // 2
            y = parent_pos.y() + (parent_size.height() - child_size.height()) // 2
            self.go_to_window.move(x, y)
            self.go_to_window.show()

    def _show_event_input_widget(self, jdate: jdatetime.date):
        if not jdate: return
        self.editing_date = jdate
        existing_text, is_yearly, remove_after_finish = self._get_user_event_for_date(jdate)
        self.event_input_widget.set_data(existing_text or "", is_yearly, remove_after_finish)
        width = self.width() - 40; height = 220
        x = (self.width() - width) // 2; y = (self.height() - height) // 2
        self.event_input_widget.setGeometry(x, y, width, height)
        self.event_input_widget.show()
        self.event_input_widget.raise_()

    def _handle_event_saved(self, text: str, is_yearly: bool, remove_after_finish: bool):
        if self.editing_date:
            if text: 
                self.event_added.emit(self.editing_date, text, is_yearly, remove_after_finish)
            else: 
                self.event_removed.emit(self.editing_date)
        self._hide_event_input_widget()

    def _handle_event_canceled(self):
        self._hide_event_input_widget()

    def _hide_event_input_widget(self):
        self.editing_date = None
        self.event_input_widget.hide()

    def _remove_event(self, jdate: jdatetime.date):
        if not jdate: return
        self.event_removed.emit(jdate)

