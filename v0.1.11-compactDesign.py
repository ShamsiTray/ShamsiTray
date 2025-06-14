import sys
import jdatetime
import requests
import datetime
import json
import os
import logging
from typing import Optional, Dict, Tuple, Any
from appdirs import user_data_dir

from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QBoxLayout,
                             QLabel, QPushButton, QGridLayout, QSystemTrayIcon,
                             QMenu, QFrame)
from PyQt5.QtCore import Qt, QTimer, QRect, QRectF, QEvent, pyqtSignal # Added pyqtSignal
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QFont, QColor, QPainterPath

# ------------------ CONFIG & CONSTANTS ------------------

class Config:
    FONT_FAMILY = "Vazirmatn"
    FONT_SIZE_LABEL = 15
    FONT_SIZE_HEADER = 28
    DAY_LABEL_SIZE = 35
    CALENDAR_BG_COLOR = "#2c2c2c"
    HOLIDAY_COLOR = "#FF4C4C"
    TEXT_COLOR = "#e0e0e0"
    GREY_COLOR = "#808080"
    HOVER_BG = "rgba(255, 255, 255, 0.08)" # This is the semi-transparent color
    API_URL_TEMPLATE = "https://api.persian-calendar.ir/api/v1/calendar/{year}/holidays"
    CACHE_FILENAME = "holidays_cache.json"
    APP_NAME = "PersianCalendarTray"
    COMPANY_NAME = ""  # For appdirs
    LOG_LEVEL = logging.DEBUG

    PERSIAN_DIGITS = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹']
    PERSIAN_MONTHS = [
        "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
        "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"
    ]
    PERSIAN_WEEKDAYS = ["ش", "ی", "د", "س", "چ", "پ", "ج"]
    PERSIAN_WEEKDAY_NAMES = [
        "شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه"
    ]

    # Calculate optimal calendar dimensions based on content and desired padding
    # Content width: 7 days * DAY_LABEL_SIZE + 6 * spacing (5px) = 7*35 + 6*5 = 245 + 30 = 275px
    CONTENT_INNER_WIDTH = 275
    # Add 15px padding on left and right for the outer container: 275 + 15 + 15 = 305px
    CALENDAR_WIDTH = 305

    # Content height calculation (approximate):
    # Top Layout Height (Header area): ~45px
    # Today/Gregorian button row: 30px (button height) + 10px (bottom margin) = 40px
    # Weekday header row: 35px (label height) + 10px (bottom margin) = 45px
    # 6 rows of days (6 * 35px = 210px) + 5 rows of grid spacing (5 * 5px = 25px) = 235px
    # Total content height = 45 + 40 + 45 + 235 = 365px
    # Add 15px padding on top and bottom for the outer container: 365 + 15 + 15 = 395px.
    CALENDAR_HEIGHT = 395


# ------------------ LOGGING SETUP ------------------

logging.basicConfig(
    format='[%(levelname)s] %(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=Config.LOG_LEVEL
)
logger = logging.getLogger(__name__)

# ------------------ UTILITY FUNCTIONS ------------------

def to_persian_digits(s: str) -> str:
    """Convert string of digits to Persian digits."""
    return ''.join(Config.PERSIAN_DIGITS[int(ch)] if ch.isdigit() else ch for ch in s)

def persian_month_name(month: int) -> str:
    return Config.PERSIAN_MONTHS[month - 1]

def persian_weekday_name(weekday: int) -> str:
    return Config.PERSIAN_WEEKDAY_NAMES[weekday]

def safe_jdate(year: int, month: int, day: int) -> Optional[jdatetime.date]:
    """Return a valid jdatetime.date or None if invalid."""
    try:
        return jdatetime.date(year, month, day)
    except ValueError:
        return None

