import ctypes.wintypes
import datetime
import json
import os
import sys
import winreg
from typing import Dict, List, Optional, Tuple

import jdatetime
from PyQt5.QtCore import (QAbstractNativeEventFilter, QCoreApplication,
                          QPoint, QRectF, QSettings, Qt, QTimer, pyqtSignal)
from PyQt5.QtGui import (QColor, QFont, QIcon, QMouseEvent, QMovie, QPainter,
                         QPainterPath, QPixmap)
from PyQt5.QtWidgets import (QApplication, QBoxLayout, QGridLayout,
                             QHBoxLayout, QLabel, QMenu, QMessageBox,
                             QPushButton, QSystemTrayIcon,
                             QVBoxLayout, QWidget, QWidgetAction)

from config import (APP_CONFIG, is_jalali_leap_year,
                    load_fonts, persian_month_name, persian_weekday_name,
                    setup_logging, to_persian_digits, verify_assets)
try:
    from dateconverter import DateConverterWindow
except ImportError:
    logger = setup_logging(__name__)
    logger.warning("dateconverter.py not found. Date conversion feature will be disabled.")
    class DateConverterWindow(QWidget):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.setWindowTitle("Date Converter (Unavailable)")
            self.setLayout(QVBoxLayout())
            self.layout().addWidget(QLabel("Date converter feature is not available."))
        def show(self):
            QMessageBox.warning(None, "Feature Unavailable", "The date conversion feature is not available. Please ensure 'dateconverter.py' is in the correct directory.")
            super().show()
        def update_styles(self):
            pass


logger = setup_logging(__name__)

# ==================== BASE CLASSES & UTILITIES ====================

class BaseFramelessWindow(QWidget):
    """A base class for frameless windows with custom drag and paint logic."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._drag_position: Optional[QPoint] = None
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def paintEvent(self, event):
        """Paints the rounded background and border."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        radius = APP_CONFIG.CALENDAR_BORDER_RADIUS_PX
        path.addRoundedRect(QRectF(self.rect()), radius, radius)
        
        painter.fillPath(path, QColor(APP_CONFIG.current_palette['BACKGROUND_COLOR']))
        painter.setPen(QColor(APP_CONFIG.current_palette['CALENDAR_BORDER_COLOR']))
        painter.drawPath(path)
        painter.setClipPath(path)
        super().paintEvent(event)

    def mousePressEvent(self, event):
        """Captures the mouse position to start dragging."""
        if event.button() == Qt.LeftButton and event.y() < 40:
            self._drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        """Moves the window if dragging, with clamping to screen edges."""
        if event.buttons() == Qt.LeftButton and self._drag_position is not None:
            new_pos = event.globalPos() - self._drag_position
            screen_geometry = QApplication.screenAt(event.globalPos()).availableGeometry()
            
            min_x = screen_geometry.left()
            max_x = screen_geometry.right() - self.width()
            clamped_x = max(min_x, min(new_pos.x(), max_x))

            min_y = screen_geometry.top()
            max_y = screen_geometry.bottom() - 50
            clamped_y = max(min_y, min(new_pos.y(), max_y))

            self.move(clamped_x, clamped_y)
            event.accept()

    def mouseReleaseEvent(self, event):
        """Stops dragging."""
        self._drag_position = None
        event.accept()

class TimeChangeEventFilter(QAbstractNativeEventFilter):
    """
    Native event filter to detect system time changes (WM_TIMECHANGE on Windows).
    Uses a direct callback for reliability.
    """
    
    def __init__(self, on_time_change_callback):
        super().__init__()
        self.on_time_change_callback = on_time_change_callback
        logger.debug("TimeChangeEventFilter initialized with direct callback.")

    def nativeEventFilter(self, eventType, message):
        if eventType == "windows_generic_MSG":
            try:
                msg = ctypes.cast(int(message), ctypes.POINTER(ctypes.wintypes.MSG)).contents
                WM_TIMECHANGE = 0x001E
                if msg.message == WM_TIMECHANGE:
                    logger.info("⏰ System time changed (WM_TIMECHANGE detected). Calling direct callback.")
                    if callable(self.on_time_change_callback):
                        self.on_time_change_callback()
            except Exception as e:
                logger.error(f"Error processing Windows message in native event filter: {e}")
        return False, 0

# ==================== CUSTOM WIDGETS ====================

