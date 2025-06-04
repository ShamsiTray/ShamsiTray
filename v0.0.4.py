import sys
import jdatetime
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QGridLayout, QSystemTrayIcon, 
                             QMenu, QFrame)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QFont, QColor, QPen

class PersianCalendarWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.current_date = jdatetime.date.today()
        self.display_date = self.current_date
        self.setup_holidays()  # Initialize holidays before UI
        self.drag_pos = None  # For window dragging
        self.setup_ui()
        
    def setup_ui(self):
        # Remove window frame and set window flags
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Create main container with background
        self.container = QFrame()
        self.container.setStyleSheet("""
            QFrame {
                background-color: #2d2d2d;
                border: 1px solid #444;
                border-radius: 12px;
            }
        """)
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(8, 8, 8, 8)
        container_layout.setSpacing(8)
        
        # Custom title bar
        title_bar = self.create_title_bar()
        container_layout.addWidget(title_bar)
        
        # Calendar content
        calendar_content = self.create_calendar_content()
        container_layout.addWidget(calendar_content)
        
        main_layout.addWidget(self.container)
        self.setLayout(main_layout)
        
        # Set window size
        self.resize(320, 400)
        
    def create_title_bar(self):
        title_bar = QFrame()
        title_bar.setFixedHeight(30)
        title_bar.setStyleSheet("QFrame { background-color: #333; border-radius: 4px; }")
        
        layout = QHBoxLayout(title_bar)
        layout.setContentsMargins(8, 0, 8, 0)
        
        # Title
        title_label = QLabel("تقویم جلالی")
        title_label.setStyleSheet("color: white; font-weight: bold; font-size: 12px;")
        layout.addWidget(title_label)
        
        layout.addStretch()
        
        # Minimize button
        min_btn = QPushButton("−")
        min_btn.setFixedSize(25, 25)
        min_btn.setStyleSheet("""
            QPushButton {
                background-color: #555;
                color: white;
                border: none;
                border-radius: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #666;
            }
        """)
        min_btn.clicked.connect(self.hide)
        layout.addWidget(min_btn)
        
        # Close button
        close_btn = QPushButton("×")
        close_btn.setFixedSize(25, 25)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #d32f2f;
                color: white;
                border: none;
                border-radius: 12px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #f44336;
            }
        """)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
        
        return title_bar
        
    def create_calendar_content(self):
        content = QFrame()
        layout = QVBoxLayout(content)
        layout.setSpacing(10)
        
        # Month navigation
        nav_layout = QHBoxLayout()
        
        # Previous month button
        prev_btn = QPushButton("❮")
        prev_btn.setFixedSize(30, 30)
        prev_btn.setStyleSheet("""
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
        prev_btn.clicked.connect(self.prev_month)
        nav_layout.addWidget(prev_btn)
        
        nav_layout.addStretch()
        
        # Month and year display
        self.month_year_label = QLabel()
        self.month_year_label.setAlignment(Qt.AlignCenter)
        self.month_year_label.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
        nav_layout.addWidget(self.month_year_label)
        
        nav_layout.addStretch()
        
        # Next month button
        next_btn = QPushButton("❯")
        next_btn.setFixedSize(30, 30)
        next_btn.setStyleSheet("""
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
        next_btn.clicked.connect(self.next_month)
        nav_layout.addWidget(next_btn)
        
        layout.addLayout(nav_layout)
        
        # Weekday headers (RTL: Saturday to Friday)
        weekdays = ["ج", "پ", "چ", "س", "د", "ی", "ش"]  # Friday to Saturday (RTL)
        weekday_layout = QHBoxLayout()
        weekday_layout.setSpacing(5)
        
        for day in weekdays:
            label = QLabel(day)
            label.setAlignment(Qt.AlignCenter)
            label.setFixedSize(35, 25)
            color = "#ff6b6b" if day == "ج" else "#999"  # Friday in red
            label.setStyleSheet(f"""
                QLabel {{
                    color: {color};
                    font-weight: bold;
                    font-size: 11px;
                    background: transparent;
                }}
            """)
            weekday_layout.addWidget(label)
        
        layout.addLayout(weekday_layout)
        
        # Calendar grid
        self.calendar_grid = QGridLayout()
        self.calendar_grid.setSpacing(3)
        self.day_labels = []
        
        for row in range(6):
            week_labels = []
            for col in range(7):
                label = QLabel()
                label.setAlignment(Qt.AlignCenter)
                label.setFixedSize(35, 32)
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
        
        layout.addLayout(self.calendar_grid)
        
        self.update_calendar()
        return content
    
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
        # Update month/year label
        persian_months = [
            "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
            "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"
        ]
        
        month_name = persian_months[self.display_date.month - 1]
        year = self.display_date.year
        self.month_year_label.setText(f"{month_name} {year}")
        
        # Clear previous calendar
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
        first_weekday = (first_day.weekday() + 1) % 7  # Adjust for RTL (0=Friday, 6=Thursday)
        
        # Number of days in month
        if self.display_date.month == 12:
            next_month = jdatetime.date(self.display_date.year + 1, 1, 1)
        else:
            next_month = jdatetime.date(self.display_date.year, self.display_date.month + 1, 1)
        
        days_in_month = (next_month - first_day).days
        
        # Fill calendar (RTL layout)
        day = 1
        for week in range(6):
            for weekday in range(7):
                if week == 0 and weekday < first_weekday:
                    continue
                if day > days_in_month:
                    break
                    
                label = self.day_labels[week][weekday]
                label.setText(str(day))
                
                # Check if it's today
                is_today = (day == self.current_date.day and 
                           self.display_date.month == self.current_date.month and
                           self.display_date.year == self.current_date.year)
                
                # Check if it's Friday or holiday (Friday is at index 0 in RTL)
                is_friday = weekday == 0
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
    
    def prev_month(self):
        if self.display_date.month == 1:
            self.display_date = jdatetime.date(self.display_date.year - 1, 12, 1)
        else:
            self.display_date = jdatetime.date(self.display_date.year, self.display_date.month - 1, 1)
        self.update_calendar()
    
    def next_month(self):
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
        new_date = jdatetime.date.today()
        if new_date != self.current_date:
            self.current_date = new_date
            self.create_tray_icon()
            if self.calendar_widget:
                self.calendar_widget.current_date = new_date
                self.calendar_widget.update_calendar()
    
    def setup_context_menu(self):
        menu = QMenu()
        
        show_action = menu.addAction("نمایش تقویم")
        show_action.triggered.connect(self.show_calendar)
        
        menu.addSeparator()
        
        exit_action = menu.addAction("خروج")
        exit_action.triggered.connect(QApplication.quit)
        
        self.setContextMenu(menu)
    
    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:  # Left click
            self.show_calendar()
    
    def show_calendar(self):
        if not self.calendar_widget:
            self.calendar_widget = PersianCalendarWidget()
        
        if self.calendar_widget.isVisible():
            self.calendar_widget.hide()
        else:
            # Position near system tray
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