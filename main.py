import sys
import os
import json
import ctypes.wintypes
import datetime
import logging
import winreg
import time # Import time for custom logging formatter
from typing import Optional, Dict, Tuple, List

import jdatetime
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QBoxLayout, QLabel,
    QPushButton, QGridLayout, QSystemTrayIcon, QMenu, QAction,
    QWidgetAction, QMessageBox, QFrame, QSizePolicy # QSizePolicy added here
)
from PyQt5.QtCore import (
    Qt, QTimer, QEvent, pyqtSignal, QRectF, QSettings, QCoreApplication, QPoint,
    QSize, QAbstractNativeEventFilter, QUrl # Added QUrl
)
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QFont, QColor, QPainterPath, QMouseEvent, QMovie # Added QMovie

from config import (
    APP_CONFIG, to_persian_digits, persian_month_name, persian_weekday_name,
    safe_jdate, load_fonts, verify_assets, is_jalali_leap_year, QLoggingFormatter
)
from dateconverter import DateConverterWindow

# --- Logging Setup ---
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    handler = logging.StreamHandler()
    formatter = QLoggingFormatter('[%(levelname)s] %(asctime)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(APP_CONFIG.LOG_LEVEL)

# ==================== UTILITY CLASSES ====================

class ClickableLabel(QLabel):
    """
    QLabel that emits a clicked signal with a Jalali date (if set), or label_clicked if not.
    """
    clicked = pyqtSignal(jdatetime.date)
    label_clicked = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.jalali_date: Optional[jdatetime.date] = None

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            if self.jalali_date:
                self.clicked.emit(self.jalali_date)
            else:
                self.label_clicked.emit()
        super().mousePressEvent(event)

# ==================== CALENDAR WIDGET ====================

class PersianCalendarWidget(QWidget):
    """
    Main calendar widget: displays a month of Persian (Jalali) dates
    with holidays and day selection.
    """
    ROWS = 6
    COLS = 7

    def __init__(self, tray_icon_parent: 'SystemTrayIcon'):
        super().__init__()
        self.tray_icon_parent = tray_icon_parent
        self.current_date = jdatetime.date.today()
        self.display_date = self.current_date
        self.day_labels: List[List[ClickableLabel]] = []
        self.holidays_cache = self.tray_icon_parent.holidays_cache
        self.holidays = self.holidays_cache.get(self.display_date.year, {})

        self.formatted_mdy = ""
        self.formatted_month_day_year = ""
        self.show_mdy_format = True
        self.selected_date: Optional[jdatetime.date] = None

        self._init_ui()
        self._setup_layout_and_content() # This method now ensures labels are created
        self._update_labels_text() # Call _update_labels_text AFTER labels are definitely created
        self._apply_theme_styles() # Apply theme styles after UI elements are created
        self._fill_calendar_grid() # Call fill grid LAST, which no longer calls _update_labels_text

    def _init_ui(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(APP_CONFIG.CALENDAR_WIDTH, APP_CONFIG.CALENDAR_HEIGHT)
        self.setStyleSheet("QWidget { background: transparent; border: 0px solid transparent; }")

    def _apply_theme_styles(self):
        """Applies theme-specific styles to all calendar elements."""
        self.container.setStyleSheet("QFrame {background: transparent; border: 0px solid transparent;}")

        # Update navigation buttons
        self.left_arrow_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {APP_CONFIG.current_palette['TEXT_COLOR']}; border: none; "
            f"font-weight: bold; font-size: 20px; font-family: '{APP_CONFIG.FONT_FAMILY}'; }}"
            f"QPushButton:hover {{ background-color: {APP_CONFIG.current_palette['HOVER_BG']}; border-radius: 8px; }}"
            f"QPushButton:pressed {{ background: {APP_CONFIG.current_palette['HOVER_BG'].replace('0.08', '0.05').replace('0.05', '0.03')}; }}"
        )
        self.right_arrow_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {APP_CONFIG.current_palette['TEXT_COLOR']}; border: none; "
            f"font-weight: bold; font-size: 20px; font-family: '{APP_CONFIG.FONT_FAMILY}'; }}"
            f"QPushButton:hover {{ background-color: {APP_CONFIG.current_palette['HOVER_BG']}; border-radius: 8px; }}"
            f"QPushButton:pressed {{ background: {APP_CONFIG.current_palette['HOVER_BG'].replace('0.08', '0.05').replace('0.05', '0.03')}; }}"
        )
        self.today_btn.setStyleSheet(
            f"QPushButton {{ background-color: rgba(60, 179, 113, 0.8); color: {APP_CONFIG.current_palette['TEXT_COLOR']}; border: none; "
            f"font-weight: bold; font-size: 20px; font-family: '{APP_CONFIG.FONT_FAMILY}'; border-radius: 8px; }}"
            f"QPushButton:hover {{ background-color: rgba(60, 179, 113, 1.0); border-radius: 8px; }}"
            f"QPushButton:pressed {{ background: rgba(46, 139, 87, 1.0); }}"
        )

        # Update header labels
        self.year_label.setStyleSheet(
            f"QLabel {{ color: {APP_CONFIG.current_palette['TEXT_COLOR']}; font-size: {APP_CONFIG.FONT_SIZE_HEADER}px; "
            f"font-weight: bold; background: transparent; font-family: '{APP_CONFIG.FONT_FAMILY}'; }}"
        )
        self.month_label.setStyleSheet(
            f"QLabel {{ color: {APP_CONFIG.current_palette['TEXT_COLOR']}; font-size: {APP_CONFIG.FONT_SIZE_HEADER}px; "
            f"font-weight: bold; background: transparent; font-family: '{APP_CONFIG.FONT_FAMILY}'; }}"
        )

        # Update Gregorian date label
        self.gregorian_date_label.setStyleSheet(
            f"QLabel {{ color: {APP_CONFIG.current_palette['TEXT_COLOR']}; font-size: {APP_CONFIG.FONT_SIZE_LABEL}px; "
            f"background-color: {APP_CONFIG.current_palette['HOVER_BG']}; font-family: 'Inter', Arial, sans-serif; font-weight: bold; "
            f"border-radius: 8px; padding: 3px 6px; min-width: 100px; }}"
            f"QLabel:hover {{ background-color: {APP_CONFIG.current_palette['HOVER_BG'].replace('0.08', '0.15').replace('0.05', '0.08')}; border-radius: 8px; }}"
        )

        # Update weekday headers
        for i, day_name in enumerate(APP_CONFIG.PERSIAN_WEEKDAYS):
            label = self.inner_content_v_layout.itemAt(2).layout().itemAt(i).widget()
            color = APP_CONFIG.current_palette['HOLIDAY_COLOR'] if day_name == "ج" else APP_CONFIG.current_palette['GREY_COLOR']
            label.setStyleSheet(
                f"QLabel {{ color: {color}; font-weight: bold; font-size: 16px; "
                f"background: transparent; font-family: '{APP_CONFIG.FONT_FAMILY}'; }}"
            )

        self.update() # Request a repaint to apply changes

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.HighQualityAntialiasing)
        rect_f = QRectF(self.rect())
        path = QPainterPath()
        radius = APP_CONFIG.CALENDAR_BORDER_RADIUS_PX
        path.addRoundedRect(rect_f, radius, radius)
        painter.fillPath(path, QColor(APP_CONFIG.current_palette['CALENDAR_BACKGROUND_COLOR']))
        painter.setPen(QColor(APP_CONFIG.current_palette['CALENDAR_BORDER_COLOR']))
        painter.drawPath(path)
        painter.setClipPath(path)
        super().paintEvent(event)

    def _setup_layout_and_content(self):
        main_v_layout = QVBoxLayout(self)
        main_v_layout.setContentsMargins(0, 0, 0, 0)
        main_v_layout.setSpacing(0)

        self.container = QFrame(self)
        self.container.setStyleSheet("QFrame {background: transparent; border: 0px solid transparent;}")
        self.container_layout = QHBoxLayout(self.container)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(0)
        self.container_layout.addStretch(1)

        self.inner_content_v_layout = QVBoxLayout()
        self.inner_content_v_layout.setContentsMargins(15, 10, 15, 10)
        self.inner_content_v_layout.setSpacing(0)
        self.inner_content_v_layout_widget = QWidget()
        self.inner_content_v_layout_widget.setStyleSheet("QWidget {background: transparent;}")
        self.inner_content_v_layout_widget.setLayout(self.inner_content_v_layout)
        self.inner_content_v_layout_widget.setFixedWidth(APP_CONFIG.CONTENT_INNER_WIDTH + 30)
        self.container_layout.addWidget(self.inner_content_v_layout_widget)
        self.container_layout.addStretch(1)

        self._setup_navigation_bar()
        self._setup_today_gregorian()
        self._setup_weekdays_header()
        self._setup_calendar_grid()

        main_v_layout.addWidget(self.container)

    def _setup_navigation_bar(self):
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, -5)
        top_layout.setSpacing(10)
        self.left_arrow_btn = self._make_nav_button("❮", self.next_month)
        self.right_arrow_btn = self._make_nav_button("❯", self.prev_month)
        self.month_year_container = QWidget()
        self.month_year_container.setStyleSheet("QWidget {background: transparent;}")
        month_year_layout = QHBoxLayout(self.month_year_container)
        month_year_layout.setSpacing(5)
        month_year_layout.setContentsMargins(0, 0, 0, 0)
        month_year_layout.setAlignment(Qt.AlignCenter)
        self.year_label = self._make_header_label()
        self.month_label = self._make_header_label()
        month_year_layout.addWidget(self.year_label)
        month_year_layout.addWidget(self.month_label)
        top_layout.addWidget(self.left_arrow_btn)
        top_layout.addStretch(1)
        top_layout.addWidget(self.month_year_container)
        top_layout.addStretch(1)
        top_layout.addWidget(self.right_arrow_btn)
        self.inner_content_v_layout.addLayout(top_layout)

    def _setup_today_gregorian(self):
        today_gregorian_layout = QHBoxLayout()
        today_gregorian_layout.setContentsMargins(0, 0, 0, 10)
        self.gregorian_date_label = ClickableLabel("")
        self.gregorian_date_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.gregorian_date_label.setStyleSheet(
            f"QLabel {{ color: {APP_CONFIG.current_palette['TEXT_COLOR']}; font-size: {APP_CONFIG.FONT_SIZE_LABEL}px; "
            f"background-color: {APP_CONFIG.current_palette['HOVER_BG']}; font-family: 'Inter', Arial, sans-serif; font-weight: bold; "
            f"border-radius: 8px; padding: 3px 6px; min-width: 100px; }}"
            f"QLabel:hover {{ background-color: {APP_CONFIG.current_palette['HOVER_BG'].replace('0.08', '0.15').replace('0.05', '0.08')}; border-radius: 8px; }}"
        )
        self.gregorian_date_label.label_clicked.connect(self._toggle_gregorian_format)
        self.today_btn = self._make_nav_button("امروز", self.go_to_today, is_today=True)
        today_gregorian_layout.addWidget(self.gregorian_date_label)
        today_gregorian_layout.addStretch(1)
        today_gregorian_layout.addWidget(self.today_btn)
        self.inner_content_v_layout.addLayout(today_gregorian_layout)

    def _setup_weekdays_header(self):
        weekday_layout = QHBoxLayout()
        weekday_layout.setSpacing(5)
        weekday_layout.setContentsMargins(0, 0, 0, 10)
        weekday_layout.setDirection(QBoxLayout.RightToLeft)
        for day_name in APP_CONFIG.PERSIAN_WEEKDAYS:
            label = QLabel(day_name)
            label.setAlignment(Qt.AlignCenter)
            label.setFixedSize(APP_CONFIG.DAY_LABEL_SIZE, APP_CONFIG.DAY_LABEL_SIZE)
            color = APP_CONFIG.current_palette['HOLIDAY_COLOR'] if day_name == "ج" else APP_CONFIG.current_palette['GREY_COLOR']
            label.setStyleSheet(
                f"QLabel {{ color: {color}; font-weight: bold; font-size: 16px; "
                f"background: transparent; font-family: '{APP_CONFIG.FONT_FAMILY}'; }}"
            )

            weekday_layout.addWidget(label)
        self.inner_content_v_layout.addLayout(weekday_layout)

    def _make_nav_button(self, text: str, slot, is_today: bool = False) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(60, 30) if is_today else btn.setFixedSize(30, 30)
        if is_today:
            btn.setStyleSheet(
                f"QPushButton {{ background-color: rgba(60, 179, 113, 0.8); color: {APP_CONFIG.current_palette['TEXT_COLOR']}; border: none; "
                f"font-weight: bold; font-size: 20px; font-family: '{APP_CONFIG.FONT_FAMILY}'; border-radius: 8px; }}"
                f"QPushButton:hover {{ background-color: rgba(60, 179, 113, 1.0); border-radius: 8px; }}"
                f"QPushButton:pressed {{ background: rgba(46, 139, 87, 1.0); }}"
            )
        else:
            btn.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {APP_CONFIG.current_palette['TEXT_COLOR']}; border: none; "
                f"font-weight: bold; font-size: 20px; font-family: '{APP_CONFIG.FONT_FAMILY}'; }}"
                f"QPushButton:hover {{ background-color: {APP_CONFIG.current_palette['HOVER_BG']}; border-radius: 8px; }}"
                f"QPushButton:pressed {{ background: {APP_CONFIG.current_palette['HOVER_BG'].replace('0.08', '0.05').replace('0.05', '0.03')}; }}"
            )
        btn.clicked.connect(slot)
        return btn

    def _make_header_label(self) -> QLabel:
        label = QLabel("")
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        label.setStyleSheet(
            f"QLabel {{ color: {APP_CONFIG.current_palette['TEXT_COLOR']}; font-size: {APP_CONFIG.FONT_SIZE_HEADER}px; "
            f"font-weight: bold; background: transparent; font-family: '{APP_CONFIG.FONT_FAMILY}'; }}"
        )
        return label

    def _setup_calendar_grid(self):
        self.day_labels.clear()
        self.calendar_grid_layout = QGridLayout()
        self.calendar_grid_layout.setSpacing(5)
        self.calendar_grid_layout.setOriginCorner(Qt.TopRightCorner)
        self.inner_content_v_layout.addLayout(self.calendar_grid_layout)
        for row in range(self.ROWS):
            week_labels = []
            for col in range(self.COLS):
                label = ClickableLabel()
                label.setAlignment(Qt.AlignCenter)
                label.setFixedSize(APP_CONFIG.DAY_LABEL_SIZE, APP_CONFIG.DAY_LABEL_SIZE)
                self.calendar_grid_layout.addWidget(label, row, col)
                week_labels.append(label)
            self.day_labels.append(week_labels)

    def _fill_calendar_grid(self):
        """Fill the calendar grid with day numbers and update styles."""
        self._update_labels_text() # Ensures month and year labels are set
        
        today_gregorian = jdatetime.date.today().togregorian()
        self.formatted_mdy = today_gregorian.strftime("%m/%d/%Y")
        self.formatted_month_day_year = today_gregorian.strftime("%b %d, %Y")
        self.gregorian_date_label.setText(
            self.formatted_mdy if self.show_mdy_format else self.formatted_month_day_year
        )

        # Clear all day labels and disconnect signals
        for row_labels in self.day_labels:
            for label in row_labels:
                if isinstance(label, ClickableLabel):
                    try:
                        label.clicked.disconnect()
                    except TypeError:
                        pass
                label.setText("")
                label.setToolTip("")
                label.setStyleSheet("")

        self._update_current_holidays()
        
        first_day_of_month = jdatetime.date(self.display_date.year, self.display_date.month, 1)
        start_col = first_day_of_month.weekday() # 0 for Saturday

        # Fill previous month's trailing days
        prev_month_date_obj = first_day_of_month - jdatetime.timedelta(days=1)
        prev_month_year = prev_month_date_obj.year
        prev_month_num = prev_month_date_obj.month
        
        # Using the new helper function for days in month
        days_in_prev_month = self._get_jalali_month_length(prev_month_year, prev_month_num)

        for col_offset in range(start_col):
            day_to_display = days_in_prev_month - (start_col - 1 - col_offset)
            jalali_date = jdatetime.date(prev_month_year, prev_month_num, day_to_display)
            label = self.day_labels[0][col_offset]
            label.setText(to_persian_digits(str(day_to_display)))
            holidays_prev_year = self.tray_icon_parent.holidays_cache.get(jalali_date.year, {})
            is_friday = jalali_date.weekday() == 6
            is_holiday = (jalali_date.month, jalali_date.day) in holidays_prev_year
            label.setStyleSheet(self._faded_day_style(is_friday or is_holiday))
            if isinstance(label, ClickableLabel):
                label.jalali_date = None # Not clickable for prev/next month days

        # Fill current month's days
        # Using the new helper function for days in month
        days_in_current_month = self._get_jalali_month_length(self.display_date.year, self.display_date.month)
        
        current_row, current_col = 0, start_col
        for day in range(1, days_in_current_month + 1):
            if current_row >= self.ROWS:
                logger.warning(f"Calendar overflow month={self.display_date.month} year={self.display_date.year}")
                break
            
            label = self.day_labels[current_row][current_col]
            current_jdate = jdatetime.date(self.display_date.year, self.display_date.month, day)
            
            label.setText(to_persian_digits(str(day)))
            if isinstance(label, ClickableLabel):
                label.jalali_date = current_jdate
                # Disconnect any old connections before connecting new one
                try:
                    label.clicked.disconnect()
                except TypeError:
                    pass
                label.clicked.connect(self._on_day_label_clicked)
            
            is_today = (current_jdate == self.current_date)
            is_selected = (current_jdate == self.selected_date)
            is_friday = current_jdate.weekday() == 6
            holiday_reasons = self.holidays.get((current_jdate.month, current_jdate.day))
            is_holiday = bool(holiday_reasons)

            # Helper function to get rgba string
            def get_rgba_string(color_hex: str, alpha: float) -> str:
                color = QColor(color_hex)
                return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha})"

            # --- Initialize styles with defaults ---
            text_color = APP_CONFIG.current_palette['TEXT_COLOR']
            background_color_rgba = "transparent" # Start with transparent
            border_style = "none"
            font_size = APP_CONFIG.FONT_SIZE_LABEL # Default font size for all days
            hover_background_color_rgba = APP_CONFIG.current_palette['HOVER_BG'] # Start with default hover
            current_tooltip = ""

            # 0. Set tooltip if holiday
            if is_holiday:
                current_tooltip = "\n".join(holiday_reasons)

            # 1. Base style for holidays/Fridays (always red text, and an initial translucent red background)
            if is_holiday or is_friday:
                text_color = APP_CONFIG.current_palette['HOLIDAY_COLOR'] # Text is ALWAYS red for holidays/Fridays
                
                # Adjusted opacity for normal holiday/Friday background to be lighter
                background_color_rgba = get_rgba_string(APP_CONFIG.current_palette['HOLIDAY_COLOR'], 0.08) # 8% opacity
                hover_background_color_rgba = get_rgba_string(APP_CONFIG.current_palette['HOLIDAY_COLOR'], 0.15) # 15% opacity

            # 2. Apply "Today" specific styling (overrides background/border, but text_color if holiday/friday)
            if is_today:
                font_size = 17 # Today zooms in (desired behavior)
                
                if is_holiday or is_friday:
                    # If today AND holiday/friday, set a prominent red background and border
                    background_color_rgba = get_rgba_string(APP_CONFIG.current_palette['HOLIDAY_COLOR'], 0.3) # More solid red
                    hover_background_color_rgba = get_rgba_string(APP_CONFIG.current_palette['HOLIDAY_COLOR'], 0.9) # Even more solid on hover
                    border_style = f"1px solid {APP_CONFIG.current_palette['HOLIDAY_COLOR']}" # Red border
                    text_color = APP_CONFIG.current_palette['HOLIDAY_COLOR'] # Keep text color red
                else:
                    # If today but NOT holiday/friday, use the standard today colors (green/grey)
                    background_color_rgba = APP_CONFIG.current_palette['CALENDAR_TODAY_BG_COLOR']
                    hover_background_color_rgba = APP_CONFIG.current_palette['CALENDAR_TODAY_HOVER_BG_COLOR']
                    border_style = f"1px solid {APP_CONFIG.current_palette['TEXT_COLOR']}" # Border based on theme text color
                    text_color = APP_CONFIG.current_palette['TEXT_COLOR'] # Default text color

            # 3. Apply "Selected" specific styling (overrides background/border, but not text_color or font_size if already set by 'today' or 'holiday/friday')
            if is_selected:
                # Selected date does NOT zoom in, unless it's also 'today'
                if not is_today:
                    font_size = APP_CONFIG.FONT_SIZE_LABEL 

                if is_holiday or is_friday:
                    # Adjusted opacity for selected holiday/friday to be a bit lower, as requested
                    background_color_rgba = get_rgba_string(APP_CONFIG.current_palette['HOLIDAY_COLOR'], 0.3) # Lower opacity for selected holiday
                    hover_background_color_rgba = get_rgba_string(APP_CONFIG.current_palette['HOLIDAY_COLOR'], 0.5) # Lower opacity for hover
                    border_style = f"1px solid {APP_CONFIG.current_palette['HOLIDAY_COLOR']}" # Red border
                    text_color = APP_CONFIG.current_palette['HOLIDAY_COLOR'] # Keep text color red
                elif not is_today: # Only apply selected default if not holiday/friday and not today
                    # If selected but NOT holiday/friday and NOT today, use the standard selected colors (green/grey)
                    background_color_rgba = APP_CONFIG.current_palette['CALENDAR_SELECTED_BG_COLOR']
                    hover_background_color_rgba = APP_CONFIG.current_palette['CALENDAR_SELECTED_HOVER_BG_COLOR']
                    border_style = f"1px solid {APP_CONFIG.current_palette['TEXT_COLOR']}" # Border based on theme text color
                    text_color = APP_CONFIG.current_palette['TEXT_COLOR'] # Default text color
                

            style_sheet = (
                f"QLabel {{ background-color: {background_color_rgba}; color: {text_color}; "
                f"border: {border_style}; border-radius: 8px; font-size: {font_size}px; "
                f"font-weight: bold; font-family: '{APP_CONFIG.FONT_FAMILY}'; }}"
                f"QLabel:hover {{ background-color: {hover_background_color_rgba}; border-radius: 8px; }}"
            )
            label.setToolTip(current_tooltip)
            label.setStyleSheet(style_sheet)
            current_col += 1
            if current_col > 6:
                current_col = 0
                current_row += 1
        self._current_row = current_row
        self._current_col = current_col

        # Fill next month's leading days
        next_day = 1
        for row_idx in range(self._current_row, self.ROWS):
            for col_idx in range(self._current_col if row_idx == self._current_row else 0, self.COLS):
                next_year = self.display_date.year + 1 if self.display_date.month == 12 else self.display_date.year
                next_month = 1 if self.display_date.month == 12 else self.display_date.month + 1
                jalali_date = jdatetime.date(next_year, next_month, next_day)
                label = self.day_labels[row_idx][col_idx]
                label.setText(to_persian_digits(str(next_day)))
                holidays_next_year = self.tray_icon_parent.holidays_cache.get(jalali_date.year, {})
                is_friday = jalali_date.weekday() == 6
                is_holiday = (jalali_date.month, jalali_date.day) in holidays_next_year
                label.setStyleSheet(self._faded_day_style(is_friday or is_holiday))
                if isinstance(label, ClickableLabel):
                    label.jalali_date = None
                next_day += 1

    def _update_labels_text(self):
        # Ensure these labels exist before setting text. They are created in _setup_navigation_bar.
        if hasattr(self, 'month_label') and self.month_label is not None:
            self.month_label.setText(persian_month_name(self.display_date.month))
        if hasattr(self, 'year_label') and self.year_label is not None:
            self.year_label.setText(to_persian_digits(str(self.display_date.year)))

    def _get_jalali_month_length(self, year: int, month: int) -> int:
        """Calculates the number of days in a given Jalali month manually."""
        if 1 <= month <= 6:
            return 31
        elif 7 <= month <= 11:
            return 30
        elif month == 12:
            # Use the imported is_jalali_leap_year function
            if is_jalali_leap_year(year):
                return 30
            else:
                return 29
        else:
            # This case should ideally not happen with valid month inputs (1-12)
            logger.error(f"Invalid Jalali month provided to _get_jalali_month_length: {month}")
            return 0 # Return 0 or raise an error for invalid months

    def _update_current_holidays(self):
        self.holidays = self.tray_icon_parent.holidays_cache.get(self.display_date.year, {})

    def prev_month(self):
        if self.display_date.month == 1:
            self.display_date = jdatetime.date(self.display_date.year - 1, 12, 1)
        else:
            self.display_date = jdatetime.date(self.display_date.year, self.display_date.month - 1, 1)
        self.selected_date = None
        self._fill_calendar_grid()

    def next_month(self):
        if self.display_date.month == 12:
            self.display_date = jdatetime.date(self.display_date.year + 1, 1, 1)
        else:
            self.display_date = jdatetime.date(self.display_date.year, self.display_date.month + 1, 1)
        self.selected_date = None
        self._fill_calendar_grid()

    def go_to_today(self):
        self.display_date = jdatetime.date.today()
        self.selected_date = self.display_date
        self._fill_calendar_grid()

    def _on_day_label_clicked(self, jalali_date: jdatetime.date):
        self.selected_date = jalali_date
        self._fill_calendar_grid()
        if jalali_date:
            gregorian_date = jalali_date.togregorian()
            self.formatted_mdy = gregorian_date.strftime("%m/%d/%Y")
            self.formatted_month_day_year = gregorian_date.strftime("%b %d, %Y")
            self.gregorian_date_label.setText(
                self.formatted_mdy if self.show_mdy_format else self.formatted_month_day_year
            )
        else:
            today_gregorian = jdatetime.date.today().togregorian()
            self.formatted_mdy = today_gregorian.strftime("%m/%d/%Y")
            self.formatted_month_day_year = today_gregorian.strftime("%b %d, %Y")
            self.gregorian_date_label.setText(
                self.formatted_mdy if self.show_mdy_format else self.formatted_month_day_year
            )

    def _toggle_gregorian_format(self):
        self.show_mdy_format = not self.show_mdy_format
        self.gregorian_date_label.setText(
            self.formatted_mdy if self.show_mdy_format else self.formatted_month_day_year
        )

    def _grey_style(self) -> str:
        # Helper function to get rgba string
        def get_rgba_string(color_hex: str, alpha: float) -> str:
            color = QColor(color_hex)
            return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha})"

        # Adjusted hover color for greyed-out days
        hover_bg_color_alpha = 0.1 if APP_CONFIG.get_current_palette() == APP_CONFIG.LIGHT_PALETTE else 0.08
        hover_background_color_rgba = get_rgba_string(APP_CONFIG.current_palette['GREY_COLOR'], hover_bg_color_alpha)

        return (
            f"QLabel {{ background: transparent; border: none; font-size: {APP_CONFIG.FONT_SIZE_LABEL}px; "
            f"font-weight: bold; color: {APP_CONFIG.current_palette['GREY_COLOR']}; border-radius: 8px; font-family: '{APP_CONFIG.FONT_FAMILY}'; }}"
            f"QLabel:hover {{ background-color: {hover_background_color_rgba}; border-radius: 8px; }}"
        )
    	
    def _faded_day_style(self, is_special: bool) -> str:
        """
        Style sheet for faded days from prev/next month.
        is_special == True   -> Friday or holiday → red text + more prominent faint red bg
        is_special == False  -> ordinary day      → grey text, no bg
        """
        # Helper function to get rgba string
        def get_rgba_string(color_hex: str, alpha: float) -> str:
            color = QColor(color_hex)
            return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha})"

        if is_special:
            # Increased alpha for more prominent red background
            holiday_faded_bg_rgba = get_rgba_string(APP_CONFIG.current_palette['HOLIDAY_COLOR'], 0.05) # 5% opacity
            holiday_faded_text_rgba = get_rgba_string(APP_CONFIG.current_palette['HOLIDAY_COLOR'], 0.45) # 45% opacity
            holiday_faded_hover_bg_rgba = get_rgba_string(APP_CONFIG.current_palette['HOLIDAY_COLOR'], 0.1) # 10% opacity
            
            return (
                f"QLabel {{ background-color: {holiday_faded_bg_rgba}; "
                f"color: {holiday_faded_text_rgba}; "
                f"border: none; border-radius: 8px; "
                f"font-size: {APP_CONFIG.FONT_SIZE_LABEL}px; font-weight: bold; "
                f"font-family: '{APP_CONFIG.FONT_FAMILY}'; }}"
                f"QLabel:hover {{ background-color: {holiday_faded_hover_bg_rgba}; "
                f"border-radius: 8px; }}"
            )
        else:
            return self._grey_style()
        