class ClickableLabel(QLabel):
    """A QLabel that emits a clicked signal, optionally with a date."""
    clicked = pyqtSignal(object)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.jalali_date: Optional[jdatetime.date] = None

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.jalali_date)
        super().mousePressEvent(event)

class HoverWidget(QWidget):
    """Base widget for menu items that handles hover effects."""
    triggered = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._is_hovered = False
        self.setMouseTracking(True)
        self.setStyleSheet("background-color: transparent; border-radius: 6px;")

    def paintEvent(self, event):
        if self._is_hovered:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()), 6, 6)
            painter.fillPath(path, QColor(*APP_CONFIG.current_palette["MENU_HOVER_COLOR"]))
        super().paintEvent(event)
        
    def enterEvent(self, event):
        self._is_hovered = True
        self.update()
    
    def leaveEvent(self, event):
        self._is_hovered = False
        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.triggered.emit()

class MenuActionWidget(HoverWidget):
    """Custom widget for a simple text-based menu action."""
    def __init__(self, text: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 6, 15, 6)
        self.label = QLabel(text)
        self.label.setAlignment(Qt.AlignCenter)
        layout.addStretch()
        layout.addWidget(self.label)
        layout.addStretch()
        self._update_style()

    def _update_style(self):
        self.label.setStyleSheet(
            f"color: {APP_CONFIG.current_palette['TEXT_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}';"
            f"font-size: 14px; font-weight: bold; background: transparent;"
        )

class IconCheckboxActionWidget(HoverWidget):
    """A context menu checkbox using FontAwesome icons."""
    toggled = pyqtSignal(bool)

    def __init__(self, text: str, is_checked: bool, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.is_checked = is_checked
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(8)
        
        self.icon_label = QLabel()
        self.icon_label.setFont(QFont(APP_CONFIG.FONT_AWESOME_FAMILY, 14))
        self.icon_label.setFixedWidth(22)

        self.text_label = QLabel(text)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label)
        layout.addStretch()
        
        self.update_visuals()

    def mousePressEvent(self, event: QMouseEvent):
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            self.is_checked = not self.is_checked
            self.toggled.emit(self.is_checked)
            self.update_visuals()

    def setChecked(self, checked: bool):
        if self.is_checked != checked:
            self.is_checked = checked
            self.update_visuals()

    def update_visuals(self):
        icon = APP_CONFIG.FAS.FA_SQUARE_CHECK_SOLID if self.is_checked else APP_CONFIG.FAS.FA_SQUARE_REGULAR
        self.icon_label.setText(icon)
        color = APP_CONFIG.current_palette['TEXT_COLOR']
        self.icon_label.setStyleSheet(f"color: {color}; background: transparent;")
        self.text_label.setStyleSheet(
            f"color: {color}; font-family: '{APP_CONFIG.FONT_FAMILY}'; "
            "font-size: 14px; font-weight: bold; background: transparent;"
        )

class ThemeToggleActionWidget(MenuActionWidget):
    """Widget for the 'App Theme' toggle in the context menu."""
    def __init__(self, current_theme_getter, parent: Optional[QWidget] = None):
        super().__init__("", parent)
        self.current_theme_getter = current_theme_getter
        
        layout = self.layout()
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self.icon_label = QLabel()
        self.icon_label.setFont(QFont(APP_CONFIG.FONT_AWESOME_FAMILY, 14))
        self.icon_label.setFixedWidth(22)
        
        self.label = QLabel("") 
        
        layout.addStretch()
        layout.addWidget(self.icon_label)
        layout.addSpacing(0)
        layout.addWidget(self.label)
        layout.addStretch()
        
        self.update_display()

    def paintEvent(self, event):
        self.update_display() 
        super().paintEvent(event)

    def update_display(self):
        theme = self.current_theme_getter()
        icon = APP_CONFIG.FAS.FA_MOON_SOLID if theme == APP_CONFIG.Theme.DARK else APP_CONFIG.FAS.FA_SUN_SOLID
        text = "    تم برنامه: تیره" if theme == APP_CONFIG.Theme.DARK else "    تم برنامه: روشن"
        
        self.icon_label.setText(icon)
        self.label.setText(text)
        
        color = APP_CONFIG.current_palette['TEXT_COLOR']
        self.icon_label.setStyleSheet(f"color: {color}; background: transparent;")
        self._update_style()

# ==================== PERSIAN CALENDAR WIDGET ====================

