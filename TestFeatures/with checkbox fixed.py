import sys
import jdatetime
import requests
import datetime
import json
import os
import ctypes
import logging
from typing import Optional, Dict, Tuple
from appdirs import user_data_dir
from dateconverter import DateConverterWindow

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QBoxLayout,
    QLabel, QPushButton, QGridLayout, QSystemTrayIcon, QMenu, QFrame, QAction, QCheckBox, QWidgetAction, QStyle, QStyleOptionButton
)
from PyQt5.QtCore import Qt, QTimer, QEvent, pyqtSignal, QRectF, QSettings, QCoreApplication, QPoint, QSize
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QFont, QColor, QPainterPath, QMouseEvent, QFontDatabase

from config import (
    Config, to_persian_digits, persian_month_name,
    persian_weekday_name, safe_jdate, load_fonts
)

# ========== LOGGING SETUP ==========

logging.basicConfig(
    format='[%(levelname)s] %(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',\
    level=Config.LOG_LEVEL
)
logger = logging.getLogger(__name__)

# ========== CLICKABLE LABEL ==========

class FontAwesomeCheckbox(QLabel):
    """
    A custom checkbox widget using Font Awesome icons.
    Uses Font Awesome 6 Pro Solid font for checkbox icons.
    """
    stateChanged = pyqtSignal(int)  # Emits Qt.Checked or Qt.Unchecked

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checked = False
        self._hover = False
        
        # Font Awesome Unicode characters
        self.UNCHECKED_ICON = "\uf0c8"  # fa-square (regular square)
        self.CHECKED_ICON = "\uf14a"    # fa-check-square (checked square)
        # Alternative icons you can use:
        # self.UNCHECKED_ICON = "\uf096"  # fa-square-o (outlined square)
        # self.CHECKED_ICON = "\uf046"    # fa-check-square-o (outlined checked)
        
        self.setFixedSize(20, 20)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)
        
        # Set up Font Awesome font
        self.font_awesome = QFont(Config.FONT_AWESOME_FAMILY, 16)
        self.setFont(self.font_awesome)
        
        self._update_appearance()
    
    def _update_appearance(self):
        """Update the checkbox appearance based on current state."""
        icon = self.CHECKED_ICON if self._checked else self.UNCHECKED_ICON
        
        # Color based on state and hover
        if self._checked:
            color = "#3c7dd1" if not self._hover else "#4a8ae8"  # Blue when checked
        else:
            color = "#606060" if not self._hover else "#808080"  # Gray when unchecked
        
        self.setStyleSheet(f"""
            QLabel {{
                color: {color};
                background: transparent;
                border: none;
            }}
        """)
        
        self.setText(icon)
    
    def isChecked(self):
        """Return the current checked state."""
        return self._checked
    
    def setChecked(self, checked: bool):
        """Set the checked state."""
        if self._checked != checked:
            self._checked = checked
            self._update_appearance()
            # Emit signal with Qt constants
            self.stateChanged.emit(Qt.Checked if checked else Qt.Unchecked)
    
    def toggle(self):
        """Toggle the checked state."""
        self.setChecked(not self._checked)
    
    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press to toggle state."""
        if event.button() == Qt.LeftButton:
            self.toggle()
        super().mousePressEvent(event)
    
    def enterEvent(self, event):
        """Handle mouse enter for hover effect."""
        self._hover = True
        self._update_appearance()
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """Handle mouse leave for hover effect."""
        self._hover = False
        self._update_appearance()
        super().leaveEvent(event)

# ========== CALENDAR WIDGET ==========

class PersianCalendarWidget(QWidget):
    """A custom widget for displaying a Persian calendar."""
    def __init__(self, tray_icon_parent: 'SystemTrayIcon'):
        super().__init__()
        self.tray_icon_parent = tray_icon_parent
        self.current_date = jdatetime.date.today()
        self.display_date = self.current_date
        self.day_labels = []
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
        """Initializes the user interface settings for the calendar widget."""
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        # Fixed size as per original main.py, no scaling
        self.setFixedSize(Config.CALENDAR_WIDTH, Config.CALENDAR_HEIGHT)
        self.setStyleSheet("QWidget { background: transparent; border: 0px solid transparent; }")

    def paintEvent(self, event):
        """Paints the background with rounded corners."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.HighQualityAntialiasing)
        rect = self.rect()
        rect_f = QRectF(rect)
        radius = Config.CALENDAR_BORDER_RADIUS_PX
        path = QPainterPath()
        path.addRoundedRect(rect_f, radius, radius)
        painter.fillPath(path, QColor(Config.CALENDAR_BACKGROUND_COLOR))
        painter.setClipPath(path)
        super().paintEvent(event)

    def _setup_layout_and_content(self):
        """Sets up the main layout and adds UI elements."""
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
        # Margins as per original main.py, no scaling
        self.inner_content_v_layout.setContentsMargins(15, 15, 15, 15)
        self.inner_content_v_layout.setSpacing(0)
        self.inner_content_v_layout_widget = QWidget()
        self.inner_content_v_layout_widget.setStyleSheet("QWidget {background: transparent;}")
        self.inner_content_v_layout_widget.setLayout(self.inner_content_v_layout)
        # Fixed width as per original main.py, no scaling
        self.inner_content_v_layout_widget.setFixedWidth(Config.CONTENT_INNER_WIDTH + 30)
        self.container_layout.addWidget(self.inner_content_v_layout_widget)
        self.container_layout.addStretch(1)

        # Top navigation (arrows and month/year)
        top_layout = QHBoxLayout()
        # Margins as per original main.py, no scaling
        top_layout.setContentsMargins(0, 0, 0, -5)
        # Spacing as per original main.py, no scaling
        top_layout.setSpacing(10)
        self.left_arrow_btn = self._make_nav_button("❮", self.next_month)
        self.right_arrow_btn = self._make_nav_button("❯", self.prev_month)

        self.month_year_container = QWidget()
        self.month_year_container.setStyleSheet("QWidget {background: transparent;}")
        month_year_layout = QHBoxLayout(self.month_year_container)
        # Spacing as per original main.py, no scaling
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

        # Today and Gregorian
        today_gregorian_layout = QHBoxLayout()
        # Margins as per original main.py, no scaling
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

        # Weekdays header
        weekday_layout = QHBoxLayout()
        # Spacing as per original main.py, no scaling
        weekday_layout.setSpacing(5)
        # Margins as per original main.py, no scaling
        weekday_layout.setContentsMargins(0, 0, 0, 10)
        weekday_layout.setDirection(QBoxLayout.RightToLeft)
        for day_name in Config.PERSIAN_WEEKDAYS:
            label = QLabel(day_name)
            label.setAlignment(Qt.AlignCenter)
            # Fixed size as per original main.py, no scaling
            label.setFixedSize(Config.DAY_LABEL_SIZE, Config.DAY_LABEL_SIZE)
            color = Config.HOLIDAY_COLOR if day_name == "ج" else "#b8b8b8"
            label.setStyleSheet(
                f"QLabel {{ color: {color}; font-weight: bold; font-size: 16px; "
                f"background: transparent; font-family: '{Config.FONT_FAMILY}'; }}"
            )
            weekday_layout.addWidget(label)
        self.inner_content_v_layout.addLayout(weekday_layout)

        # Calendar grid
        self.calendar_grid_layout = QGridLayout()
        # Spacing as per original main.py, no scaling
        self.calendar_grid_layout.setSpacing(5)
        self.calendar_grid_layout.setOriginCorner(Qt.TopRightCorner)
        self.inner_content_v_layout.addLayout(self.calendar_grid_layout)

        main_v_layout.addWidget(self.container)
        self._setup_calendar_grid()

    def _make_nav_button(self, text, slot, is_today=False):
        """Creates a navigation button for the calendar."""
        # Fixed sizes as per original main.py, no scaling
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

    def _make_header_label(self):
        """Creates a QLabel for the month/year header."""
        label = QLabel("")
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        label.setStyleSheet(
            f"QLabel {{ color: {Config.TEXT_COLOR}; font-size: {Config.FONT_SIZE_HEADER}px; "
            f"font-weight: bold; background: transparent; font-family: '{Config.FONT_FAMILY}'; }}"
        )
        return label

    def _setup_calendar_grid(self):
        """Sets up the grid layout for calendar days."""
        self.day_labels.clear()
        for row in range(6):
            week_labels = []
            for col in range(7):
                label = ClickableLabel()
                label.setAlignment(Qt.AlignCenter)
                # Fixed size as per original main.py, no scaling
                label.setFixedSize(Config.DAY_LABEL_SIZE, Config.DAY_LABEL_SIZE)
                self.calendar_grid_layout.addWidget(label, row, col)
                week_labels.append(label)
            self.day_labels.append(week_labels)

    def _fill_calendar_grid(self):
        """Fills the calendar grid with day numbers and applies styling."""
        self._update_labels_text()
        today_gregorian = jdatetime.date.today().togregorian()
        self.formatted_mdy = today_gregorian.strftime("%m/%d/%Y")
        self.formatted_month_day_year = today_gregorian.strftime("%b %d, %Y")
        self.gregorian_date_label.setText(self.formatted_mdy if self.show_mdy_format else self.formatted_month_day_year)
        
        for row_labels in self.day_labels:
            for label in row_labels:
                if isinstance(label, ClickableLabel):
                    try: label.clicked.disconnect()
                    except Exception: pass
                label.setText("")
                label.setToolTip("")
                label.setStyleSheet("")

        self._update_current_holidays()
        first_day = jdatetime.date(self.display_date.year, self.display_date.month, 1)
        start_col = first_day.weekday()
        prev_month_year = self.display_date.year - 1 if self.display_date.month == 1 else self.display_date.year
        prev_month_num = 12 if self.display_date.month == 1 else self.display_date.month - 1
        days_in_prev_month = max(d for d in (31, 30, 29) if safe_jdate(prev_month_year, prev_month_num, d))

        current_row, current_col = 0, start_col
        for col_offset in range(start_col):
            day_to_display = days_in_prev_month - (start_col - 1 - col_offset)
            label = self.day_labels[current_row][col_offset]
            label.setText(to_persian_digits(str(day_to_display)))
            label.setStyleSheet(self._grey_style())
            if isinstance(label, ClickableLabel):
                label.jalali_date = None

        days_in_month = max(d for d in (31, 30, 29) if safe_jdate(self.display_date.year, self.display_date.month, d))
        day = 1
        while day <= days_in_month:
            if current_row >= 6:
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
            is_holiday = (self.display_date.month, day) in self.holidays
            is_selected = (current_jdate == self.selected_date)
            
            style_background_color = "transparent"
            style_text_color = Config.TEXT_COLOR
            style_border = "none"
            style_font_size = Config.FONT_SIZE_LABEL # Original font size, no scaling
            style_hover_background_color = Config.HOVER_BG
            current_tooltip = ""

            # Apply holiday/Friday base styling
            if is_holiday or is_friday:
                style_text_color = Config.HOLIDAY_COLOR
                style_background_color = "rgba(255, 76, 76, 0.15)" # Light red background
                style_hover_background_color = "rgba(255, 76, 76, 0.3)" # Darker red on hover
                if is_holiday: # Only add tooltip if it's an actual holiday
                    current_tooltip = f"{self.holidays[(self.display_date.month, day)]}"

            # Apply "Today" specific styling if applicable
            if is_today:
                style_font_size = 17 # Larger font size for today, original value
                if not (is_holiday or is_friday): # If today is normal (not holiday/friday)
                    style_background_color = "rgba(128, 128, 128, 0.3)" # Grey background for normal today
                    style_border = "1px solid #FFFFFF" # White border for normal today
                    style_hover_background_color = Config.HOVER_BG # Default hover for normal today
                else: # If today is also a holiday/friday
                    style_border = f"1px solid {Config.HOLIDAY_COLOR}" # Red border for holiday/friday today
                
                # Tooltip for today: only show holiday if it is one, otherwise empty
                if is_holiday:
                    current_tooltip = f"تعطیلی: {self.holidays[(self.display_date.month, self.current_date.day)]}"
                else:
                    current_tooltip = "" # No "امروز" tooltip


            # Apply "Selected" styling if applicable (highest priority for background/border/hover)
            if is_selected:
                if is_today: # Selected day is also today
                    style_font_size = 17 # Keep today's font size
                    if is_holiday or is_friday: # Selected today and also holiday/friday
                        style_background_color = "rgba(255, 76, 76, 0.6)" # More opaque red for selected holiday/friday today
                        style_border = f"1px solid {Config.HOLIDAY_COLOR}"
                        style_hover_background_color = "rgba(255, 76, 76, 0.8)" # Even darker red on hover
                elif is_holiday or is_friday: # Selected day is holiday/friday (but not today)
                    style_background_color = "rgba(255, 76, 76, 0.5)" # More opaque red for selected holiday/friday
                    style_text_color = Config.HOLIDAY_COLOR
                    style_border = f"1px solid {Config.HOLIDAY_COLOR}"
                    style_hover_background_color = "rgba(255, 76, 76, 0.7)"
                    style_font_size = Config.FONT_SIZE_LABEL # Ensure normal size for non-today
                else: # Selected normal day (not today, not holiday/friday)
                    style_background_color = "rgba(128, 128, 128, 0.4)" # More opaque grey for selected normal day
                    style_text_color = Config.TEXT_COLOR
                    style_border = f"1px solid {Config.TEXT_COLOR}"
                    style_hover_background_color = "rgba(128, 128, 128, 0.6)"
                    style_font_size = Config.FONT_SIZE_LABEL # Ensure normal size for non-today
            
            # Construct the final stylesheet string
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

        next_day = 1
        for row_idx in range(current_row, 6):
            for col_idx in range(current_col if row_idx == current_row else 0, 7):
                label = self.day_labels[row_idx][col_idx]
                label.setText(to_persian_digits(str(next_day)))
                label.setStyleSheet(self._grey_style())
                if isinstance(label, ClickableLabel):
                    label.jalali_date = None
                next_day += 1

    def _update_labels_text(self):
        """Updates the text for month and year labels."""
        self.month_label.setText(persian_month_name(self.display_date.month))
        self.year_label.setText(to_persian_digits(str(self.display_date.year)))

    def _update_current_holidays(self):
        """Fetches and updates holidays for the current display year."""
        self.holidays = self.tray_icon_parent._fetch_and_cache_holidays(self.display_date.year)

    def prev_month(self):
        """Navigates to the previous month."""
        if self.display_date.month == 1:
            self.display_date = jdatetime.date(self.display_date.year - 1, 12, 1)
        else:
            self.display_date = jdatetime.date(self.display_date.year, self.display_date.month - 1, 1)
        self.selected_date = None
        self._fill_calendar_grid()

    def next_month(self):
        """Navigates to the next month."""
        if self.display_date.month == 12:
            self.display_date = jdatetime.date(self.display_date.year + 1, 1, 1)
        else:
            self.display_date = jdatetime.date(self.display_date.year, self.display_date.month + 1, 1)
        self.selected_date = None
        self._fill_calendar_grid()

    def go_to_today(self):
        """Navigates the calendar to today's date."""
        self.display_date = jdatetime.date.today()
        self.selected_date = self.display_date
        self._fill_calendar_grid()
        today_gregorian = jdatetime.date.today().togregorian()
        self.formatted_mdy = today_gregorian.strftime("%m/%d/%Y")
        self.formatted_month_day_year = today_gregorian.strftime("%b %d, %Y")
        self.gregorian_date_label.setText(self.formatted_mdy if self.show_mdy_format else self.formatted_month_day_year)

    def _on_day_label_clicked(self, jalali_date: jdatetime.date):
        """Handles a click on a day label, setting it as selected."""
        self.selected_date = jalali_date
        self._fill_calendar_grid() # Re-fill to apply new selection style

        if jalali_date:
            gregorian_date = jalali_date.togregorian()
            self.formatted_mdy = gregorian_date.strftime("%m/%d/%Y")
            self.formatted_month_day_year = gregorian_date.strftime("%b %d, %Y")
            self.gregorian_date_label.setText(self.formatted_mdy if self.show_mdy_format else self.formatted_month_day_year)
        else:
            today_gregorian = jdatetime.date.today().togregorian()
            self.formatted_mdy = today_gregorian.strftime("%m/%d/%Y")
            self.formatted_month_day_year = today_gregorian.strftime("%b %d, %Y")
            self.gregorian_date_label.setText(self.formatted_mdy if self.show_mdy_format else self.formatted_month_day_year)

    def _toggle_gregorian_format(self):
        """Toggles the format of the Gregorian date display."""
        self.show_mdy_format = not self.show_mdy_format
        self.gregorian_date_label.setText(self.formatted_mdy if self.show_mdy_format else self.formatted_month_day_year)

    def _grey_style(self):
        """Returns the stylesheet for greyed-out (previous/next month) day labels."""
        return (
            f"QLabel {{ background: transparent; border: none; font-size: {Config.FONT_SIZE_LABEL}px; "
            f"font-weight: bold; color: {Config.GREY_COLOR}; border-radius: 8px; font-family: '{Config.FONT_FAMILY}'; }}"
            f"QLabel:hover {{ background-color: rgba(128, 128, 128, 0.1); border-radius: 8px; }}"
        )