class TimeChangeEventFilter(QAbstractNativeEventFilter):
    def __init__(self, on_time_change_callback, on_theme_change_callback):
        super().__init__()
        self.on_time_change_callback = on_time_change_callback
        self.on_theme_change_callback = on_theme_change_callback
        self.last_theme = APP_CONFIG.get_windows_theme() # Track initial theme

    def nativeEventFilter(self, eventType, message):
        if eventType != "windows_generic_MSG":
            return False, 0

        msg_ptr = ctypes.cast(int(message), ctypes.POINTER(ctypes.wintypes.MSG))
        msg = msg_ptr.contents

        WM_TIMECHANGE = 0x001E
        WM_SETTINGCHANGE = 0x001A # Message for system setting changes

        if msg.message == WM_TIMECHANGE:
            logger.info("⏰ Windows system time changed")
            if callable(self.on_time_change_callback):
                self.on_time_change_callback()
        elif msg.message == WM_SETTINGCHANGE:
            # Check for theme change specifically by comparing with current
            current_theme = APP_CONFIG.get_windows_theme()
            if current_theme != self.last_theme:
                logger.info(f"🎨 Windows theme changed from {self.last_theme} to {current_theme}")
                self.last_theme = current_theme
                if callable(self.on_theme_change_callback):
                    # We pass the theme change to the tray icon, which will handle applying it.
                    self.on_time_change_callback(current_theme) # Changed to on_time_change_callback to force icon update and calendar refilling


        return False, 0

