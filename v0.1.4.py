import sys
import jdatetime
import requests
import datetime

from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QBoxLayout,
                             QLabel, QPushButton, QGridLayout, QSystemTrayIcon,
                             QMenu, QFrame)
from PyQt5.QtCore import Qt, QTimer, QRect
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QFont, QColor, QPen, QPainterPath


# Custom QFrame class to draw grid lines for the calendar
class CalendarGridFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.grid_layout = None
        # Make the background transparent so the parent's dark mode background is visible
        self.setStyleSheet("QFrame { background: transparent; }")

    def set_grid_layout(self, layout):
        self.grid_layout = layout

    def paintEvent(self, event):
        # First, let the base class paint its background (which is transparent due to stylesheet)
        # and then its children.
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(60, 60, 60, 150), 1)) # Subtle gray line, slightly transparent

        if not self.grid_layout or self.grid_layout.count() == 0:
            return

        # Determine the bounding box of the active grid area
        min_x = float('inf')
        max_x = float('-inf')
        min_y = float('inf')
        max_y = float('-inf')

        # Find the overall extent of the grid cells
        for row in range(self.grid_layout.rowCount()):
            for col in range(self.grid_layout.columnCount()):
                item = self.grid_layout.itemAtPosition(row, col)
                if item and item.widget() and item.widget().isVisible(): # Only consider visible labels
                    rect = item.widget().geometry()
                    min_x = min(min_x, rect.left())
                    max_x = max(max_x, rect.right())
                    min_y = min(min_y, rect.top())
                    max_y = max(max_y, rect.bottom())

        if min_x == float('inf'): # No visible widgets in grid
            return

        # Calculate grid boundaries including the spacing for outer lines
        h_spacing = self.grid_layout.horizontalSpacing()
        v_spacing = self.grid_layout.verticalSpacing()

        # Adjust min/max to cover the full space including half of the spacing on edges
        draw_x_start = min_x - h_spacing / 2
        draw_x_end = max_x + h_spacing / 2
        draw_y_start = min_y - v_spacing / 2
        draw_y_end = max_y + v_spacing / 2

        # Draw horizontal lines
        for row_idx in range(self.grid_layout.rowCount() + 1): # +1 for the bottom line
            if row_idx == 0: # Top line
                line_y = draw_y_start
            else:
                # Line after the current row of cells
                # The visual layout is RTL, so col 0 is on the right.
                # Use col 0 for simplicity if it exists.
                label_rect = self.grid_layout.itemAtPosition(row_idx - 1, 0).widget().geometry()
                line_y = label_rect.bottom() + v_spacing / 2

            # Ensure line stays within visible bounds of the frame
            if line_y >= self.rect().top() and line_y <= self.rect().bottom():
                # Convert coordinates to integers before drawing
                painter.drawLine(int(draw_x_start), int(line_y), int(draw_x_end), int(line_y))

        # Draw vertical lines
        for col_idx in range(self.grid_layout.columnCount() + 1): # +1 for the leftmost line
            if col_idx == 0: # Rightmost line
                line_x = draw_x_end
            else:
                # Line to the left of the current column of cells
                # In RTL, col 0 is rightmost, col 6 is leftmost.
                # So itemAtPosition(0, col_idx-1) gives the widget to the right of the line we want to draw
                label_rect = self.grid_layout.itemAtPosition(0, col_idx - 1).widget().geometry()
                line_x = label_rect.left() - h_spacing / 2

            # Ensure line stays within visible bounds of the frame
            if line_x >= self.rect().left() and line_x <= self.rect().right():
                # Convert coordinates to integers before drawing
                painter.drawLine(int(line_x), int(draw_y_start), int(line_x), int(draw_y_end))