# ========== Custom Widget for Menu Actions ==========
class MenuActionWidget(QWidget):
    """
    A base custom widget to be used with QWidgetAction for menu items.
    It provides a QLabel for text and handles its own full-width hover effect by overriding paintEvent.
    """
    def __init__(self, text: str, parent=None, hover_color: str = "rgba(255, 255, 255, 0.1)"):
        super().__init__(parent)
        self._hover_color = hover_color
        self._is_hovered = False # Track hover state
        self.setContentsMargins(0, 0, 0, 0)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(15, 6, 15, 6) # Visual padding for content
        self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(30)
        
        # Set a proper background color that matches the menu theme
        self.setStyleSheet("""
            MenuActionWidget {
                background-color: transparent;
                border-radius: 6px;
            }
            MenuActionWidget:hover {
                background-color: rgba(255, 255, 255, 0.08);
            }
        """)
        self.setMouseTracking(True) # Enable mouse tracking for hover events

        self.label = QLabel(text)
        self.label.setStyleSheet(
            f"QLabel {{ color: {Config.TEXT_COLOR}; font-size: 14px; font-weight: bold; font-family: '{Config.FONT_FAMILY}'; background: transparent; }}"
        )
        self.label.setAlignment(Qt.AlignCenter)

        self.layout.addStretch()
        self.layout.addWidget(self.label)
        self.layout.addStretch()

    def paintEvent(self, event):
        """Paints the background based on hover state and then delegates to super."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.HighQualityAntialiasing)

        # Draw the background if hovered
        if self._is_hovered:
            rect_f = QRectF(self.rect())
            radius = 6 # Rounded corners matching menu
            path = QPainterPath()
            path.addRoundedRect(rect_f, radius, radius)
            # Use a lighter, more visible hover color
            painter.fillPath(path, QColor(60, 60, 60, 180))  # Semi-transparent gray instead of the problematic color

        # Always call super().paintEvent to draw child widgets (label, checkbox)
        super().paintEvent(event)

    def enterEvent(self, event):
        """Handle mouse entering the widget."""
        self._is_hovered = True
        self.update() # Request a repaint
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Handle mouse leaving the widget."""
        self._is_hovered = False
        self.update() # Request a repaint
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            event.accept()
        super().mousePressEvent(event)


