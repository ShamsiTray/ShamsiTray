import sys
import jdatetime
import requests
import datetime
import json
import os
from appdirs import user_data_dir # For cross-platform data directory handling

from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QBoxLayout,
                             QLabel, QPushButton, QGridLayout, QSystemTrayIcon,
                             QMenu, QFrame)
from PyQt5.QtCore import Qt, QTimer, QRect, QEvent
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QFont, QColor, QPen, QPainterPath


class PersianCalendarWidget(QWidget):
    """
    A widget that displays a Persian (Jalali) calendar with right-to-left day ordering.
    It supports displaying holidays, today's date, and navigation through months and years.
    It receives holiday data and its cache from the SystemTrayIcon.
    """

    def __init__(self, tray_icon_parent): # Pass reference to SystemTrayIcon
        super().__init__()
        self.tray_icon_parent = tray_icon_parent # Store reference to SystemTrayIcon
        self.current_date = jdatetime.date.today()
        self.display_date = self.current_date
        # Access holidays_cache from the parent SystemTrayIcon
        self.holidays_cache = self.tray_icon_parent.holidays_cache
        # Initialize holidays for the current display year from the shared cache
        self.holidays = self.holidays_cache.get(self.display_date.year, {})

        self.initUI()
        self.setup_layout_and_content()

        self.update_calendar() # Initial calendar display

    def initUI(self):
        """
        Initializes the main window properties, including flags for framelessness
        and transparency.
        """
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Popup)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setStyleSheet("QWidget { background: transparent; }")

        self.setFixedSize(380, 430)

    def paintEvent(self, event):
        """
        Overrides the paint event to draw the custom rounded background.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(float(self.rect().x()), float(self.rect().y()),
                            float(self.rect().width()), float(self.rect().height()),
                            25, 25)

        painter.fillPath(path, QColor("#2c2c2c"))
        super().paintEvent(event)


    def setup_layout_and_content(self):
        """
        Sets up the main layout and adds all content widgets.
        """
        main_v_layout = QVBoxLayout(self)
        main_v_layout.setContentsMargins(0, 0, 0, 0)
        main_v_layout.setSpacing(0)

        self.container = QFrame()
        self.container.setStyleSheet("""
            QFrame {
                background: transparent;
                border-radius: 25px;
            }
        """)
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(20, 15, 20, 20)
        self.container_layout.setSpacing(0)

        # Top section for Month and Year labels with Navigation buttons
        top_layout = QHBoxLayout()
        # Adjusted bottom margin to reduce space after the month/year row
        top_layout.setContentsMargins(0, 0, 0, -5) # Reduced bottom margin
        top_layout.setSpacing(10)
        top_layout.setAlignment(Qt.AlignCenter)

        # Left arrow button - now named for its visual direction "❮"
        self.left_arrow_btn = QPushButton("❮")
        self.left_arrow_btn.setFixedSize(30, 30)
        self.left_arrow_btn.setStyleSheet("""
            QPushButton {
                background: transparent; /* Removed background */
                color: #e0e0e0;
                border: none;
                font-weight: bold;
                font-size: 20px; /* Increased font size */
                font-family: "Vazirmatn"; /* Added Vazirmatn font */
                padding-top: 2px; /* Adjusted padding to center text */
                outline: none;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.08); /* Semi-transparent square on hover */
                border-radius: 8px; /* Square shape */
            }
            QPushButton:pressed {
                background: rgba(255, 255, 255, 0.05); /* Slightly darker on press */
            }
        """)
        top_layout.addWidget(self.left_arrow_btn)

        # Create a container for month and year labels to fix their combined width
        self.month_year_container = QWidget()
        # Set a fixed width for this container to prevent arrows from moving
        self.month_year_container.setFixedWidth(220)

        month_year_layout = QHBoxLayout(self.month_year_container)
        month_year_layout.setSpacing(5)
        month_year_layout.setContentsMargins(0,0,0,0) # Ensure no extra margins within this container
        month_year_layout.setAlignment(Qt.AlignCenter)

        # Swapped positions: Year then Month
        self.year_label = QLabel("")
        self.year_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.year_label.setStyleSheet("""
            QLabel {
                color: #e0e0e0;
                font-size: 28px;
                font-weight: bold;
                background: transparent;
                font-family: "Vazirmatn";
                padding: 0px; /* Added to remove any implicit padding */
                margin: 0px;  /* Added to remove any implicit margin */
            }
        """)
        month_year_layout.addWidget(self.year_label)

        self.month_label = QLabel("")
        self.month_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.month_label.setStyleSheet("""
            QLabel {
                color: #e0e0e0;
                font-size: 28px;
                font-weight: bold;
                background: transparent;
                font-family: "Vazirmatn";
                padding: 0px; /* Added to remove any implicit padding */
                margin: 0px;  /* Added to remove any implicit margin */
            }
        """)
        month_year_layout.addWidget(self.month_label)

        # Use addStretch instead of addSpacing to push arrows to the ends
        top_layout.addStretch(1) # Flexible space
        top_layout.addWidget(self.month_year_container) # Add the fixed-width container
        top_layout.addStretch(1) # Flexible space

        # Right arrow button - now named for its visual direction "❯"
        self.right_arrow_btn = QPushButton("❯")
        self.right_arrow_btn.setFixedSize(30, 30)
        self.right_arrow_btn.setStyleSheet("""
            QPushButton {
                background: transparent; /* Removed background */
                color: #e0e0e0;
                border: none;
                font-weight: bold;
                font-size: 20px; /* Increased font size */
                font-family: "Vazirmatn"; /* Added Vazirmatn font */
                padding-top: 2px; /* Adjusted padding to center text */
                outline: none;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.08); /* Semi-transparent square on hover */
                border-radius: 8px; /* Square shape */
            }
            QPushButton:pressed {
                background: rgba(255, 255, 255, 0.05); /* Slightly darker on press */
            }
        """)
        top_layout.addWidget(self.right_arrow_btn)

        self.container_layout.addLayout(top_layout)

        # Weekday headers (RTL: Saturday to Friday)
        weekday_layout = QHBoxLayout()
        # Changed spacing to match calendar grid for better alignment
        weekday_layout.setSpacing(5) # Aligned with calendar grid spacing
        # Reduced top margin to decrease empty space (already 0, but included for clarity)
        weekday_layout.setContentsMargins(0, 0, 0, 10)
        weekday_layout.setDirection(QBoxLayout.RightToLeft)

        weekdays = ["ش", "ی", "د", "س", "چ", "پ", "ج"]
        for day_name in weekdays:
            label = QLabel(day_name)
            label.setAlignment(Qt.AlignCenter)
            label.setFixedSize(35, 35)
            # Brighter red: #FF4C4C
            color = "#FF4C4C" if day_name == "ج" else "#b8b8b8"
            label.setStyleSheet(f"""
                QLabel {{
                    color: {color};
                    font-weight: bold;
                    font-size: 16px;
                    background: transparent;
                    font-family: "Vazirmatn";
                }}
            """)
            weekday_layout.addWidget(label)

        self.container_layout.addLayout(weekday_layout)

        # Calendar grid (direct QGridLayout, no CalendarGridFrame)
        self.calendar_grid_layout = QGridLayout()
        # Spacing is already 5, matching weekday_layout now
        self.calendar_grid_layout.setSpacing(5)
        self.calendar_grid_layout.setOriginCorner(Qt.TopRightCorner)

        self.container_layout.addLayout(self.calendar_grid_layout)

        main_v_layout.addWidget(self.container)

        # Corrected connections: left arrow goes next (forward in time), right arrow goes prev (backward in time)
        self.left_arrow_btn.clicked.connect(self.next_month)
        self.right_arrow_btn.clicked.connect(self.prev_month)

        self.setup_calendar_grid()

    def _update_current_holidays(self):
        """
        Updates the self.holidays dictionary with holidays for the current
        display_date's year, using the shared cache.
        This method will also trigger a fetch if the year's holidays are not in cache.
        """
        # Call the parent SystemTrayIcon's method to ensure holidays for this year are fetched/cached
        self.holidays = self.tray_icon_parent._fetch_and_cache_holidays(self.display_date.year)


    def _update_labels_text(self):
        """Updates the text of month and year labels."""
        persian_months = [
            "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
            "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"
        ]
        month_name = persian_months[self.display_date.month - 1]
        self.month_label.setText(month_name)

        year_str = str(self.display_date.year)
        persian_digits = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹']
        persian_year_text = ''.join(persian_digits[int(d)] for d in year_str)
        self.year_label.setText(persian_year_text)


    def setup_calendar_grid(self):
        """
        Sets up the calendar grid with empty QLabel widgets for each day cell.
        The labels are added to the QGridLayout in a standard left-to-right, top-to-bottom order.
        """
        self.day_labels = []

        # Clear any existing widgets in the grid layout to prevent duplicates
        while self.calendar_grid_layout.count():
            child = self.calendar_grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for row in range(6):  # 6 rows for up to 42 days (6 weeks * 7 days)
            week_labels = []
            for col in range(7):  # 7 columns, from left (0) to right (6)
                label = QLabel()
                label.setAlignment(Qt.AlignCenter)
                label.setFixedSize(35, 35)
                label.setStyleSheet("""
                    QLabel {
                        background: transparent;
                        border: none;
                        font-size: 15px;
                        font-weight: bold; /* Ensured bold */
                        color: #e0e0e0;
                        border-radius: 8px; /* Changed to square for default */
                        font-family: "Vazirmatn";
                    }
                    QLabel:hover {
                        background-color: rgba(255, 255, 255, 0.08); /* Square hover */
                        border-radius: 8px; /* Ensure square on hover */
                    }
                """)
                self.calendar_grid_layout.addWidget(label, row, col)
                week_labels.append(label)
            self.day_labels.append(week_labels)

    def on_month_changed(self):
        pass

    def on_year_changed(self):
        pass

    def update_calendar(self):
        """
        Updates the calendar grid with the days of the currently selected month and year.
        Handles Persian digit display, today's date highlighting, and holiday/Friday styling.
        Ensures right-to-left display of days within the grid.
        Also displays days from previous and next months in grey if space is available.
        """
        self._update_labels_text()

        for week in self.day_labels:
            for label in week:
                label.setText("")
                label.setToolTip("")
                label.setStyleSheet("""
                    QLabel {
                        background: transparent;
                        border: none;
                        font-size: 15px;
                        font-weight: bold; /* Ensured bold */
                        color: #e0e0e0;
                        border-radius: 8px; /* Default square */
                        font-family: "Vazirmatn";
                    }
                    QLabel:hover {
                        background-color: rgba(255, 255, 255, 0.08); /* Square hover */
                        border-radius: 8px;
                    }
                """)

        # Define styles with 'bold' and refined orange highlight
        default_style = """
            QLabel {
                background: transparent;
                border: none;
                font-size: 15px;
                font-weight: bold;
                color: #e0e0e0;
                border-radius: 8px; /* Square shape */
                font-family: "Vazirmatn";
            }
            QLabel:hover {
                background-color: rgba(255, 255, 255, 0.08); /* Square hover */
                border-radius: 8px;
            }
        """
        # Style for holidays and now Fridays: red square with low opacity
        holiday_and_friday_style = """
            QLabel {
                background-color: rgba(255, 76, 76, 0.15); /* Low opacity red square */
                color: #FF4C4C; /* Brighter red text */
                border-radius: 8px; /* Square shape */
                font-size: 15px;
                font-weight: bold;
                border: none;
                font-family: "Vazirmatn";
            }
            QLabel:hover {
                background-color: rgba(255, 76, 76, 0.3); /* Higher opacity on hover */
                border-radius: 8px; /* Keep square on hover */
            }
        """

        # Today highlight on a normal day (white line)
        today_normal_style = """
            QLabel {
                background: transparent;
                color: #e0e0e0;
                border: 1px solid #FFFFFF; /* White line border */
                border-radius: 8px; /* Square shape */
                font-size: 17px;
                font-weight: bold;
                font-family: "Vazirmatn";
            }
            QLabel:hover {
                background-color: rgba(255, 255, 255, 0.08); /* Subtle grey background on hover */
                border: 1px solid #FFFFFF; /* Keep border on hover */
                border-radius: 8px;
            }
        """
        # Today highlight on a holiday/Friday (red line, WITH background opacity)
        today_holiday_friday_style = """
            QLabel {
                background-color: rgba(255, 76, 76, 0.15); /* Low opacity red square background */
                color: #FF4C4C; /* Red text */
                border: 1px solid #FF4C4C; /* Red line border */
                border-radius: 8px; /* Square shape */
                font-size: 17px;
                font-weight: bold;
                font-family: "Vazirmatn";
            }
            QLabel:hover {
                background-color: rgba(255, 76, 76, 0.3); /* Higher opacity on hover */
                border: 1px solid #FF4C4C; /* Keep border on hover */
                border-radius: 8px;
            }
        """

        grey_style = """
            QLabel {
                background: transparent;
                border: none;
                font-size: 15px;
                font-weight: bold;
                color: #808080;
                border-radius: 8px; /* Square shape */
                font-family: "Vazirmatn";
            }
            QLabel:hover {
                background-color: rgba(128, 128, 128, 0.1); /* Square hover */
                border-radius: 8px;
            }
        """

        persian_digits = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹']

        # --- Handle Previous Month's Days ---
        first_day_of_month = jdatetime.date(self.display_date.year, self.display_date.month, 1)
        start_col_in_grid = first_day_of_month.weekday()

        prev_month_date = None
        if self.display_date.month == 1:
            prev_month_date = jdatetime.date(self.display_date.year - 1, 12, 1)
        else:
            prev_month_date = jdatetime.date(self.display_date.year, self.display_date.month - 1, 1)

        days_in_prev_month = 0
        try:
            jdatetime.date(prev_month_date.year, prev_month_date.month, 31)
            days_in_prev_month = 31
        except ValueError:
            try:
                jdatetime.date(prev_month_date.year, prev_month_date.month, 30)
                days_in_prev_month = 30
            except ValueError:
                days_in_prev_month = 29


        current_row = 0
        current_col = start_col_in_grid

        for col_offset in range(start_col_in_grid):
            day_to_display = days_in_prev_month - (start_col_in_grid - 1 - col_offset)

            # Ensure we don't go out of bounds if the grid is smaller than expected
            if current_row < len(self.day_labels) and col_offset < len(self.day_labels[current_row]):
                label = self.day_labels[current_row][col_offset]
                persian_day_text = ''.join(persian_digits[int(d)] for d in str(day_to_display))
                label.setText(persian_day_text)
                label.setStyleSheet(grey_style)


        # --- Handle Current Month's Days ---
        day = 1
        days_in_month = 31
        try:
            jdatetime.date(self.display_date.year, self.display_date.month, 31)
            days_in_month = 31
        except ValueError:
            try:
                jdatetime.date(self.display_date.year, self.display_date.month, 30)
                days_in_month = 30
            except ValueError:
                days_in_month = 29


        while day <= days_in_month:
            if current_row >= 6:
                print(f"Warning: Calendar attempting to draw beyond 6 rows for month {self.display_date.month}, year {self.display_date.year}")
                break

            if current_row < len(self.day_labels) and current_col < len(self.day_labels[current_row]):
                label = self.day_labels[current_row][current_col]
            else:
                print(f"Warning: Attempted to access out-of-bounds label at row {current_row}, col {current_col}")
                day += 1
                current_col += 1
                if current_col > 6:
                    current_col = 0
                    current_row += 1
                continue

            day_str = str(day)
            persian_day_text = ''.join(persian_digits[int(d)] for d in day_str)
            label.setText(persian_day_text)

            actual_day_of_week_jdatetime_index = (first_day_of_month.weekday() + day - 1) % 7

            is_today = (day == self.current_date.day and
                        self.display_date.month == self.current_date.month and
                        self.display_date.year == self.current_date.year)
            is_friday = actual_day_of_week_jdatetime_index == 6
            is_holiday = (self.display_date.month, day) in self.holidays

            today_tooltip = ""
            if is_today:
                today_tooltip = "امروز"
                if is_holiday:
                    today_tooltip += f" (تعطیلی: {self.holidays[(self.display_date.month, day)]})"
            elif is_holiday:
                label.setToolTip(self.holidays[(self.display_date.month, day)])

            # Apply styling based on priority: Today > Holiday/Friday > Default
            if is_today:
                if is_holiday or is_friday: # Apply today_holiday_friday_style if it's today AND a holiday or Friday
                    label.setStyleSheet(today_holiday_friday_style)
                else: # Apply today_normal_style if it's today and NOT a holiday/Friday
                    label.setStyleSheet(today_normal_style)
                label.setToolTip(today_tooltip)
            elif is_holiday or is_friday: # Apply holiday_and_friday_style if it's a holiday OR Friday (and not today)
                label.setStyleSheet(holiday_and_friday_style)
                if is_holiday: # Only set tooltip for holidays
                    label.setToolTip(self.holidays[(self.display_date.month, day)])
            else: # Default style for other days
                label.setStyleSheet(default_style)

            day += 1
            current_col += 1
            if current_col > 6:
                current_col = 0
                current_row += 1

        # --- Handle Next Month's Days ---
        next_day = 1
        for row_idx in range(current_row, 6):
            for col_idx in range(current_col if row_idx == current_row else 0, 7):
                # Ensure we don't go out of bounds if the grid is smaller than expected
                if row_idx < len(self.day_labels) and col_idx < len(self.day_labels[row_idx]):
                    label = self.day_labels[row_idx][col_idx]
                    persian_day_text = ''.join(persian_digits[int(d)] for d in str(next_day))
                    label.setText(persian_day_text)
                    label.setStyleSheet(grey_style)
                else:
                    print(f"Warning: Attempted to access out-of-bounds label for next month at row {row_idx}, col {col_idx}")
                next_day += 1


    def prev_month(self):
        """Navigates to the previous month."""
        previous_year = self.display_date.year
        if self.display_date.month == 1:
            self.display_date = jdatetime.date(self.display_date.year - 1, 12, 1)
        else:
            self.display_date = jdatetime.date(self.display_date.year, self.display_date.month - 1, 1)

        # If year changed, proactively fetch/cache holidays for the new year
        if self.display_date.year != previous_year:
            self.holidays = self.tray_icon_parent._fetch_and_cache_holidays(self.display_date.year) # Update current holidays too!
        else:
            # If year didn't change, just get from existing cache (which is already loaded/updated)
            self.holidays = self.holidays_cache.get(self.display_date.year, {})

        self.update_calendar()

    def next_month(self):
        """Navitakes to the next month."""
        previous_year = self.display_date.year
        if self.display_date.month == 12:
            self.display_date = jdatetime.date(self.display_date.year + 1, 1, 1)
        else:
            self.display_date = jdatetime.date(self.display_date.year, self.display_date.month + 1, 1)

        # If year changed, proactively fetch/cache holidays for the new year
        if self.display_date.year != previous_year:
            self.holidays = self.tray_icon_parent._fetch_and_cache_holidays(self.display_date.year) # Update current holidays too!
        else:
            # If year didn't change, just get from existing cache (which is already loaded/updated)
            self.holidays = self.holidays_cache.get(self.display_date.year, {})

        self.update_calendar()


class SystemTrayIcon(QSystemTrayIcon):
    """
    A QSystemTrayIcon that displays the current Persian day and provides
    a context menu and allows toggling the PersianCalendarWidget.
    """

    def __init__(self):
        super().__init__()
        self.app_name = "PersianCalendarTray"
        # Set company_name to an empty string to put data directly in the app folder
        self.company_name = "" 
        self.data_dir = user_data_dir(self.app_name, self.company_name)
        os.makedirs(self.data_dir, exist_ok=True) # Ensure data directory exists
        self.cache_file_path = os.path.join(self.data_dir, "holidays_cache.json")

        self.calendar_widget = None # Instance of PersianCalendarWidget
        self._is_calendar_visible = False # Internal state for calendar visibility
        self.current_date = jdatetime.date.today() # This is the current date of the system

        # Load holidays and last checked date from file on startup
        self.holidays_cache, self.last_checked_date = self._load_holidays_from_file()
        # Initialize current_date's holidays from the loaded cache
        self.holidays = self.holidays_cache.get(self.current_date.year, {})

        # Perform an initial daily update check right after loading
        self._perform_daily_update_check()

        self.create_tray_icon()
        self.setup_context_menu()
        self.activated.connect(self.on_tray_icon_activated)

        self.timer = QTimer()
        # The timer will trigger the update_tray_icon, which in turn calls _perform_daily_update_check
        self.timer.timeout.connect(self.update_tray_icon)
        self.timer.start(60000) # Check every minute

    def _load_holidays_from_file(self):
        """
        Loads holiday data and last_checked_date from the cache file.
        Converts string keys in nested holiday dictionaries back to tuples.
        Returns (holidays_cache_dict, last_checked_date_obj).
        """
        holidays_data = {}
        last_checked = None
        if os.path.exists(self.cache_file_path):
            try:
                with open(self.cache_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    loaded_holidays_raw = data.get('holidays', {})
                    for year_str, holidays_for_year_raw in loaded_holidays_raw.items():
                        deserialized_holidays_for_year = {}
                        for month_day_str, desc in holidays_for_year_raw.items():
                            # Parse "month-day" string back to tuple (month, day)
                            try:
                                month, day = map(int, month_day_str.split('-'))
                                deserialized_holidays_for_year[(month, day)] = desc
                            except ValueError:
                                print(f"Warning: Could not parse month-day string '{month_day_str}' for year {year_str}")
                                continue # Skip invalid entries
                        holidays_data[int(year_str)] = deserialized_holidays_for_year

                    last_checked_str = data.get('last_checked_date')
                    if last_checked_str:
                        last_checked = datetime.datetime.strptime(last_checked_str, "%Y-%m-%d").date()
                print(f"Holidays loaded from file: {self.cache_file_path}")
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                print(f"Error loading holidays from file: {e}. Starting with empty cache.")
        return holidays_data, last_checked

    def _save_holidays_to_file(self):
        """
        Saves the current holiday cache and last_checked_date to the cache file.
        Converts tuple keys in nested holiday dictionaries to strings for JSON serialization.
        """
        try:
            serializable_holidays = {}
            for year, holidays_for_year in self.holidays_cache.items():
                # holidays_for_year has tuple keys (month, day)
                serializable_inner_dict = {}
                for (month, day), description in holidays_for_year.items():
                    serializable_inner_dict[f"{month}-{day}"] = description
                serializable_holidays[str(year)] = serializable_inner_dict

            last_checked_str = self.last_checked_date.strftime("%Y-%m-%d") if self.last_checked_date else None
            
            with open(self.cache_file_path, 'w', encoding='utf-8') as f:
                json.dump({'holidays': serializable_holidays, 'last_checked_date': last_checked_str},
                          f, ensure_ascii=False, indent=4)
            print(f"Holidays saved to file: {self.cache_file_path}")
        except IOError as e:
            print(f"Error saving holidays to file: {e}")

    def _fetch_and_cache_holidays(self, year):
        """
        Fetches holiday data for a given year from the Persian Calendar API
        and caches it in the SystemTrayIcon's central cache.
        Returns a dictionary of holidays for the requested year.
        This method is now called from both SystemTrayIcon and PersianCalendarWidget.
        """
        if year in self.holidays_cache:
            print(f"Holidays for year {year} fetched from in-memory cache (SystemTrayIcon).")
            return self.holidays_cache[year]

        print(f"Fetching holidays for year {year} from API (SystemTrayIcon)...")
        holidays_for_year = {}
        api_url = f"https://api.persian-calendar.ir/api/v1/calendar/{year}/holidays"
        try:
            response = requests.get(api_url, timeout=5)
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

            json_data = response.json()

            if not isinstance(json_data, dict) or 'data' not in json_data:
                print(f"API response for year {year} was not a dictionary with a 'data' key. Received: {json_data}")
                return {}

            data = json_data['data']

            if not isinstance(data, list):
                print(f"API response 'data' for year {year} was not a list. Received: {type(data)}")
                return {}

            for holiday_info in data:
                if not isinstance(holiday_info, dict):
                    print(f"Unexpected item in API response 'data' for year {year}: {holiday_info} (expected dictionary)")
                    continue

                jalali_date_str = holiday_info.get('date')
                description = holiday_info.get('holidayDesription')

                if jalali_date_str and description:
                    try:
                        y, m, d = map(int, jalali_date_str.split('/'))
                        jalali_date = jdatetime.date(y, m, d)
                        # Store as tuple key (month, day) for internal use
                        holidays_for_year[(jalali_date.month, jalali_date.day)] = description
                    except ValueError as e:
                        print(f"Error parsing Jalali date {jalali_date_str} from API for year {year}: {e}")
                        continue
        except requests.exceptions.RequestException as e:
            print(f"Error fetching holidays from API for year {year}: {e}")
            # If API fetch fails, return an empty dict for this year, but keep existing cached data
            return self.holidays_cache.get(year, {}) # Return old data if available
        except ValueError as e:
            print(f"Error decoding JSON from API for year {year}: {e}")
            return self.holidays_cache.get(year, {}) # Return old data if available


        self.holidays_cache[year] = holidays_for_year # Update in-memory cache
        self._save_holidays_to_file() # Save the updated cache to file after a successful fetch
        return holidays_for_year

    def _update_current_holidays(self):
        """
        Updates the self.holidays dictionary (for the tray icon's tooltip)
        with holidays for the current system date's year, fetching from cache or API.
        """
        self.holidays = self._fetch_and_cache_holidays(self.current_date.year)

    def _perform_daily_update_check(self):
        """
        Checks if a daily update for holidays is needed and performs it.
        Fetches data for last, current, and next year.
        """
        today = datetime.date.today()
        if not self.last_checked_date or self.last_checked_date < today:
            print(f"Performing daily holiday update check for {today}...")
            current_jalali_year = jdatetime.date.today().year
            years_to_check = [current_jalali_year - 1, current_jalali_year, current_jalali_year + 1]
            
            for year in years_to_check:
                # _fetch_and_cache_holidays will handle caching/fetching from API
                self._fetch_and_cache_holidays(year)
            
            self.last_checked_date = today
            self._save_holidays_to_file() # Save updated last_checked_date and any new cache data
        else:
            print(f"Daily holiday update check already performed for {today}.")

    def create_tray_icon(self):
        """
        Generates a custom tray icon showing the current day number in Persian digits.
        The icon number turns red if the current day is a holiday or a Friday.
        Also sets a detailed tooltip with the full Persian date.
        """
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        persian_digits = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹']
        day_str = str(self.current_date.day)
        persian_day = ''.join(persian_digits[int(d)] for d in day_str)

        is_friday = self.current_date.weekday() == 6
        # Ensure self.holidays is up-to-date with current_date.year's holidays
        current_year_holidays = self.holidays_cache.get(self.current_date.year, {})
        is_holiday = (self.current_date.month, self.current_date.day) in current_year_holidays

        if is_holiday or is_friday:
            painter.setPen(QColor("#FF4C4C")) # Brighter red color for holiday/Friday
        else:
            painter.setPen(QColor(255, 255, 255)) # White color for other days


        font = QFont("Vazirmatn", 20, QFont.Bold)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, persian_day)
        painter.end()

        icon = QIcon(pixmap)
        self.setIcon(icon)

        weekday_names = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه"]
        weekday_name = weekday_names[self.current_date.weekday()]
        month_names = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
        month_name = month_names[self.current_date.month - 1]

        year_str = str(self.current_date.year)
        month_str = f"{self.current_date.month:02d}"
        day_str = f"{self.current_date.day:02d}"

        # Customize the tooltip text here
        tooltip = f"{weekday_name}\n{year_str}-{month_str}-{day_str}\n{day_str} {month_name} {year_str}"
        if is_holiday:
            tooltip += f"\n(تعطیلی: {current_year_holidays[(self.current_date.month, self.current_date.day)]})"
        self.setToolTip(tooltip)

    def update_tray_icon(self):
        """
        Checks if the date has changed and updates the tray icon and calendar widget if necessary.
        Also triggers the daily holiday update check.
        """
        new_date = jdatetime.date.today()
        if new_date != self.current_date:
            print(f"Date changed from {self.current_date} to {new_date}.")
            self.current_date = new_date
            self._update_current_holidays() # Update holidays for new current_date.year
            self.create_tray_icon() # Recreate icon with new date/holiday status
        
        # Always perform the daily update check, it will only execute API calls if needed
        self._perform_daily_update_check()

        # If calendar widget is visible, update its content (holidays and current date)
        if self.calendar_widget and self._is_calendar_visible: # Check internal state
            self.calendar_widget.current_date = new_date # Ensure calendar widget knows today's date
            # Update the calendar widget's displayed holidays for its *current display year*
            # This implicitly calls self.tray_icon_parent._fetch_and_cache_holidays
            self.calendar_widget._update_current_holidays() 
            self.calendar_widget.update_calendar()

    def setup_context_menu(self):
        """
        Sets up the context menu that appears when right-clicking the tray icon.
        Includes an "Exit" action and applies custom styling.
        """
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #2c2c2c; /* Same as calendar background */
                border: 1px solid #606060;
                border-radius: 8px; /* Rounded corners for the menu itself */
                padding: 5px;
            }
            QMenu::item {
                color: #e0e0e0;
                background-color: transparent;
                padding: 6px 15px; /* Padding for items */
                margin: 2px 0px; /* Vertical spacing between items */
                border-radius: 6px; /* Rounded corners for menu items */
                font-size: 14px;
                font-weight: bold;
                font-family: "Vazirmatn";
            }
            QMenu::item:selected {
                background-color: rgba(255, 76, 76, 0.2); /* Subtle red highlight on hover/selection */
                color: #FF4C4C; /* Brighter red text on hover */
            }
            QMenu::separator {
                height: 1px;
                background-color: #606060;
                margin: 5px 0px;
            }
        """)

        exit_action = menu.addAction("خروج")
        exit_action.triggered.connect(QApplication.quit)
        self.setContextMenu(menu)

    def on_tray_icon_activated(self, reason):
        """
        Handles activation events of the tray icon (e.g., left-click).
        Toggles the visibility of the calendar widget.
        """
        if reason == QSystemTrayIcon.Trigger:
            self.toggle_calendar()

    def toggle_calendar(self):
        """
        Shows or hides the PersianCalendarWidget.
        It ensures only one instance of the calendar widget is created,
        and handles its visibility robustly, including when it's closed by the user.
        """
        if not self.calendar_widget:
            # Create the widget only once on the first activation
            # Pass a reference to this SystemTrayIcon instance itself
            self.calendar_widget = PersianCalendarWidget(self)
            # Install event filter to catch external hide events
            self.calendar_widget.installEventFilter(self)

        # Toggle visibility based on the internal state flag
        if self._is_calendar_visible:
            self.calendar_widget.hide()
            self._is_calendar_visible = False # Update internal state
        else:
            self.calendar_widget.show()
            self.position_calendar_above_tray()
            self.calendar_widget.activateWindow()
            self.calendar_widget.raise_()
            self._is_calendar_visible = True # Update internal state

            # Ensure calendar widget displays correctly upon showing (especially after hide)
            self.calendar_widget.current_date = jdatetime.date.today() # Update its understanding of "today"
            # Trigger update for holidays based on its current display year
            self.calendar_widget._update_current_holidays()
            self.calendar_widget.update_calendar()


    def eventFilter(self, obj, event):
        """
        Filters events for the calendar_widget to detect when it's hidden externally
        (e.g., by clicking outside the popup) and update the internal state flag.
        The widget instance itself is explicitly hidden here to ensure state consistency.
        """
        # If the object is our calendar_widget and the event type is Hide
        if obj == self.calendar_widget and event.type() == QEvent.Hide:
            # Explicitly hide it in case it was an external hide (e.g., losing focus)
            # This ensures self.calendar_widget.isVisible() correctly returns False
            # and prevents re-showing issues on subsequent tray icon clicks.
            if self.calendar_widget.isVisible(): # Only hide if it's actually visible
                self.calendar_widget.hide()
            self._is_calendar_visible = False # Update internal state
        # Always call the base class's eventFilter
        return super().eventFilter(obj, event)

    def position_calendar_above_tray(self):
        """
        Calculates and sets the position of the calendar widget to appear
        just above the system tray icon, adjusting for screen boundaries.
        """
        screen = QApplication.primaryScreen().availableGeometry()
        tray_geometry = self.geometry()

        widget_width = self.calendar_widget.width()
        widget_height = self.calendar_widget.height()

        target_x = 0
        target_y = 0

        if tray_geometry.isValid():
            target_x = tray_geometry.center().x() - widget_width // 2
            target_y = tray_geometry.top() - widget_height - 5

            if target_y < 0:
                target_y = tray_geometry.bottom() + 5
        else:
            # Fallback if tray_geometry is not valid (e.g., on some Linux desktops)
            target_x = screen.width() - widget_width - 20
            target_y = 20

        # Ensure the calendar stays within screen boundaries
        target_x = max(0, min(target_x, screen.width() - widget_width))
        target_y = max(0, min(target_y, screen.height() - widget_height))

        self.calendar_widget.move(target_x, target_y)

def main():
    """
    Main function to initialize and run the PyQt application.
    """
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet("""
        QToolTip {
            background-color: #3a3a3a;
            color: #FF4C4C; /* Brighter red text for ALL tooltips */
            border: 1px solid #606060;
            border-radius: 8px;
            padding: 5px 8px;
            font-size: 14px;
            font-weight: bold;
        }
    """)

    # Attempt to load the font. If not found, PyQt will use a default.
    # It's recommended to install "Vazirmatn" font on the system for it to render correctly.
    # from PyQt5.QtGui import QFontDatabase
    # font_db = QFontDatabase.addApplicationFont("path/to/Vazirmatn-Regular.ttf")
    # if font_db != -1:
    #     print("Vazirmatn font loaded successfully.")
    # else:
    #     print("Failed to load Vazirmatn font. Ensure the font file is accessible or installed.")
    # if font_db.addApplicationFont("path/to/Vazirmatn-Bold.ttf") != -1:
    #     print("Vazirmatn Bold font loaded successfully.")
    # else:
    #     print("Failed to load Vazirmatn Bold font. Ensure the font file is accessible or installed.")


    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("System tray is not available on this system.")
        sys.exit(1)

    tray_icon = SystemTrayIcon()
    tray_icon.show()

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
