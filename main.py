import sys
import os
import json
import ctypes.wintypes
import datetime
import logging
import winreg
from typing import Optional, Dict, Tuple, List

import jdatetime
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QBoxLayout, QLabel,
    QPushButton, QGridLayout, QSystemTrayIcon, QMenu, QFrame, QAction,
    QWidgetAction, QMessageBox
)
from PyQt5.QtCore import (
    Qt, QTimer, QEvent, pyqtSignal, QRectF, QSettings, QCoreApplication, QPoint,
    QSize, QAbstractNativeEventFilter
)
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QFont, QColor, QPainterPath, QMouseEvent

from config import (
    Config, to_persian_digits, persian_month_name, persian_weekday_name,
    safe_jdate, load_fonts, verify_assets
)
from dateconverter import DateConverterWindow

logger = logging.getLogger(__name__)
logger.setLevel(Config.LOG_LEVEL)

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
        self._setup_layout_and_content()
        self._fill_calendar_grid()

    def _init_ui(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(Config.CALENDAR_WIDTH, Config.CALENDAR_HEIGHT)
        self.setStyleSheet("QWidget { background: transparent; border: 0px solid transparent; }")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.HighQualityAntialiasing)
        rect_f = QRectF(self.rect())
        path = QPainterPath()
        radius = Config.CALENDAR_BORDER_RADIUS_PX
        path.addRoundedRect(rect_f, radius, radius)
        painter.fillPath(path, QColor(Config.CALENDAR_BACKGROUND_COLOR))
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
        self.inner_content_v_layout_widget.setFixedWidth(Config.CONTENT_INNER_WIDTH + 30)
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
            f"QLabel {{ color: {Config.TEXT_COLOR}; font-size: {Config.FONT_SIZE_LABEL}px; "
            f"background-color: {Config.HOVER_BG}; font-family: 'Inter', Arial, sans-serif; font-weight: bold; "
            f"border-radius: 8px; padding: 3px 6px; min-width: 100px; }}"
            f"QLabel:hover {{ background-color: rgba(255, 255, 255, 0.15); border-radius: 8px; }}"
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
        for day_name in Config.PERSIAN_WEEKDAYS:
            label = QLabel(day_name)
            label.setAlignment(Qt.AlignCenter)
            label.setFixedSize(Config.DAY_LABEL_SIZE, Config.DAY_LABEL_SIZE)
            color = Config.HOLIDAY_COLOR if day_name == "ج" else "#b8b8b8"
            label.setStyleSheet(
                f"QLabel {{ color: {color}; font-weight: bold; font-size: 16px; "
                f"background: transparent; font-family: '{Config.FONT_FAMILY}'; }}"
            )
            weekday_layout.addWidget(label)
        self.inner_content_v_layout.addLayout(weekday_layout)

    def _make_nav_button(self, text: str, slot, is_today: bool = False) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(60, 30) if is_today else btn.setFixedSize(30, 30)
        if is_today:
            btn.setStyleSheet(
                f"QPushButton {{ background-color: rgba(60, 179, 113, 0.8); color: {Config.TEXT_COLOR}; border: none; "
                f"font-weight: bold; font-size: 20px; font-family: '{Config.FONT_FAMILY}'; border-radius: 8px; }}"
                f"QPushButton:hover {{ background-color: rgba(60, 179, 113, 1.0); border-radius: 8px; }}"
                f"QPushButton:pressed {{ background: rgba(46, 139, 87, 1.0); }}"
            )
        else:
            btn.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {Config.TEXT_COLOR}; border: none; "
                f"font-weight: bold; font-size: 20px; font-family: '{Config.FONT_FAMILY}'; }}"
                f"QPushButton:hover {{ background-color: {Config.HOVER_BG}; border-radius: 8px; }}"
                f"QPushButton:pressed {{ background: rgba(255, 255, 255, 0.05); }}"
            )
        btn.clicked.connect(slot)
        return btn

    def _make_header_label(self) -> QLabel:
        label = QLabel("")
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        label.setStyleSheet(
            f"QLabel {{ color: {Config.TEXT_COLOR}; font-size: {Config.FONT_SIZE_HEADER}px; "
            f"font-weight: bold; background: transparent; font-family: '{Config.FONT_FAMILY}'; }}"
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
                label.setFixedSize(Config.DAY_LABEL_SIZE, Config.DAY_LABEL_SIZE)
                self.calendar_grid_layout.addWidget(label, row, col)
                week_labels.append(label)
            self.day_labels.append(week_labels)

    def _fill_calendar_grid(self):
        """Fill the calendar grid with day numbers and update styles."""
        self._update_labels_text()
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
        self._fill_grid_prev_month()
        self._fill_grid_current_month()
        self._fill_grid_next_month()

    def _update_labels_text(self):
        self.month_label.setText(persian_month_name(self.display_date.month))
        self.year_label.setText(to_persian_digits(str(self.display_date.year)))

    def _update_current_holidays(self):
        self.holidays = self.tray_icon_parent.holidays_cache.get(self.display_date.year, {})

    def _fill_grid_prev_month(self):
        first_day = jdatetime.date(self.display_date.year, self.display_date.month, 1)
        start_col = first_day.weekday()
        prev_month_year = self.display_date.year - 1 if self.display_date.month == 1 else self.display_date.year
        prev_month_num = 12 if self.display_date.month == 1 else self.display_date.month - 1
        days_in_prev_month = max(
            d for d in (31, 30, 29) if safe_jdate(prev_month_year, prev_month_num, d)
        )
        for col_offset in range(start_col):
            day_to_display = days_in_prev_month - (start_col - 1 - col_offset)
            jalali_date = jdatetime.date(prev_month_year, prev_month_num, day_to_display)
            label = self.day_labels[0][col_offset]
            label.setText(to_persian_digits(str(day_to_display)))
            holidays_prev_year = self.tray_icon_parent.holidays_cache.get(jalali_date.year, {})
            is_friday = jalali_date.weekday() == 6
            is_holiday = (jalali_date.month, jalali_date.day) in holidays_prev_year
            label.setStyleSheet(self._faded_day_style(is_friday or is_holiday))
            label.setStyleSheet(self._grey_style())
            if isinstance(label, ClickableLabel):
                label.jalali_date = None

    def _fill_grid_current_month(self):
        first_day = jdatetime.date(self.display_date.year, self.display_date.month, 1)
        start_col = first_day.weekday()
        days_in_month = max(
            d for d in (31, 30, 29) if safe_jdate(self.display_date.year, self.display_date.month, d)
        )
        current_row, current_col = 0, start_col
        day = 1
        while day <= days_in_month:
            if current_row >= self.ROWS:
                logger.warning(f"Calendar overflow month={self.display_date.month} year={self.display_date.year}")
                break
            label = self.day_labels[current_row][current_col]
            current_jdate = jdatetime.date(self.display_date.year, self.display_date.month, day)
            label.setText(to_persian_digits(str(day)))
            if isinstance(label, ClickableLabel):
                label.jalali_date = current_jdate
                label.clicked.connect(self._on_day_label_clicked)
            actual_weekday = (first_day.weekday() + day - 1) % 7
            is_today = (
                day == self.current_date.day and
                self.display_date.month == self.current_date.month and
                self.display_date.year == self.current_date.year
            )
            is_friday = actual_weekday == 6
            holiday_reasons = self.holidays.get((self.display_date.month, day))
            is_holiday = bool(holiday_reasons)
            is_selected = (current_jdate == self.selected_date)

            style_background_color = "transparent"
            style_text_color = Config.TEXT_COLOR
            style_border = "none"
            style_font_size = Config.FONT_SIZE_LABEL
            style_hover_background_color = Config.HOVER_BG
            current_tooltip = ""

            if is_holiday or is_friday:
                style_text_color = Config.HOLIDAY_COLOR
                style_background_color = "rgba(255, 76, 76, 0.15)"
                style_hover_background_color = "rgba(255, 76, 76, 0.3)"
                if is_holiday:
                    current_tooltip = "\n".join(holiday_reasons)

            if is_today:
                style_font_size = 17
                if not (is_holiday or is_friday):
                    style_background_color = "rgba(128, 128, 128, 0.3)"
                    style_border = "1px solid #FFFFFF"
                else:
                    style_border = f"1px solid {Config.HOLIDAY_COLOR}"
                if is_holiday:
                    tooltip_prefix = "تعطیلی:\n" if holiday_reasons else ""
                    current_tooltip = tooltip_prefix + "\n".join(holiday_reasons)

            if is_selected:
                if is_today:
                    style_font_size = 17
                    if is_holiday or is_friday:
                        style_background_color = "rgba(255, 76, 76, 0.6)"
                        style_border = f"1px solid {Config.HOLIDAY_COLOR}"
                        style_hover_background_color = "rgba(255, 76, 76, 0.8)"
                    else:
                        style_background_color = "rgba(128, 128, 128, 0.5)"
                        style_border = "1px solid #FFFFFF"
                        style_hover_background_color = "rgba(128, 128, 128, 0.7)"
                elif is_holiday or is_friday:
                    style_background_color = "rgba(255, 76, 76, 0.5)"
                    style_text_color = Config.HOLIDAY_COLOR
                    style_border = f"1px solid {Config.HOLIDAY_COLOR}"
                    style_hover_background_color = "rgba(255, 76, 76, 0.7)"
                else:
                    style_background_color = "rgba(128, 128, 128, 0.4)"
                    style_text_color = Config.TEXT_COLOR
                    style_border = f"1px solid {Config.TEXT_COLOR}"
                    style_hover_background_color = "rgba(128, 128, 128, 0.6)"

            style_sheet = (
                f"QLabel {{ background-color: {style_background_color}; color: {style_text_color}; "
                f"border: {style_border}; border-radius: 8px; font-size: {style_font_size}px; "
                f"font-weight: bold; font-family: '{Config.FONT_FAMILY}'; }}"
                f"QLabel:hover {{ background-color: {style_hover_background_color}; border-radius: 8px; }}"
            )
            label.setToolTip(current_tooltip)
            label.setStyleSheet(style_sheet)
            day += 1
            current_col += 1
            if current_col > 6:
                current_col = 0
                current_row += 1
        self._current_row = current_row
        self._current_col = current_col

    def _fill_grid_next_month(self):
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
        return (
            f"QLabel {{ background: transparent; border: none; font-size: {Config.FONT_SIZE_LABEL}px; "
            f"font-weight: bold; color: {Config.GREY_COLOR}; border-radius: 8px; font-family: '{Config.FONT_FAMILY}'; }}"
            f"QLabel:hover {{ background-color: rgba(128, 128, 128, 0.1); border-radius: 8px; }}"
        )
    	
    def _faded_day_style(self, is_special: bool) -> str:
        """
        Style sheet for faded days from prev/next month.
        is_special == True   -> Friday or holiday → red text + faint red bg
        is_special == False  -> ordinary day      → grey text, no bg
        """
        if is_special:
            return (
                f"QLabel {{ background-color: rgba(255, 76, 76, 0.05); "
                f"color: rgba(255, 76, 76, 0.45); "
                f"border: none; border-radius: 8px; "
                f"font-size: {Config.FONT_SIZE_LABEL}px; font-weight: bold; "
                f"font-family: '{Config.FONT_FAMILY}'; }}"
                f"QLabel:hover {{ background-color: rgba(255, 76, 76, 0.10); "
                f"border-radius: 8px; }}"
            )
        else:
            return self._grey_style()
        

class TimeChangeEventFilter(QAbstractNativeEventFilter):
    def __init__(self, on_time_change_callback):
        super().__init__()
        self.on_time_change_callback = on_time_change_callback

    def nativeEventFilter(self, eventType, message):
        if eventType != "windows_generic_MSG":
            return False, 0

        msg_ptr = ctypes.cast(int(message), ctypes.POINTER(ctypes.wintypes.MSG))
        msg = msg_ptr.contents

        WM_TIMECHANGE = 0x001E

        if msg.message == WM_TIMECHANGE:
            logger.info("⏰ Windows system time changed")
            if callable(self.on_time_change_callback):
                self.on_time_change_callback()

        return False, 0

# ==================== SYSTEM TRAY ICON ====================

class SystemTrayIcon(QSystemTrayIcon):
    """Represents the application's system tray icon and main controller."""

    def __init__(self):
        super().__init__()
        self.calendar_widget: Optional[PersianCalendarWidget] = None
        self._is_calendar_visible = False
        self.current_date: jdatetime.date = jdatetime.date.today()
        self.holidays_cache = self._load_holidays_from_file()
        self.holidays = self.holidays_cache.get(self.current_date.year, {})
        self.event_filter = TimeChangeEventFilter(self._on_system_time_changed)
        QCoreApplication.instance().installNativeEventFilter(self.event_filter)
        self.schedule_next_midnight_check()

        QCoreApplication.setOrganizationName(Config.APP_NAME)
        QCoreApplication.setApplicationName(Config.APP_NAME)

        self.settings = QSettings()
        self.is_open_at_login = self.settings.value(
            Config.AUTO_START_SETTING_KEY, False, type=bool
        )
        self._create_tray_icon()
        self._setup_context_menu()
        self.activated.connect(self.on_tray_icon_activated)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_tray_icon)
        self.timer.start(60000)
        self._apply_startup_setting(self.is_open_at_login)

    def _load_holidays_from_file(self) -> Dict[int, Dict[Tuple[int, int], List[str]]]:
        holidays_data: Dict[int, Dict[Tuple[int, int], List[str]]] = {}
        try:
            with open(Config.HOLIDAYS_FILE_PATH, 'r', encoding='utf-8') as f:
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
            logger.info(f"Holidays loaded successfully from {Config.HOLIDAYS_FILE_PATH}")
        except FileNotFoundError:
            logger.error(f"Holidays file not found at: {Config.HOLIDAYS_FILE_PATH}")
            QMessageBox.critical(None, "خطا در بارگزاری فایل", f"فایل تعطیلات در مسیر زیر یافت نشد:\n{Config.HOLIDAYS_FILE_PATH}")
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

        painter.setPen(QColor(Config.HOLIDAY_COLOR) if is_holiday or is_friday else QColor(255, 255, 255))
        font = QFont(Config.FONT_FAMILY, 20, QFont.Bold)
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
        self.settings.setValue(Config.AUTO_START_SETTING_KEY, checked)
        self.is_open_at_login = checked
        self._apply_startup_setting(checked)
        logger.info(f"Open at boot set to: {checked}")

    def _setup_context_menu(self):
        menu = QMenu()
        menu.setStyleSheet(
            f"QMenu {{ background-color: #2c2c2c; border: 1px solid #606060; border-radius: 8px; padding: 5px; }}"
            f"QMenu::item {{ background-color: transparent; padding: 0px; margin: 0px; }}"
            f"QMenu::item:hover {{ background-color: transparent; }}"
            f"QMenu::item:selected {{ background-color: transparent; }}"
            f"QMenu::separator {{ height: 1px; background-color: #606060; margin: 5px 0px; }}"
        )

        convert_date_widget_action = QWidgetAction(self)
        convert_date_widget = MenuActionWidget("تبدیل تاریخ", parent=menu, hover_color="rgba(255,255,255,0.08)")
        convert_date_widget_action.setDefaultWidget(convert_date_widget)
        convert_date_widget_action.triggered.connect(self._open_date_converter)
        menu.addAction(convert_date_widget_action)
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
        exit_widget = MenuActionWidget("خروج", parent=menu, hover_color="rgba(255,76,76,0.15)")
        exit_widget_action.setDefaultWidget(exit_widget)
        exit_widget_action.triggered.connect(QApplication.quit)
        menu.addAction(exit_widget_action)

        self.setContextMenu(menu)

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
        if not hasattr(self, 'converter_window'):
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
        self.calendar_widget.gregorian_date_label.setText(
            self.calendar_widget.formatted_mdy if self.calendar_widget.show_mdy_format else self.calendar_widget.formatted_month_day_year
        )
        self.calendar_widget.current_date = jdatetime.date.today()
        self.calendar_widget._fill_calendar_grid()

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
    def __init__(self, text: str, parent: Optional[QWidget] = None, hover_color: str = "rgba(255,255,255,0.1)"):
        super().__init__(parent)
        self._hover_color = hover_color
        self._is_hovered = False
        self.setContentsMargins(0, 0, 0, 0)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(15, 6, 15, 6)
        self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(30)

        self.setStyleSheet("""
            MenuActionWidget {
                background-color: transparent;
                border-radius: 6px;
            }
            MenuActionWidget:hover {
                background-color: rgba(255, 255, 255, 0.08);
            }
        """)
        self.setMouseTracking(True)
        self.label = QLabel(text)
        self.label.setStyleSheet(
            f"QLabel {{ color: {Config.TEXT_COLOR}; font-size: 14px; font-weight: bold; font-family: '{Config.FONT_FAMILY}'; background: transparent; }}"
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
            event.accept()
        super().mousePressEvent(event)

class IconCheckboxActionWidget(QWidget):
    """A context menu checkbox using FontAwesome icons."""
    toggled = pyqtSignal(bool)

    def __init__(self, text: str, is_checked: bool = False, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.is_checked = is_checked
        self.setAttribute(Qt.WA_Hover)
        self.setMouseTracking(True)
        self._hovered = False
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_NoMousePropagation)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(8)

        self.icon_label = QLabel()
        self.icon_label.setFont(QFont(Config.FONT_AWESOME_FAMILY, 14))
        self.icon_label.setFixedWidth(22)

        self.text_label = QLabel(text)
        self.text_label.setStyleSheet(
            f"color: {Config.TEXT_COLOR}; font-family: '{Config.FONT_FAMILY}'; font-size: 14px; font-weight: bold;"
        )

        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label)
        layout.addStretch()

        self.setStyleSheet("background-color: transparent; border-radius: 6px;")
        self._update_icon()

    def _update_icon(self):
        if self.is_checked:
            icon = Config.FAS.FA_SQUARE_CHECK_SOLID
            color = Config.CHECKBOX_CHECKED_COLOR
        else:
            icon = Config.FAS.FA_SQUARE_REGULAR
            color = "#606060"
        self.icon_label.setText(icon)
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
        super().paintEvent(event)
        if self._hovered:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.HighQualityAntialiasing)
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()), 6, 6)
            painter.fillPath(path, QColor(255, 255, 255, 20))

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            event.accept()
            self.is_checked = not self.is_checked
            self._update_icon()
            self.toggled.emit(self.is_checked)
        else:
            super().mousePressEvent(event)

    def setChecked(self, checked: bool):
        self.is_checked = checked
        self._update_icon()

    def isChecked(self) -> bool:
        return self.is_checked