class PersianCalendarWidget(BaseFramelessWindow):
    """Main calendar widget displaying a month of Persian (Jalali) dates."""
    ROWS, COLS = 6, 7

    def __init__(self, holidays_cache: dict):
        super().__init__()
        self.holidays_cache = holidays_cache
        self.holidays: Dict[Tuple[int, int], List[str]] = {}
        
        self.current_date = jdatetime.date.today()
        self.display_date = self.current_date
        self.selected_date = self.current_date
        
        self.day_labels: List[List[ClickableLabel]] = []
        self._show_gregorian_mdy = True
        
        self._setup_ui()
        self.update_styles()
        self.fill_calendar_grid()

    def _setup_ui(self):
        """Initialize and layout all UI components."""
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

    def _create_header(self) -> QHBoxLayout:
        """Create the top navigation bar with month/year and arrows."""
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
        """Create the bar with the Gregorian date and 'Today' button."""
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
        """Create the header row with weekday names (Sh, Ye, ...)."""
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
        """Create the main 6x7 grid for calendar days using QGridLayout."""
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
                grid_layout.addWidget(label, row, col)
                week_labels.append(label)
            self.day_labels.append(week_labels)
        return grid_layout
    
    def _get_nav_button_style(self, bg_color: str, is_today_button: bool = False) -> str:
        """
        Helper to generate stylesheet for navigation buttons.
        Added is_today_button flag to apply specific hover/pressed effects.
        """
        palette = APP_CONFIG.get_current_palette()
        text_color = palette['TEXT_COLOR']

        if is_today_button:
            base_color = QColor(bg_color)
            hover_color = base_color.lighter(120).name()
            pressed_color = base_color.darker(120).name()
            
            return (
                f"QPushButton {{ background-color: {base_color.name()}; color: white; border: none; border-radius: 8px; }}"
                f"QPushButton:hover {{ background-color: {hover_color}; }}"
                f"QPushButton:pressed {{ background-color: {pressed_color}; }}"
            )
        else:
            hover_color = QColor(bg_color).darker(120).name() if bg_color != "transparent" else palette['HOVER_BG']
            return (
                f"QPushButton {{ background-color: {bg_color}; color: {text_color}; border: none; border-radius: 8px; }}"
                f"QPushButton:hover {{ background-color: {hover_color}; }}"
            )

    def update_styles(self):
        """Apply theme-specific colors and fonts to all widgets."""
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
        
        self.gregorian_date_label.setStyleSheet(
            f"QLabel {{"
            f"  color: {text_color};"
            f"  font-size: {APP_CONFIG.FONT_SIZE_LABEL}px;"
            f"  background-color: {palette['HOVER_BG']};"
            f"  font-family: '{APP_CONFIG.GREGORIAN_FONT_FAMILY}';"
            f"  font-weight: bold;"
            f"  border-radius: 8px;"
            f"  padding: 3px 6px;"
            f"}}"
            f"QLabel:hover {{"
            f"  background-color: {palette['GREGORIAN_DATE_HOVER_BG']};"
            f"}}"
        )
        
        for i in range(self.weekdays_layout.count()):
            day_label = self.weekdays_layout.itemAt(i).widget()
            if isinstance(day_label, QLabel):
                is_friday = day_label.text() == 'ج'
                color = palette['HOLIDAY_COLOR'] if is_friday else palette['WEEKDAY_NAMES_COLOR']
                day_label.setStyleSheet(
                    f"color: {color}; font-weight: bold; font-size: 16px; "
                    f"background: transparent; font-family: '{APP_CONFIG.FONT_FAMILY}';"
                )
                
        self.fill_calendar_grid()

    def fill_calendar_grid(self):
        """Fill the calendar grid with day numbers and apply styles."""
        self._update_header()
        self.holidays = self.holidays_cache.get(self.display_date.year, {})
        
        first_day = self.display_date.replace(day=1)
        start_day_of_week = first_day.weekday()
        
        current_day = first_day - datetime.timedelta(days=start_day_of_week)

        for row in range(self.ROWS):
            for col in range(self.COLS):
                label = self.day_labels[row][col]
                label.jalali_date = current_day
                label.setText(to_persian_digits(current_day.day))
                
                is_in_display_month = (current_day.month == self.display_date.month)
                stylesheet, tooltip = self._get_day_style(current_day, is_in_display_month)
                
                label.setStyleSheet(stylesheet)
                label.setToolTip(tooltip)
                
                current_day += datetime.timedelta(days=1)

    def _update_header(self):
        """Update month, year, and Gregorian date labels."""
        self.month_label.setText(persian_month_name(self.display_date.month))
        self.year_label.setText(to_persian_digits(self.display_date.year))
        
        greg_date = self.selected_date.togregorian()
        if self._show_gregorian_mdy:
            self.gregorian_date_label.setText(greg_date.strftime("%m/%d/%Y"))
        else:
            self.gregorian_date_label.setText(greg_date.strftime("%b %d, %Y"))

    def _get_rgba_string(self, color_hex: str, alpha: float) -> str:
        """Helper function to get rgba string from hex color and alpha."""
        color = QColor(color_hex)
        return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha})"

    def _get_day_style(self, jdate: jdatetime.date, is_in_month: bool) -> Tuple[str, str]:
        """Determine the stylesheet and tooltip for a calendar day."""
        is_today = (jdate == self.current_date)
        is_selected = (jdate == self.selected_date)
        is_friday = jdate.weekday() == 6
        holiday_reasons = self.holidays.get((jdate.month, jdate.day))
        is_holiday = bool(holiday_reasons)
        tooltip = "\n".join(holiday_reasons) if is_holiday else ""

        palette = APP_CONFIG.get_current_palette()
        text_color = palette['TEXT_COLOR']
        background_color_rgba = "transparent"
        border_style = "none"
        font_size = APP_CONFIG.FONT_SIZE_LABEL
        hover_background_color_rgba = palette['HOVER_BG']

        if not is_in_month:
            if is_holiday or is_friday:
                text_color = self._get_rgba_string(palette['HOLIDAY_COLOR'], 0.45)
                background_color_rgba = self._get_rgba_string(palette['HOLIDAY_COLOR'], 0.05)
                hover_background_color_rgba = self._get_rgba_string(palette['HOLIDAY_COLOR'], 0.10)
            else:
                text_color = palette['GREY_COLOR']
                hover_background_color_rgba = self._get_rgba_string(palette['GREY_COLOR'], 0.10)
        else:
            if is_today and (is_holiday or is_friday) and is_selected:
                text_color = palette['HOLIDAY_COLOR']
                background_color_rgba = self._get_rgba_string(palette['HOLIDAY_COLOR'], 0.60)
                hover_background_color_rgba = self._get_rgba_string(palette['HOLIDAY_COLOR'], 0.80)
                border_style = f"1px solid {palette['HOLIDAY_COLOR']}"
            elif is_today and is_selected:
                background_color_rgba = palette['CALENDAR_TODAY_SELECTED_BG_COLOR']
                hover_background_color_rgba = palette['CALENDAR_TODAY_HOVER_BG_COLOR']
                border_style = f"1px solid {palette['TEXT_COLOR']}"
            elif is_holiday or is_friday:
                text_color = palette['HOLIDAY_COLOR']
                if is_selected:
                    background_color_rgba = self._get_rgba_string(palette['HOLIDAY_COLOR'], 0.50)
                    hover_background_color_rgba = self._get_rgba_string(palette['HOLIDAY_COLOR'], 0.70)
                    border_style = f"1px solid {palette['HOLIDAY_COLOR']}"
                else:
                    background_color_rgba = self._get_rgba_string(palette['HOLIDAY_COLOR'], 0.15)
                    hover_background_color_rgba = self._get_rgba_string(palette['HOLIDAY_COLOR'], 0.30)
            elif is_today:
                background_color_rgba = palette['CALENDAR_TODAY_BG_COLOR']
                hover_background_color_rgba = palette['CALENDAR_TODAY_HOVER_BG_COLOR']
                border_style = f"1px solid {palette['TEXT_COLOR']}"
            elif is_selected:
                background_color_rgba = palette['CALENDAR_SELECTED_BG_COLOR']
                hover_background_color_rgba = palette['CALENDAR_SELECTED_HOVER_BG_COLOR']
                border_style = f"1px solid {palette['TEXT_COLOR']}"

            if is_today:
                font_size = 17

            if is_today and (is_holiday or is_friday):
                border_style = f"1px solid {palette['HOLIDAY_COLOR']}"

        style = (
            f"background-color: {background_color_rgba};"
            f"color: {text_color};"
            f"border: {border_style};"
            f"border-radius: 8px;"
            f"font-size: {font_size}px;"
            f"font-weight: bold;"
            f"font-family: '{APP_CONFIG.FONT_FAMILY}';"
        )
        return f"QLabel {{ {style} }} QLabel:hover {{ background-color: {hover_background_color_rgba}; }}", tooltip


    def _navigate(self, months: int):
        """Navigate forward or backward by a number of months."""
        new_year, new_month = self.display_date.year, self.display_date.month + months
        while new_month < 1:
            new_month += 12
            new_year -= 1
        while new_month > 12:
            new_month -= 12
            new_year += 1
        
        new_day = self.display_date.day
        try:
            self.display_date = jdatetime.date(new_year, new_month, new_day)
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

    def _on_day_clicked(self, jdate: Optional[jdatetime.date]):
        if jdate:
            self.selected_date = jdate
            if jdate.month != self.display_date.month:
                self.display_date = jdate
            self.fill_calendar_grid()

    def _toggle_gregorian_format(self, _):
        self._show_gregorian_mdy = not self._show_gregorian_mdy
        self._update_header()