# ------------------ CUSTOM CLICKABLE LABEL ------------------
class ClickableLabel(QLabel):
    """
    A QLabel that emits a signal when clicked, carrying the associated jdatetime.date.
    """
    clicked = pyqtSignal(jdatetime.date)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.jalali_date: Optional[jdatetime.date] = None

    def mousePressEvent(self, event):
        """Handle mouse press events for click detection."""
        if event.button() == Qt.LeftButton and self.jalali_date:
            self.clicked.emit(self.jalali_date)
        super().mousePressEvent(event)

# ------------------ PERSIAN CALENDAR WIDGET ------------------

class PersianCalendarWidget(QWidget):
    """
    Persian (Jalali) calendar widget with RTL day ordering and holiday display.
    """
    def __init__(self, tray_icon_parent: 'SystemTrayIcon'):
        super().__init__()
        self.tray_icon_parent = tray_icon_parent
        self.current_date = jdatetime.date.today()
        self.display_date = self.current_date
        self.holidays_cache = self.tray_icon_parent.holidays_cache
        self.holidays = self.holidays_cache.get(self.display_date.year, {})
        self._init_ui()
        self._setup_layout_and_content()
        self.update_calendar()

    def _init_ui(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Popup)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setStyleSheet("QWidget { background: transparent; }")
        self.setFixedSize(Config.CALENDAR_WIDTH, Config.CALENDAR_HEIGHT)

    def paintEvent(self, event):
        temp_pixmap = QPixmap(self.size())
        temp_pixmap.fill(QColor(Config.CALENDAR_BG_COLOR))
    
        painter = QPainter(temp_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0, 0, self.width(), self.height())
        path = QPainterPath()
        path.addRoundedRect(rect, 25, 25)
        painter.setClipPath(path)
        painter.fillPath(path, QColor(Config.CALENDAR_BG_COLOR))
        painter.end()
    
        final_painter = QPainter(self)
        final_painter.drawPixmap(0, 0, temp_pixmap)

    def _setup_layout_and_content(self):
        main_v_layout = QVBoxLayout(self)
        main_v_layout.setContentsMargins(0, 0, 0, 0)
        main_v_layout.setSpacing(0)

        self.container = QFrame(self)
        self.container.setStyleSheet("""
            QFrame {background: transparent; border-radius: 25px;}
        """)
        # This container_layout now serves as the outermost layout within the rounded frame.
        # It holds a central_content_v_layout that ensures fixed width and alignment.
        self.container_layout = QHBoxLayout(self.container) # Changed to QHBoxLayout
        self.container_layout.setContentsMargins(0, 0, 0, 0) # No margins here, handled by padding in inner layout
        self.container_layout.setSpacing(0)

        # Left stretch to center the content horizontally
        self.container_layout.addStretch(1)

        # --- NEW: Inner vertical layout for all core content to ensure fixed width and vertical stacking ---
        self.inner_content_v_layout = QVBoxLayout()
        self.inner_content_v_layout.setContentsMargins(15, 15, 15, 15) # Consistent padding around content
        self.inner_content_v_layout.setSpacing(0) # Keep spacing between layouts inside this

        # Set fixed width for the inner content layout
        self.inner_content_v_layout_widget = QWidget()
        self.inner_content_v_layout_widget.setLayout(self.inner_content_v_layout)
        self.inner_content_v_layout_widget.setFixedWidth(Config.CONTENT_INNER_WIDTH + 30) # Content width + inner margins (15px left/right)

        # Add the inner content layout to the main container layout
        self.container_layout.addWidget(self.inner_content_v_layout_widget)


        # Right stretch to center the content horizontally
        self.container_layout.addStretch(1)

        # Top navigation (arrows and month/year) - Now added to inner_content_v_layout
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, -5) # Adjust vertical spacing within inner content
        top_layout.setSpacing(10)
        
        self.left_arrow_btn = self._make_nav_button("❮")
        self.right_arrow_btn = self._make_nav_button("❯")
        self.left_arrow_btn.clicked.connect(self.next_month)
        self.right_arrow_btn.clicked.connect(self.prev_month)

        self.month_year_container = QWidget()
        month_year_layout = QHBoxLayout(self.month_year_container)
        month_year_layout.setSpacing(5)
        month_year_layout.setContentsMargins(0,0,0,0)
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
        self.inner_content_v_layout.addLayout(top_layout) # Add to inner_content_v_layout


        # "Today" button and Gregorian date display
        today_gregorian_layout = QHBoxLayout()
        today_gregorian_layout.setContentsMargins(0, 0, 0, 10) # Add some margin below this row
        
        # Gregorian date label (invisible box)
        self.gregorian_date_label = QLabel("")
        self.gregorian_date_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.gregorian_date_label.setStyleSheet(f"""
            QLabel {{
                color: {Config.TEXT_COLOR};
                font-size: {Config.FONT_SIZE_LABEL}px;
                background: transparent; /* Makes it "invisible" until text */
                font-family: "{Config.FONT_FAMILY}";
                padding: 0px; margin: 0px;
                font-weight: bold;
            }}
        """)
        self.gregorian_date_label.setWordWrap(False) # Prevent wrapping for date string

        # "Today" button setup
        self.today_btn = self._make_nav_button("امروز")
        self.today_btn.clicked.connect(self.go_to_today)
        # Apply permanent semi-transparent background to the "Today" button
        self.today_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Config.HOVER_BG};
                color: {Config.TEXT_COLOR}; border: none;
                font-weight: bold; font-size: 20px; font-family: "{Config.FONT_FAMILY}";
                padding-top: 2px; outline: none; border-radius: 8px;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.15); /* Slightly darker on hover */
                border-radius: 8px;
            }}
            QPushButton:pressed {{
                background: rgba(255, 255, 255, 0.10); /* Even darker on press */
            }}
        """)
        self.today_btn.setFixedSize(60, 30) # Ensure size is maintained for "امروز"

        today_gregorian_layout.addWidget(self.gregorian_date_label)
        today_gregorian_layout.addStretch(1) # Stretch between Gregorian label and Today button
        today_gregorian_layout.addWidget(self.today_btn)
        self.inner_content_v_layout.addLayout(today_gregorian_layout) # Add to inner_content_v_layout


        # Weekdays header - Now added to inner_content_v_layout
        weekday_layout = QHBoxLayout()
        weekday_layout.setSpacing(5)
        weekday_layout.setContentsMargins(0, 0, 0, 10) # Keep original vertical margin
        weekday_layout.setDirection(QBoxLayout.RightToLeft)
        for day_name in Config.PERSIAN_WEEKDAYS:
            label = QLabel(day_name)
            label.setAlignment(Qt.AlignCenter)
            label.setFixedSize(Config.DAY_LABEL_SIZE, Config.DAY_LABEL_SIZE)
            color = Config.HOLIDAY_COLOR if day_name == "ج" else "#b8b8b8"
            label.setStyleSheet(f"""
                QLabel {{
                    color: {color}; font-weight: bold; font-size: 16px;
                    background: transparent; font-family: "{Config.FONT_FAMILY}";
                }}
            """)
            weekday_layout.addWidget(label)
        self.inner_content_v_layout.addLayout(weekday_layout) # Add to inner_content_v_layout

        # Calendar grid - Now added to inner_content_v_layout
        self.calendar_grid_layout = QGridLayout()
        self.calendar_grid_layout.setSpacing(5)
        self.calendar_grid_layout.setOriginCorner(Qt.TopRightCorner)
        self.inner_content_v_layout.addLayout(self.calendar_grid_layout) # Add to inner_content_v_layout

        # Add the overall container (which now contains the horizontally centered inner_content_v_layout_widget)
        # to the main_v_layout
        main_v_layout.addWidget(self.container)
        
        self._setup_calendar_grid() # This populates the calendar_grid_layout

    def _make_nav_button(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(30, 30) # Smaller size for nav arrows
        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Config.TEXT_COLOR}; border: none;
                font-weight: bold; font-size: 20px; font-family: "{Config.FONT_FAMILY}";
                padding-top: 2px; outline: none;
            }}
            QPushButton:hover {{
                background-color: {Config.HOVER_BG}; border-radius: 8px;
            }}
            QPushButton:pressed {{
                background: rgba(255, 255, 255, 0.05);
            }}
        """)
        return btn

    def _make_header_label(self) -> QLabel:
        label = QLabel("")
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        label.setStyleSheet(f"""
            QLabel {{
                color: {Config.TEXT_COLOR}; font-size: {Config.FONT_SIZE_HEADER}px;
                font-weight: bold; background: transparent;
                font-family: "{Config.FONT_FAMILY}"; padding: 0px; margin: 0px;
            }}
        """)
        return label

    def _update_current_holidays(self):
        self.holidays = self.tray_icon_parent._fetch_and_cache_holidays(self.display_date.year)

    def _update_labels_text(self):
        self.month_label.setText(persian_month_name(self.display_date.month))
        persian_year_text = to_persian_digits(str(self.display_date.year))
        self.year_label.setText(persian_year_text)

    def _setup_calendar_grid(self):
        # Clear existing labels and widgets from the layout
        self.day_labels = [] # Ensure day_labels is empty before populating
        while self.calendar_grid_layout.count():
            child = self.calendar_grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Populate the grid with new ClickableLabel instances
        for row in range(6):
            week_labels = []
            for col in range(7):
                label = ClickableLabel() # Use ClickableLabel
                label.setAlignment(Qt.AlignCenter)
                label.setFixedSize(Config.DAY_LABEL_SIZE, Config.DAY_LABEL_SIZE)
                # Style will be applied in _fill_calendar_grid based on date properties
                self.calendar_grid_layout.addWidget(label, row, col)
                week_labels.append(label)
            self.day_labels.append(week_labels) # CORRECT: Append each row's labels here


    def _default_label_style(self) -> str:
        return f"""
            QLabel {{
                background: transparent; border: none; font-size: {Config.FONT_SIZE_LABEL}px;
                font-weight: bold; color: {Config.TEXT_COLOR};
                border-radius: 8px; font-family: "{Config.FONT_FAMILY}";
            }}
            QLabel:hover {{
                background-color: {Config.HOVER_BG}; border-radius: 8px;
            }}
        """

    def update_calendar(self):
        self._update_labels_text()
        # Clear Gregorian date display when calendar updates
        self.gregorian_date_label.setText("") 
        # Clear labels and disconnect signals
        for row_labels in self.day_labels: # Iterate through rows
            for label in row_labels:       # Iterate through labels in each row
                if isinstance(label, ClickableLabel):
                    try:
                        label.clicked.disconnect(self._on_day_label_clicked)
                    except TypeError:
                        pass # Signal not connected or already disconnected
        
        # Call _setup_calendar_grid to re-create labels and grid widgets properly
        # This implicitly clears the old widgets from the layout.
        self._setup_calendar_grid() 
        
        # Fill grid
        self._fill_calendar_grid()

    def _fill_calendar_grid(self):
        # Styles
        default_style = self._default_label_style()
        holiday_friday_style = f"""
            QLabel {{
                background-color: rgba(255, 76, 76, 0.15);
                color: {Config.HOLIDAY_COLOR}; border-radius: 8px;
                font-size: {Config.FONT_SIZE_LABEL}px; font-weight: bold;
                border: none; font-family: "{Config.FONT_FAMILY}";
            }}
            QLabel:hover {{
                background-color: rgba(255, 76, 76, 0.3); border-radius: 8px;
            }}
        """
        today_normal_style = f"""
            QLabel {{
                
                background-color: rgba(128, 128, 128, 0.3); color: {Config.TEXT_COLOR};
                border: 1px solid #FFFFFF; border-radius: 8px;
                font-size: 17px; font-weight: bold; font-family: "{Config.FONT_FAMILY}";
            }}
            QLabel:hover {{
                background-color: {Config.HOVER_BG}; border: 1px solid #FFFFFF; border-radius: 8px;
            }}
        """
        today_holiday_friday_style = f"""
            QLabel {{
                background-color: rgba(255, 76, 76, 0.15);
                color: {Config.HOLIDAY_COLOR}; border: 1px solid {Config.HOLIDAY_COLOR};
                border-radius: 8px; font-size: 17px; font-weight: bold; font-family: "{Config.FONT_FAMILY}";
            }}
            QLabel:hover {{
                background-color: rgba(255, 76, 76, 0.3); border: 1px solid {Config.HOLIDAY_COLOR}; border-radius: 8px;
            }}
        """
        grey_style = f"""
            QLabel {{
                background: transparent; border: none; font-size: {Config.FONT_SIZE_LABEL}px;
                font-weight: bold; color: {Config.GREY_COLOR}; border-radius: 8px;
                font-family: "{Config.FONT_FAMILY}";
            }}
            QLabel:hover {{
                background-color: rgba(128, 128, 128, 0.1); border-radius: 8px;
            }}
        """

        # Calculate first day
        first_day = jdatetime.date(self.display_date.year, self.display_date.month, 1)
        start_col = first_day.weekday()

        # Previous month days (non-clickable)
        prev_month_year = self.display_date.year - 1 if self.display_date.month == 1 else self.display_date.year
        prev_month_num = 12 if self.display_date.month == 1 else self.display_date.month - 1
        days_in_prev_month = 31
        for d in (31, 30, 29):
            if safe_jdate(prev_month_year, prev_month_num, d):
                days_in_prev_month = d
                break

        current_row, current_col = 0, start_col
        for col_offset in range(start_col):
            day_to_display = days_in_prev_month - (start_col - 1 - col_offset)
            label = self.day_labels[current_row][col_offset]
            label.setText(to_persian_digits(str(day_to_display)))
            label.setStyleSheet(grey_style)
            if isinstance(label, ClickableLabel):
                label.jalali_date = None # Ensure non-clickable for prev/next month days


        # Current month days (clickable)
        days_in_month = 31
        for d in (31, 30, 29):
            if safe_jdate(self.display_date.year, self.display_date.month, d):
                days_in_month = d
                break

        day = 1
        while day <= days_in_month:
            if current_row >= 6:
                logger.warning(f"Calendar overflow month={self.display_date.month} year={self.display_date.year}")
                break
            
            label = self.day_labels[current_row][current_col]
            current_jdate = jdatetime.date(self.display_date.year, self.display_date.month, day)
            
            label.setText(to_persian_digits(str(day)))
            
            if isinstance(label, ClickableLabel):
                label.jalali_date = current_jdate # Set the jdatetime.date for clickable labels
                label.clicked.connect(self._on_day_label_clicked) # Connect the signal
                
            actual_weekday = (first_day.weekday() + day - 1) % 7
            is_today = (day == self.current_date.day and
                        self.display_date.month == self.current_date.month and
                        self.display_date.year == self.current_date.year)
            is_friday = actual_weekday == 6
            is_holiday = (self.display_date.month, day) in self.holidays
            if is_today:
                tooltip = "امروز"
                if is_holiday:
                    tooltip += f" (تعطیلی: {self.holidays[(self.display_date.month, day)]})"
                label.setToolTip(tooltip)
                label.setStyleSheet(today_holiday_friday_style if (is_holiday or is_friday) else today_normal_style)
            elif is_holiday or is_friday:
                if is_holiday:
                    label.setToolTip(self.holidays[(self.display_date.month, day)])
                label.setStyleSheet(holiday_friday_style)
            else:
                label.setStyleSheet(default_style)

            day += 1
            current_col += 1
            if current_col > 6:
                current_col = 0
                current_row += 1

        # Next month days (non-clickable)
        next_day = 1
        for row_idx in range(current_row, 6):
            for col_idx in range(current_col if row_idx == current_row else 0, 7):
                label = self.day_labels[row_idx][col_idx]
                label.setText(to_persian_digits(str(next_day)))
                label.setStyleSheet(grey_style)
                if isinstance(label, ClickableLabel):
                    label.jalali_date = None # Ensure non-clickable for prev/next month days
                next_day += 1

    def prev_month(self):
        previous_year = self.display_date.year
        if self.display_date.month == 1:
            self.display_date = jdatetime.date(self.display_date.year - 1, 12, 1)
        else:
            self.display_date = jdatetime.date(self.display_date.year, self.display_date.month - 1, 1)
        if self.display_date.year != previous_year:
            self.holidays = self.tray_icon_parent._fetch_and_cache_holidays(self.display_date.year)
        else:
            self.holidays = self.holidays_cache.get(self.display_date.year, {})
        self.update_calendar()

    def next_month(self):
        previous_year = self.display_date.year
        if self.display_date.month == 12:
            self.display_date = jdatetime.date(self.display_date.year + 1, 1, 1)
        else:
            self.display_date = jdatetime.date(self.display_date.year, self.display_date.month + 1, 1)
        if self.display_date.year != previous_year:
            self.holidays = self.tray_icon_parent._fetch_and_cache_holidays(self.display_date.year)
        else:
            self.holidays = self.holidays_cache.get(self.display_date.year, {})
        self.update_calendar()

    def go_to_today(self):
        """Resets the calendar view to the current date."""
        self.display_date = jdatetime.date.today()
        self._update_current_holidays()
        self.update_calendar()

    def _on_day_label_clicked(self, jalali_date: jdatetime.date):
        """
        Slot to handle clicks on day labels and display the Gregorian equivalent.
        """
        if jalali_date: # Ensure a valid date was passed
            gregorian_date = jalali_date.togregorian()
            # Format as "Mon DD, YYYY" (e.g., Jun 07, 2025)
            formatted_gregorian_date = gregorian_date.strftime("%b %d, %Y")
            self.gregorian_date_label.setText(formatted_gregorian_date)
        else:
            self.gregorian_date_label.setText("") # Clear if an invalid date is clicked (shouldn't happen with current logic)