class PersianCalendarWidget(QWidget):
    """
    A widget that displays a Persian (Jalali) calendar with right-to-left day ordering.
    It supports displaying holidays, today's date, and navigation through months and years.
    """
    def __init__(self):
        super().__init__()
        # Initialize current date to today's Jalali date
        self.current_date = jdatetime.date.today()
        # The date currently being displayed on the calendar
        self.display_date = self.current_date
        self.holidays_cache = {} # Cache for storing fetched holidays by year
        self.holidays = {} # Dictionary to store holidays for the current displayed year

        self.initUI() # Call the new initUI method for window setup
        self.setup_layout_and_content() # Separate method for layout and content
        
        # Fetch holidays for the initial displayed year before updating the calendar
        self._update_current_holidays() # This method is defined below
        self.update_calendar() # Initial update after holidays are potentially loaded

    def initUI(self):
        """
        Initializes the main window properties, including flags for framelessness
        and transparency. This is separated for clarity.
        """
        # Crucial for rounded corners and transparency:
        # 1. Qt.FramelessWindowHint: Removes the default window frame drawn by the OS.
        # 2. Qt.WA_TranslucentBackground: Enables per-pixel transparency.
        # 3. Qt.WA_NoSystemBackground: Prevents the underlying widget from drawing a default opaque background.
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Popup)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        # Explicitly make the top-level widget's background transparent
        self.setStyleSheet("QWidget { background: transparent; }")

        # Set the fixed size early to ensure consistent rendering
        self.setFixedSize(450, 480) # Increased size

    def paintEvent(self, event):
        """
        Overrides the paint event to draw the custom rounded background.
        This handles the visual appearance of the rounded corners and dark mode.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing) # For smooth edges

        # Define the path for the rounded rectangle
        path = QPainterPath()
        # Explicitly pass x, y, width, height as floats for addRoundedRect
        path.addRoundedRect(float(self.rect().x()), float(self.rect().y()),
                            float(self.rect().width()), float(self.rect().height()),
                            25, 25) # Use the same radius as the container's border-radius

        # Fill the path with the dark background color
        painter.fillPath(path, QColor("#2c2c2c"))

        # Call the superclass paintEvent to ensure child widgets are drawn
        super().paintEvent(event)


    def setup_layout_and_content(self):
        """
        Sets up the main layout and adds all content widgets.
        Separated from initUI for better organization.
        """
        # Main vertical layout for the entire widget
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Create a main container frame. Its background is now handled by the parent widget's paintEvent.
        self.container = QFrame()
        self.container.setStyleSheet("""
            QFrame {
                background: transparent; /* Background now handled by parent's paintEvent */
                border-radius: 25px; /* Keep for potential inner element styling, or remove if not needed */
            }
        """)
        container_layout = QVBoxLayout(self.container)
        # Adjusted margins to provide more space for the calendar elements
        container_layout.setContentsMargins(30, 20, 30, 30)
        container_layout.setSpacing(0)

        # Top section for Month and Year labels with Navigation buttons
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(10) # Spacing between elements in the top row
        top_layout.setAlignment(Qt.AlignCenter)

        self.prev_btn = QPushButton("❮")
        self.prev_btn.setFixedSize(30, 30) # Slightly larger buttons
        self.prev_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #505050, stop:1 #404040);
                color: #e0e0e0;
                border: 1px solid #606060;
                border-radius: 15px; /* Half of fixed size for perfect circle */
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #606060, stop:1 #505050);
            }
        """)
        top_layout.addWidget(self.prev_btn)

        # Layout for Month and Year labels (side-by-side)
        month_year_layout = QHBoxLayout()
        month_year_layout.setSpacing(5) # Small spacing between month and year
        month_year_layout.setAlignment(Qt.AlignCenter) # Center month and year within their space

        self.month_label = QLabel("")
        self.month_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter) # Align month to the right
        self.month_label.setStyleSheet("""
            QLabel {
                color: #e0e0e0;
                font-size: 28px; /* Larger font for month */
                font-weight: bold;
                background: transparent;
                font-family: "IRANSans"; /* Set font to IRANSans */
            }
        """)
        month_year_layout.addWidget(self.month_label)

        self.year_label = QLabel("")
        self.year_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter) # Align year to the left
        self.year_label.setStyleSheet("""
            QLabel {
                color: #e0e0e0; /* Changed to match month label color for consistency */
                font-size: 28px; /* Matched font size to month label */
                font-weight: bold; /* Matched font weight to month label */
                background: transparent;
                font-family: "IRANSans"; /* Set font to IRANSans */
            }
        """)
        month_year_layout.addWidget(self.year_label)

        top_layout.addStretch() # Push buttons to sides of month/year group
        top_layout.addLayout(month_year_layout)
        top_layout.addStretch()

        self.next_btn = QPushButton("❯")
        self.next_btn.setFixedSize(30, 30) # Slightly larger buttons
        self.next_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #505050, stop:1 #404040);
                color: #e0e0e0;
                border: 1px solid #606060;
                border-radius: 15px; /* Half of fixed size for perfect circle */
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #606060, stop:1 #505050);
            }
        """)
        top_layout.addWidget(self.next_btn)

        container_layout.addLayout(top_layout)

        # Weekday headers (RTL: Saturday to Friday)
        weekday_layout = QHBoxLayout()
        weekday_layout.setSpacing(15) # Increased spacing for weekdays
        weekday_layout.setContentsMargins(0, 30, 0, 10) # Adjusted margins
        weekday_layout.setDirection(QBoxLayout.RightToLeft) # Crucial for RTL display of headers

        weekdays = ["ش", "ی", "د", "س", "چ", "پ", "ج"]  # Saturday to Friday
        for day_name in weekdays:
            label = QLabel(day_name)
            label.setAlignment(Qt.AlignCenter)
            label.setFixedSize(35, 35) # Increased size for weekday labels
            color = "#ff7979" if day_name == "ج" else "#b8b8b8" # Friday is red
            label.setStyleSheet(f"""
                QLabel {{
                    color: {color};
                    font-weight: 600;
                    font-size: 16px; /* Larger font for weekdays */
                    background: transparent;
                    font-family: "IRANSans"; /* Set font to IRANSans */
                }}
            """)
            weekday_layout.addWidget(label)

        container_layout.addLayout(weekday_layout)

        # Calendar grid container frame (custom class for drawing lines)
        self.calendar_frame = CalendarGridFrame()
        self.calendar_frame.setStyleSheet("QFrame { background: transparent; }")
        calendar_layout_inner = QVBoxLayout(self.calendar_frame)
        calendar_layout_inner.setContentsMargins(0, 0, 0, 0)
        calendar_layout_inner.setSpacing(0)

        # The QGridLayout where day numbers will be placed
        self.calendar_grid_layout = QGridLayout()
        self.calendar_grid_layout.setSpacing(15) # Increased spacing between day cells
        self.calendar_grid_layout.setOriginCorner(Qt.TopRightCorner)
        calendar_layout_inner.addLayout(self.calendar_grid_layout)
        self.calendar_frame.set_grid_layout(self.calendar_grid_layout)

        container_layout.addWidget(self.calendar_frame)

        main_layout.addWidget(self.container)

        # Connect signals for navigation buttons (SWAPPED as per previous request)
        self.prev_btn.clicked.connect(self.next_month) # Left arrow goes to NEXT month
        self.next_btn.clicked.connect(self.prev_month) # Right arrow goes to PREVIOUS month

        self.setup_calendar_grid()

    def _fetch_and_cache_holidays(self, year):
        """
        Fetches holiday data for a given year from the Persian Calendar API
        and caches it.
        Returns a dictionary of holidays in the format {(month, day): "description"}.
        """
        # Check if holidays for this year are already in the cache
        if year in self.holidays_cache:
            return self.holidays_cache[year]

        holidays_for_year = {}
        api_url = f"https://api.persian-calendar.ir/api/v1/calendar/{year}/holidays"
        try:
            # Make the API request with a timeout
            response = requests.get(api_url, timeout=5)
            response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)

            json_data = response.json() # Parse the top-level JSON response

            # The actual list of holidays is nested under the 'data' key
            # Ensure json_data is a dictionary and contains the 'data' key
            if not isinstance(json_data, dict) or 'data' not in json_data:
                print(f"API response for year {year} was not a dictionary with a 'data' key. Received: {json_data}")
                return {} # Return empty dict if structure is unexpected

            data = json_data['data'] # Extract the list of holidays

            # Ensure data is a list before iterating (additional check for safety)
            if not isinstance(data, list):
                print(f"API response 'data' for year {year} was not a list. Received: {type(data)}")
                return {} # Return empty dict if data is not a list

            for holiday_info in data:
                # Ensure each item in the list is a dictionary
                if not isinstance(holiday_info, dict):
                    print(f"Unexpected item in API response 'data' for year {year}: {holiday_info} (expected dictionary)")
                    continue # Skip this item if it's not a dictionary

                jalali_date_str = holiday_info.get('date') # API returns Jalali date string here
                # The API uses 'holidayDesription' (note the typo 'Desription') for the description
                description = holiday_info.get('holidayDesription')

                if jalali_date_str and description: # Ensure both date and description are present
                    try:
                        # Parse the Jalali date string (e.g., "1404/01/01") into year, month, day integers
                        y, m, d = map(int, jalali_date_str.split('/'))
                        # Create a jdatetime.date object directly from the parsed components
                        jalali_date = jdatetime.date(y, m, d)

                        # Store in the format {(month, day): "description"}
                        holidays_for_year[(jalali_date.month, jalali_date.day)] = description
                    except ValueError as e:
                        # Print an error if a specific date string cannot be parsed
                        print(f"Error parsing Jalali date {jalali_date_str} from API for year {year}: {e}")
                        continue
        except requests.exceptions.RequestException as e:
            # Handle network-related errors (e.g., connection refused, timeout)
            print(f"Error fetching holidays from API for year {year}: {e}")
        except ValueError as e:
            # Handle JSON decoding errors
            print(f"Error decoding JSON from API for year {year}: {e}")

        # Cache the fetched holidays for the year
        self.holidays_cache[year] = holidays_for_year
        return holidays_for_year

    def _update_current_holidays(self):
        """
        Updates the self.holidays dictionary with holidays for the current
        display_date's year, fetching from cache or API if needed.
        """
        # Call the helper method to get holidays for the current display year
        self.holidays = self._fetch_and_cache_holidays(self.display_date.year)


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

        for row in range(6): # 6 rows for up to 42 days (6 weeks * 7 days)
            week_labels = []
            for col in range(7): # 7 columns, from left (0) to right (6)
                label = QLabel()
                label.setAlignment(Qt.AlignCenter)
                label.setFixedSize(35, 35) # Increased size for day labels
                label.setStyleSheet("""
                    QLabel {
                        background: transparent;
                        border: none;
                        font-size: 15px; /* Larger font for days */
                        font-weight: 500;
                        color: #e0e0e0;
                        border-radius: 17px; /* Half of fixed size for round effect */
                        font-family: "IRANSans"; /* Set font to IRANSans */
                    }
                    QLabel:hover {
                        background-color: rgba(255, 255, 255, 0.08);
                    }
                """)
                # Add widget to the QGridLayout using the logical column index
                self.calendar_grid_layout.addWidget(label, row, col)
                week_labels.append(label)
            self.day_labels.append(week_labels) # Store labels in visual order (col 0 is leftmost)

    def on_month_changed(self):
        """This method is no longer used for comboboxes, but keeping as a placeholder if needed."""
        pass

    def on_year_changed(self):
        """This method is no longer used for comboboxes, but keeping as a placeholder if needed."""
        pass

    def update_calendar(self):
        """
        Updates the calendar grid with the days of the currently selected month and year.
        Handles Persian digit display, today's date highlighting, and holiday/Friday styling.
        Ensures right-to-left display of days within the grid.
        Also displays days from previous and next months in grey if space is available.
        """
        self._update_labels_text() # Update month and year labels

        # Clear all previous day labels and reset their styling
        for week in self.day_labels:
            for label in week:
                label.setText("")
                label.setToolTip("") # Clear any previous tooltips
                label.setStyleSheet("""
                    QLabel {
                        background: transparent;
                        border: none;
                        font-size: 15px;
                        font-weight: 500;
                        color: #e0e0e0;
                        border-radius: 17px;
                        font-family: "IRANSans"; /* Set font to IRANSans */
                    }
                    QLabel:hover {
                        background-color: rgba(255, 255, 255, 0.08);
                    }
                """)

        # Define styles
        default_style = """
            QLabel {
                background: transparent;
                border: none;
                font-size: 15px;
                font-weight: 500;
                color: #e0e0e0;
                border-radius: 17px;
                font-family: "IRANSans"; /* Set font to IRANSans */
            }
            QLabel:hover {
                background-color: rgba(255, 255, 255, 0.08);
            }
        """
        red_style = """
            QLabel {
                background: transparent;
                color: #ff7979;
                border-radius: 17px;
                font-size: 15px;
                font-weight: 500;
                border: none;
                font-family: "IRANSans"; /* Set font to IRANSans */
            }
            QLabel:hover {
                background-color: rgba(255, 121, 121, 0.1);
            }
        """
        today_style = """
            QLabel {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(255, 159, 67, 0.4), stop:1 rgba(255, 107, 53, 0.4)); /* Orange gradient with 40% transparency */
                color: white;
                border-radius: 17px;
                font-size: 17px; /* Larger font for today's date */
                font-weight: bold;
                font-family: "IRANSans"; /* Set font to IRANSans */
            }
            QLabel:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(255, 183, 77, 0.6), stop:1 rgba(255, 138, 80, 0.6)); /* Hover with 60% transparency */
            }
        """
        today_and_holiday_style = """
            QLabel {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(255, 159, 67, 0.4), stop:1 rgba(255, 107, 53, 0.4)); /* Orange gradient with 40% transparency */
                color: #ff7979; /* Red color from red_style */
                border-radius: 17px;
                font-size: 17px; /* Larger font for today's date */
                font-weight: bold;
                font-family: "IRANSans"; /* Set font to IRANSans */
            }
            QLabel:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(255, 183, 77, 0.6), stop:1 rgba(255, 138, 80, 0.6)); /* Hover with 60% transparency */
            }
        """
        grey_style = """
            QLabel {
                background: transparent;
                border: none;
                font-size: 15px;
                font-weight: 500;
                color: #808080; /* Grey color for days from prev/next month */
                border-radius: 17px;
                font-family: "IRANSans"; /* Set font to IRANSans */
            }
            QLabel:hover {
                background-color: rgba(128, 128, 128, 0.1);
            }
        """

        persian_digits = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹']

        # --- Handle Previous Month's Days ---
        first_day_of_month = jdatetime.date(self.display_date.year, self.display_date.month, 1)
        start_col_in_grid = first_day_of_month.weekday() # 0=Saturday, 6=Friday

        # Determine the number of days in the previous month
        prev_month_date = None
        if self.display_date.month == 1:
            prev_month_date = jdatetime.date(self.display_date.year - 1, 12, 1)
        else:
            prev_month_date = jdatetime.date(self.display_date.year, self.display_date.month - 1, 1)

        days_in_prev_month = 0
        # Determine the number of days in the previous month more robustly
        try:
            jdatetime.date(prev_month_date.year, prev_month_date.month, 31)
            days_in_prev_month = 31
        except ValueError:
            try:
                jdatetime.date(prev_month_date.year, prev_month_date.month, 30)
                days_in_prev_month = 30
            except ValueError:
                days_in_prev_month = 29 # If 31 and 30 fail, it must be 29


        # Fill leading empty cells with days from the previous month
        current_row = 0
        current_col = start_col_in_grid

        for col_offset in range(start_col_in_grid):
            day_to_display = days_in_prev_month - (start_col_in_grid - 1 - col_offset)

            label = self.day_labels[current_row][col_offset]

            persian_day_text = ''.join(persian_digits[int(d)] for d in str(day_to_display))
            label.setText(persian_day_text)
            label.setStyleSheet(grey_style)


        # --- Handle Current Month's Days ---
        day = 1
        # Determine the number of days in the current month more robustly
        days_in_month = 31 # Initialize with a default to guarantee it's defined
        try:
            jdatetime.date(self.display_date.year, self.display_date.month, 31)
            days_in_month = 31
        except ValueError:
            try:
                jdatetime.date(self.display_date.year, self.display_date.month, 30)
                days_in_month = 30
            except ValueError:
                days_in_month = 29 # If 31 and 30 fail, it must be 29


        while day <= days_in_month:
            if current_row >= 6:
                print(f"Warning: Calendar attempting to draw beyond 6 rows for month {self.display_date.month}, year {self.display_date.year}")
                break

            label = self.day_labels[current_row][current_col]

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

            if is_today and is_holiday:
                label.setStyleSheet(today_and_holiday_style)
                label.setToolTip(today_tooltip)
            elif is_today:
                label.setStyleSheet(today_style)
                label.setToolTip(today_tooltip)
            elif is_holiday:
                label.setStyleSheet(red_style)
                label.setToolTip(self.holidays[(self.display_date.month, day)])
            elif is_friday:
                label.setStyleSheet(red_style)
            else:
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
                label = self.day_labels[row_idx][col_idx]

                persian_day_text = ''.join(persian_digits[int(d)] for d in str(next_day))
                label.setText(persian_day_text)
                label.setStyleSheet(grey_style)
                next_day += 1


        self.calendar_frame.update() # Request repaint for grid lines

    def prev_month(self):
        """Navigates to the previous month."""
        if self.display_date.month == 1:
            self.display_date = jdatetime.date(self.display_date.year - 1, 12, 1)
        else:
            self.display_date = jdatetime.date(self.display_date.year, self.display_date.month - 1, 1)
        self._update_current_holidays() # Fetch holidays for the new year if needed
        self.update_calendar()

    def next_month(self):
        """Navigates to the next month."""
        if self.display_date.month == 12:
            self.display_date = jdatetime.date(self.display_date.year + 1, 1, 1)
        else:
            self.display_date = jdatetime.date(self.display_date.year, self.display_date.month + 1, 1)
        self._update_current_holidays() # Fetch holidays for the new year if needed
        self.update_calendar()

class SystemTrayIcon(QSystemTrayIcon):
    """
    A QSystemTrayIcon that displays the current Persian day and provides
    a context menu and allows toggling the PersianCalendarWidget.
    """
    def __init__(self):
        super().__init__()
        self.calendar_widget = None
        self.current_date = jdatetime.date.today()
        self.holidays_cache = {}
        self.holidays = {}

        self._update_current_holidays()

        self.create_tray_icon()
        self.setup_context_menu()
        self.activated.connect(self.on_tray_icon_activated)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_tray_icon)
        self.timer.start(60000)

    def _fetch_and_cache_holidays(self, year):
        """
        Fetches holiday data for a given year from the Persian Calendar API
        and caches it.
        Returns a dictionary of holidays in the format {(month, day): "description"}.
        """
        if year in self.holidays_cache:
            return self.holidays_cache[year]

        holidays_for_year = {}
        api_url = f"https://api.persian-calendar.ir/api/v1/calendar/{year}/holidays"
        try:
            response = requests.get(api_url, timeout=5)
            response.raise_for_status()

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

                        holidays_for_year[(jalali_date.month, jalali_date.day)] = description
                    except ValueError as e:
                        print(f"Error parsing Jalali date {jalali_date_str} from API for year {year}: {e}")
                        continue
        except requests.exceptions.RequestException as e:
            print(f"Error fetching holidays from API for year {year}: {e}")
        except ValueError as e:
            print(f"Error decoding JSON from API for year {year}: {e}")

        self.holidays_cache[year] = holidays_for_year
        return holidays_for_year

    def _update_current_holidays(self):
        """
        Updates the self.holidays dictionary with holidays for the current
        current_date's year, fetching from cache or API if needed.
        """
        self.holidays = self._fetch_and_cache_holidays(self.current_date.year)


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
        is_holiday = (self.current_date.month, self.current_date.day) in self.holidays

        if is_holiday:
            painter.setPen(QColor(255, 121, 121)) # Red color for holiday
        elif is_friday:
            painter.setPen(QColor(255, 121, 121)) # Red color for Friday
        else:
            painter.setPen(QColor(255, 255, 255)) # White color for other days


        font = QFont("IRANSans", 20, QFont.Bold) # Ensured IRANSans font is used for tray icon
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

        tooltip = f"{weekday_name}\n{year_str}-{month_str}-{day_str}\n{day_str} {month_name} {year_str}"
        if is_holiday:
            tooltip += f"\n(تعطیلی: {self.holidays[(self.current_date.month, self.current_date.day)]})"
        self.setToolTip(tooltip)

    def update_tray_icon(self):
        """
        Checks if the date has changed and updates the tray icon and calendar widget if necessary.
        """
        new_date = jdatetime.date.today()
        if new_date != self.current_date:
            self.current_date = new_date
            self._update_current_holidays()
            self.create_tray_icon()
            if self.calendar_widget:
                self.calendar_widget.current_date = new_date
                self.calendar_widget._update_current_holidays()
                self.calendar_widget.update_calendar()

    def setup_context_menu(self):
        """
        Sets up the context menu that appears when right-clicking the tray icon.
        Includes an "Exit" action.
        """
        menu = QMenu()
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
        If the widget is not yet created, it instantiates it.
        """
        if not self.calendar_widget:
            self.calendar_widget = PersianCalendarWidget()
            self.calendar_widget.show()
            self.position_calendar_above_tray()
            self.calendar_widget.activateWindow()
            self.calendar_widget.raise_()
        elif self.calendar_widget.isVisible():
            self.calendar_widget.hide()
        else:
            self.calendar_widget.show()
            self.position_calendar_above_tray()
            self.calendar_widget.activateWindow()
            self.calendar_widget.raise_()

    def position_calendar_above_tray(self):
        """
        Calculates and sets the position of the calendar widget to appear
        just above the system tray icon, adjusting for screen boundaries.
        """
        screen = QApplication.primaryScreen().availableGeometry()
        tray_geometry = self.geometry()

        # Use the fixed size set in setup_ui
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
            target_x = screen.width() - widget_width - 20
            target_y = 20

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
            color: #ff5555;
            border: 1px solid #606060;
            border-radius: 8px;
            padding: 5px 8px;
            font-size: 14px;
            font-weight: bold;
        }
    """)

    # Attempt to load the font. If not found, PyQt will use a default.
    # It's recommended to install "IRANSans" font on the system for it to render correctly.
    # from PyQt5.QtGui import QFontDatabase
    # font_db = QFontDatabase()
    # if font_db.addApplicationFont("path/to/IRANSans.ttf") != -1:
    #     print("IRANSans font loaded successfully.")
    # else:
    #     print("Failed to load IRANSans font. Ensure the font file is accessible or installed.")

    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("System tray is not available on this system.")
        sys.exit(1)

    tray_icon = SystemTrayIcon()
    tray_icon.show()

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