# ==================== SYSTEM TRAY ICON ====================

class SystemTrayIcon(QSystemTrayIcon):
    """Represents the application's system tray icon and main controller."""

    def __init__(self):
        super().__init__()
        self.calendar_widget: Optional[PersianCalendarWidget] = None
        # NOTE: converter_window is intentionally not modified in this response per user request.
        self.converter_window: Optional[DateConverterWindow] = None 
        self._is_calendar_visible = False
        self.current_date: jdatetime.date = jdatetime.date.today()
        self.holidays_cache = self._load_holidays_from_file()
        self.holidays = self.holidays_cache.get(self.current_date.year, {})

        # Pass theme change callback to event filter
        self.event_filter = TimeChangeEventFilter(self._on_system_time_changed, self._on_windows_theme_changed)
        QCoreApplication.instance().installNativeEventFilter(self.event_filter)
        self.schedule_next_midnight_check()

        QCoreApplication.setOrganizationName(APP_CONFIG.APP_NAME)
        QCoreApplication.setApplicationName(APP_CONFIG.APP_NAME)

        self.settings = QSettings()
        # Read the stored theme setting, default to Windows theme if not set
        stored_theme = self.settings.value(APP_CONFIG.CURRENT_THEME_SETTING_KEY, APP_CONFIG.get_windows_theme(), type=str)
        APP_CONFIG.set_theme(stored_theme) # Apply the stored or default theme
        logger.info(f"Initial theme loaded from settings: {stored_theme}")

        self.is_open_at_login = self.settings.value(
            APP_CONFIG.AUTO_START_SETTING_KEY, False, type=bool
        )
        # _create_tray_icon and _setup_context_menu will be called by _on_app_theme_changed
        self._on_app_theme_changed() # Apply initial theme to all UI elements based on loaded settings

        self.activated.connect(self.on_tray_icon_activated)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_tray_icon)
        self.timer.start(60000)
        self._apply_startup_setting(self.is_open_at_login)


    def _on_windows_theme_changed(self, new_windows_theme: str):
        """Called when Windows theme setting changes. Updates the application's theme."""
        logger.info(f"Windows theme changed to: {new_windows_theme}. Updating app theme.")
        self._set_app_theme(new_windows_theme)


    def _set_app_theme(self, theme: str):
        """Sets the application theme and updates settings, then applies changes."""
        # Only proceed if the theme is actually changing to avoid unnecessary updates
        current_theme_enum = APP_CONFIG.Theme.DARK if APP_CONFIG.get_current_palette() == APP_CONFIG.DARK_PALETTE else APP_CONFIG.Theme.LIGHT
        if theme == current_theme_enum:
            logger.info(f"Theme already {theme}. No change needed.")
            return

        APP_CONFIG.set_theme(theme)
        self.settings.setValue(APP_CONFIG.CURRENT_THEME_SETTING_KEY, theme) # Persist theme setting
        logger.info(f"User selected theme: {theme}. Stored setting and applying changes.")
        self._on_app_theme_changed() # Call without argument, it uses global APP_CONFIG


    def _on_app_theme_changed(self):
        """Consolidated method to apply theme changes across the application."""
        logger.info(f"Applying new theme across app: {APP_CONFIG.current_palette['BACKGROUND_COLOR']}")

        # Update application-wide stylesheet
        QApplication.instance().setStyleSheet(
            f"QToolTip {{ background-color: {APP_CONFIG.current_palette['INPUT_BG_COLOR']}; color: {APP_CONFIG.current_palette['HOLIDAY_COLOR']}; border: 1px solid {APP_CONFIG.current_palette['CALENDAR_BORDER_COLOR']}; "
            f"border-radius: 8px; padding: 5px 8px; font-size: 14px; font-weight: bold; }}"
        )
        # Force update tray icon with new colors
        self._create_tray_icon()
        # Update context menu colors - this will now set the correct checked states
        self._setup_context_menu() 

        # Update calendar widget if visible/exists
        if self.calendar_widget:
            self.calendar_widget._apply_theme_styles()
            self.calendar_widget._fill_calendar_grid() # Re-fill the grid after theme change to update day styles
            self.calendar_widget.repaint()

        # Update date converter window if open
        if self.converter_window and self.converter_window.isVisible():
            self.converter_window._set_theme_colors()


    def _load_holidays_from_file(self) -> Dict[int, Dict[Tuple[int, int], List[str]]]:
        holidays_data: Dict[int, Dict[Tuple[int, int], List[str]]] = {}
        try:
            with open(APP_CONFIG.HOLIDAYS_FILE_PATH, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
                loaded_holidays_raw = raw_data.get('holidays', {})

                for year_str, holidays_for_year_raw in loaded_holidays_raw.items():
                    year_int = int(year_str)
                    holidays_data[year_int] = {}
                    for month_day_str, descriptions in holidays_for_year_raw.items():
                        try:
                            month, day = map(int, month_day_str.split('-'))
                            date_tuple = (month, day)
                            if isinstance(descriptions, list):
                                holidays_data[year_int][date_tuple] = descriptions
                            elif isinstance(descriptions, str):
                                holidays_data[year_int][date_tuple] = [descriptions]
                            else:
                                logger.warning(f"Unexpected holiday description type for {month_day_str} in year {year_str}: {type(descriptions)}")
                        except ValueError:
                            logger.warning(f"Could not parse month-day '{month_day_str}' in year {year_str}")
            logger.info(f"Holidays loaded successfully from {APP_CONFIG.HOLIDAYS_FILE_PATH}")
        except FileNotFoundError:
            logger.error(f"Holidays file not found at: {APP_CONFIG.HOLIDAYS_FILE_PATH}")
            QMessageBox.critical(None, "خطا در بارگزاری فایل", f"فایل تعطیلات در مسیر زیر یافت نشد:\n{APP_CONFIG.HOLIDAYS_FILE_PATH}")
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Error parsing holidays file: {e}")
            QMessageBox.critical(None, "خطا در خواندن فایل", f"مشکلی در خواندن یا پردازش فایل تعطیلات پیش آمد.\n{e}")

        return holidays_data

    def _create_tray_icon(self):
        pixmap = QPixmap(36, 36)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        day_str = to_persian_digits(str(self.current_date.day))
        is_friday = self.current_date.weekday() == 6
        current_year_holidays = self.holidays_cache.get(self.current_date.year, {})
        holiday_reasons = current_year_holidays.get((self.current_date.month, self.current_date.day))
        is_holiday = bool(holiday_reasons)

        # Determine tray icon color based on current app theme and holiday/Friday status
        if is_holiday or is_friday:
            tray_icon_text_color = APP_CONFIG.current_palette['HOLIDAY_COLOR'] # Red for holidays/Fridays
        elif APP_CONFIG.get_current_palette() == APP_CONFIG.DARK_PALETTE:
            tray_icon_text_color = APP_CONFIG.TRAY_ICON_DARK_COLOR # White for dark mode app
        else: # Light mode palette
            tray_icon_text_color = APP_CONFIG.TRAY_ICON_LIGHT_COLOR # Black for light mode app

        painter.setPen(QColor(tray_icon_text_color)) # Use the determined color
        font = QFont(APP_CONFIG.FONT_FAMILY, 20, QFont.Bold)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, day_str)
        painter.end()
        self.setIcon(QIcon(pixmap))
        weekday_name = persian_weekday_name(self.current_date.weekday())
        month_name = persian_month_name(self.current_date.month)
        year_str = str(self.current_date.year)
        month_str = f"{self.current_date.month:02d}"
        day_str_2 = f"{self.current_date.day:02d}"
        month_written = f"\u200F{day_str_2} {month_name} {year_str}"
        tooltip = f"{weekday_name}\n{year_str}-{month_str}-{day_str_2}\n {month_written}"

        if is_holiday:
            tooltip += f"\nتعطیلی:\n" + "\n".join(holiday_reasons)
        self.setToolTip(tooltip)

    def update_tray_icon(self, force: bool = False):
        new_date = jdatetime.date.today()
        if force or new_date != self.current_date:
            logger.info(f"Date changed: {self.current_date} → {new_date}")
            self.current_date = new_date
            self.holidays = self.holidays_cache.get(self.current_date.year, {})
            self._create_tray_icon()
        if self.calendar_widget and self._is_calendar_visible:
            self.calendar_widget.current_date = new_date
            self.calendar_widget._fill_calendar_grid()

    def _toggle_open_at_boot(self, checked: bool):
        self.settings.setValue(APP_CONFIG.AUTO_START_SETTING_KEY, checked)
        self.is_open_at_login = checked
        self._apply_startup_setting(checked)
        logger.info(f"Open at boot set to: {checked}")

    def _setup_context_menu(self):
        menu = QMenu()
        menu.setStyleSheet(
            f"QMenu {{ background-color: {APP_CONFIG.current_palette['BACKGROUND_COLOR']}; border: 1px solid {APP_CONFIG.current_palette['MENU_BORDER_COLOR']}; border-radius: 8px; padding: 5px; }}"
            f"QMenu::item {{ background-color: transparent; padding: 0px; margin: 0px; }}"
            f"QMenu::separator {{ height: 1px; background-color: {APP_CONFIG.current_palette['MENU_BORDER_COLOR']}; margin: 5px 0px; }}"
        )

        convert_date_widget_action = QWidgetAction(self)
        convert_date_widget = MenuActionWidget("تبدیل تاریخ", parent=menu)
        convert_date_widget_action.setDefaultWidget(convert_date_widget)
        convert_date_widget_action.triggered.connect(self._open_date_converter)
        menu.addAction(convert_date_widget_action)
        menu.addSeparator()

        # Theme selection action using the new ThemeToggleActionWidget
        self.theme_toggle_widget_action = QWidgetAction(self)
        # Pass the current theme to the widget so it can display the correct icon initially
        self.theme_toggle_widget = ThemeToggleActionWidget("تم برنامه", parent=menu)
        # Connect to the 'triggered' signal of the custom widget, which now emits it
        self.theme_toggle_widget.triggered.connect(self._toggle_theme_from_menu)
        self.theme_toggle_widget_action.setDefaultWidget(self.theme_toggle_widget)
        menu.addAction(self.theme_toggle_widget_action)
        
        menu.addSeparator()

        self.open_at_boot_action = QWidgetAction(self)
        self.open_at_boot_widget = IconCheckboxActionWidget(
                "راه اندازی همراه با سیستم", self.is_open_at_login, parent=menu
        )
        self.open_at_boot_widget.toggled.connect(self._toggle_open_at_boot)
        self.open_at_boot_action.setDefaultWidget(self.open_at_boot_widget)
        if sys.platform.startswith('win'):
            menu.addAction(self.open_at_boot_action)
        menu.addSeparator()

        exit_widget_action = QWidgetAction(self)
        exit_widget = MenuActionWidget("خروج", parent=menu)
        exit_widget_action.setDefaultWidget(exit_widget)
        exit_widget_action.triggered.connect(QApplication.quit)
        menu.addAction(exit_widget_action)

        self.setContextMenu(menu)

    def _toggle_theme_from_menu(self):
        # Determine the current theme and switch to the opposite
        if APP_CONFIG.get_current_palette() == APP_CONFIG.DARK_PALETTE:
            self._set_app_theme(APP_CONFIG.Theme.LIGHT)
        else:
            self._set_app_theme(APP_CONFIG.Theme.DARK)

    def _get_executable_path(self) -> str:
        if getattr(sys, 'frozen', False):
            return sys.executable
        else:
            return os.path.abspath(sys.argv[0])

    def _apply_startup_setting(self, enable: bool):
        app_path = self._get_executable_path()
        app_name = QCoreApplication.applicationName()
        if sys.platform.startswith('win'):
            self._set_windows_startup(app_path, app_name, enable)
        else:
            logger.warning(f"Auto-start is only supported on Windows for this application. Platform: {sys.platform}")

    def _set_windows_startup(self, app_path: str, app_name: str, enable: bool):
        try:
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
            if enable:
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, f'"{app_path}"')
                logger.info(f"Added '{app_name}' to Windows startup: '{app_path}'")
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                    logger.info(f"Removed '{app_name}' from Windows startup.")
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            logger.error(f"Error setting Windows startup for '{app_name}': {e}")

    def _open_date_converter(self):
        # This function will open the DateConverterWindow if it exists or create a new one.
        if not hasattr(self, 'converter_window') or self.converter_window is None:
            self.converter_window = DateConverterWindow()
        self.converter_window.show()
        self.converter_window.activateWindow()
        self.converter_window.raise_()

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            if self._is_calendar_visible:
                self.hide_calendar()
            else:
                self.show_calendar()

    def show_calendar(self):
        if not self.calendar_widget:
            self.calendar_widget = PersianCalendarWidget(self)
        self.calendar_widget.show()
        self.position_calendar_above_tray()
        self.calendar_widget.activateWindow()
        self.calendar_widget.raise_()
        self._is_calendar_visible = True
        today_gregorian = jdatetime.date.today().togregorian()
        self.calendar_widget.formatted_mdy = today_gregorian.strftime("%m/%d/%Y")
        self.calendar_widget.formatted_month_day_year = today_gregorian.strftime("%b %d, %Y")
        # FIX: Changed self.calendar_date_label to self.calendar_widget.gregorian_date_label
        self.calendar_widget.gregorian_date_label.setText(
            self.calendar_widget.formatted_mdy if self.calendar_widget.show_mdy_format else self.calendar_widget.formatted_month_day_year
        )
        self.calendar_widget.current_date = jdatetime.date.today()
        # Re-fill grid for accurate display (this will now get the labels correctly updated via __init__)
        self.calendar_widget._fill_calendar_grid() 
        self.calendar_widget._apply_theme_styles() # Apply theme styles to ensure correct colors

    def hide_calendar(self):
        if self.calendar_widget:
            self.calendar_widget.hide()
            self._is_calendar_visible = False

    def position_calendar_above_tray(self):
        screen = QApplication.primaryScreen().availableGeometry()
        tray_geometry = self.geometry()
        widget_width = self.calendar_widget.width()
        widget_height = self.calendar_widget.height()
        if tray_geometry.isValid():
            target_x = tray_geometry.center().x() - widget_width // 2
            target_y = tray_geometry.top() - widget_height - 5
            if target_y < 0:
                target_y = tray_geometry.bottom() + 5
        else:
            target_x = screen.width() - widget_width - 20
            target_y = 20
        target_x = max(0, min(target_x, screen.width() - widget_width))
        target_y = max(0, min(target_y, screen.height() - widget_height))
        self.calendar_widget.move(target_x, target_y)

    def _on_system_time_changed(self):
        self.update_tray_icon(force=True)
        self.schedule_next_midnight_check()

    def schedule_next_midnight_check(self):
        now = datetime.datetime.now()
        tomorrow = now + datetime.timedelta(days=1)
        midnight = datetime.datetime(tomorrow.year, tomorrow.month, tomorrow.day)
        millis_until_midnight = int((midnight - now).total_seconds() * 1000)
        QTimer.singleShot(millis_until_midnight + 500, self._on_midnight)

    def _on_midnight(self):
        self.update_tray_icon()
        self.schedule_next_midnight_check()

