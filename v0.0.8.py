import sys
import jdatetime
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QGridLayout, QSystemTrayIcon,
                             QMenu, QFrame, QSizePolicy, QSpacerItem) # Import QSizePolicy and QSpacerItem
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QSize
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QFont, QColor, QPen

class PersianCalendarWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.current_date = jdatetime.date.today()
        self.display_date = self.current_date
        self.setup_holidays()
        self.drag_pos = None

        # Set window flags and attributes
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(0, 0, 320, 400) # Set initial geometry
        self.setWindowTitle("تقویم جلالی") # Removed [cite: 1]

        self.setup_ui() # Call a method to set up the UI

        # Initialize day labels list (they are created dynamically)
        self.day_labels = []
        for row in range(6):
            week_labels = []
            for col in range(7):
                label = QLabel()
                label.setAlignment(Qt.AlignCenter)
                label.setFixedSize(35, 32)
                # Apply base styling for day labels
                label.setStyleSheet("""
                    QLabel {
                        background: transparent;
                        border: none;
                        font-size: 13px;
                        font-weight: 500;
                        border-radius: 16px;
                    }
                    QLabel:hover {
                        background-color: rgba(255, 255, 255, 0.1);
                    }
                """)
                self.calendar_grid.addWidget(label, row, col)
                week_labels.append(label)
            self.day_labels.append(week_labels)

        self.update_calendar()
        
    def setup_ui(self):
        """Manually sets up the UI elements defined in calendar.txt."""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        container = QFrame(self)
        container.setObjectName('container') # Set object name for consistency
        container.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3a3a3a, stop:1 #2a2a2a);
                border: 1px solid #4a4a4a;
                border-radius: 16px;
            }
        """)
        container.setFrameShape(QFrame.NoFrame)
        container.setFrameShadow(QFrame.Raised)
        
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(8)
        container_layout.setContentsMargins(8, 8, 8, 8)

        # Title Bar
        self.title_bar = QFrame(container)
        self.title_bar.setObjectName('title_bar')
        self.title_bar.setMinimumSize(QSize(0, 35))
        self.title_bar.setMaximumSize(QSize(16777215, 35))
        self.title_bar.setStyleSheet("""
            QFrame { 
                background-color: rgba(50, 50, 50, 0.9);
                border-radius: 8px;
                border-bottom: 1px solid #555;
            }
        """)
        self.title_bar.setFrameShape(QFrame.NoFrame)
        self.title_bar.setFrameShadow(QFrame.Raised)

        title_bar_layout = QHBoxLayout(self.title_bar)
        title_bar_layout.setSpacing(0)
        title_bar_layout.setContentsMargins(12, 0, 8, 0)

        self.title_label = QLabel("تقویم جلالی", self.title_bar)
        self.title_label.setObjectName('title_label')
        self.title_label.setStyleSheet("""
            color: #e0e0e0;
            font-weight: 600;
            font-size: 13px;
            background: transparent;
        """)
        title_bar_layout.addWidget(self.title_label)

        horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        title_bar_layout.addItem(horizontalSpacer)

        self.min_btn = QPushButton("−", self.title_bar)
        self.min_btn.setObjectName('min_btn')
        self.min_btn.setMinimumSize(QSize(28, 28))
        self.min_btn.setMaximumSize(QSize(28, 28))
        self.min_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(100, 100, 100, 0.3);
                color: #e0e0e0;
                border: none;
                border-radius: 14px;
                font-weight: bold;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: rgba(120, 120, 120, 0.5);
            }
            QPushButton:pressed {
                background-color: rgba(80, 80, 80, 0.7);
            }
        """)
        title_bar_layout.addWidget(self.min_btn)

        self.close_btn = QPushButton("×", self.title_bar)
        self.close_btn.setObjectName('close_btn')
        self.close_btn.setMinimumSize(QSize(28, 28))
        self.close_btn.setMaximumSize(QSize(28, 28))
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(220, 50, 50, 0.3);
                color: #e0e0e0;
                border: none;
                border-radius: 14px;
                font-weight: bold;
                font-size: 18px;
            }
            QPushButton:hover {
                background-color: rgba(220, 50, 50, 0.6);
            }
            QPushButton:pressed {
                background-color: rgba(180, 40, 40, 0.8);
            }
        """)
        title_bar_layout.addWidget(self.close_btn)
        container_layout.addWidget(self.title_bar)

        # Calendar Content
        self.calendar_content = QFrame(container)
        self.calendar_content.setObjectName('calendar_content')
        self.calendar_content.setFrameShape(QFrame.NoFrame)
        self.calendar_content.setFrameShadow(QFrame.Raised)
        
        calendar_content_layout = QVBoxLayout(self.calendar_content)
        calendar_content_layout.setSpacing(10)

        # Navigation Layout
        nav_layout = QHBoxLayout()
        nav_layout.setObjectName('nav_layout')
        
        self.prev_btn = QPushButton("❮", self.calendar_content)
        self.prev_btn.setObjectName('prev_btn')
        self.prev_btn.setMinimumSize(QSize(30, 30))
        self.prev_btn.setMaximumSize(QSize(30, 30))
        self.prev_btn.setStyleSheet("""
            QPushButton {
                background-color: #555;
                color: white;
                border: none;
                border-radius: 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #666;
            }
        """)
        nav_layout.addWidget(self.prev_btn)

        horizontalSpacer_2 = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        nav_layout.addItem(horizontalSpacer_2)

        self.month_year_label = QLabel("Month Year", self.calendar_content)
        self.month_year_label.setObjectName('month_year_label')
        self.month_year_label.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
        self.month_year_label.setAlignment(Qt.AlignCenter)
        nav_layout.addWidget(self.month_year_label)

        horizontalSpacer_3 = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        nav_layout.addItem(horizontalSpacer_3)

        self.next_btn = QPushButton("❯", self.calendar_content)
        self.next_btn.setObjectName('next_btn')
        self.next_btn.setMinimumSize(QSize(30, 30))
        self.next_btn.setMaximumSize(QSize(30, 30))
        self.next_btn.setStyleSheet("""
            QPushButton {
                background-color: #555;
                color: white;
                border: none;
                border-radius: 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #666;
            }
        """)
        nav_layout.addWidget(self.next_btn)
        calendar_content_layout.addLayout(nav_layout)

        # Weekday Layout
        weekday_layout = QHBoxLayout()
        weekday_layout.setObjectName('weekday_layout')
        weekday_layout.setSpacing(5)

        weekdays = [
            ("label_friday", "ج", "#ff6b6b"), # Friday
            ("label_thursday", "پ", "#999"), # Thursday
            ("label_wednesday", "چ", "#999"), # Wednesday
            ("label_tuesday", "س", "#999"), # Tuesday
            ("label_monday", "د", "#999"), # Monday
            ("label_sunday", "ی", "#999"), # Sunday
            ("label_saturday", "ش", "#999") # Saturday
        ]

        for obj_name, text, color in weekdays:
            label = QLabel(text, self.calendar_content)
            label.setObjectName(obj_name)
            label.setMinimumSize(QSize(35, 25))
            label.setMaximumSize(QSize(35, 25))
            label.setStyleSheet(f"""
                QLabel {{
                    color: {color};
                    font-weight: bold;
                    font-size: 11px;
                    background: transparent;
                }}
            """)
            label.setAlignment(Qt.AlignCenter)
            weekday_layout.addWidget(label)
        calendar_content_layout.addLayout(weekday_layout)

        # Calendar Grid
        self.calendar_grid = QGridLayout()
        self.calendar_grid.setObjectName('calendar_grid')
        self.calendar_grid.setSpacing(3)
        calendar_content_layout.addLayout(self.calendar_grid)
        
        container_layout.addWidget(self.calendar_content)
        main_layout.addWidget(container)

        # Connect signals
        self.min_btn.clicked.connect(self.hide)
        self.close_btn.clicked.connect(self.close)
        self.prev_btn.clicked.connect(self.prev_month)
        self.next_btn.clicked.connect(self.next_month)

        # Make title bar draggable
        self.title_bar.mousePressEvent = self.mousePressEvent
        self.title_bar.mouseMoveEvent = self.mouseMoveEvent
        self.title_bar.mouseReleaseEvent = self.mouseReleaseEvent

    def setup_holidays(self):
        """Define Persian holidays"""
        self.holidays = {
            (1, 1): "نوروز",
            (1, 2): "نوروز",
            (1, 3): "نوروز",
            (1, 4): "نوروز",
            (1, 12): "روز جمهوری اسلامی",
            (1, 13): "سیزده بدر",
            (3, 14): "رحلت امام خمینی",
            (3, 15): "قیام ۱۵ خرداد",
            (11, 22): "پیروزی انقلاب اسلامی",
            (12, 29): "روز ملی شدن صنعت نفت",
            # Add more holidays as needed
        }
    
    def update_calendar(self):
        """Updates the calendar grid with dates and applies styling based on today, Fridays, and holidays."""
        # Update month/year label
        persian_months = [
            "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
            "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"
        ]
        
        month_name = persian_months[self.display_date.month - 1]
        year = self.display_date.year
        self.month_year_label.setText(f"{month_name} {year}")
        
        # Clear previous calendar and reset styling
        for week in self.day_labels:
            for label in week:
                label.setText("")
                label.setStyleSheet("""
                    QLabel {
                        background: transparent;
                        border: none;
                        font-size: 13px;
                        font-weight: 500;
                        color: #ddd;
                        border-radius: 16px;
                    }
                    QLabel:hover {
                        background-color: rgba(255, 255, 255, 0.1);
                    }
                """)
                label.setToolTip("")
        
        # Get first day of month and number of days
        first_day = jdatetime.date(self.display_date.year, self.display_date.month, 1)
        # Adjust for RTL (0=Friday, 6=Thursday)
        # jdatetime.weekday() returns 0 for Saturday, 1 for Sunday, ..., 6 for Friday.
        # We want Friday to be index 0 in our display.
        first_weekday = (first_day.weekday() + 1) % 7 
        
        # Number of days in month
        if self.display_date.month == 12:
            next_month = jdatetime.date(self.display_date.year + 1, 1, 1)
        else:
            next_month = jdatetime.date(self.display_date.year, self.display_date.month + 1, 1)
        
        days_in_month = (next_month - first_day).days
        
        # Fill calendar (RTL layout)
        day = 1
        for week in range(6):
            for col_display_idx in range(7): # col_display_idx runs from 0 (Friday) to 6 (Thursday)
                if week == 0 and col_display_idx < first_weekday:
                    # Skip cells before the first day of the month
                    continue
                if day > days_in_month:
                    break
                        
                label = self.day_labels[week][col_display_idx]
                label.setText(str(day))
                
                # Check if it's today
                is_today = (day == self.current_date.day and 
                            self.display_date.month == self.current_date.month and
                            self.display_date.year == self.current_date.year)
                
                # Check if it's Friday or holiday (Friday is at index 0 in RTL grid)
                is_friday = col_display_idx == 0
                is_holiday = (self.display_date.month, day) in self.holidays
                
                if is_today:
                    label.setStyleSheet("""
                        QLabel {
                            background-color: #ff8a00;
                            color: white;
                            border-radius: 16px;
                            font-size: 13px;
                            font-weight: bold;
                            border: none;
                        }
                        QLabel:hover {
                            background-color: #e67600;
                        }
                    """)
                elif is_friday or is_holiday:
                    label.setStyleSheet("""
                        QLabel {
                            background: transparent;
                            color: #ff6b6b;
                            border-radius: 16px;
                            font-size: 13px;
                            font-weight: 500;
                            border: none;
                        }
                        QLabel:hover {
                            background-color: rgba(255, 107, 107, 0.1);
                        }
                    """)
                    if is_holiday:
                        label.setToolTip(self.holidays[(self.display_date.month, day)])
                else:
                    label.setStyleSheet("""
                        QLabel {
                            background: transparent;
                            color: #ddd;
                            border-radius: 16px;
                            font-size: 13px;
                            font-weight: 500;
                            border: none;
                        }
                        QLabel:hover {
                            background-color: rgba(255, 255, 255, 0.1);
                        }
                    """)
                
                day += 1
    
    def mousePressEvent(self, event):
        """Handles mouse press events for window dragging."""
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event):
        """Handles mouse move events for window dragging."""
        if event.buttons() == Qt.LeftButton and self.drag_pos:
            self.move(event.globalPos() - self.drag_pos)
            event.accept()
    
    def mouseReleaseEvent(self, event):
        """Handles mouse release events for window dragging."""
        self.drag_pos = None

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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.calendar_widget = None
        self.current_date = jdatetime.date.today()
        
        # Create tray icon with current day
        self.create_tray_icon()
        
        # Setup context menu
        self.setup_context_menu()
        
        # Connect signals
        self.activated.connect(self.on_tray_icon_activated)
        
        # Update icon daily
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_tray_icon)
        self.timer.start(60000)  # Check every minute for date change
    
    def create_tray_icon(self):
        """Creates or updates the system tray icon with the current day."""
        # Create a pixmap with the current day number
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw background circle
        painter.setBrush(QColor(45, 45, 45))
        painter.setPen(QPen(QColor(85, 85, 85), 2))
        painter.drawEllipse(2, 2, 28, 28)
        
        # Draw day number
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Arial", 12, QFont.Bold)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, str(self.current_date.day))
        
        painter.end()
        
        icon = QIcon(pixmap)
        self.setIcon(icon)
        self.setToolTip(f"تقویم جلالی - {self.current_date.day}")
    
    def update_tray_icon(self):
        """Checks if the date has changed and updates the tray icon and calendar widget."""
        new_date = jdatetime.date.today()
        if new_date != self.current_date:
            self.current_date = new_date
            self.create_tray_icon()
            if self.calendar_widget:
                self.calendar_widget.current_date = new_date
                self.calendar_widget.update_calendar()
    
    def setup_context_menu(self):
        """Sets up the context menu for the system tray icon."""
        menu = QMenu()
        
        show_action = menu.addAction("نمایش تقویم")
        show_action.triggered.connect(self.show_calendar)
        
        menu.addSeparator()
        
        exit_action = menu.addAction("خروج")
        exit_action.triggered.connect(QApplication.quit)
        
        self.setContextMenu(menu)
    
    def on_tray_icon_activated(self, reason):
        """Handles activation events of the system tray icon."""
        if reason == QSystemTrayIcon.Trigger:  # Left click
            self.show_calendar()
    
    def show_calendar(self):
        """Shows or hides the calendar widget."""
        if not self.calendar_widget:
            self.calendar_widget = PersianCalendarWidget()
        
        if self.calendar_widget.isVisible():
            self.calendar_widget.hide()
        else:
            # Position near system tray (you might want to refine this for exact positioning)
            self.calendar_widget.show()
            self.calendar_widget.activateWindow()
            self.calendar_widget.raise_()

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    # Check if system tray is available
    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("System tray is not available on this system.")
        sys.exit(1)
    
    # Create and show system tray icon
    tray_icon = SystemTrayIcon()
    tray_icon.show()
    
    # Show a message when starting
    tray_icon.showMessage("تقویم جلالی", "تقویم جلالی در سیستم تری فعال شد", 
                          QSystemTrayIcon.Information, 3000)
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