# ==================== TUTORIAL WINDOW ====================

class TutorialWindow(BaseFramelessWindow):
    """A window to display a first-time tutorial for the app."""
    tutorial_closed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("راهنمای شروع")
        self.setFixedSize(500, 400)
        self._setup_ui()
        self.update_styles()
        self._apply_windows_styles()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        self.message_label = QLabel(
            "برای دسترسی آسان، می‌توانید آیکون برنامه را از بخش آیکون‌های پنهان ویندوز، به نوار وظیفه اصلی بکشید."
        )
        self.message_label.setWordWrap(True)
        self.message_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.message_label)

        self.gif_label = QLabel()
        self.gif_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.gif_label, alignment=Qt.AlignCenter)
        self._load_gif()

        main_layout.addStretch(1)
        self.close_button = QPushButton("بستن آموزش")
        self.close_button.clicked.connect(self._close_tutorial)
        main_layout.addWidget(self.close_button)

    def _load_gif(self):
        gif_path = str(APP_CONFIG.TUTORIAL_GIF_PATH)
        if not os.path.exists(gif_path):
            logger.error(f"Tutorial GIF not found: {gif_path}")
            self.gif_label.setText("فایل GIF یافت نشد.")
            return

        self.movie = QMovie(gif_path)
        if self.movie.isValid():
            self.gif_label.setMovie(self.movie)
            self.movie.setCacheMode(QMovie.CacheAll)
            self.movie.setSpeed(100)
            self.movie.loopCount = -1
            self.movie.start()
        else:
            logger.warning(f"Failed to load GIF from {gif_path}.")

    def update_styles(self):
        palette = APP_CONFIG.get_current_palette()
        self.message_label.setFont(QFont(APP_CONFIG.FONT_FAMILY, 12))
        self.message_label.setStyleSheet(f"color: {palette['TEXT_COLOR']};")
        
        self.close_button.setFixedHeight(50)
        self.close_button.setStyleSheet(
            f"QPushButton {{ background-color: {palette['ACCENT_COLOR']}; color: white; border: none; "
            f"border-radius: 8px; font-size: 16px; font-weight: bold; font-family: '{APP_CONFIG.FONT_FAMILY}'; }}"
            f"QPushButton:hover {{ background-color: {QColor(palette['ACCENT_COLOR']).darker(120).name()}; }}"
        )

    def _close_tutorial(self):
        if hasattr(self, 'movie') and self.movie:
            self.movie.stop()
        self.tutorial_closed.emit()
        self.close()

    def _apply_windows_styles(self):
        """Adds minimize and system menu to the frameless window on Windows."""
        try:
            import win32con, win32gui
            hwnd = self.winId().__int__()
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
            win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style | win32con.WS_MINIMIZEBOX | win32con.WS_SYSMENU)
        except (ImportError, Exception) as e:
            logger.warning(f"Could not set Windows styles for tutorial: {e}")