# ==================== CUSTOM MENU WIDGETS ====================

class MenuActionWidget(QWidget):
    """Custom widget for menu actions with full-width hover effect."""
    # Add a signal for when the widget is clicked, to be used by QWidgetAction
    triggered = pyqtSignal()

    def __init__(self, text: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._is_hovered = False
        self.setContentsMargins(0, 0, 0, 0)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(15, 6, 15, 6)
        self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignCenter) # Center the content
        self.setMinimumHeight(30)

        self.setStyleSheet("""
            MenuActionWidget {
                background-color: transparent;
                border-radius: 6px;
            }
        """)
        self.setMouseTracking(True)
        self.label = QLabel(text)
        self.label.setStyleSheet(
            f"QLabel {{ color: {APP_CONFIG.current_palette['TEXT_COLOR']}; font-size: 14px; font-weight: bold; font-family: '{APP_CONFIG.FONT_FAMILY}'; background: transparent; }}"
        )
        self.label.setAlignment(Qt.AlignCenter)
        self.layout.addStretch()
        self.layout.addWidget(self.label)
        self.layout.addStretch()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.HighQualityAntialiasing)
        if self._is_hovered:
            rect_f = QRectF(self.rect())
            radius = 6
            path = QPainterPath()
            path.addRoundedRect(rect_f, radius, radius)
            painter.fillPath(path, QColor(60, 60, 60, 180))
        super().paintEvent(event)


    def enterEvent(self, event):
        self._is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.triggered.emit() # Emit the triggered signal
            event.accept()
        super().mousePressEvent(event)


