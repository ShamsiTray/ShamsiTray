import sys
import jdatetime
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QBoxLayout,
                             QLabel, QPushButton, QGridLayout, QSystemTrayIcon,
                             QMenu, QFrame, QComboBox)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QFont, QColor, QPen

# Common Persian holidays
PERSIAN_HOLIDAYS = {
    (1, 1): "نوروز", (1, 2): "نوروز", (1, 3): "نوروز", (1, 4): "نوروز",
    (1, 12): "روز جمهوری اسلامی", (1, 13): "سیزده بدر",
    (3, 14): "رحلت امام خمینی", (3, 15): "قیام ۱۵ خرداد",
    (11, 22): "پیروزی انقلاب اسلامی", (12, 29): "روز ملی شدن صنعت نفت",
}

# Persian month names
PERSIAN_MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"
]

# Persian weekday names
PERSIAN_WEEKDAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه"]

# Persian digits
PERSIAN_DIGITS = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹']

def to_persian_digits(number):
    """Convert English digits to Persian digits."""
    return ''.join(PERSIAN_DIGITS[int(d)] for d in str(number))

def get_days_in_month(year, month):
    """Get number of days in a Persian month."""
    if month == 12:  # Esfand
        try:
            jdatetime.date(year, 12, 30)
            return 30
        except ValueError:
            return 29
    elif month <= 6:  # Farvardin to Shahrivar
        return 31
    else:  # Mehr to Bahman
        return 30