# ==================== SYSTEM TRAY ICON (MAIN CONTROLLER) ====================

class SystemTrayIcon(QSystemTrayIcon):
    """The main application controller, managing the tray icon, windows, and settings."""

    def __init__(self):
        super().__init__()
        self.settings = QSettings(APP_CONFIG.COMPANY_NAME, APP_CONFIG.APP_NAME)
        self.holidays_cache = self._load_holidays_from_file()
        
        self.calendar_widget = PersianCalendarWidget(self.holidays_cache)
        self.converter_window: Optional[DateConverterWindow] = None
        self.tutorial_window: Optional[TutorialWindow] = None

        self._load_settings()
        self._apply_theme()
        
        self.activated.connect(self.on_tray_icon_activated)
        
        self._setup_timers()
        self.update_tray_icon(force=True)

    def _load_settings(self):
        """Load user preferences from QSettings."""
        self.is_open_at_login = self.settings.value(APP_CONFIG.AUTO_START_SETTING_KEY, False, type=bool)
        self.current_theme = self.settings.value(APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY, APP_CONFIG.Theme.DARK, type=str)
        logger.info(f"Loaded settings: OpenAtLogin={self.is_open_at_login}, Theme={self.current_theme}")

    def _apply_theme(self):
        """Applies the current theme to the entire application."""
        APP_CONFIG.set_theme(self.current_theme)
        QApplication.instance().setStyleSheet(self._build_global_stylesheet())
        
        self.update_tray_icon(force=True)
        self._setup_context_menu()

        if self.calendar_widget: self.calendar_widget.update_styles()
        if self.converter_window and self.converter_window.isVisible(): self.converter_window.update_styles()
        if self.tutorial_window and self.tutorial_window.isVisible(): self.tutorial_window.update_styles()
    
    def _setup_timers(self):
        """Sets up timers for periodic and midnight updates."""
        self.minute_timer = QTimer(self)
        self.minute_timer.timeout.connect(lambda: self.update_tray_icon(force=False))
        self.minute_timer.start(60 * 1000)

        self.event_filter = TimeChangeEventFilter(self._handle_system_time_change)
        QCoreApplication.instance().installNativeEventFilter(self.event_filter)

        self.schedule_next_midnight_check()

    def _on_midnight_timer_triggered(self):
        """Triggered at midnight to update the tray icon and reschedule."""
        logger.info("Midnight timer triggered. Updating tray icon for new day.")
        self.update_tray_icon(force=True)
        self.schedule_next_midnight_check()

    def schedule_next_midnight_check(self):
        """Schedules a single shot timer to trigger at midnight for date update."""
        now = datetime.datetime.now()
        tomorrow = now + datetime.timedelta(days=1)
        midnight = datetime.datetime(tomorrow.year, tomorrow.month, tomorrow.day)
        
        millis_until_midnight = int((midnight - now).total_seconds() * 1000)
        buffer_ms = 500

        if hasattr(self, '_midnight_timer') and self._midnight_timer.isActive():
            self._midnight_timer.stop()
            del self._midnight_timer

        self._midnight_timer = QTimer(self)
        self._midnight_timer.setSingleShot(True)
        self._midnight_timer.timeout.connect(self._on_midnight_timer_triggered)
        self._midnight_timer.start(millis_until_midnight + buffer_ms)
        logger.debug(f"Next midnight check scheduled in {millis_until_midnight + buffer_ms} ms.")

    def _handle_system_time_change(self):
        """Handles system time changes detected by the native event filter."""
        logger.info("System time change detected. Forcing tray icon update and rescheduling midnight check.")
        self.update_tray_icon(force=True)
        self.schedule_next_midnight_check()


    def _build_global_stylesheet(self) -> str:
        """Constructs a global stylesheet for tooltips and scrollbars."""
        palette = APP_CONFIG.get_current_palette()
        return (
            f"QToolTip {{ "
            f"  background-color: {palette['INPUT_BG_COLOR']};"
            f"  color: {palette['HOLIDAY_COLOR']};"
            f"  border: 1px solid {palette['CALENDAR_BORDER_COLOR']};"
            f"  border-radius: 8px; padding: 5px;"
            f"  font-family: '{APP_CONFIG.FONT_FAMILY}'; font-weight: bold; font-size: 14px;"
            f"}}"
            f"QScrollBar:vertical {{"
            f"  border: none; background: {palette['SCROLLBAR_GROOVE_COLOR']}; width: 10px; margin: 0px; border-radius: 5px;"
            f"}}"
            f"QScrollBar::handle:vertical {{"
            f"  background: {palette['SCROLLBAR_HANDLE_COLOR']}; border-radius: 5px; min-height: 20px;"
            f"}}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}"
            f"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}"
        )
    
    def _load_holidays_from_file(self) -> Dict[int, Dict[Tuple[int, int], List[str]]]:
        """Loads and parses the holiday data from the JSON file."""
        try:
            with open(APP_CONFIG.HOLIDAYS_FILE_PATH, 'r', encoding='utf-8') as f:
                raw_data = json.load(f).get('holidays', {})
            
            holidays_data = {}
            for year_str, events in raw_data.items():
                year_int = int(year_str)
                holidays_data[year_int] = {}
                for month_day_str, desc in events.items():
                    month, day = map(int, month_day_str.split('-'))
                    holidays_data[year_int][(month, day)] = [desc] if isinstance(desc, str) else desc
            logger.info("Holidays loaded successfully.")
            return holidays_data
        except (IOError, json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to load or parse holidays file: {e}")
            return {}
    
    def update_tray_icon(self, force: bool = False):
        """Updates the tray icon if the date has changed or if forced."""
        new_date = jdatetime.date.today()
        if not force and new_date == self.calendar_widget.current_date:
            return

        logger.info(f"Updating tray icon for new date: {new_date}")
        self.calendar_widget.current_date = new_date
        if self.calendar_widget.isVisible():
            self.calendar_widget.fill_calendar_grid()

        screen = QApplication.primaryScreen()
        if screen:
            dpi = screen.logicalDotsPerInch()
            
            if dpi >= 110:
                icon_size = 36
                font_size = 20
            else:
                icon_size = 38
                font_size = 26
        else:
            icon_size = 38
            font_size = 26
        
        pixmap = QPixmap(icon_size, icon_size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        day_str = to_persian_digits(new_date.day)
        is_holiday = new_date.weekday() == 6 or self.holidays_cache.get(new_date.year, {}).get((new_date.month, new_date.day))
        
        color = APP_CONFIG.TRAY_ICON_DARK_COLOR if self.current_theme == APP_CONFIG.Theme.DARK else APP_CONFIG.TRAY_ICON_LIGHT_COLOR
        if is_holiday:
            color = APP_CONFIG.current_palette['HOLIDAY_COLOR']
        
        painter.setPen(QColor(color))
        painter.setFont(QFont(APP_CONFIG.FONT_FAMILY, font_size, QFont.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, day_str)
        painter.end()
        self.setIcon(QIcon(pixmap))

        weekday_name = persian_weekday_name(new_date.weekday())
        month_name = persian_month_name(new_date.month)
        year_str = str(new_date.year)
        month_str = f"{new_date.month:02d}"
        day_str2 = f"{new_date.day:02d}"
        
        month_written = f"\u200F{day_str2} {month_name} {year_str}"
        
        tooltip_lines = [
            weekday_name,
            f"{year_str}/{month_str}/{day_str2}",
            month_written
        ]

        if is_holiday:
            holiday_reasons = self.holidays_cache.get(new_date.year, {}).get((new_date.month, new_date.day), [])
            if holiday_reasons:
                tooltip_lines.append("تعطیلی:")
                tooltip_lines.extend(holiday_reasons)
                
        self.setToolTip("\n".join(tooltip_lines))

    def _setup_context_menu(self):
        """Creates the right-click context menu for the tray icon."""
        menu = QMenu()
        palette = APP_CONFIG.get_current_palette()
        menu.setStyleSheet(
            f"QMenu {{ background-color: {palette['BACKGROUND_COLOR']}; border: 1px solid {palette['MENU_BORDER_COLOR']};"
            f"  border-radius: 8px; padding: 5px; }}"
            f"QMenu::separator {{ height: 1px; background-color: {palette['MENU_BORDER_COLOR']}; margin: 5px 0px; }}"
        )
        
        self._add_menu_action(menu, "تبدیل تاریخ", self._open_date_converter)
        menu.addSeparator()

        self._add_theme_toggle_action(menu)
        menu.addSeparator()
        self._add_startup_action(menu)
        menu.addSeparator()
        self._add_menu_action(menu, "خروج", QApplication.quit)

        self.setContextMenu(menu)
    
    def _add_menu_action(self, menu, text, slot):
        action = QWidgetAction(self)
        widget = MenuActionWidget(text, parent=menu)
        widget.triggered.connect(slot)
        action.setDefaultWidget(widget)
        menu.addAction(action)

    def _add_theme_toggle_action(self, menu):
        action = QWidgetAction(self)
        widget = ThemeToggleActionWidget(lambda: self.current_theme, parent=menu)
        widget.triggered.connect(self._toggle_theme)
        action.setDefaultWidget(widget)
        menu.addAction(action)

    def _add_startup_action(self, menu):
        if not sys.platform.startswith('win'): return
        action = QWidgetAction(self)
        widget = IconCheckboxActionWidget("راه اندازی همراه با سیستم", self.is_open_at_login, parent=menu)
        widget.toggled.connect(self._toggle_open_at_boot)
        action.setDefaultWidget(widget)
        menu.addAction(action)

    def on_tray_icon_activated(self, reason):
        """Shows or hides the calendar on left-click."""
        if reason == QSystemTrayIcon.Trigger:
            if self.calendar_widget.isVisible():
                self.calendar_widget.hide()
            else:
                self.show_calendar()

    def show_calendar(self):
        """Positions and shows the calendar widget."""
        self.calendar_widget.current_date = jdatetime.date.today()
        if self.calendar_widget.selected_date is None or self.calendar_widget.selected_date.month != self.calendar_widget.display_date.month:
             self.calendar_widget.display_date = jdatetime.date.today()
             self.calendar_widget.selected_date = jdatetime.date.today()

        self.calendar_widget.fill_calendar_grid()
        self.calendar_widget.update_styles()

        screen = QApplication.primaryScreen().availableGeometry()
        tray_geom = self.geometry()
        widget_size = self.calendar_widget.size()
        
        x = screen.right() - widget_size.width() - 10
        y = screen.bottom() - widget_size.height() - 45 

        if tray_geom.isValid():
            x = tray_geom.center().x() - widget_size.width() // 2
            y = tray_geom.top() - widget_size.height() - 5
            x = max(screen.left(), min(x, screen.right() - widget_size.width()))
            y = max(screen.top(), min(y, screen.bottom() - widget_size.height()))
        
        self.calendar_widget.move(int(x), int(y))
        self.calendar_widget.show()
        self.calendar_widget.activateWindow()

    def _toggle_theme(self):
        self.current_theme = APP_CONFIG.Theme.LIGHT if self.current_theme == APP_CONFIG.Theme.DARK else APP_CONFIG.Theme.DARK
        self.settings.setValue(APP_CONFIG.CURRENT_THEME_CHOICE_SETTING_KEY, self.current_theme)
        logger.info(f"Theme toggled to: {self.current_theme}")
        self._apply_theme()

    def _toggle_open_at_boot(self, checked: bool):
        """Sets the application to run at Windows startup."""
        if not sys.platform.startswith('win'):
            logger.warning("Auto-start is only supported on Windows.")
            return

        self.is_open_at_login = checked
        self.settings.setValue(APP_CONFIG.AUTO_START_SETTING_KEY, checked)
        logger.info(f"Setting 'Open at Login' to {checked}.")
        
        try:
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
            if checked:
                executable_path = f'"{sys.argv[0]}"'
                winreg.SetValueEx(key, APP_CONFIG.APP_NAME, 0, winreg.REG_SZ, executable_path)
            else:
                winreg.DeleteValue(key, APP_CONFIG.APP_NAME)
            winreg.CloseKey(key)
        except FileNotFoundError:
             logger.warning(f"Could not remove startup key (it may not exist).")
        except Exception as e:
            logger.error(f"Error modifying Windows startup registry: {e}")

    def _open_date_converter(self):
        if self.converter_window is None or not self.converter_window.isVisible():
            self.converter_window = DateConverterWindow()
            self.converter_window.show()
            self.converter_window.activateWindow()
        else:
            self.converter_window.activateWindow()


# ==================== MAIN APPLICATION ENTRY ====================

def main():
    """Initializes and runs the ShamsiTray application."""
    try:
        verify_assets()
    except FileNotFoundError as e:
        QMessageBox.critical(None, "خطا در فایل‌های برنامه", str(e))
        sys.exit(1)

    if sys.platform == 'win32':
        myappid = f"{APP_CONFIG.COMPANY_NAME}.{APP_CONFIG.APP_NAME}.1"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps,    True)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    try:
        load_fonts()
    except (RuntimeError, FileNotFoundError) as e:
        QMessageBox.critical(None, "خطای فونت", str(e))
        sys.exit(1)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "خطا", "هیچ System Tray در این سیستم یافت نشد.")
        sys.exit(1)

    tray_icon = SystemTrayIcon()
    tray_icon.show()
    settings = QSettings(APP_CONFIG.COMPANY_NAME, APP_CONFIG.APP_NAME)
    if not settings.value(APP_CONFIG.TUTORIAL_SHOWN_SETTING_KEY, False, type=bool):
        logger.info("First run: Showing tutorial.")
        tutorial = TutorialWindow()
        tray_icon.tutorial_window = tutorial
        tutorial.show()
        screen_center = QApplication.primaryScreen().availableGeometry().center()
        tutorial.move(screen_center - tutorial.rect().center())
        settings.setValue(APP_CONFIG.TUTORIAL_SHOWN_SETTING_KEY, True)

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()