class IconCheckboxActionWidget(QWidget):
    """A context menu checkbox using FontAwesome icons."""
    toggled = pyqtSignal(bool)

    def __init__(self, text: str, is_checked: bool = False, parent: Optional[QWidget] = None,
                 checked_icon: str = APP_CONFIG.FAS.FA_SQUARE_CHECK_SOLID,
                 unchecked_icon: str = APP_CONFIG.FAS.FA_SQUARE_REGULAR):
        super().__init__(parent)
        self.is_checked = is_checked
        self.checked_icon = checked_icon
        self.unchecked_icon = unchecked_icon
        self.setAttribute(Qt.WA_Hover)
        self.setMouseTracking(True)
        self._hovered = False
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_NoMousePropagation)
        # Crucial: Tell Qt that this widget manages its own background painting
        self.setAttribute(Qt.WA_StyledBackground, False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(8)

        self.icon_label = QLabel()
        self.icon_label.setFont(QFont(APP_CONFIG.FONT_AWESOME_FAMILY, 14))
        self.icon_label.setFixedWidth(22)

        self.text_label = QLabel(text)
        self.text_label.setStyleSheet(
            f"color: {APP_CONFIG.current_palette['TEXT_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 14px; font-weight: bold; background: transparent;"
        )

        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label)
        layout.addStretch()

        self.setStyleSheet("background-color: transparent; border-radius: 6px;")
        self._update_icon()

    def _update_icon(self):
        if self.is_checked:
            icon_to_set = self.checked_icon
            color = APP_CONFIG.CHECKBOX_CHECKED_COLOR
        else:
            icon_to_set = self.unchecked_icon
            color = APP_CONFIG.current_palette['GREY_COLOR'] 
        self.icon_label.setText(icon_to_set)
        self.icon_label.setStyleSheet(f"color: {color}; background: transparent;")

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.HighQualityAntialiasing)
        if self._hovered:
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()), 6, 6)
            painter.fillPath(path, QColor(60, 60, 60, 180))
        super().paintEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            event.accept()
            self.is_checked = not self.is_checked
            self._update_icon()
            self.toggled.emit(self.is_checked)
        else:
            super().mousePressEvent(event)

    def setChecked(self, checked: bool):
        # Only update if the state is actually changing to avoid unnecessary redraws
        if self.is_checked != checked:
            self.is_checked = checked
            self._update_icon()

    def isChecked(self) -> bool:
        return self.is_checked