# ==================== MAIN APP ENTRY ====================

def main():
    """Main function to run the ShamsiTray application."""
    import logging
    logging.basicConfig(level=logging.INFO)
    if not verify_assets():
        QMessageBox.critical(None, "خطا در فایل‌های برنامه", "برخی از فایل‌های موردنیاز برنامه (مانند فونت، آیکون، یا فایل تعطیلات) وجود ندارند. لطفاً نصب را بررسی کنید.")
        sys.exit(1)
    myappid = 'Rayden.ShamsiTray.TrayApp.1.0'
    if sys.platform == 'win32':
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv)
    if os.path.exists(Config.ICON_PATH):
        app.setWindowIcon(QIcon(str(Config.ICON_PATH)))
    else:
        logger.warning(f"Application icon file not found: {Config.ICON_PATH}")
        app.setWindowIcon(QIcon.fromTheme("applications-other"))
    load_fonts()
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(
        f"QToolTip {{ background-color: #3a3a3a; color: {Config.HOLIDAY_COLOR}; border: 1px solid #606060; "
        f"border-radius: 8px; padding: 5px 8px; font-size: 14px; font-weight: bold; }}"
    )
    if not QSystemTrayIcon.isSystemTrayAvailable():
        logger.critical("System tray not available. Exiting application.")
        sys.exit(1)
    tray_icon = SystemTrayIcon()
    tray_icon.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()