class FontAwesomeCheckBox(QCheckBox):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.fa_font = QFont(Config.FONT_AWESOME_FAMILY, 14) # Font for the icon
        # Set the font for the checkbox text to 9pt
        self.setFont(QFont(Config.FONT_FAMILY, 9, QFont.Bold)) # Changed font size to 9
        self.setStyleSheet(f"""
            FontAwesomeCheckBox {{
                background: transparent;
                color: white; /* Default text color */
            }}
        """)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.HighQualityAntialiasing)

        # Create a QStyleOptionButton manually
        option = QStyleOptionButton()
        option.initFrom(self)
        
        # Determine the indicator's size and position
        indicator_size = QSize(18, 18) # Fixed size for the indicator
        indicator_rect = QApplication.style().subElementRect(QStyle.SE_CheckBoxIndicator, option, self)
        indicator_rect.setSize(indicator_size) # Ensure consistent size
        # Draw the custom indicator background and border
        # The color changes here based on the checked state
        painter.setBrush(QColor("White") if self.isChecked() else QColor("transparent"))
        painter.setPen(QColor("#606060"))
        painter.drawRoundedRect(indicator_rect, 3, 3) # Rounded corners for the box

        # Draw the Font Awesome icon if checked
        if self.isChecked():
            painter.setFont(self.fa_font)
            painter.setPen(QColor("#3c7dd1")) # Color of the checkmark
            # Draw the Font Awesome icon centered within the indicator's rectangle
            painter.drawText(indicator_rect, Qt.AlignCenter, "\uf14a") # \uf14a is the solid square checkmark

        # Draw the checkbox text label
        # Get the rectangle for the text content
        text_rect = QApplication.style().subElementRect(QStyle.SE_CheckBoxContents, option, self)
        text_rect.setLeft(text_rect.left() + 2)
        painter.setPen(QColor(Config.TEXT_COLOR)) # Set text color from Config
        painter.setFont(self.font()) # Use the widget's font for its text content
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, self.text())
        
        # No super().paintEvent(event) call needed as we are fully custom painting.