# ------------------ SYSTEM TRAY ICON ------------------

class SystemTrayIcon(QSystemTrayIcon):
    """
    QSystemTrayIcon for Persian Calendar.
    """

    def __init__(self):
        super().__init__()
        self.data_dir = user_data_dir(Config.APP_NAME, Config.COMPANY_NAME)
        os.makedirs(self.data_dir, exist_ok=True)
        self.cache_file_path = os.path.join(self.data_dir, Config.CACHE_FILENAME)
        self.calendar_widget: Optional[PersianCalendarWidget] = None
        self._is_calendar_visible = False
        self.current_date: jdatetime.date = jdatetime.date.today()
        self.holidays_cache, self.last_checked_date = self._load_holidays_from_file()
        self.holidays = self.holidays_cache.get(self.current_date.year, {})
        self._perform_daily_update_check()
        self._create_tray_icon()
        self._setup_context_menu()
        self.activated.connect(self.on_tray_icon_activated)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_tray_icon)
        self.timer.start(60000)

    def _load_holidays_from_file(self) -> Tuple[Dict[int, Dict[Tuple[int, int], str]], Optional[datetime.date]]:
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
        try:
            serializable = {}
            for year, holidays_for_year in self.holidays_cache.items():
                serializable_inner = {f"{month}-{day}": description
                                     for (month, day), description in holidays_for_year.items()}
                serializable[str(year)] = serializable_inner
            last_checked_str = self.last_checked_date.strftime("%Y-%m-%d") if self.last_checked_date else None
            with open(self.cache_file_path, 'w', encoding='utf-8') as f:
                json.dump({'holidays': serializable, 'last_checked_date': last_checked_str},
                          f, ensure_ascii=False, indent=4)
            logger.info(f"Holidays saved to {self.cache_file_path}")
        except IOError as e:
            logger.error(f"Error saving holidays to file: {e}")

    def _fetch_and_cache_holidays(self, year: int) -> Dict[Tuple[int, int], str]:
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
                # Note: The API typo "holidayDesription" is preserved for compatibility.
                jalali_date_str = holiday_info.get('date')
                description = holiday_info.get('holidayDesription')
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
        self.holidays = self._fetch_and_cache_holidays(self.current_date.year)

    def _perform_daily_update_check(self):
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
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        day_str = to_persian_digits(str(self.current_date.day))
        is_friday = self.current_date.weekday() == 6
        current_year_holidays = self.holidays_cache.get(self.current_date.year, {})
        is_holiday = (self.current_date.month, self.current_date.day) in current_year_holidays
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
        tooltip = f"{weekday_name}\n{year_str}-{month_str}-{day_str_2}\n{day_str_2} {month_name} {year_str}"
        if is_holiday:
            tooltip += f"\n(تعطیلی: {current_year_holidays[(self.current_date.month, self.current_date.day)]})"
        self.setToolTip(tooltip)

    def update_tray_icon(self):
        new_date = jdatetime.date.today()
        if new_date != self.current_date:
            logger.info(f"Date changed: {self.current_date} → {new_date}")
            self.current_date = new_date
            self._update_current_holidays()
            self._create_tray_icon()
        self._perform_daily_update_check()
        if self.calendar_widget and self._is_calendar_visible:
            self.calendar_widget.current_date = new_date
            self.calendar_widget._update_current_holidays()
            self.calendar_widget.update_calendar()

    def _setup_context_menu(self):
        menu = QMenu()
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {Config.CALENDAR_BG_COLOR};
                border: 1px solid #606060;
                border-radius: 8px; padding: 5px;
            }}
            QMenu::item {{
                color: {Config.TEXT_COLOR}; background-color: transparent;
                padding: 6px 15px; margin: 2px 0px; border-radius: 6px;
                font-size: 14px; font-weight: bold; font-family: "{Config.FONT_FAMILY}";
            }}
            QMenu::item:selected {{
                background-color: rgba(255, 76, 76, 0.2);
                color: {Config.HOLIDAY_COLOR};
            }}
            QMenu::separator {{
                height: 1px; background-color: #606060; margin: 5px 0px;
            }}
        """)
        exit_action = menu.addAction("خروج")
        exit_action.triggered.connect(QApplication.quit)
        self.setContextMenu(menu)

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.toggle_calendar()

    def toggle_calendar(self):
        if not self.calendar_widget:
            self.calendar_widget = PersianCalendarWidget(self)
            self.calendar_widget.installEventFilter(self)
        if self._is_calendar_visible:
            self.calendar_widget.hide()
            self._is_calendar_visible = False
        else:
            self.calendar_widget.show()
            self.position_calendar_above_tray()
            self.calendar_widget.activateWindow()
            self.calendar_widget.raise_()
            self._is_calendar_visible = True
            self.calendar_widget.current_date = jdatetime.date.today()
            self.calendar_widget._update_current_holidays()
            self.calendar_widget.update_calendar()

    def eventFilter(self, obj, event):
        if obj == self.calendar_widget:
           if event.type() == QEvent.WindowDeactivate or event.type() == QEvent.FocusOut:
            if self._is_calendar_visible:
                self.calendar_widget.hide()
                self._is_calendar_visible = False
                return True
        return super().eventFilter(obj, event)

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

# ------------------ MAIN ------------------

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(f"""
        QToolTip {{
            background-color: #3a3a3a;
            color: {Config.HOLIDAY_COLOR};
            border: 1px solid #606060;
            border-radius: 8px;
            padding: 5px 8px;
            font-size: 14px;
            font-weight: bold;
        }}
    """)
    if not QSystemTrayIcon.isSystemTrayAvailable():
        logger.critical("System tray not available.")
        sys.exit(1)
    tray_icon = SystemTrayIcon()
    tray_icon.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()