import sys
import jdatetime
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QBoxLayout,
                             QLabel, QPushButton, QGridLayout, QSystemTrayIcon,
                             QMenu, QFrame, QComboBox)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QFont, QColor, QPen

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
        self.setup_holidays()
        self.setup_ui()

    def setup_ui(self):
        """
        Sets up the user interface for the calendar widget programmatically.
        Connects signals for navigation and dropdowns.
        """
        # Remove window frame and set window flags for a popup appearance
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Popup)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Main vertical layout for the entire widget
        main_layout = QVBoxLayout(self) # Set self as parent for main_layout
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Create a main container frame with a gradient background and rounded borders
        self.container = QFrame()
        self.container.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3a3a3a, stop:1 #2a2a2a);
                border: 1px solid #4a4a4a;
                border-radius: 16px;
            }
        """)
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(12, 12, 12, 12)
        container_layout.setSpacing(10)

        # Horizontal layout for month/year navigation
        nav_layout = QHBoxLayout()
        nav_layout.setContentsMargins(5, 5, 5, 5)

        # Previous month button
        self.prev_btn = QPushButton("❮")
        self.prev_btn.setFixedSize(30, 30)
        self.prev_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #505050, stop:1 #404040);
                color: #e0e0e0;
                border: 1px solid #606060;
                border-radius: 15px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #606060, stop:1 #505050);
            }
        """)
        nav_layout.addWidget(self.prev_btn)

    # Year dropdown
        self.year_combo = QComboBox()
        self.year_combo.setFixedHeight(32)
        current_year = self.current_date.year
        for year in range(current_year - 10, current_year + 10):
            self.year_combo.addItem(str(year))
        self.year_combo.setCurrentText(str(current_year))
        self.year_combo.setStyleSheet("""
            QComboBox {
                background: #404040;
                color: #e0e0e0;
                border: 1px solid #606060;
                border-radius: 6px;
                padding: 5px;
                font-size: 13px;
                font-weight: 500;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #e0e0e0;
                margin-right: 5px;
            }
            QComboBox QAbstractItemView {
                background: #404040;
                color: #e0e0e0;
                border: 1px solid #606060;
                selection-background-color: #505050;
            }
        """)
        nav_layout.addWidget(self.year_combo)

        # Month dropdown with Persian month names
        self.month_combo = QComboBox()
        self.month_combo.setFixedHeight(32)
        persian_months = [
            "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
            "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"
        ]
        for month in persian_months:
            self.month_combo.addItem(month)
        self.month_combo.setCurrentIndex(self.current_date.month - 1)
        self.month_combo.setStyleSheet("""
            QComboBox {
                background: #404040;
                color: #e0e0e0;
                border: 1px solid #606060;
                border-radius: 6px;
                padding: 5px;
                font-size: 13px;
                font-weight: 500;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #e0e0e0;
                margin-right: 5px;
            }
            QComboBox QAbstractItemView {
                background: #404040;
                color: #e0e0e0;
                border: 1px solid #606060;
                selection-background-color: #505050;
            }
        """)
        nav_layout.addWidget(self.month_combo)

        # Next month button
        self.next_btn = QPushButton("❯")
        self.next_btn.setFixedSize(30, 30)
        self.next_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #505050, stop:1 #404040);
                color: #e0e0e0;
                border: 1px solid #606060;
                border-radius: 15px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #606060, stop:1 #505050);
            }
        """)
        nav_layout.addWidget(self.next_btn)

        container_layout.addLayout(nav_layout)

        # Weekday headers (RTL: Saturday to Friday)
        weekdays = ["ش", "ی", "د", "س", "چ", "پ", "ج"]  # Saturday to Friday
        weekday_layout = QHBoxLayout()
        weekday_layout.setSpacing(6)
        weekday_layout.setContentsMargins(5, 5, 5, 5)
        weekday_layout.setDirection(QBoxLayout.RightToLeft) # Crucial for RTL display of headers

        for day_name in weekdays:
            label = QLabel(day_name)
            label.setAlignment(Qt.AlignCenter)
            label.setFixedSize(35, 25)
            color = "#ff7979" if day_name == "ج" else "#b8b8b8" # Friday is red
            label.setStyleSheet(f"""
                QLabel {{
                    color: {color};
                    font-weight: 600;
                    font-size: 11px;
                    background: transparent;
                }}
            """)
            weekday_layout.addWidget(label)

        container_layout.addLayout(weekday_layout)

        # Calendar grid container frame
        self.calendar_frame = QFrame()
        self.calendar_frame.setStyleSheet("QFrame { background: transparent; }")
        calendar_layout = QVBoxLayout(self.calendar_frame)
        calendar_layout.setContentsMargins(5, 0, 5, 5)

        # The QGridLayout where day numbers will be placed
        self.calendar_grid_layout = QGridLayout()
        self.calendar_grid_layout.setSpacing(4)
        calendar_layout.addLayout(self.calendar_grid_layout)

        container_layout.addWidget(self.calendar_frame)
        main_layout.addWidget(self.container)

        # Set default window size
        self.resize(300, 350)

        # Connect signals for month and year changes, and navigation buttons
        self.month_combo.currentIndexChanged.connect(self.on_month_changed)
        self.year_combo.currentIndexChanged.connect(self.on_year_changed)
        self.prev_btn.clicked.connect(self.prev_month)
        self.next_btn.clicked.connect(self.next_month)

        self.setup_calendar_grid()
        self.update_calendar()

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
                label.setFixedSize(35, 32)
                label.setStyleSheet("""
                    QLabel {
                        background: transparent;
                        border: none;
                        font-size: 13px;
                        font-weight: 500;
                        color: #e0e0e0;
                        border-radius: 16px;
                    }
                    QLabel:hover {
                        background-color: rgba(255, 255, 255, 0.08);
                    }
                """)
                self.calendar_grid_layout.addWidget(label, row, col)
                week_labels.append(label)
            self.day_labels.append(week_labels) # Store labels in visual order (col 0 is leftmost)

    def setup_holidays(self):
        """
        Defines a dictionary of common Persian (Jalali) holidays with their names.
        (Month, Day) tuples are used as keys.
        """
        self.holidays = {
            (1, 1): "نوروز", (1, 2): "نوروز", (1, 3): "نوروز", (1, 4): "نوروز",
            (1, 12): "روز جمهوری اسلامی", (1, 13): "سیزده بدر",
            (3, 14): "رحلت امام خمینی", (3, 15): "قیام ۱۵ خرداد",
            (11, 22): "پیروزی انقلاب اسلامی", (12, 29): "روز ملی شدن صنعت نفت",
        }

    def on_month_changed(self):
        """Handler for month combobox selection change."""
        month = self.month_combo.currentIndex() + 1
        year = int(self.year_combo.currentText())
        self.display_date = jdatetime.date(year, month, 1)
        self.update_calendar()

    def on_year_changed(self):
        """Handler for year combobox selection change."""
        month = self.month_combo.currentIndex() + 1
        year = int(self.year_combo.currentText())
        self.display_date = jdatetime.date(year, month, 1)
        self.update_calendar()

    def update_calendar(self):
        """
        Updates the calendar grid with the days of the currently selected month and year.
        Handles Persian digit display, today's date highlighting, and holiday/Friday styling.
        Ensures right-to-left display of days within the grid.
        """
        # Update dropdowns to match the currently displayed date
        self.month_combo.setCurrentIndex(self.display_date.month - 1)
        self.year_combo.setCurrentText(str(self.display_date.year))

        # Clear all previous day labels and reset their styling
        for week in self.day_labels:
            for label in week:
                label.setText("")
                label.setToolTip("") # Clear any previous tooltips
                label.setStyleSheet("""
                    QLabel {
                        background: transparent;
                        border: none;
                        font-size: 13px;
                        font-weight: 500;
                        color: #e0e0e0;
                        border-radius: 16px;
                    }
                    QLabel:hover {
                        background-color: rgba(255, 255, 255, 0.08);
                    }
                """)

        # Get the first day of the month being displayed
        first_day_of_month = jdatetime.date(self.display_date.year, self.display_date.month, 1)
        # jdatetime weekday: 0=Saturday, 1=Sunday, ..., 6=Friday

        # Calculate the starting column in the QGridLayout (0=leftmost, 6=rightmost)
        # We want Saturday (jdatetime weekday 0) to be in the rightmost column (6)
        # and Friday (jdatetime weekday 6) to be in the leftmost column (0).
        start_col_in_grid = 6 - first_day_of_month.weekday()

        # Determine the number of days in the current month
        if self.display_date.month == 12: # Esfand
            try:
                jdatetime.date(self.display_date.year, 12, 30)
                days_in_month = 30
            except ValueError: # If 30th Esfand is invalid, it's a 29-day month
                days_in_month = 29
        elif self.display_date.month <= 6: # Farvardin to Shahrivar
            days_in_month = 31
        else: # Mehr to Bahman
            days_in_month = 30

        # Fill the calendar grid with day numbers
        day = 1
        current_row = 0
        current_col = start_col_in_grid # Start at the calculated column for the first day

        persian_digits = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹']
        default_style = """
            QLabel {
                background: transparent;
                border: none;
                font-size: 18px;
                font-weight: 500;
                color: #e0e0e0;
                border-radius: 16px;
            }
            QLabel:hover {
                background-color: rgba(255, 255, 255, 0.08);
            }
        """
        red_style = """
            QLabel {
                background: transparent;
                color: #ff7979;
                border-radius: 16px;
                font-size: 18px;
                font-weight: 500;
                border: none;
            }
            QLabel:hover {
                background-color: rgba(255, 121, 121, 0.1);
            }
        """
        today_style = """
            QLabel {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ff9f43, stop:1 #ff6b35); /* Orange gradient for today */
                color: white;
                border-radius: 16px;
                font-size: 13px;
                font-weight: bold;
                border: 2px solid rgba(255, 159, 67, 0.5);
            }
            QLabel:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ffb74d, stop:1 #ff8a50);
            }
        """

        while day <= days_in_month:
            if current_row >= 6:
                break

            label = self.day_labels[current_row][current_col]

            day_str = str(day)
            persian_day_text = ''.join(persian_digits[int(d)] for d in day_str)
            label.setText(persian_day_text)

            actual_day_of_week_jdatetime_index = (first_day_of_month.weekday() + day - 1) % 7
            is_today = (day == self.current_date.day and
                        self.display_date.month == self.current_date.month and
                        self.display_date.year == self.current_date.year)
            is_friday = actual_day_of_week_jdatetime_index == 6 # Friday in jdatetime is index 6
            is_holiday = (self.display_date.month, day) in self.holidays

            if is_today:
                label.setStyleSheet(today_style)
            elif is_friday or is_holiday:
                label.setStyleSheet(red_style)
                if is_holiday:
                    label.setToolTip(self.holidays[(self.display_date.month, day)])
            else:
                label.setStyleSheet(default_style)

            day += 1
            current_col -= 1 # Decrement column for right-to-left flow of days
            if current_col < 0:
                current_col = 6
                current_row += 1

        # Clear any remaining labels in the grid that might have old data
        clear_start_row = current_row
        clear_start_col = current_col + 1 if day > 1 else 0

        if clear_start_col > 6:
            clear_start_col = 0
            clear_start_row += 1

        for row_idx in range(clear_start_row, 6):
            for col_idx in range(clear_start_col if row_idx == clear_start_row else 0, 7):
                label = self.day_labels[row_idx][col_idx]
                label.setText("")
                label.setToolTip("")
                label.setStyleSheet(default_style) # Reset to default transparent style

    def prev_month(self):
        """Navigates to the previous month."""
        if self.display_date.month == 1:
            self.display_date = jdatetime.date(self.display_date.year - 1, 12, 1)
        else:
            self.display_date = jdatetime.date(self.display_date.year, self.display_date.month - 1, 1)
        self.update_calendar()

    def next_month(self):
        """Navigates to the next month."""
        if self.display_date.month == 12:
            self.display_date = jdatetime.date(self.display_date.year + 1, 1, 1)
        else:
            self.display_date = jdatetime.date(self.display_date.year, self.display_date.month + 1, 1)
        self.update_calendar()

class SystemTrayIcon(QSystemTrayIcon):
    """
    A QSystemTrayIcon that displays the current Persian day and provides
    a context menu and allows toggling the PersianCalendarWidget.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.calendar_widget = None
        self.current_date = jdatetime.date.today()
        self.setup_holidays() # Initialize holidays here

        self.create_tray_icon()
        self.setup_context_menu()
        self.activated.connect(self.on_tray_icon_activated)

        # Set up a timer to update the icon daily (checks every minute)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_tray_icon)
        self.timer.start(60000)

    def setup_holidays(self):
        """
        Defines a dictionary of common Persian (Jalali) holidays with their names.
        (Month, Day) tuples are used as keys. Duplicated here for tray icon logic.
        """
        self.holidays = {
            (1, 1): "نوروز", (1, 2): "نوروز", (1, 3): "نوروز", (1, 4): "نوروز",
            (1, 12): "روز جمهوری اسلامی", (1, 13): "سیزده بدر",
            (3, 14): "رحلت امام خمینی", (3, 15): "قیام ۱۵ خرداد",
            (11, 22): "پیروزی انقلاب اسلامی", (12, 29): "روز ملی شدن صنعت نفت",
        }

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

        # Convert current day number to Persian digits
        persian_digits = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹']
        day_str = str(self.current_date.day)
        persian_day = ''.join(persian_digits[int(d)] for d in day_str)

        # Determine if today is Friday or a holiday
        is_friday = self.current_date.weekday() == 6 # Friday in jdatetime is index 6
        is_holiday = (self.current_date.month, self.current_date.day) in self.holidays

        # Set color based on whether it's a Friday or a holiday
        if is_friday or is_holiday:
            painter.setPen(QColor(255, 121, 121)) # Red color
        else:
            painter.setPen(QColor(255, 255, 255)) # White color

        # Draw the Persian day number on the icon
        font = QFont("IRANSans", 20, QFont.Bold)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, persian_day)
        painter.end()

        icon = QIcon(pixmap)
        self.setIcon(icon)

        # Create a detailed tooltip with day name and full date in Persian
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
            self.create_tray_icon() # Recreate icon with new date and potential new color
            if self.calendar_widget:
                self.calendar_widget.current_date = new_date
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
            # Ensure the calendar widget's current_date is in sync with the tray icon's
            self.calendar_widget.current_date = self.current_date
            self.calendar_widget.update_calendar()


        if self.calendar_widget.isVisible():
            self.calendar_widget.hide()
        else:
            self.position_calendar_above_tray()
            self.calendar_widget.show()
            self.calendar_widget.activateWindow()
            self.calendar_widget.raise_()

    def position_calendar_above_tray(self):
        """
        Calculates and sets the position of the calendar widget to appear
        just above the system tray icon, adjusting for screen boundaries.
        """
        screen = QApplication.primaryScreen().availableGeometry()
        tray_geometry = self.geometry()

        if tray_geometry.isValid():
            widget_width = self.calendar_widget.width()
            widget_height = self.calendar_widget.height()

            x = tray_geometry.center().x() - widget_width // 2
            y = tray_geometry.top() - widget_height - 5

            if x < 0:
                x = 5
            elif x + widget_width > screen.width():
                x = screen.width() - widget_width - 5

            if y < 0:
                y = tray_geometry.bottom() + 5
        else:
            widget_width = self.calendar_widget.width()
            widget_height = self.calendar_widget.height()

            x = screen.width() - widget_width - 10
            y = screen.height() - widget_height - 50

        self.calendar_widget.move(x, y)

def main():
    """
    Main function to initialize and run the PyQt application.
    """
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    # Holiday Hover Style
    app.setStyleSheet("""
        QToolTip {
            background-color: #3a3a3a;
            color: #ff5555;;
            border: 1px solid #606060;
            border-radius: 8px;
            padding: 5px 8px;
            font-size: 14px;
            font-weight: bold;
        }
    """)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("System tray is not available on this system.")
        sys.exit(1)

    tray_icon = SystemTrayIcon()
    tray_icon.show()

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()