class PersianCalendarWidget(QWidget):
    """
    A widget that displays a Persian (Jalali) calendar with right-to-left day ordering.
    It supports displaying holidays, today's date, and navigation through months and years.
    """
    
    def __init__(self):
        super().__init__()
        self.current_date = jdatetime.date.today()
        self.display_date = self.current_date
        self.day_labels = []
        self.setup_ui()

    def setup_ui(self):
        """Sets up the user interface for the calendar widget."""
        # Set application-wide font
        font = QFont("IRANSans", 10)
        self.setFont(font)
        
        # Window properties
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Popup)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Container frame
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

        # Navigation layout
        self.setup_navigation(container_layout)
        
        # Weekday headers
        self.setup_weekday_headers(container_layout)
        
        # Calendar grid
        self.setup_calendar_grid(container_layout)

        main_layout.addWidget(self.container)
        self.resize(320, 380)

        # Connect signals
        self.connect_signals()
        self.update_calendar()

    def setup_navigation(self, parent_layout):
        """Set up the navigation controls."""
        nav_layout = QHBoxLayout()
        nav_layout.setContentsMargins(5, 5, 5, 5)
        nav_layout.setSpacing(8)

        button_style = """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #505050, stop:1 #404040);
                color: #e0e0e0;
                border: 1px solid #606060;
                border-radius: 15px;
                font-weight: bold;
                font-size: 12px;
                font-family: 'IRANSans';
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #606060, stop:1 #505050);
            }
        """

        # Previous month button
        self.prev_btn = QPushButton("❮")
        self.prev_btn.setFixedSize(30, 30)
        self.prev_btn.setStyleSheet(button_style)
        nav_layout.addWidget(self.prev_btn)

        # Year dropdown
        self.year_combo = QComboBox()
        self.year_combo.setFixedHeight(32)
        current_year = self.current_date.year
        for year in range(current_year - 20, current_year + 20):
            self.year_combo.addItem(str(year))
        self.year_combo.setCurrentText(str(current_year))
        self.year_combo.setStyleSheet(self.get_combo_style())
        nav_layout.addWidget(self.year_combo)

        # Month dropdown
        self.month_combo = QComboBox()
        self.month_combo.setFixedHeight(32)
        for month in PERSIAN_MONTHS:
            self.month_combo.addItem(month)
        self.month_combo.setCurrentIndex(self.current_date.month - 1)
        self.month_combo.setStyleSheet(self.get_combo_style())
        nav_layout.addWidget(self.month_combo)

        # Next month button
        self.next_btn = QPushButton("❯")
        self.next_btn.setFixedSize(30, 30)
        self.next_btn.setStyleSheet(button_style)
        nav_layout.addWidget(self.next_btn)

        parent_layout.addLayout(nav_layout)

    def get_combo_style(self):
        """Get the stylesheet for combo boxes."""
        return """
            QComboBox {
                background: #404040;
                color: #e0e0e0;
                border: 1px solid #606060;
                border-radius: 6px;
                padding: 5px;
                font-size: 13px;
                font-weight: 500;
                font-family: 'IRANSans';
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
                font-family: 'IRANSans';
            }
        """

    def setup_weekday_headers(self, parent_layout):
        """Set up the weekday headers with colored background."""
        weekdays = ["ش", "ی", "د", "س", "چ", "پ", "ج"]  # Saturday to Friday
        
        # Create container frame for the colored bar
        weekday_container = QFrame()
        weekday_container.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4a9f4a, stop:1 #3a8a3a);
                border-radius: 8px;
                margin: 2px;
            }
        """)
        
        weekday_container_layout = QHBoxLayout(weekday_container)
        weekday_container_layout.setSpacing(0)
        weekday_container_layout.setContentsMargins(8, 8, 8, 8)
        weekday_container_layout.setDirection(QBoxLayout.RightToLeft)

        for day_name in weekdays:
            label = QLabel(day_name)
            label.setAlignment(Qt.AlignCenter)
            label.setFixedSize(35, 25)
            color = "#ffffff" if day_name == "ج" else "#f0f0f0"  # White for Friday
            label.setStyleSheet(f"""
                QLabel {{
                    color: {color};
                    font-family: 'IRANSans';
                    font-weight: 600;
                    font-size: 12px;
                    background: transparent;
                }}
            """)
            weekday_container_layout.addWidget(label)

        parent_layout.addWidget(weekday_container)

    def setup_calendar_grid(self, parent_layout):
        """Set up the calendar grid layout."""
        self.calendar_frame = QFrame()
        self.calendar_frame.setStyleSheet("QFrame { background: transparent; }")
        calendar_layout = QVBoxLayout(self.calendar_frame)
        calendar_layout.setContentsMargins(5, 0, 5, 5)

        self.calendar_grid_layout = QGridLayout()
        self.calendar_grid_layout.setSpacing(4)
        calendar_layout.addLayout(self.calendar_grid_layout)

        # Create day labels
        self.create_day_labels()
        
        parent_layout.addWidget(self.calendar_frame)

    def create_day_labels(self):
        """Create QLabel widgets for each day cell."""
        self.day_labels = []
        
        # Clear existing widgets
        while self.calendar_grid_layout.count():
            child = self.calendar_grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for row in range(6):
            week_labels = []
            for col in range(7):
                label = QLabel()
                label.setAlignment(Qt.AlignCenter)
                label.setFixedSize(35, 32)
                label.setStyleSheet(self.get_default_day_style())
                self.calendar_grid_layout.addWidget(label, row, col)
                week_labels.append(label)
            self.day_labels.append(week_labels)

    def get_default_day_style(self):
        """Get the default stylesheet for day labels."""
        return """
            QLabel {
                background: transparent;
                border: none;
                font-size: 13px;
                font-weight: 500;
                color: #e0e0e0;
                border-radius: 16px;
                font-family: 'IRANSans';
            }
            QLabel:hover {
                background-color: rgba(255, 255, 255, 0.08);
            }
        """

    def get_day_styles(self):
        """Get different day styles."""
        styles = {
            'default': """
                QLabel {
                    background: transparent;
                    border: none;
                    font-size: 18px;
                    font-weight: 500;
                    color: #e0e0e0;
                    border-radius: 16px;
                    font-family: 'IRANSans';
                }
                QLabel:hover {
                    background-color: rgba(255, 255, 255, 0.08);
                }
            """,
            'red': """
                QLabel {
                    background: transparent;
                    color: #7979FF;
                    border-radius: 16px;
                    font-size: 18px;
                    font-weight: 500;
                    border: none;
                    font-family: 'IRANSans';
                }
                QLabel:hover {
                    background-color: rgba(255, 121, 121, 0.1);
                }
            """,
            'today': """
                QLabel {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #ff9f43, stop:1 #ff6b35);
                    color: white;
                    border-radius: 16px;
                    font-size: 18px;
                    font-weight: bold;
                    border: 2px solid rgba(255, 159, 67, 0.5);
                    font-family: 'IRANSans';
                }
                QLabel:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #ffb74d, stop:1 #ff8a50);
                }
            """,
            'prev_month': """
                QLabel {
                    background: transparent;
                    border: none;
                    font-size: 13px;
                    font-weight: 300;
                    color: #666666;
                    border-radius: 16px;
                    font-family: 'IRANSans';
                }
                QLabel:hover {
                    background-color: rgba(255, 255, 255, 0.05);
                }
            """
        }
        return styles

    def connect_signals(self):
        """Connect all widget signals."""
        self.month_combo.currentIndexChanged.connect(self.on_month_changed)
        self.year_combo.currentIndexChanged.connect(self.on_year_changed)
        self.prev_btn.clicked.connect(self.prev_month)
        self.next_btn.clicked.connect(self.next_month)

    def on_month_changed(self):
        """Handle month combobox change."""
        month = self.month_combo.currentIndex() + 1
        year = int(self.year_combo.currentText())
        self.display_date = jdatetime.date(year, month, 1)
        self.update_calendar()

    def on_year_changed(self):
        """Handle year combobox change."""
        month = self.month_combo.currentIndex() + 1
        year = int(self.year_combo.currentText())
        self.display_date = jdatetime.date(year, month, 1)
        self.update_calendar()

    def update_calendar(self):
        """Update the calendar grid with the current month's days."""
        # Update dropdowns
        self.month_combo.setCurrentIndex(self.display_date.month - 1)
        self.year_combo.setCurrentText(str(self.display_date.year))

        # Clear all labels
        self.clear_all_labels()

        # Get month info
        first_day = jdatetime.date(self.display_date.year, self.display_date.month, 1)
        start_col = 6 - first_day.weekday()  # RTL positioning
        days_in_month = get_days_in_month(self.display_date.year, self.display_date.month)
        
        styles = self.get_day_styles()

        # Fill previous month's days
        self.fill_previous_month_days(start_col, styles['prev_month'])
        
        # Fill current month's days
        self.fill_current_month_days(start_col, days_in_month, styles)
        
        # Fill next month's days
        self.fill_next_month_days(start_col, days_in_month, styles['prev_month'])

    def clear_all_labels(self):
        """Clear all day labels."""
        for week in self.day_labels:
            for label in week:
                label.setText("")
                label.setToolTip("")
                label.setStyleSheet(self.get_default_day_style())

    def fill_previous_month_days(self, start_col, style):
        """Fill the previous month's days."""
        if start_col < 6:  # If first day isn't Saturday
            prev_month = 12 if self.display_date.month == 1 else self.display_date.month - 1
            prev_year = self.display_date.year - 1 if self.display_date.month == 1 else self.display_date.year
            prev_month_days = get_days_in_month(prev_year, prev_month)
            
            for col in range(start_col + 1, 7):
                prev_day = prev_month_days - (6 - col)
                label = self.day_labels[0][col]
                label.setText(to_persian_digits(prev_day))
                label.setStyleSheet(style)

    def fill_current_month_days(self, start_col, days_in_month, styles):
        """Fill the current month's days."""
        first_day = jdatetime.date(self.display_date.year, self.display_date.month, 1)
        
        day = 1
        current_row = 0
        current_col = start_col

        while day <= days_in_month and current_row < 6:
            label = self.day_labels[current_row][current_col]
            label.setText(to_persian_digits(day))

            # Determine day properties
            actual_weekday = (first_day.weekday() + day - 1) % 7
            is_today = (day == self.current_date.day and 
                       self.display_date.month == self.current_date.month and
                       self.display_date.year == self.current_date.year)
            is_friday = actual_weekday == 6
            is_holiday = (self.display_date.month, day) in PERSIAN_HOLIDAYS

            # Apply appropriate style
            if is_today:
                label.setStyleSheet(styles['today'])
            elif is_friday or is_holiday:
                label.setStyleSheet(styles['red'])
                if is_holiday:
                    holiday_name = PERSIAN_HOLIDAYS[(self.display_date.month, day)]
                    label.setToolTip(f'<span style="color: #7979FF; font-family: IRANSans; font-size: 12px;">{holiday_name}</span>')
            else:
                label.setStyleSheet(styles['default'])

            day += 1
            current_col -= 1
            if current_col < 0:
                current_col = 6
                current_row += 1

    def fill_next_month_days(self, start_col, days_in_month, style):
        """Fill the next month's days to complete the grid."""
        first_day = jdatetime.date(self.display_date.year, self.display_date.month, 1)
        last_day_col = (start_col - (days_in_month - 1)) % 7
        last_day_row = (days_in_month + start_col - 1) // 7
        
        if last_day_col < 6:  # If there are empty spaces
            next_day = 1
            for row in range(last_day_row, 6):
                start_col_for_row = last_day_col - 1 if row == last_day_row else 6
                for col in range(start_col_for_row, -1, -1):
                    if next_day <= 31:  # Reasonable limit
                        label = self.day_labels[row][col]
                        label.setText(to_persian_digits(next_day))
                        label.setStyleSheet(style)
                        next_day += 1

    def prev_month(self):
        """Navigate to previous month."""
        if self.display_date.month == 1:
            new_year = self.display_date.year - 1
            self.display_date = jdatetime.date(new_year, 12, 1)
            self.ensure_year_in_combo(new_year)
        else:
            self.display_date = jdatetime.date(self.display_date.year, self.display_date.month - 1, 1)
        self.update_calendar()

    def next_month(self):
        """Navigate to next month."""
        if self.display_date.month == 12:
            new_year = self.display_date.year + 1
            self.display_date = jdatetime.date(new_year, 1, 1)
            self.ensure_year_in_combo(new_year)
        else:
            self.display_date = jdatetime.date(self.display_date.year, self.display_date.month + 1, 1)
        self.update_calendar()

    def ensure_year_in_combo(self, year):
        """Ensure the year is available in the combo box."""
        year_str = str(year)
        if self.year_combo.findText(year_str) == -1:
            self.year_combo.addItem(year_str)
            # Sort items numerically
            items = [self.year_combo.itemText(i) for i in range(self.year_combo.count())]
            items.sort(key=int)
            self.year_combo.clear()
            self.year_combo.addItems(items)