class ThemeToggleActionWidget(MenuActionWidget):
    """Custom widget for the 'App Theme' toggle in the context menu."""
    # Add the 'toggled' signal here, similar to IconCheckboxActionWidget
    toggled = pyqtSignal()

    def __init__(self, text: str, parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        # Remove the stretches added by MenuActionWidget and re-add them around the content
        # to ensure the content is centered.
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # If there's a nested layout, dispose of its widgets too
                nested_layout = item.layout()
                while nested_layout.count():
                    nested_layout.takeAt(0).widget().deleteLater()
                nested_layout.deleteLater()
            del item

        self.icon_label = QLabel()
        self.icon_label.setFont(QFont(APP_CONFIG.FONT_AWESOME_FAMILY, 14))
        self.icon_label.setFixedWidth(22) # Ensure consistent width for icon

        self.label = QLabel(text) # Re-create or reuse the label from MenuActionWidget
        self.label.setStyleSheet(
            f"QLabel {{ color: {APP_CONFIG.current_palette['TEXT_COLOR']}; font-size: 14px; font-weight: bold; font-family: '{APP_CONFIG.FONT_FAMILY}'; background: transparent; }}"
        )
        self.label.setAlignment(Qt.AlignCenter) # Ensure the text within the label is centered

        self.layout.addStretch()
        self.layout.addWidget(self.icon_label)
        self.layout.addSpacing(8) # Space between icon and text
        self.layout.addWidget(self.label)
        self.layout.addStretch()

        self._update_icon_and_color()

    def _update_icon_and_color(self):
        if APP_CONFIG.get_current_palette() == APP_CONFIG.DARK_PALETTE:
            icon = APP_CONFIG.FAS.FA_SUN_SOLID
        else:
            icon = APP_CONFIG.FAS.FA_MOON_SOLID
        
        # Match the text color of the icon to the current theme's text color
        color = APP_CONFIG.current_palette['TEXT_COLOR'] 
        
        self.icon_label.setText(icon)
        self.icon_label.setStyleSheet(f"color: {color}; background: transparent;")
        # Also update the text label's color in case theme changed
        self.label.setStyleSheet(
            f"QLabel {{ color: {APP_CONFIG.current_palette['TEXT_COLOR']}; font-size: 14px; font-weight: bold; font-family: '{APP_CONFIG.FONT_FAMILY}'; background: transparent; }}"
        )

    def paintEvent(self, event):
        # Ensure icon and text color are updated right before painting,
        # in case theme changed but no mouse event triggered _update_icon_and_color
        self._update_icon_and_color()
        super().paintEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            # Emit the 'toggled' signal (or 'triggered' if that's what's expected by QWidgetAction)
            self.toggled.emit() # Emit the toggled signal
            event.accept()
        super().mousePressEvent(event) # Call super to handle base class hover/visuals

# ==================== TUTORIAL WINDOW ====================

class TutorialWindow(QWidget):
    """
    A window to display a first-time tutorial for dragging the tray icon.
    This window will only appear once per installation.
    """
    tutorial_closed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("TutorialWindow") # Set object name for specific stylesheet targeting
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(500, 400) # Adjust size as needed for GIF and content
        self._drag_position: Optional[QPoint] = None

        self._setup_ui()
        self._apply_theme_styles() # Apply theme styles after UI is set up

        if sys.platform == "win32":
            # Add minimize/exit buttons to the window's system menu for better UX
            import win32api, win32con, win32gui
            hwnd = self.winId().__int__()
            current_style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
            new_style = current_style | win32con.WS_MINIMIZEBOX | win32con.WS_SYSMENU
            win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, new_style)
            win32gui.SetWindowPos(
                hwnd, None, 0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOZORDER | win32con.SWP_FRAMECHANGED
            )

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # Top section: Title and Close Button
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        # Tutorial Message
        tutorial_message_label = QLabel(
            "برای دسترسی آسان، می‌توانید آیکون برنامه را از بخش آیکون‌های پنهان ویندوز، به نوار وظیفه اصلی بکشید."
        )
        tutorial_message_label.setFont(QFont(APP_CONFIG.FONT_FAMILY, 12))
        tutorial_message_label.setWordWrap(True)
        tutorial_message_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(tutorial_message_label)

        # GIF Display
        self.gif_label = QLabel()
        self.gif_label.setAlignment(Qt.AlignCenter)
        self.gif_label.setFixedSize(300, 200) # Adjust size as needed
        gif_path = str(APP_CONFIG.TUTORIAL_GIF_PATH)

        if os.path.exists(gif_path):
            self.movie = QMovie(gif_path)
            if self.movie.isValid():
                self.movie.setCacheMode(QMovie.CacheAll)
                self.movie.setSpeed(100) # 100% speed
                
                # Check if setLoopCount exists, otherwise connect finished to start
                if hasattr(self.movie, 'setLoopCount'):
                    self.movie.setLoopCount(-1) # Play GIF on repeat indefinitely
                else:
                    # Fallback for older PyQt5 versions: loop manually
                    self.movie.finished.connect(self.movie.start)
                    logger.warning("QMovie.setLoopCount not found, falling back to connecting finished to start.")
                
                self.gif_label.setMovie(self.movie)
                self.movie.start()
            else:
                logger.warning(f"Failed to load GIF from {gif_path}. QMovie is invalid.")
                self.gif_label.setText("GIF بارگذاری نشد.")
                self.gif_label.setFont(QFont(APP_CONFIG.FONT_FAMILY, 16))
        else:
            logger.error(f"Tutorial GIF file not found: {gif_path}")
            self.gif_label.setText("فایل GIF آموزشی پیدا نشد.")
            self.gif_label.setFont(QFont(APP_CONFIG.FONT_FAMILY, 16))

        main_layout.addWidget(self.gif_label, alignment=Qt.AlignCenter)

        main_layout.addStretch(1) # Push content to top

        # Bottom Close Button
        self.close_button_bottom = QPushButton("بستن آموزش")
        self.close_button_bottom.setFixedHeight(50)
        self.close_button_bottom.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.close_button_bottom.clicked.connect(self._close_tutorial)
        main_layout.addWidget(self.close_button_bottom)

    def _apply_theme_styles(self):
        # Apply styles to self (window background and border)
        self.setStyleSheet(self._build_stylesheet())

        # Apply styles to labels
        for label in [self.findChild(QLabel, "") for ql in self.findChildren(QLabel) if ql is not self.gif_label]:
            # Filter for valid QLabel instances and exclude the gif_label
            if isinstance(label, QLabel) and label != self.gif_label:
                # Set color to TEXT_COLOR
                label.setStyleSheet(f"color: {APP_CONFIG.current_palette['TEXT_COLOR']}; background: transparent;")

        # Apply styles to buttons
        self.close_button_bottom.setStyleSheet(
            f"QPushButton {{ background-color: {APP_CONFIG.current_palette['ACCENT_COLOR']}; color: {APP_CONFIG.current_palette['TEXT_COLOR']}; "
            f"border: none; border-radius: 8px; padding: 8px 15px; font-size: 16px; "
            f"font-weight: bold; font-family: '{APP_CONFIG.FONT_FAMILY}'; }}"
            f"QPushButton:hover {{ background-color: {QColor(APP_CONFIG.current_palette['ACCENT_COLOR']).darker(120).name()}; }}"
            f"QPushButton:pressed {{ background-color: {QColor(APP_CONFIG.current_palette['ACCENT_COLOR']).darker(150).name()}; }}"
        )
        self.repaint() # Ensure repaint after applying styles

    def _build_stylesheet(self) -> str:
        radius = APP_CONFIG.CALENDAR_BORDER_RADIUS_PX
        return (
            f"QWidget#TutorialWindow {{ "
            f"    background-color: {APP_CONFIG.current_palette['BACKGROUND_COLOR']}; "
            f"    border: 1px solid {APP_CONFIG.current_palette['CALENDAR_BORDER_COLOR']}; "
            f"    border-radius: {radius}px; "
            f"}}"
        )
    
    def _close_tutorial(self):
        logger.debug("Tutorial close button clicked.")
        # Stop the GIF movie when the window is closed to save resources
        if hasattr(self, 'movie') and self.movie.isValid():
            self.movie.stop()
        self.tutorial_closed.emit()
        self.close()
        logger.debug("Tutorial window closed.")

    def paintEvent(self, event):
        # Custom paint event to draw the rounded background and border
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.HighQualityAntialiasing)
        rect = self.rect()
        path = QPainterPath()
        radius = APP_CONFIG.CALENDAR_BORDER_RADIUS_PX # Use same radius as calendar for consistency
        path.addRoundedRect(rect.x() + 1, rect.y() + 1, rect.width() - 2, rect.height() - 2, radius, radius)
        painter.fillPath(path, QColor(APP_CONFIG.current_palette['BACKGROUND_COLOR']))
        painter.setPen(QColor(APP_CONFIG.current_palette['CALENDAR_BORDER_COLOR']))
        painter.drawPath(path)

    # Allow dragging the window
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.pos()
            # Only allow dragging from the top bar area, excluding buttons
            if pos.y() < 60:
                self._drag_position = event.globalPos() - self.frameGeometry().topLeft()
                event.accept()
            else:
                event.ignore()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_position is not None:
            new_pos = event.globalPos() - self._drag_position
            screen_geometry = QApplication.desktop().availableGeometry(self)
            min_x = screen_geometry.left()
            max_x = screen_geometry.right() - self.width()
            min_y = screen_geometry.top()
            max_y = screen_geometry.bottom() - 50
            clamped_x = max(min_x, min(new_pos.x(), max_x))
            clamped_y = max(min_y, min(new_pos.y(), max_y))
            self.move(clamped_x, clamped_y)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_position = None
        QApplication.processEvents()
        event.accept()

