import sys
import os
import json
import ctypes.wintypes
import datetime
import logging
import winreg
import time
from typing import Optional, Dict, Tuple, List

import jdatetime
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QBoxLayout, QLabel,
    QPushButton, QGridLayout, QSystemTrayIcon, QMenu, QAction,
    QWidgetAction, QMessageBox, QFrame, QSizePolicy
)
from PyQt5.QtCore import (
    Qt, QTimer, QEvent, pyqtSignal, QRectF, QSettings, QCoreApplication, QPoint,
    QSize, QAbstractNativeEventFilter
)
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QFont, QColor, QPainterPath, QMouseEvent, QMovie

from config import (
    APP_CONFIG, to_persian_digits, persian_month_name, persian_weekday_name,
    safe_jdate, load_fonts, verify_assets, is_jalali_leap_year, QLoggingFormatter,
    is_gregorian_leap_year
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

class MenuActionWidget(QWidget):
    """Custom widget for menu actions with full-width hover effect."""
    triggered = pyqtSignal()

    def __init__(self, text: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._is_hovered = False
        self.setContentsMargins(0, 0, 0, 0)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(15, 6, 15, 6)
        self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(30)

        self.setStyleSheet("background-color: transparent; border-radius: 6px;")
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
            painter.fillPath(path, QColor(*APP_CONFIG.current_palette["MENU_HOVER_COLOR"]))
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
            self.triggered.emit()
            event.accept()
        super().mousePressEvent(event)


class IconCheckboxActionWidget(QWidget):
    """A context menu checkbox using FontAwesome icons."""
    toggled = pyqtSignal(bool)

    # Moved _update_icon definition here, before __init__
    def _update_icon(self):
        """Updates the icon displayed based on the checked state."""
        icon = self.checked_icon if self.is_checked else self.unchecked_icon
        # The color is always the current text color from the palette
        color = APP_CONFIG.current_palette['TEXT_COLOR']
        
        # Ensure icon_label is initialized before use (it is, in __init__)
        self.icon_label.setText(icon)
        self.icon_label.setStyleSheet(f"color: {color}; background: transparent;")

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
        self.setAttribute(Qt.WA_StyledBackground, False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(8)

        self.icon_label = QLabel() # This is initialized here, before _update_icon is called
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
        self._update_icon() # Call to update the initial icon based on is_checked

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
            painter.fillPath(path, QColor(*APP_CONFIG.current_palette["MENU_HOVER_COLOR"]))
        super().paintEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            event.accept()
            self.is_checked = not self.is_checked
            self._update_icon() # Call to update icon on click
            self.toggled.emit(self.is_checked)
        else:
            super().mousePressEvent(event)

    def setChecked(self, checked: bool):
        if self.is_checked != checked:
            self.is_checked = checked
            self._update_icon() # Call to update icon when programmatically set

    def isChecked(self) -> bool:
        return self.is_checked

class ThemeToggleActionWidget(MenuActionWidget):
    """Custom widget for the 'App Theme' toggle in the context menu."""
    triggered = pyqtSignal()

    _theme_icon_map = {
        APP_CONFIG.Theme.DARK: APP_CONFIG.FAS.FA_MOON_SOLID,
        APP_CONFIG.Theme.LIGHT: APP_CONFIG.FAS.FA_SUN_SOLID,
    }
    _theme_text_map = {
        APP_CONFIG.Theme.DARK: "تم برنامه: تیره",
        APP_CONFIG.Theme.LIGHT: "تم برنامه: روشن",
    }

    def __init__(self, current_theme_getter, parent: Optional[QWidget] = None):
        super().__init__("", parent)
        self.current_theme_getter = current_theme_getter
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            del item

        self.icon_label = QLabel()
        self.icon_label.setFont(QFont(APP_CONFIG.FONT_AWESOME_FAMILY, 14))
        self.icon_label.setFixedWidth(22)

        self.label = QLabel("")
        self.label.setStyleSheet(
            f"QLabel {{ color: {APP_CONFIG.current_palette['TEXT_COLOR']}; font-size: 14px; font-weight: bold; font-family: '{APP_CONFIG.FONT_FAMILY}'; background: transparent; }}"
        )
        self.label.setAlignment(Qt.AlignCenter)

        self.layout.addStretch()
        self.layout.addWidget(self.icon_label)
        self.layout.addSpacing(8)
        self.layout.addWidget(self.label)
        self.layout.addStretch()

        self._update_display()

    def _update_display(self):
        """Updates the icon and text based on the current theme choice."""
        current_choice = self.current_theme_getter()
        icon = self._theme_icon_map.get(current_choice)
        text = self._theme_text_map.get(current_choice, "تم برنامه: نامشخص")
        
        color = APP_CONFIG.current_palette['TEXT_COLOR'] 
        
        self.icon_label.setText(icon)
        self.icon_label.setStyleSheet(f"color: {color}; background: transparent;")
        self.label.setText(text)
        self.label.setStyleSheet(
            f"QLabel {{ color: {APP_CONFIG.current_palette['TEXT_COLOR']}; font-size: 14px; font-weight: bold; font-family: '{APP_CONFIG.FONT_FAMILY}'; background: transparent; }}"
        )
        self.update()

    def paintEvent(self, event):
        self._update_display()
        super().paintEvent(event)

class TimeChangeEventFilter(QAbstractNativeEventFilter):
    """
    Native event filter to detect system time changes (WM_TIMECHANGE).
    """
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
            logger.info("⏰ Windows system time changed (WM_TIMECHANGE).")
            if callable(self.on_time_change_callback):
                self.on_time_change_callback()

        return False, 0

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
        self.display_date = self.current_date # This will be set by SystemTrayIcon.show_calendar
        self.day_labels: List[List[ClickableLabel]] = []
        # Ensure holidays_cache is accessible via tray_icon_parent
        self.holidays_cache = self.tray_icon_parent.holidays_cache 
        self.holidays: Dict[Tuple[int, int], List[str]] = {}

        self.formatted_mdy = ""
        self.formatted_month_day_year = ""
        self.show_mdy_format = True
        self.selected_date: Optional[jdatetime.date] = None # This will be set by SystemTrayIcon.show_calendar

        self._init_ui()
        self._setup_layout_and_content()
        self._apply_theme_styles()
        self._fill_calendar_grid() # Initial fill, will be re-filled by show_calendar

    def _init_ui(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(APP_CONFIG.CALENDAR_WIDTH, APP_CONFIG.CALENDAR_HEIGHT)
        self.setStyleSheet("QWidget { background: transparent; border: 0px solid transparent; }")

    def _apply_theme_styles(self):
        """Applies theme-specific styles to all calendar elements."""
        self.container.setStyleSheet("QFrame {background: transparent; border: 0px solid transparent;}")

        def get_button_style(bg_color: str, hover_darker: int = 120, pressed_darker: int = 150) -> str:
            hover_color = QColor(bg_color).darker(hover_darker).name() if bg_color != "transparent" else APP_CONFIG.current_palette['HOVER_BG']
            pressed_color = QColor(bg_color).darker(pressed_darker).name() if bg_color != "transparent" else APP_CONFIG.current_palette['HOVER_BG'].replace('0.08', '0.03')

            return (
                f"QPushButton {{ background-color: {bg_color}; color: {APP_CONFIG.current_palette['TEXT_COLOR']}; border: none; "
                f"font-weight: bold; font-size: 20px; font-family: '{APP_CONFIG.FONT_FAMILY}'; border-radius: 8px; }}"
                f"QPushButton:hover {{ background-color: {hover_color}; border-radius: 8px; }}"
                f"QPushButton:pressed {{ background-color: {pressed_color}; }}"
            )
        
        self.left_arrow_btn.setStyleSheet(get_button_style("transparent", hover_darker=100, pressed_darker=100))
        self.right_arrow_btn.setStyleSheet(get_button_style("transparent", hover_darker=100, pressed_darker=100))
        self.today_btn.setStyleSheet(get_button_style(APP_CONFIG.current_palette['ACCENT_COLOR'], hover_darker=90, pressed_darker=120))


        header_label_style = (
            f"QLabel {{ color: {APP_CONFIG.current_palette['TEXT_COLOR']}; font-size: {APP_CONFIG.FONT_SIZE_HEADER}px; "
            f"font-weight: bold; background: transparent; font-family: '{APP_CONFIG.FONT_FAMILY}'; }}"
        )
        self.year_label.setStyleSheet(header_label_style)
        self.month_label.setStyleSheet(header_label_style)

        self.gregorian_date_label.setStyleSheet(
            f"QLabel {{ color: {APP_CONFIG.current_palette['TEXT_COLOR']}; font-size: {APP_CONFIG.FONT_SIZE_LABEL}px; "
            f"background-color: {APP_CONFIG.current_palette['HOVER_BG']}; font-family: 'Inter', Arial, sans-serif; font-weight: bold; "
            f"border-radius: 8px; padding: 3px 6px; min-width: 100px; }}"
            f"QLabel:hover {{ background-color: {APP_CONFIG.current_palette['GREGORIAN_DATE_HOVER_BG']}; border-radius: 8px; }}"
        )

        for i, day_name in enumerate(APP_CONFIG.PERSIAN_WEEKDAYS):
            label = self.inner_content_v_layout.itemAt(2).layout().itemAt(i).widget()
            color = APP_CONFIG.current_palette['HOLIDAY_COLOR'] if day_name == "ج" else APP_CONFIG.current_palette['WEEKDAY_NAMES_COLOR']
            label.setStyleSheet(
                f"QLabel {{ color: {color}; font-weight: bold; font-size: 16px; "
                f"background: transparent; font-family: '{APP_CONFIG.FONT_FAMILY}'; }}"
            )

        self._fill_calendar_grid() 
        self.update()

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
        self.left_arrow_btn = self._create_nav_button("❮", self.next_month)
        self.right_arrow_btn = self._create_nav_button("❯", self.prev_month)
        self.month_year_container = QWidget()
        self.month_year_container.setStyleSheet("QWidget {background: transparent;}")
        month_year_layout = QHBoxLayout(self.month_year_container)
        month_year_layout.setSpacing(5)
        month_year_layout.setContentsMargins(0, 0, 0, 0)
        month_year_layout.setAlignment(Qt.AlignCenter)
        self.year_label = self._create_header_label()
        self.month_label = self._create_header_label()
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
        self.gregorian_date_label.label_clicked.connect(self._toggle_gregorian_format)
        self.today_btn = self._create_nav_button("امروز", self.go_to_today, is_today=True)
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
            weekday_layout.addWidget(label)
        self.inner_content_v_layout.addLayout(weekday_layout)

    def _create_nav_button(self, text: str, slot, is_today: bool = False) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(60, 30) if is_today else btn.setFixedSize(30, 30)
        btn.clicked.connect(slot)
        return btn

    def _create_header_label(self) -> QLabel:
        label = QLabel("")
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
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

    def _get_rgba_string(self, color_hex: str, alpha: float) -> str:
        """Helper function to get rgba string from hex color and alpha."""
        color = QColor(color_hex)
        return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha})"

    def _get_day_label_style(self, jdate: jdatetime.date, is_faded: bool = False) -> str:
        """
        Determines the CSS style for a single day label based on its properties.
        """
        is_today = (jdate == self.current_date)
        is_selected = (jdate == self.selected_date)
        is_friday = jdate.weekday() == 6
        holiday_reasons = self.holidays.get((jdate.month, jdate.day))
        is_holiday = bool(holiday_reasons)

        text_color = APP_CONFIG.current_palette['TEXT_COLOR']
        background_color_rgba = "transparent"
        border_style = "none"
        font_size = APP_CONFIG.FONT_SIZE_LABEL
        hover_background_color_rgba = APP_CONFIG.current_palette['HOVER_BG']
        current_tooltip = ""

        if is_holiday:
            current_tooltip = "\n".join(holiday_reasons)

        if is_faded:
            text_alpha = 0.45
            bg_alpha = 0.05
            hover_bg_alpha = 0.1
            if is_holiday or is_friday:
                text_color = self._get_rgba_string(APP_CONFIG.current_palette['HOLIDAY_COLOR'], text_alpha)
                background_color_rgba = self._get_rgba_string(APP_CONFIG.current_palette['HOLIDAY_COLOR'], bg_alpha)
                hover_background_color_rgba = self._get_rgba_string(APP_CONFIG.current_palette['HOLIDAY_COLOR'], hover_bg_alpha)
            else:
                text_color = APP_CONFIG.current_palette['GREY_COLOR']
                hover_background_color_rgba = self._get_rgba_string(APP_CONFIG.current_palette['GREY_COLOR'], 0.1 if APP_CONFIG.get_current_palette() == APP_CONFIG.LIGHT_PALETTE else 0.08)
        else:
            # Priority: Today AND Selected > Holiday/Friday (and potentially selected) > Today > Selected > Default
            if is_today and is_selected:
                font_size = 17 # Keep font size for today
                if is_holiday or is_friday: # If it's a holiday/friday that is also today and selected
                    background_color_rgba = self._get_rgba_string(APP_CONFIG.current_palette['HOLIDAY_COLOR'], 0.6) # Brighter holiday selected
                    hover_background_color_rgba = self._get_rgba_string(APP_CONFIG.current_palette['HOLIDAY_COLOR'], 0.8)
                    border_style = f"1px solid {APP_CONFIG.current_palette['HOLIDAY_COLOR']}"
                else: # Today and selected, not holiday/friday
                    background_color_rgba = APP_CONFIG.current_palette['CALENDAR_TODAY_SELECTED_BG_COLOR'] # Use new brighter color
                    hover_background_color_rgba = APP_CONFIG.current_palette['CALENDAR_TODAY_HOVER_BG_COLOR'] # Keep existing hover for today
                    border_style = f"1px solid {APP_CONFIG.current_palette['TEXT_COLOR']}"

            elif is_holiday or is_friday: # Holiday or Friday (not today and selected, or just holiday/friday)
                text_color = APP_CONFIG.current_palette['HOLIDAY_COLOR']
                background_color_rgba = self._get_rgba_string(APP_CONFIG.current_palette['HOLIDAY_COLOR'], 0.15)
                hover_background_color_rgba = self._get_rgba_string(APP_CONFIG.current_palette['HOLIDAY_COLOR'], 0.3)
                if is_selected: # If it's a selected holiday/friday, but not today
                     background_color_rgba = self._get_rgba_string(APP_CONFIG.current_palette['HOLIDAY_COLOR'], 0.5)
                     hover_background_color_rgba = self._get_rgba_string(APP_CONFIG.current_palette['HOLIDAY_COLOR'], 0.7)
                     border_style = f"1px solid {APP_CONFIG.current_palette['HOLIDAY_COLOR']}"

            elif is_today: # Only today (not selected, not holiday/friday)
                font_size = 17
                background_color_rgba = APP_CONFIG.current_palette['CALENDAR_TODAY_BG_COLOR']
                hover_background_color_rgba = APP_CONFIG.current_palette['CALENDAR_TODAY_HOVER_BG_COLOR']
                border_style = f"1px solid {APP_CONFIG.current_palette['TEXT_COLOR']}"
            
            elif is_selected: # Only selected (not today, not holiday/friday)
                background_color_rgba = APP_CONFIG.current_palette['CALENDAR_SELECTED_BG_COLOR']
                hover_background_color_rgba = APP_CONFIG.current_palette['CALENDAR_SELECTED_HOVER_BG_COLOR']
                border_style = f"1px solid {APP_CONFIG.current_palette['TEXT_COLOR']}"


        style_sheet = (
            f"QLabel {{ background-color: {background_color_rgba}; color: {text_color}; "
            f"border: {border_style}; border-radius: 8px; font-size: {font_size}px; "
            f"font-weight: bold; font-family: '{APP_CONFIG.FONT_FAMILY}'; }}"
            f"QLabel:hover {{ background-color: {hover_background_color_rgba}; border-radius: 8px; }}"
        )
        return style_sheet, current_tooltip

    def _fill_calendar_grid(self):
        """Fill the calendar grid with day numbers and update styles."""
        self._update_month_year_labels()

        # The gregorian date label should reflect the selected_date, or today if none selected
        gregorian_date_for_label = (self.selected_date or jdatetime.date.today()).togregorian()
        self.formatted_mdy = gregorian_date_for_label.strftime("%m/%d/%Y")
        self.formatted_month_day_year = gregorian_date_for_label.strftime("%b %d, %Y")
        self.gregorian_date_label.setText(
            self.formatted_mdy if self.show_mdy_format else self.formatted_month_day_year
        )

        for row_labels in self.day_labels:
            for label in row_labels:
                if isinstance(label, ClickableLabel):
                    try:
                        label.clicked.disconnect()
                    except TypeError:
                        pass
                    label.jalali_date = None
                label.setText("")
                label.setToolTip("")
                label.setStyleSheet("")

        self._update_current_holidays()
        
        first_day_of_month = jdatetime.date(self.display_date.year, self.display_date.month, 1)
        start_col = first_day_of_month.weekday()

        prev_month_date_obj = first_day_of_month - jdatetime.timedelta(days=1)
        prev_month_year = prev_month_date_obj.year
        prev_month_num = prev_month_date_obj.month
        
        days_in_prev_month = self._get_jalali_month_length(prev_month_year, prev_month_num)

        for col_offset in range(start_col):
            day_to_display = days_in_prev_month - (start_col - 1 - col_offset)
            jalali_date = jdatetime.date(prev_month_year, prev_month_num, day_to_display)
            label = self.day_labels[0][col_offset]
            label.setText(to_persian_digits(str(day_to_display)))
            style_sheet, tooltip = self._get_day_label_style(jalali_date, is_faded=True)
            label.setStyleSheet(style_sheet)
            label.setToolTip(tooltip)

        days_in_current_month = self._get_jalali_month_length(self.display_date.year, self.display_date.month)
        
        current_row, current_col = 0, start_col
        for day in range(1, days_in_current_month + 1):
            if current_row >= self.ROWS:
                logger.warning(f"Calendar overflow month={self.display_date.month} year={self.display_date.year}. Max rows reached.")
                break
            
            label = self.day_labels[current_row][current_col]
            current_jdate = jdatetime.date(self.display_date.year, self.display_date.month, day)
            
            label.setText(to_persian_digits(str(day)))
            if isinstance(label, ClickableLabel):
                label.jalali_date = current_jdate
                label.clicked.connect(self._on_day_label_clicked)
            
            style_sheet, tooltip = self._get_day_label_style(current_jdate)
            label.setToolTip(tooltip)
            label.setStyleSheet(style_sheet)

            current_col += 1
            if current_col > 6:
                current_col = 0
                current_row += 1
        self._current_row = current_row
        self._current_col = current_col

        next_day = 1
        for row_idx in range(self._current_row, self.ROWS):
            for col_idx in range(self._current_col if row_idx == self._current_row else 0, self.COLS):
                next_year = self.display_date.year + 1 if self.display_date.month == 12 else self.display_date.year
                next_month = 1 if self.display_date.month == 12 else self.display_date.month + 1
                jalali_date = jdatetime.date(next_year, next_month, next_day)
                label = self.day_labels[row_idx][col_idx]
                label.setText(to_persian_digits(str(next_day)))
                style_sheet, tooltip = self._get_day_label_style(jalali_date, is_faded=True)
                label.setStyleSheet(style_sheet)
                label.setToolTip(tooltip)
                next_day += 1

    def _update_month_year_labels(self):
        """Updates the text of the month and year labels in the header."""
        self.month_label.setText(persian_month_name(self.display_date.month))
        self.year_label.setText(to_persian_digits(str(self.display_date.year)))

    def _get_jalali_month_length(self, year: int, month: int) -> int:
        """Calculates the number of days in a given Jalali month."""
        if 1 <= month <= 6:
            return 31
        elif 7 <= month <= 11:
            return 30
        elif month == 12:
            return 30 if is_jalali_leap_year(year) else 29
        else:
            logger.error(f"Invalid Jalali month provided to _get_jalali_month_length: {month}")
            return 0

    def _update_current_holidays(self):
        """Updates the holidays dictionary for the currently displayed year."""
        self.holidays = self.holidays_cache.get(self.display_date.year, {})

    def prev_month(self):
        """Navigates to the previous month."""
        try:
            self.display_date = self.display_date.replace(month=self.display_date.month - 1)
        except ValueError:
            self.display_date = jdatetime.date(self.display_date.year - 1, 12, self.display_date.day)
        if not safe_jdate(self.display_date.year, self.display_date.month, self.display_date.day):
            self.display_date = jdatetime.date(
                self.display_date.year,
                self.display_date.month,
                self._get_jalali_month_length(self.display_date.year, self.display_date.month)
            )
        self._fill_calendar_grid()

    def next_month(self):
        """Navigates to the next month."""
        try:
            self.display_date = self.display_date.replace(month=self.display_date.month + 1)
        except ValueError:
            self.display_date = jdatetime.date(self.display_date.year + 1, 1, self.display_date.day)
        if not safe_jdate(self.display_date.year, self.display_date.month, self.display_date.day):
            self.display_date = jdatetime.date(
                self.display_date.year,
                self.display_date.month,
                self._get_jalali_month_length(self.display_date.year, self.display_date.month)
            )
        self._fill_calendar_grid()

    def go_to_today(self):
        """Resets the calendar to display today's date and selects it."""
        self.display_date = jdatetime.date.today()
        self.selected_date = self.display_date
        self._fill_calendar_grid()

    def _on_day_label_clicked(self, jalali_date: jdatetime.date):
        """Handles a click on a calendar day label."""
        self.selected_date = jalali_date
        self._fill_calendar_grid()
        
        gregorian_date = jalali_date.togregorian()
        self.formatted_mdy = gregorian_date.strftime("%m/%d/%Y")
        self.formatted_month_day_year = gregorian_date.strftime("%b %d, %Y")
        
        self.gregorian_date_label.setText(
            self.formatted_mdy if self.show_mdy_format else self.formatted_month_day_year
        )

    def _toggle_gregorian_format(self):
        """Toggles the format of the Gregorian date display."""
        self.show_mdy_format = not self.show_mdy_format
        current_greg_date = (self.selected_date or self.current_date).togregorian()
        self.formatted_mdy = current_greg_date.strftime("%m/%d/%Y")
        self.formatted_month_day_year = current_greg_date.strftime("%b %d, %Y")
        
        self.gregorian_date_label.setText(
            self.formatted_mdy if self.show_mdy_format else self.formatted_month_day_year
        )

# ==================== SYSTEM TRAY ICON ====================

class SystemTrayIcon(QSystemTrayIcon):
    """Represents the application's system tray icon and main controller."""

    def __init__(self):
        super().__init__()
        # Initialize holidays_cache BEFORE calendar_widget
        self.holidays_cache = self._load_holidays_from_file() 
        # Initialize calendar_widget here, it will be shown/hidden later
        self.calendar_widget: Optional[PersianCalendarWidget] = PersianCalendarWidget(self) 
        self.converter_window: Optional[DateConverterWindow] = None 
        self.tutorial_window: Optional[TutorialWindow] = None
        self._is_calendar_visible = False
        self.current_date: jdatetime.date = jdatetime.date.today()

        self.event_filter = TimeChangeEventFilter(self._on_system_time_changed)
        QCoreApplication.instance().installNativeEventFilter(self.event_filter)
        
        QCoreApplication.setOrganizationName(APP_CONFIG.APP_NAME)
        QCoreApplication.setApplicationName(APP_CONFIG.APP_NAME)

        self.settings = QSettings()
        self.is_open_at_login = self.settings.value(
            APP_CONFIG.AUTO_START_SETTING_KEY, False, type=bool
        )
        logger.info(f"Initial 'Open at Login' setting: {self.is_open_at_login}")

        # Simplified theme handling: Read saved theme, default to Dark. No more "system".
        self.current_theme = self.settings.value(
            APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY, APP_CONFIG.Theme.DARK, type=str
        )
        self._apply_theme()

        self._apply_startup_setting(self.is_open_at_login)

        self.activated.connect(self.on_tray_icon_activated)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_tray_icon)
        self.timer.start(60000)
        self.schedule_next_midnight_check()

    def _apply_theme(self):
        """Sets the application theme based on self.current_theme and updates UI."""
        # 1. Set theme in config
        APP_CONFIG.set_theme(self.current_theme)
        logger.info(f"Theme set to: {self.current_theme}")

        # 2. Persist the choice
        self.settings.setValue(APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY, self.current_theme)

        # 3. Update all UI components
        self._on_app_theme_changed()

    def _on_app_theme_changed(self):
        """Consolidated method to apply theme changes across the application."""
        logger.debug(f"Applying new theme styles to UI components (Current APP_CONFIG palette background: {APP_CONFIG.current_palette['BACKGROUND_COLOR']}).")

        global_stylesheet = (
            f"QToolTip {{ background-color: {APP_CONFIG.current_palette['INPUT_BG_COLOR']}; "
            f"color: {APP_CONFIG.current_palette['HOLIDAY_COLOR']}; "
            f"border: 1px solid {APP_CONFIG.current_palette['CALENDAR_BORDER_COLOR']}; "
            f"border-radius: 8px; padding: 5px 8px; font-size: 14px; font-weight: bold; font-family: '{APP_CONFIG.FONT_FAMILY}';}}\n"
            
            f"QScrollBar:vertical {{ "
            f"    border: none; "
            f"    background-color: {APP_CONFIG.current_palette['SCROLLBAR_GROOVE_COLOR']}; "
            f"    width: 10px; "
            f"    margin: 0px; "
            f"    border-radius: 5px; "
            f"}}\n"
            f"QScrollBar::handle:vertical {{ "
            f"    background-color: {APP_CONFIG.current_palette['SCROLLBAR_HANDLE_COLOR']}; "
            f"    border-radius: 5px; "
            f"    min-height: 20px; "
            f"}}\n"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ "
            f"    height: 0px; "
            f"}}\n"
            f"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ "
            f"    background: none; "
            f"}}\n"
            f"QScrollBar:horizontal {{ "
            f"    border: none; "
            f"    background-color: {APP_CONFIG.current_palette['SCROLLBAR_GROOVE_COLOR']}; "
            f"    height: 10px; "
            f"    margin: 0px; "
            f"    border-radius: 5px; "
            f"}}\n"
            f"QScrollBar::handle:horizontal {{ "
            f"    background-color: {APP_CONFIG.current_palette['SCROLLBAR_HANDLE_COLOR']}; "
            f"    border-radius: 5px; "
            f"    min-width: 20px; "
            f"}}\n"
            f"QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ "
            f"    width: 0px; "
            f"}}\n"
            f"QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ "
            f"    background: none; "
            f"}}"
        )
        QApplication.instance().setStyleSheet(global_stylesheet)
        
        self._create_tray_icon()
        self._setup_context_menu()

        if self.calendar_widget:
            self.calendar_widget._apply_theme_styles()
            self.calendar_widget.repaint()

        if self.converter_window and self.converter_window.isVisible():
            self.converter_window._set_theme_colors()
            
        if self.tutorial_window and self.tutorial_window.isVisible():
            self.tutorial_window._apply_theme_styles()


    def _load_holidays_from_file(self) -> Dict[int, Dict[Tuple[int, int], List[str]]]:
        """Loads holiday data from the JSON file."""
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
        """Creates or updates the system tray icon with the current date and theme-based color."""
        pixmap = QPixmap(36, 36)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        day_str = to_persian_digits(str(self.current_date.day))
        is_friday = self.current_date.weekday() == 6
        current_year_holidays = self.holidays_cache.get(self.current_date.year, {})
        holiday_reasons = current_year_holidays.get((self.current_date.month, self.current_date.day))
        is_holiday = bool(holiday_reasons)

        if is_holiday or is_friday:
            tray_icon_text_color = APP_CONFIG.current_palette['HOLIDAY_COLOR']
        elif APP_CONFIG.get_current_palette() == APP_CONFIG.DARK_PALETTE:
            tray_icon_text_color = APP_CONFIG.TRAY_ICON_DARK_COLOR
        else:
            tray_icon_text_color = APP_CONFIG.TRAY_ICON_LIGHT_COLOR

        painter.setPen(QColor(tray_icon_text_color))
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
        
        tooltip_lines = [
            weekday_name,
            f"{year_str}-{month_str}-{day_str_2}",
            month_written
        ]

        if is_holiday:
            tooltip_lines.append("تعطیلی:")
            tooltip_lines.extend(holiday_reasons)
            
        self.setToolTip("\n".join(tooltip_lines))


    def update_tray_icon(self, force: bool = False):
        """Updates the tray icon if the date has changed or if forced."""
        new_date = jdatetime.date.today()
        if force or new_date != self.current_date:
            logger.info(f"Date changed or forced update: {self.current_date} → {new_date}")
            self.current_date = new_date
            self._create_tray_icon()
            if self.calendar_widget and self._is_calendar_visible:
                self.calendar_widget.current_date = new_date
                # No longer forcing display_date/selected_date to today here
                # The calendar will maintain its last selected date.
                self.calendar_widget._fill_calendar_grid()

    def _toggle_open_at_boot(self, checked: bool):
        """Toggles the 'Open at Boot' setting and applies it."""
        self.settings.setValue(APP_CONFIG.AUTO_START_SETTING_KEY, checked)
        self.is_open_at_login = checked
        self._apply_startup_setting(checked)
        logger.info(f"Open at boot set to: {checked}")

    def _setup_context_menu(self):
        """Sets up the system tray context menu with dynamic items."""
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

        self.theme_toggle_widget_action = QWidgetAction(self)
        self.theme_toggle_widget = ThemeToggleActionWidget(self.get_current_theme, parent=menu)
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

    def get_current_theme(self) -> str:
        """Getter method for the ThemeToggleActionWidget to know the current theme."""
        return self.current_theme

    def _toggle_theme_from_menu(self):
        """Cycles the user's preferred theme choice between Dark and Light."""
        if self.current_theme == APP_CONFIG.Theme.DARK:
            self.current_theme = APP_CONFIG.Theme.LIGHT
        else:
            self.current_theme = APP_CONFIG.Theme.DARK
        
        logger.info(f"Toggling theme to: {self.current_theme}")
        self._apply_theme()


    def _get_executable_path(self) -> str:
        """Returns the path to the current executable."""
        if getattr(sys, 'frozen', False):
            return sys.executable
        else:
            return os.path.abspath(sys.argv[0])

    def _apply_startup_setting(self, enable: bool):
        """Applies or removes the application from Windows startup."""
        app_path = self._get_executable_path()
        app_name = QCoreApplication.applicationName()
        if sys.platform.startswith('win'):
            self._set_windows_startup(app_path, app_name, enable)
        else:
            logger.warning(f"Auto-start is only supported on Windows for this application. Platform: {sys.platform}")

    def _set_windows_startup(self, app_path: str, app_name: str, enable: bool):
        """Manages Windows Registry entry for startup."""
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
                    logger.info(f"'{app_name}' not found in startup registry, nothing to delete.")
            winreg.CloseKey(key)
        except Exception as e:
            logger.error(f"Error setting Windows startup for '{app_name}': {e}")

    def _open_date_converter(self):
        """Opens or shows the DateConverterWindow."""
        if self.converter_window is None:
            self.converter_window = DateConverterWindow()
        self.converter_window.show()
        self.converter_window.activateWindow()
        self.converter_window.raise_()

    def on_tray_icon_activated(self, reason):
        """Handles clicks on the system tray icon."""
        if reason == QSystemTrayIcon.Trigger:
            if self._is_calendar_visible:
                self.hide_calendar()
            else:
                self.show_calendar()

    def show_calendar(self):
        """Shows the calendar widget."""
        # The calendar_widget is now always instantiated in __init__
        # No need for `if not self.calendar_widget:` here anymore for instantiation
        
        # If no specific date was selected before, default to today
        if self.calendar_widget.selected_date is None:
            self.calendar_widget.selected_date = jdatetime.date.today()
            self.calendar_widget.display_date = jdatetime.date.today()
        else:
            # If a date was selected, ensure the calendar displays that month
            self.calendar_widget.display_date = self.calendar_widget.selected_date
            # Also update current_date in calendar_widget if tray icon's date has changed
            self.calendar_widget.current_date = jdatetime.date.today()

        self.calendar_widget.show()
        self.position_calendar_above_tray()
        self.calendar_widget.activateWindow()
        self.calendar_widget.raise_()
        self._is_calendar_visible = True
        
        # Update the Gregorian date label for the selected/displayed date
        current_greg_date_for_label = (self.calendar_widget.selected_date or jdatetime.date.today()).togregorian()
        self.calendar_widget.formatted_mdy = current_greg_date_for_label.strftime("%m/%d/%Y")
        self.calendar_widget.formatted_month_day_year = current_greg_date_for_label.strftime("%b %d, %Y")
        
        self.calendar_widget.gregorian_date_label.setText(
            self.calendar_widget.formatted_mdy if self.calendar_widget.show_mdy_format else self.calendar_widget.formatted_month_day_year
        )
        
        self.calendar_widget._fill_calendar_grid()
        self.calendar_widget._apply_theme_styles()

    def hide_calendar(self):
        """Hides the calendar widget."""
        if self.calendar_widget:
            self.calendar_widget.hide()
            self._is_calendar_visible = False

    def position_calendar_above_tray(self):
        """Positions the calendar widget above the system tray icon."""
        screen = QApplication.primaryScreen().availableGeometry()
        tray_geometry = self.geometry()

        widget_width = self.calendar_widget.width()
        widget_height = self.calendar_widget.height()

        target_x = screen.width() - widget_width - 20
        target_y = screen.height() - widget_height - 20

        if tray_geometry.isValid():
            target_x = tray_geometry.center().x() - widget_width // 2
            target_y = tray_geometry.top() - widget_height - 5

            if target_y < 0:
                target_y = tray_geometry.bottom() + 5
        
        target_x = max(0, min(target_x, screen.width() - widget_width))
        target_y = max(0, min(target_y, screen.height() - widget_height))
        
        self.calendar_widget.move(target_x, target_y)

    def _on_system_time_changed(self):
        """Callback for system time changes, forces tray icon update."""
        logger.info("System time change detected. Updating tray icon and rescheduling midnight check.")
        self.update_tray_icon(force=True)
        self.schedule_next_midnight_check()

    def schedule_next_midnight_check(self):
        """Schedules a single shot timer to trigger at midnight for date update."""
        now = datetime.datetime.now()
        tomorrow = now + datetime.timedelta(days=1)
        midnight = datetime.datetime(tomorrow.year, tomorrow.month, tomorrow.day)
        millis_until_midnight = int((midnight - now).total_seconds() * 1000)
        
        buffer_ms = 500
        QTimer.singleShot(millis_until_midnight + buffer_ms, self._on_midnight_timer_triggered)

    def _on_midnight_timer_triggered(self):
        """Triggered at midnight to update the tray icon and reschedule."""
        logger.info("Midnight timer triggered. Updating tray icon for new day.")
        self.update_tray_icon(force=True)
        self.schedule_next_midnight_check()

# ==================== TUTORIAL WINDOW ====================

class TutorialWindow(QWidget):
    """
    A window to display a first-time tutorial for dragging the tray icon.
    This window will only appear once per installation.
    """
    tutorial_closed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("TutorialWindow")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(500, 400)
        self._drag_position: Optional[QPoint] = None

        self._setup_ui()
        self._apply_theme_styles()

        if sys.platform == "win32":
            try:
                import win32api, win32con, win32gui
                hwnd = self.winId().__int__()
                current_style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
                new_style = current_style | win32con.WS_MINIMIZEBOX | win32con.WS_SYSMENU
                win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, new_style)
                win32gui.SetWindowPos(
                    hwnd, None, 0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOZORDER | win32con.SWP_FRAMECHANGED
                )
            except Exception as e:
                logger.error(f"Failed to apply Windows window styles to tutorial window: {e}")

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        self.tutorial_message_label = QLabel(
            "برای دسترسی آسان، می‌توانید آیکون برنامه را از بخش آیکون‌های پنهان ویندوز، به نوار وظیفه اصلی بکشید."
        )
        self.tutorial_message_label.setFont(QFont(APP_CONFIG.FONT_FAMILY, 12))
        self.tutorial_message_label.setWordWrap(True)
        self.tutorial_message_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.tutorial_message_label)

        self.gif_label = QLabel()
        self.gif_label.setAlignment(Qt.AlignCenter)
        self.gif_label.setFixedSize(300, 200)
        gif_path = str(APP_CONFIG.TUTORIAL_GIF_PATH)

        if os.path.exists(gif_path):
            self.movie = QMovie(gif_path)
            if self.movie.isValid():
                self.movie.setCacheMode(QMovie.CacheAll)
                self.movie.setSpeed(100)
                
                if hasattr(self.movie, 'setLoopCount'):
                    self.movie.setLoopCount(-1)
                else:
                    self.movie.finished.connect(self.movie.start)
                    logger.warning("QMovie.setLoopCount not found, falling back to connecting finished to start for GIF loop.")
                
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

        main_layout.addStretch(1)

        self.close_button_bottom = QPushButton("بستن آموزش")
        self.close_button_bottom.setFixedHeight(50)
        self.close_button_bottom.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.close_button_bottom.clicked.connect(self._close_tutorial)
        main_layout.addWidget(self.close_button_bottom)

    def _apply_theme_styles(self):
        """Applies theme-specific styles to the tutorial window and its elements."""
        self.setStyleSheet(self._build_stylesheet())

        self.tutorial_message_label.setStyleSheet(f"color: {APP_CONFIG.current_palette['TEXT_COLOR']}; background: transparent;")

        self.close_button_bottom.setStyleSheet(
            f"QPushButton {{ background-color: {APP_CONFIG.current_palette['ACCENT_COLOR']}; color: {APP_CONFIG.current_palette['TEXT_COLOR']}; "
            f"border: none; border-radius: 8px; padding: 8px 15px; font-size: 16px; "
            f"font-weight: bold; font-family: '{APP_CONFIG.FONT_FAMILY}'; }}"
            f"QPushButton:hover {{ background-color: {QColor(APP_CONFIG.current_palette['ACCENT_COLOR']).darker(120).name()}; }}"
            f"QPushButton:pressed {{ background-color: {QColor(APP_CONFIG.current_palette['ACCENT_COLOR']).darker(150).name()}; }}"
        )
        self.repaint()

    def _build_stylesheet(self) -> str:
        """Constructs the base stylesheet for the tutorial window."""
        radius = APP_CONFIG.CALENDAR_BORDER_RADIUS_PX
        return (
            f"QWidget#TutorialWindow {{ "
            f"    background-color: {APP_CONFIG.current_palette['BACKGROUND_COLOR']}; "
            f"    border: 1px solid {APP_CONFIG.current_palette['CALENDAR_BORDER_COLOR']}; "
            f"    border-radius: {radius}px; "
            f"}}"
        )
    
    def _close_tutorial(self):
        """Handles the closing of the tutorial window."""
        logger.debug("Tutorial close button clicked.")
        if hasattr(self, 'movie') and self.movie.isValid():
            self.movie.stop()
        self.tutorial_closed.emit()
        self.close()
        logger.debug("Tutorial window closed.")

    def paintEvent(self, event):
        """Custom paint event to draw the rounded background and border."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.HighQualityAntialiasing)
        rect = self.rect()
        path = QPainterPath()
        radius = APP_CONFIG.CALENDAR_BORDER_RADIUS_PX
        path.addRoundedRect(rect.x() + 1, rect.y() + 1, rect.width() - 2, rect.height() - 2, radius, radius)
        painter.fillPath(path, QColor(APP_CONFIG.current_palette['BACKGROUND_COLOR']))
        painter.setPen(QColor(APP_CONFIG.current_palette['CALENDAR_BORDER_COLOR']))
        painter.drawPath(path)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.pos()
            if pos.y() < 60:
                self._drag_position = event.globalPos() - self.frameGeometry().topLeft()
                event.accept()
            else:
                event.ignore()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_position is not None:
            new_pos = event.globalPos() - self._drag_position
            screen_geometry = QApplication.primaryScreen().availableGeometry()
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
        event.accept()

# ==================== MAIN APP ENTRY ====================

_global_tray_icon_instance: Optional['SystemTrayIcon'] = None

def start_main_app():
    """Initializes and shows the SystemTrayIcon."""
    global _global_tray_icon_instance
    if _global_tray_icon_instance is None:
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

    settings = QSettings()
    has_shown_tutorial = settings.value(APP_CONFIG.TUTORIAL_SHOWN_SETTING_KEY, False, type=bool)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        logger.critical("System tray not available. Exiting application.")
        sys.exit(1)

    start_main_app()

    if not has_shown_tutorial:
        logger.info("Showing tutorial for the first time.")
        tutorial_window = TutorialWindow()
        tutorial_window.setAttribute(Qt.WA_DeleteOnClose)
        
        # Link the tutorial window to the main app instance for theme updates
        _global_tray_icon_instance.tutorial_window = tutorial_window
        tutorial_window.tutorial_closed.connect(lambda: setattr(_global_tray_icon_instance, 'tutorial_window', None))
        
        tutorial_window.show()
        settings.setValue(APP_CONFIG.TUTORIAL_SHOWN_SETTING_KEY, True)
        
        screen_geo = QApplication.primaryScreen().availableGeometry()
        x = (screen_geo.width() - tutorial_window.width()) // 2
        y = (screen_geo.height() - tutorial_window.height()) // 2
        tutorial_window.move(x, y)
    else:
        logger.info("Tutorial already shown. Main app started directly.")

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()