class CheckboxActionWidget(MenuActionWidget):  # Keep inheritance from MenuActionWidget
    """
    A custom widget for a QWidgetAction, containing a FontAwesome checkbox and a QLabel.
    It ensures that clicking anywhere on the widget toggles the checkbox and prevents
    the menu from closing automatically.
    """
    def __init__(self, text: str, is_checked: bool, parent=None, hover_color: str = "rgba(255, 255, 255, 0.1)"):
        super().__init__(text, parent=parent, hover_color=hover_color)

        # Clear the layout from the parent constructor to reconfigure for checkbox and label
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(15, 6, 15, 6)
        self.layout.setSpacing(10)  # Space between checkbox and label
        self.layout.setAlignment(Qt.AlignCenter)

        # Create FontAwesome checkbox
        self.checkbox = FontAwesomeCheckbox()
        self.checkbox.setChecked(is_checked)

        # Create label
        self.label = QLabel(text)
        self.label.setStyleSheet(
            f"QLabel {{ color: {Config.TEXT_COLOR}; font-size: 14px; font-weight: bold; "
            f"font-family: '{Config.FONT_FAMILY}'; background: transparent; }}"
        )
        self.label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # Add widgets to layout (checkbox first, then label)
        self.layout.addStretch()
        self.layout.addWidget(self.checkbox)
        self.layout.addWidget(self.label)
        self.layout.addStretch()

        # Set background style
        self.setStyleSheet("""
            CheckboxActionWidget {
                background-color: transparent;
                border-radius: 6px;
            }
        """)

    def paintEvent(self, event):
        """Paint the background based on hover state."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self._is_hovered:
            # Removed redundant imports here
            rect_f = QRectF(self.rect())
            radius = 6
            path = QPainterPath()
            path.addRoundedRect(rect_f, radius, radius)
            painter.fillPath(path, QColor(60, 60, 60, 180))

        super().paintEvent(event)

    def enterEvent(self, event):
        """Handle mouse entering the widget."""
        self._is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Handle mouse leaving the widget."""
        self._is_hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press to toggle checkbox."""
        if event.button() == Qt.LeftButton:
            # Toggle the checkbox when clicking anywhere on the widget
            self.checkbox.toggle()
            event.accept()  # Prevent menu from closing
        super().mousePressEvent(event)

    def isChecked(self):
        """Return the current checked state."""
        return self.checkbox.isChecked()

    def setChecked(self, checked: bool):
        """Set the checked state."""
        self.checkbox.setChecked(checked)

# ========== SYSTEM TRAY ICON ==========

class SystemTrayIcon(QSystemTrayIcon):
    """Represents the application's system tray icon."""
    def __init__(self):
        super().__init__()
        # No scaling factor for UI elements, maintaining original size

        self.data_dir = user_data_dir(Config.APP_NAME, Config.COMPANY_NAME)
        os.makedirs(self.data_dir, exist_ok=True)
        self.cache_file_path = os.path.join(self.data_dir, Config.CACHE_FILENAME)
        self.calendar_widget: Optional[PersianCalendarWidget] = None
        self._is_calendar_visible = False
        self.current_date: jdatetime.date = jdatetime.date.today()
        self.holidays_cache, self.last_checked_date = self._load_holidays_from_file()
        self.holidays = self.holidays_cache.get(self.current_date.year, {})
        self._perform_daily_update_check()
        QCoreApplication.setOrganizationName(Config.APP_NAME)
        QCoreApplication.setApplicationName(Config.APP_NAME)
        
        # Initialize QSettings and auto-start logic
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
        self._apply_startup_setting(self.is_open_at_login) # Apply initial startup setting

    def _load_holidays_from_file(self) -> Tuple[Dict[int, Dict[Tuple[int, int], str]], Optional[datetime.date]]:
        """Loads holiday data from a cached JSON file."""
        holidays_data: Dict[int, Dict[Tuple[int, int], str]] = {}
        last_checked = None
        if os.path.exists(self.cache_file_path):
            try:
                with open(self.cache_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    loaded_holidays_raw = data.get('holidays', {})
                    for year_str, holidays_for_year_raw in loaded_holidays_raw.items():
                        deserialized = {}
                        for month_day_str, desc in holidays_for_year_raw.items():
                            try:
                                month, day = map(int, month_day_str.split('-'))
                                deserialized[(month, day)] = desc
                            except ValueError:
                                logger.warning(f"Could not parse month-day '{month_day_str}' in year {year_str}")
                        holidays_data[int(year_str)] = deserialized
                    last_checked_str = data.get('last_checked_date')
                    if last_checked_str:
                        last_checked = datetime.datetime.strptime(last_checked_str, "%Y-%m-%d").date()
                logger.info(f"Holidays loaded from {self.cache_file_path}")
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.error(f"Error loading holidays from file: {e}. Starting with empty cache.")
        return holidays_data, last_checked

    def _save_holidays_to_file(self):
        """Saves holiday data to a JSON cache file."""
        try:
            serializable = {}
            for year, holidays_for_year in self.holidays_cache.items():
                serializable_inner = {
                    f"{month}-{day}": description
                    for (month, day), description in holidays_for_year.items()
                }
                serializable[str(year)] = serializable_inner
            last_checked_str = self.last_checked_date.strftime("%Y-%m-%d") if self.last_checked_date else None
            with open(self.cache_file_path, 'w', encoding='utf-8') as f:
                json.dump({'holidays': serializable, 'last_checked_date': last_checked_str},
                          f, ensure_ascii=False, indent=4)
            logger.info(f"Holidays saved to {self.cache_file_path}")
        except IOError as e:
            logger.error(f"Error saving holidays to file: {e}")

    def _fetch_and_cache_holidays(self, year: int) -> Dict[Tuple[int, int], str]:
        """Fetches holidays for a given year from API and caches them."""
        if year in self.holidays_cache:
            logger.debug(f"Holidays for {year} fetched from cache.")
            return self.holidays_cache[year]
        url = Config.API_URL_TEMPLATE.format(year=year)
        holidays_for_year = {}
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            json_data = response.json()
            data = json_data.get('data', [])
            for holiday_info in data:
                jalali_date_str = holiday_info.get('date')
                description = (
                    holiday_info.get('holidayDesription') or
                    holiday_info.get('holidayDescription')
                )
                if jalali_date_str and description:
                    try:
                        y, m, d = map(int, jalali_date_str.split('/'))
                        holidays_for_year[(m, d)] = description
                    except Exception as e:
                        logger.warning(f"Invalid Jalali date: {jalali_date_str}, error: {e}")
        except Exception as e:
            logger.error(f"Failed to fetch holidays for {year}: {e}")
            return self.holidays_cache.get(year, {})
        self.holidays_cache[year] = holidays_for_year
        self._save_holidays_to_file()
        return holidays_for_year

    def _update_current_holidays(self):
        """Updates the holidays for the current date's year."""
        self.holidays = self._fetch_and_cache_holidays(self.current_date.year)

    def _perform_daily_update_check(self):
        """Checks if a daily holiday update is needed and performs it."""
        today = datetime.date.today()
        if not self.last_checked_date or self.last_checked_date < today:
            logger.info(f"Performing daily holiday update for {today}")
            current_jalali_year = jdatetime.date.today().year
            for year in [current_jalali_year - 1, current_jalali_year, current_jalali_year + 1]:
                self._fetch_and_cache_holidays(year)
            self.last_checked_date = today
            self._save_holidays_to_file()
        else:
            logger.debug(f"Daily holiday check already performed for {today}")

    def _create_tray_icon(self):
        """
        Creates and sets the system tray icon with the current day.
        The day number displayed on the icon is already centered using Qt.AlignCenter.
        """
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        day_str = to_persian_digits(str(self.current_date.day))
        is_friday = self.current_date.weekday() == 6
        current_year_holidays = self.holidays_cache.get(self.current_date.year, {})
        is_holiday = (self.current_date.month, self.current_date.day) in current_year_holidays
        painter.setPen(QColor(Config.HOLIDAY_COLOR) if is_holiday or is_friday else QColor(255, 255, 255))
        # Original font size, no scaling
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
        tooltip = f"{weekday_name}\n{year_str}-{month_str}-{day_str_2}\n{day_str_2} {month_name} {year_str}"
        if is_holiday:
            tooltip += f"\n(تعطیلی: {current_year_holidays[(self.current_date.month, self.current_date.day)]})"
        self.setToolTip(tooltip)

    def update_tray_icon(self):
        """Updates the tray icon and calendar widget if the date changes."""
        new_date = jdatetime.date.today()
        if new_date != self.current_date:
            logger.info(f"Date changed: {self.current_date} → {new_date}")
            self.current_date = new_date
            self._perform_daily_update_check()
            self._update_current_holidays()
            self._create_tray_icon()
        if self.calendar_widget and self._is_calendar_visible:
            self.calendar_widget.current_date = new_date
            self.calendar_widget._fill_calendar_grid()

    def _toggle_open_at_boot(self, state: int):
        """Toggles the 'open at boot' setting for the application."""
        new_value = (state == Qt.Checked)
        self.settings.setValue(Config.AUTO_START_SETTING_KEY, new_value)
        self.is_open_at_login = new_value
        self._apply_startup_setting(new_value)
        logger.info(f"Open at boot set to: {new_value}")

    def _setup_context_menu(self):
        """Sets up the context menu for the system tray icon."""
        menu = QMenu()
        menu.setStyleSheet(
            f"QMenu {{ background-color: #2c2c2c; border: 1px solid #606060; border-radius: 8px; padding: 5px; }}"
            # IMPORTANT: Set padding and margin to 0 for QMenu::item
            # This ensures the QWidgetAction can fully control its own drawing area.
            # Also, remove any default background/selection styles from QMenu::item
            f"QMenu::item {{ background-color: transparent; padding: 0px; margin: 0px; }}" 
            f"QMenu::item:hover {{ background-color: transparent; }}" 
            f"QMenu::item:selected {{ background-color: transparent; }}"
            f"QMenu::separator {{ height: 1px; background-color: #606060; margin: 5px 0px; }}"
        )
        
        # QWidgetAction for "تبدیل تاریخ"
        convert_date_widget_action = QWidgetAction(self)
        convert_date_widget = MenuActionWidget("تبدیل تاریخ", parent=menu, hover_color="rgba(255, 255, 255, 0.08)")
        convert_date_widget_action.setDefaultWidget(convert_date_widget)
        convert_date_widget_action.triggered.connect(self._open_date_converter)
        menu.addAction(convert_date_widget_action)
        
        menu.addSeparator()
        
        # QWidgetAction for "اجرا هنگام روشن شدن"
        self.open_at_boot_action = QWidgetAction(self)
        self.open_at_boot_widget = CheckboxActionWidget(
            "راه اندازی همراه با سیستم", 
            self.is_open_at_login, 
            parent=menu,
            hover_color="rgba(255, 255, 255, 0.08)"
        )
        # Connect the stateChanged signal of the checkbox within the custom widget
        self.open_at_boot_widget.checkbox.stateChanged.connect(self._toggle_open_at_boot)
        self.open_at_boot_action.setDefaultWidget(self.open_at_boot_widget)
        
        if sys.platform.startswith('win'):
            menu.addAction(self.open_at_boot_action)
        menu.addSeparator()
        
        # QWidgetAction for "خروج"
        exit_widget_action = QWidgetAction(self)
        exit_widget = MenuActionWidget("خروج", parent=menu, hover_color="rgba(255, 76, 76, 0.15)") # Light red for exit
        exit_widget_action.setDefaultWidget(exit_widget)
        exit_widget_action.triggered.connect(QApplication.quit)
        menu.addAction(exit_widget_action)
        
        self.setContextMenu(menu)


    def _get_executable_path(self) -> str:
        """Returns the path to the main executable."""
        # For a PyInstaller bundled app, sys.executable points to the executable.
        # For a script run directly, sys.argv[0] points to the script.
        if getattr(sys, 'frozen', False): # Check if running as a bundled executable
            return sys.executable
        else:
            return os.path.abspath(sys.argv[0])

    def _apply_startup_setting(self, enable: bool):
        """Applies or removes the application from system startup."""
        app_path = self._get_executable_path()
        app_name = QCoreApplication.applicationName()

        if sys.platform.startswith('win'):
            self._set_windows_startup(app_path, app_name, enable)
        else:
            logger.warning(f"Auto-start is only supported on Windows for this application. Current platform: {sys.platform}")

    def _set_windows_startup(self, app_path: str, app_name: str, enable: bool):
        """Sets or unsets the application to run at Windows startup."""
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)

            if enable:
                # Add quotes around the path to handle spaces
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, f'"{app_path}"')
                logger.info(f"Added '{app_name}' to Windows startup: '{app_path}'")
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                    logger.info(f"Removed '{app_name}' from Windows startup.")
                except FileNotFoundError:
                    # Value doesn't exist, no need to delete
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            logger.error(f"Error setting Windows startup for '{app_name}': {e}")

    def _verify_and_update_startup_path(self):
        """Verifies and updates the application's path in startup settings if needed."""
        if not sys.platform.startswith('win'):
            return # Only applies to Windows

        current_app_path = self._get_executable_path()
        app_name = QCoreApplication.applicationName()

        import winreg
        reg_path_in_startup = None

        try:
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
            reg_path_raw, _ = winreg.QueryValueEx(key, app_name)
            winreg.CloseKey(key)
            reg_path_in_startup = reg_path_raw.strip('"') # Remove quotes from the path
            logger.debug(f"Current Registry startup path for {app_name}: {reg_path_in_startup}")
        except FileNotFoundError:
            logger.debug(f"'{app_name}' not found in Windows startup registry.")
        except Exception as e:
            logger.error(f"Error reading Windows startup registry for '{app_name}': {e}")

        # Condition 1: App is supposed to open at login (according to QSettings)
        # Condition 2: But the path in the registry is either wrong or missing
        if self.is_open_at_login and reg_path_in_startup != current_app_path:
            logger.info(f"Startup path discrepancy detected. Updating Registry for '{app_name}'.")
            self._set_windows_startup(current_app_path, app_name, True) # Force update with current path
        # Condition 3: App is NOT supposed to open at login (according to QSettings)
        # Condition 4: But there's still an entry in the registry
        elif not self.is_open_at_login and reg_path_in_startup is not None:
             logger.info(f"Startup setting disabled, but old entry found. Removing Registry entry for '{app_name}'.")
             self._set_windows_startup(current_app_path, app_name, False) # Force removal
        else:
            logger.info(f"Startup path for '{app_name}' is consistent with settings.")


    def _open_date_converter(self):
        """Opens the date converter window."""
        if not hasattr(self, 'converter_window'):
            self.converter_window = DateConverterWindow()
        self.converter_window.show()
        self.converter_window.activateWindow()
        self.converter_window.raise_()

    def on_tray_icon_activated(self, reason):
        """Handles activation events of the system tray icon."""
        if reason == QSystemTrayIcon.Trigger:
            if self._is_calendar_visible:
                self.hide_calendar()
            else:
                self.show_calendar()

    def show_calendar(self):
        """Shows the calendar widget."""
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
        if tray_geometry.isValid():
            target_x = tray_geometry.center().x() - widget_width // 2
            # Reverted to original positioning logic from main.py
            target_y = tray_geometry.top() - widget_height - 5 
            if target_y < 0:
                target_y = tray_geometry.bottom() + 5
        else:
            target_x = screen.width() - widget_width - 20
            target_y = 20
        target_x = max(0, min(target_x, screen.width() - widget_width))
        target_y = max(0, min(target_y, screen.height() - widget_height))
        self.calendar_widget.move(target_x, target_y)

# ========== MAIN ==========

def main():
    """Main function to run the application."""
    myappid = 'Rayden.ShamsiTray.TrayApp.1.0' # IMPORTANT: Replace with a unique ID for your app
    if sys.platform == 'win32':
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    app = QApplication(sys.argv)
    if os.path.exists(Config.ICON_PATH):
       app.setWindowIcon(QIcon(Config.ICON_PATH))
    else:
       logger.warning(f"Application icon file not found: {Config.ICON_PATH}")
    app.setWindowIcon(QIcon.fromTheme("applications-other"))
    load_fonts() # Ensure fonts are loaded before any widgets that use them are created
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