# ==================== MAIN APP ENTRY ====================

# Global variable to hold the tray icon instance so it's accessible after tutorial closes
_global_tray_icon_instance: Optional['SystemTrayIcon'] = None

def start_main_app():
    """Initializes and shows the SystemTrayIcon."""
    global _global_tray_icon_instance
    if _global_tray_icon_instance is None: # Ensure it's only created once
        _global_tray_icon_instance = SystemTrayIcon()
        _global_tray_icon_instance.show()
        logger.info("SystemTrayIcon application started.")
    else:
        logger.info("SystemTrayIcon application already running.")


def main():
    """Main function to run the ShamsiTray application."""
    if not verify_assets():
        QMessageBox.critical(None, "خطا در فایل‌های برنامه", "برخی از فایل‌های موردنیاز برنامه (مانند فونت، آیکون، یا فایل تعطیلات) وجود ندارند. لطفاً نصب را بررسی کنید.")
        sys.exit(1)

    myappid = 'Rayden.ShamsiTray.TrayApp.1.0'
    if sys.platform == 'win32':
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False) 
    
    if os.path.exists(APP_CONFIG.ICON_PATH):
        app.setWindowIcon(QIcon(str(APP_CONFIG.ICON_PATH)))
    else:
        logger.warning(f"Application icon file not found: {APP_CONFIG.ICON_PATH}")
        app.setWindowIcon(QIcon.fromTheme("applications-other"))
    
    load_fonts()

    # Get settings instance
    settings = QSettings()
    has_shown_tutorial = settings.value(APP_CONFIG.TUTORIAL_SHOWN_SETTING_KEY, False, type=bool)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        logger.critical("System tray not available. Exiting application.")
        sys.exit(1)

    # Always start the main app first, so the tray icon is available
    start_main_app()

    if not has_shown_tutorial:
        logger.info("Showing tutorial for the first time.")
        tutorial_window = TutorialWindow()
        tutorial_window.setAttribute(Qt.WA_DeleteOnClose) # Ensure proper cleanup
        # No need to connect tutorial_closed to start_main_app, as it's already started
        tutorial_window.show()
        # Set the tutorial shown flag
        settings.setValue(APP_CONFIG.TUTORIAL_SHOWN_SETTING_KEY, True)
        
        # Center the tutorial window on screen
        screen_geo = QApplication.desktop().screenGeometry()
        x = (screen_geo.width() - tutorial_window.width()) // 2
        y = (screen_geo.height() - tutorial_window.height()) // 2
        tutorial_window.move(x, y)

    else:
        logger.info("Tutorial already shown. Main app started directly.")
        # Main app is already started by start_main_app() call before this block

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()