class SystemTrayIcon(QSystemTrayIcon):
    """System tray icon that displays the current Persian day."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.calendar_widget = None
        self.current_date = jdatetime.date.today()
        
        self.create_tray_icon()
        self.setup_context_menu()
        self.activated.connect(self.on_tray_icon_activated)
        
        # Update timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_tray_icon)
        self.timer.start(60000)  # Check every minute

    def create_tray_icon(self):
        """Create the tray icon with current day number."""
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Check if today is a holiday
        is_holiday = (self.current_date.month, self.current_date.day) in PERSIAN_HOLIDAYS
        color = QColor(255, 100, 100) if is_holiday else QColor(255, 255, 255)
        painter.setPen(color)

        # Draw Persian day number
        persian_day = to_persian_digits(self.current_date.day)
        font = QFont("IRANSans", 20, QFont.Bold)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, persian_day)
        painter.end()

        self.setIcon(QIcon(pixmap))
        self.create_tooltip()

    def create_tooltip(self):
        """Create detailed tooltip with Persian date."""
        weekday_name = PERSIAN_WEEKDAYS[self.current_date.weekday()]
        month_name = PERSIAN_MONTHS[self.current_date.month - 1]
        
        year_str = str(self.current_date.year)
        month_str = f"{self.current_date.month:02d}"
        day_str = f"{self.current_date.day:02d}"
        
        tooltip = f"{weekday_name}\n{year_str}-{month_str}-{day_str}\n{day_str} {month_name} {year_str}"
        
        # Add holiday info if applicable
        if (self.current_date.month, self.current_date.day) in PERSIAN_HOLIDAYS:
            holiday_name = PERSIAN_HOLIDAYS[(self.current_date.month, self.current_date.day)]
            tooltip += f"\n{holiday_name}"
        
        self.setToolTip(tooltip)

    def update_tray_icon(self):
        """Update tray icon if date has changed."""
        new_date = jdatetime.date.today()
        if new_date != self.current_date:
            self.current_date = new_date
            self.create_tray_icon()
            if self.calendar_widget:
                self.calendar_widget.current_date = new_date
                self.calendar_widget.update_calendar()

    def setup_context_menu(self):
        """Set up the context menu."""
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #404040;
                color: #e0e0e0;
                border: 1px solid #606060;
                font-family: 'IRANSans';
            }
            QMenu::item {
                padding: 5px 15px;
            }
            QMenu::item:selected {
                background-color: #505050;
            }
        """)
        
        exit_action = menu.addAction("خروج")
        exit_action.triggered.connect(QApplication.quit)
        self.setContextMenu(menu)

    def on_tray_icon_activated(self, reason):
        """Handle tray icon activation."""
        if reason == QSystemTrayIcon.Trigger:
            self.toggle_calendar()

    def toggle_calendar(self):
        """Show or hide the calendar widget."""
        if not self.calendar_widget:
            self.calendar_widget = PersianCalendarWidget()

        if self.calendar_widget.isVisible():
            self.calendar_widget.hide()
        else:
            self.position_calendar_above_tray()
            self.calendar_widget.show()
            self.calendar_widget.activateWindow()
            self.calendar_widget.raise_()

    def position_calendar_above_tray(self):
        """Position calendar widget above tray icon."""
        screen = QApplication.primaryScreen().availableGeometry()
        tray_geometry = self.geometry()

        widget_width = self.calendar_widget.width()
        widget_height = self.calendar_widget.height()

        if tray_geometry.isValid():
            x = tray_geometry.center().x() - widget_width // 2
            y = tray_geometry.top() - widget_height - 5

            # Adjust for screen boundaries
            if x < 0:
                x = 5
            elif x + widget_width > screen.width():
                x = screen.width() - widget_width - 5

            if y < 0:
                y = tray_geometry.bottom() + 5
        else:
            # Fallback positioning
            x = screen.width() - widget_width - 10
            y = screen.height() - widget_height - 50

        self.calendar_widget.move(x, y)


def main():
    """Main function to run the application."""
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Check system tray availability
    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("System tray is not available on this system.")
        sys.exit(1)

    # Create and show tray icon
    tray_icon = SystemTrayIcon()
    tray_icon.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()