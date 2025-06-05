import sys
from PyQt5.QtWidgets import (QApplication, QSystemTrayIcon, QWidget, QVBoxLayout, 
                            QGridLayout, QLabel, QPushButton, QFrame, QToolTip)
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QCursor
from PyQt5.QtCore import Qt, QSize, QPoint, QTimer
import jdatetime
from datetime import datetime, timedelta

# Persian month names
PERSIAN_MONTHS = {
    1: "فروردین",
    2: "اردیبهشت",
    3: "خرداد",
    4: "تیر",
    5: "مرداد",
    6: "شهریور",
    7: "مهر",
    8: "آبان",
    9: "آذر",
    10: "دی",
    11: "بهمن",
    12: "اسفند"
}

# Persian weekday abbreviations (RTL order)
WEEKDAYS = ["ش", "ی", "د", "س", "ج", "ب", "ع"]

# Holidays database (month, day, event_name)
HOLIDAYS = [
    (1, 1, "عید نوروز"),
    (1, 2, "عید نوروز"),
    (1, 3, "عید نوروز"),
    (1, 4, "عید نوروز"),
    (1, 12, "روز جمهوری اسلامی"),
    (1, 13, "روز طبیعت"),
    (3, 14, "رحلت امام خمینی"),
    (3, 15, "قیام ۱۵ خرداد"),
    (11, 22, "پیروزی انقلاب اسلامی"),
    (12, 29, "روز ملی شدن صنعت نفت")
]

def to_persian_digits(text):
    """Convert English digits to Persian digits"""
    persian_digits = {
        '0': '۰', '1': '۱', '2': '۲', '3': '۳', '4': '۴',
        '5': '۵', '6': '۶', '7': '۷', '8': '۸', '9': '۹'
    }
    return ''.join(persian_digits.get(char, char) for char in str(text))

def get_jalali_days_in_month(year, month):
    """Get number of days in a Jalali month"""
    if month <= 6:
        return 31
    elif month <= 11:
        return 30
    else:  # Esfand (month 12)
        # Check if leap year (leap years have 30 days in Esfand)
        # Jalali leap year formula: (year % 4 == 3)
        return 30 if (year % 4 == 3) else 29

class TitleBar(QWidget):
    """Custom title bar for the calendar popup with drag functionality"""
    def __init__(self, parent):
        super().__init__(parent)
        self.setFixedHeight(30)
        self.setStyleSheet("background-color: #222; border-radius: 5px;")
        self.parent = parent
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 0, 5, 0)
        
        # Horizontal layout for buttons and title
        h_layout = QVBoxLayout()
        h_layout.setContentsMargins(0, 0, 0, 0)
        
        # Close button
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(20, 20)
        self.close_btn.setStyleSheet(
            "QPushButton { background-color: #444; color: white; border: none; border-radius: 3px; }"
            "QPushButton:hover { background-color: #f00; }"
        )
        self.close_btn.clicked.connect(parent.close)
        
        # Title (empty space for visual balance)
        self.title = QLabel()
        
        # Add widgets to layout
        h_layout.addWidget(self.close_btn, 0, Qt.AlignRight)
        h_layout.addWidget(self.title)
        layout.addLayout(h_layout)
    
    def mousePressEvent(self, event):
        """Handle mouse press for window dragging"""
        if event.button() == Qt.LeftButton:
            self.parent.dragging = True
            self.parent.offset = event.globalPos() - self.parent.pos()
            event.accept()
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for window dragging"""
        if self.parent.dragging and event.buttons() == Qt.LeftButton:
            self.parent.move(event.globalPos() - self.parent.offset)
            event.accept()
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release for window dragging"""
        if event.button() == Qt.LeftButton:
            self.parent.dragging = False
            event.accept()

class CalendarPopup(QWidget):
    """Popup window showing the Jalali calendar with movable capability"""
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Popup | Qt.WindowStaysOnTopHint)
        self.setFixedSize(350, 300)
        self.setStyleSheet("""
            background-color: #333; 
            color: white; 
            border: 1px solid #555;
            border-radius: 5px;
        """)
        self.setLayoutDirection(Qt.RightToLeft)
        
        # Initialize dragging variables
        self.dragging = False
        self.offset = QPoint()
        
        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 10)
        main_layout.setSpacing(0)
        
        # Custom title bar
        self.title_bar = TitleBar(self)
        main_layout.addWidget(self.title_bar)
        
        # Calendar content
        self.calendar_frame = QFrame()
        self.calendar_frame.setStyleSheet("background-color: #333;")
        main_layout.addWidget(self.calendar_frame)
        
        self.setLayout(main_layout)
        self.update_calendar()

    def update_calendar(self):
        """Generate and display the current month's calendar"""
        # Clear previous content
        if hasattr(self, 'grid_layout'):
            for i in reversed(range(self.grid_layout.count())):
                self.grid_layout.itemAt(i).widget().deleteLater()
        
        # Setup new layout
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 10, 15, 10)
        self.calendar_frame.setLayout(layout)
        
        # Month and year header
        now = jdatetime.date.today()
        month_name = PERSIAN_MONTHS[now.month]
        header = QLabel(f"{month_name} {to_persian_digits(now.year)}")
        header.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 15px;")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)
        
        # Grid layout for calendar days
        self.grid_layout = QGridLayout()
        self.grid_layout.setHorizontalSpacing(5)
        self.grid_layout.setVerticalSpacing(8)
        
        # Add weekday headers
        for i, day in enumerate(WEEKDAYS):
            label = QLabel(day)
            label.setStyleSheet("color: #aaa; font-weight: bold;")
            label.setAlignment(Qt.AlignCenter)
            self.grid_layout.addWidget(label, 0, i)
        
        # Get first day of month and total days
        first_day = jdatetime.date(now.year, now.month, 1)
        start_offset = (first_day.weekday() + 2) % 7  # Adjust for RTL Saturday start
        total_days = get_jalali_days_in_month(now.year, now.month)
        
        # Add day cells to grid
        row, col = 1, 0
        for day in range(1, total_days + 1):
            # Calculate position in grid
            if day == 1:
                col = start_offset
            elif col == 6:
                row += 1
                col = 0
            else:
                col += 1
            
            # Create day label
            day_label = QLabel(to_persian_digits(day))
            day_label.setAlignment(Qt.AlignCenter)
            day_label.setFixedSize(30, 30)
            
            # Check if today
            if day == now.day:
                day_label.setStyleSheet(
                    "background-color: #555; border-radius: 15px; font-weight: bold;"
                )
            # Check if holiday or Friday
            elif self.is_holiday(now.year, now.month, day):
                day_label.setStyleSheet("color: #ff5555; font-weight: bold;")
                # Add tooltip for holiday
                event = self.get_holiday_event(now.year, now.month, day)
                day_label.setToolTip(event)
            else:
                day_label.setStyleSheet("color: white;")
            
            # Add to grid
            self.grid_layout.addWidget(day_label, row, col)
        
        layout.addLayout(self.grid_layout)

    def is_holiday(self, year, month, day):
        """Check if a date is a holiday or Friday"""
        date = jdatetime.date(year, month, day)
        # Friday is always a holiday
        if date.weekday() == 4:  # Friday
            return True
        # Check fixed holidays
        for m, d, _ in HOLIDAYS:
            if m == month and d == day:
                return True
        return False

    def get_holiday_event(self, year, month, day):
        """Get holiday event name for a date"""
        # Friday
        date = jdatetime.date(year, month, day)
        if date.weekday() == 4:
            return "جمعه"
        # Fixed holidays
        for m, d, event in HOLIDAYS:
            if m == month and d == day:
                return event
        return ""

class TrayCalendarApp(QSystemTrayIcon):
    """System tray application with calendar popup"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setToolTip("تقویم جلالی")
        
        # Create tray icon
        self.update_icon()
        
        # Create calendar popup
        self.calendar_popup = CalendarPopup()
        
        # Setup timer to update date at midnight
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_date)
        self.timer.start(60_000)  # Update every minute
        
        # Connect click event
        self.activated.connect(self.on_tray_activated)

    def update_icon(self):
        """Create tray icon with current day number"""
        today = jdatetime.date.today().day
        
        # Create pixmap with day number
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw circle background
        painter.setBrush(QColor(60, 60, 60))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, 32, 32)
        
        # Draw day number
        painter.setFont(QFont("Arial", 14, QFont.Bold))
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, to_persian_digits(today))
        painter.end()
        
        self.setIcon(QIcon(pixmap))

    def update_date(self):
        """Update the icon and calendar at regular intervals"""
        self.update_icon()
        self.calendar_popup.update_calendar()

    def on_tray_activated(self, reason):
        """Show calendar when tray icon is clicked"""
        if reason == QSystemTrayIcon.Trigger:  # Left click
            # Position popup at cursor
            pos = QCursor.pos()
            # Adjust position to ensure it's visible
            screen_geometry = QApplication.desktop().availableGeometry()
            x = min(pos.x() - 175, screen_geometry.width() - self.calendar_popup.width())
            y = min(pos.y() - 10, screen_geometry.height() - self.calendar_popup.height())
            self.calendar_popup.move(x, y)
            self.calendar_popup.show()

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    # Set application name and style
    app.setApplicationName("Jalali Calendar")
    app.setStyle("Fusion")
    
    # Create tray app
    tray_app = TrayCalendarApp()
    tray_app.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()