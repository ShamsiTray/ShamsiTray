import sys
import jdatetime
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QGridLayout, QSystemTrayIcon,
                             QMenu, QFrame, QComboBox)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QFont, QColor, QPen

# Remove the uic import as we're no longer loading from a .ui file
# from PyQt5 import uic

class PersianCalendarWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.current_date = jdatetime.date.today()
        self.display_date = self.current_date
        self.setup_holidays()
        # Directly call create_fallback_ui as the primary UI setup
        self.create_fallback_ui()

        # Connect signals
        self.month_combo.currentIndexChanged.connect(self.on_month_changed)
        self.year_combo.currentIndexChanged.connect(self.on_year_changed)
        self.prev_btn.clicked.connect(self.prev_month)
        self.next_btn.clicked.connect(self.next_month)

        # Setup calendar grid
        self.setup_calendar_grid()
        self.update_calendar()

    # The setup_ui_from_file method is no longer needed
    # def setup_ui_from_file(self):
    #     """Setup UI components when loaded from .ui file"""
    #     # Set window properties
    #     self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Popup)
    #     self.setAttribute(Qt.WA_TranslucentBackground)
    #
    #     # Populate year combo
    #     current_year = self.current_date.year
    #     self.year_combo.clear()
    #     for year in range(current_year - 10, current_year + 10):
    #         self.year_combo.addItem(str(year))
    #     self.year_combo.setCurrentText(str(current_year))
    #
    #     # Populate month combo
    #     persian_months = [
    #         "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    #         "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"
    #     ]
    #     self.month_combo.clear()
    #     for month in persian_months:
    #         self.month_combo.addItem(month)
    #     self.month_combo.setCurrentIndex(self.current_date.month - 1)
    #
    #     # Set window size
    #     self.resize(300, 350)

    def create_fallback_ui(self):
        """Programmatic UI creation directly from .ui file structure"""
        # Remove window frame and set window flags
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Popup)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Main layout
        main_layout = QVBoxLayout(self) # Set self as parent for main_layout
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Create main container with background
        self.container = QFrame()
        self.container.setObjectName("container") # Set object name for styling
        self.container.setStyleSheet("""
            QFrame#container { /* Use object name for targeted styling */
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3a3a3a, stop:1 #2a2a2a);
                border: 1px solid #4a4a4a;
                border-radius: 16px;
            }
        """)
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(12, 12, 12, 12)
        container_layout.setSpacing(10)

        # Month/Year selection (nav_layout)
        nav_layout = QHBoxLayout()
        nav_layout.setContentsMargins(5, 5, 5, 5)

        # Previous month button
        self.prev_btn = QPushButton("❮")
        self.prev_btn.setObjectName("prev_btn") # Set object name
        self.prev_btn.setFixedSize(30, 30)
        self.prev_btn.setStyleSheet("""
            QPushButton#prev_btn { /* Use object name for targeted styling */
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #505050, stop:1 #404040);
                color: #e0e0e0;
                border: 1px solid #606060;
                border-radius: 15px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton#prev_btn:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #606060, stop:1 #505050);
            }
        """)
        nav_layout.addWidget(self.prev_btn)

        # Year dropdown
        self.year_combo = QComboBox()
        self.year_combo.setObjectName("year_combo") # Set object name
        self.year_combo.setMinimumSize(0, 32) # Corresponds to minimumSize in .ui
        current_year = self.current_date.year
        for year in range(current_year - 10, current_year + 10):
            self.year_combo.addItem(str(year))
        self.year_combo.setCurrentText(str(current_year))
        self.year_combo.setStyleSheet("""
            QComboBox#year_combo {
                background: #404040;
                color: #e0e0e0;
                border: 1px solid #606060;
                border-radius: 6px;
                padding: 5px;
                font-size: 13px;
                font-weight: 500;
            }
            QComboBox#year_combo::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox#year_combo::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #e0e0e0;
                margin-right: 5px;
            }
            QComboBox#year_combo QAbstractItemView {
                background: #404040;
                color: #e0e0e0;
                border: 1px solid #606060;
                selection-background-color: #505050;
            }
        """)
        nav_layout.addWidget(self.year_combo)

        # Month dropdown
        self.month_combo = QComboBox()
        self.month_combo.setObjectName("month_combo") # Set object name
        self.month_combo.setMinimumSize(0, 32) # Corresponds to minimumSize in .ui
        persian_months = [
            "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
            "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"
        ]
        for month in persian_months:
            self.month_combo.addItem(month)
        self.month_combo.setCurrentIndex(self.current_date.month - 1)
        self.month_combo.setStyleSheet("""
            QComboBox#month_combo {
                background: #404040;
                color: #e0e0e0;
                border: 1px solid #606060;
                border-radius: 6px;
                padding: 5px;
                font-size: 13px;
                font-weight: 500;
            }
            QComboBox#month_combo::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox#month_combo::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #e0e0e0;
                margin-right: 5px;
            }
            QComboBox#month_combo QAbstractItemView {
                background: #404040;
                color: #e0e0e0;
                border: 1px solid #606060;
                selection-background-color: #505050;
            }
        """)
        nav_layout.addWidget(self.month_combo)

        # Next month button
        self.next_btn = QPushButton("❯")
        self.next_btn.setObjectName("next_btn") # Set object name
        self.next_btn.setFixedSize(30, 30)
        self.next_btn.setStyleSheet("""
            QPushButton#next_btn {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #505050, stop:1 #404040);
                color: #e0e0e0;
                border: 1px solid #606060;
                border-radius: 15px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton#next_btn:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #606060, stop:1 #505050);
            }
        """)
        nav_layout.addWidget(self.next_btn)

        container_layout.addLayout(nav_layout)

        # Weekday headers (RTL: Saturday to Friday)
        weekdays = ["ش", "ی", "د", "س", "چ", "پ", "ج"]  # Saturday to Friday (RTL)
        weekday_layout = QHBoxLayout()
        weekday_layout.setSpacing(6)
        weekday_layout.setContentsMargins(5, 5, 5, 5)

        # Create QLabel objects for each weekday header
        self.sat_label = QLabel("ش")
        self.sun_label = QLabel("ی")
        self.mon_label = QLabel("د")
        self.tue_label = QLabel("س")
        self.wed_label = QLabel("چ")
        self.thu_label = QLabel("پ")
        self.fri_label = QLabel("ج")

        # Add object names and styling for each weekday label
        self.sat_label.setObjectName("sat_label")
        self.sat_label.setAlignment(Qt.AlignCenter)
        self.sat_label.setFixedSize(35, 25)
        self.sat_label.setStyleSheet("QLabel#sat_label { color: #b8b8b8; font-weight: 600; font-size: 11px; background: transparent; }")
        weekday_layout.addWidget(self.sat_label)

        self.sun_label.setObjectName("sun_label")
        self.sun_label.setAlignment(Qt.AlignCenter)
        self.sun_label.setFixedSize(35, 25)
        self.sun_label.setStyleSheet("QLabel#sun_label { color: #b8b8b8; font-weight: 600; font-size: 11px; background: transparent; }")
        weekday_layout.addWidget(self.sun_label)

        self.mon_label.setObjectName("mon_label")
        self.mon_label.setAlignment(Qt.AlignCenter)
        self.mon_label.setFixedSize(35, 25)
        self.mon_label.setStyleSheet("QLabel#mon_label { color: #b8b8b8; font-weight: 600; font-size: 11px; background: transparent; }")
        weekday_layout.addWidget(self.mon_label)

        self.tue_label.setObjectName("tue_label")
        self.tue_label.setAlignment(Qt.AlignCenter)
        self.tue_label.setFixedSize(35, 25)
        self.tue_label.setStyleSheet("QLabel#tue_label { color: #b8b8b8; font-weight: 600; font-size: 11px; background: transparent; }")
        weekday_layout.addWidget(self.tue_label)

        self.wed_label.setObjectName("wed_label")
        self.wed_label.setAlignment(Qt.AlignCenter)
        self.wed_label.setFixedSize(35, 25)
        self.wed_label.setStyleSheet("QLabel#wed_label { color: #b8b8b8; font-weight: 600; font-size: 11px; background: transparent; }")
        weekday_layout.addWidget(self.wed_label)

        self.thu_label.setObjectName("thu_label")
        self.thu_label.setAlignment(Qt.AlignCenter)
        self.thu_label.setFixedSize(35, 25)
        self.thu_label.setStyleSheet("QLabel#thu_label { color: #b8b8b8; font-weight: 600; font-size: 11px; background: transparent; }")
        weekday_layout.addWidget(self.thu_label)

        self.fri_label.setObjectName("fri_label")
        self.fri_label.setAlignment(Qt.AlignCenter)
        self.fri_label.setFixedSize(35, 25)
        self.fri_label.setStyleSheet("QLabel#fri_label { color: #ff7979; font-weight: 600; font-size: 11px; background: transparent; }")
        weekday_layout.addWidget(self.fri_label)

        container_layout.addLayout(weekday_layout)

        # Calendar grid container
        self.calendar_frame = QFrame()
        self.calendar_frame.setObjectName("calendar_frame")
        self.calendar_frame.setStyleSheet("QFrame#calendar_frame { background: transparent; }")
        calendar_container_layout = QVBoxLayout(self.calendar_frame) # Changed to calendar_container_layout
        calendar_container_layout.setContentsMargins(5, 0, 5, 5)

        self.calendar_grid_layout = QGridLayout()
        self.calendar_grid_layout.setSpacing(4)
        calendar_container_layout.addLayout(self.calendar_grid_layout)

        container_layout.addWidget(self.calendar_frame)
        main_layout.addWidget(self.container)

        # Set window size based on .ui file
        self.setGeometry(0, 0, 300, 350) # Set initial geometry as in .ui

    def setup_calendar_grid(self):
        """Setup the calendar grid with day labels"""
        self.day_labels = []

        # Clear existing widgets if any
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
                label.setStyleSheet("""
                    QLabel {
                        background: transparent;
                        border: none;
                        font-size: 13px;
                        font-weight: 500;
                        border-radius: 16px;
                        color: #e0e0e0;
                    }
                    QLabel:hover {
                        background-color: rgba(255, 255, 255, 0.08);
                    }
                """)
                self.calendar_grid_layout.addWidget(label, row, col)
                week_labels.append(label)
            self.day_labels.append(week_labels)

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
        }

    def on_month_changed(self):
        month = self.month_combo.currentIndex() + 1
        year = int(self.year_combo.currentText())
        self.display_date = jdatetime.date(year, month, 1)
        self.update_calendar()

    def on_year_changed(self):
        month = self.month_combo.currentIndex() + 1
        year = int(self.year_combo.currentText())
        self.display_date = jdatetime.date(year, month, 1)
        self.update_calendar()

    def update_calendar(self):
        # Update dropdowns to match display_date
        self.month_combo.setCurrentIndex(self.display_date.month - 1)
        self.year_combo.setCurrentText(str(self.display_date.year))

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
                        color: #e0e0e0;
                        border-radius: 16px;
                    }
                    QLabel:hover {
                        background-color: rgba(255, 255, 255, 0.08);
                    }
                """)
                label.setToolTip("")

        # Get first day of month and number of days
        first_day = jdatetime.date(self.display_date.year, self.display_date.month, 1)
        # jdatetime weekday: 0=Saturday, 6=Friday
        first_weekday = first_day.weekday()

        # Number of days in month
        if self.display_date.month == 12:
            try:
                jdatetime.date(self.display_date.year, 12, 30) # Check if 30th Esfand exists (leap year)
                days_in_month = 30
            except ValueError:
                days_in_month = 29
        elif self.display_date.month <= 6:
            days_in_month = 31
        else:
            days_in_month = 30

        # Fill calendar (RTL layout: Saturday to Friday, right to left)
        day = 1
        for week in range(6):
            for col_index in range(7):
                # RTL: rightmost column (6) is Saturday (0), leftmost (0) is Friday (6)
                actual_weekday = 6 - col_index  # Convert RTL column to weekday

                if week == 0 and actual_weekday < first_weekday:
                    continue
                if day > days_in_month:
                    break

                label = self.day_labels[week][col_index]

                # Right-to-left number display
                persian_digits = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹']
                day_str = str(day)
                persian_day = ''.join(persian_digits[int(d)] for d in day_str)
                label.setText(persian_day)

                # Check if it's today
                is_today = (day == self.current_date.day and
                           self.display_date.month == self.current_date.month and
                           self.display_date.year == self.current_date.year)

                # Check if it's Friday or holiday
                current_weekday = (first_day.weekday() + day - 1) % 7
                is_friday = current_weekday == 6  # Friday in jdatetime is 6
                is_holiday = (self.display_date.month, day) in self.holidays

                if is_today:
                    label.setStyleSheet("""
                        QLabel {
                            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #ff9f43, stop:1 #ff6b35);
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
                    """)
                elif is_friday or is_holiday:
                    label.setStyleSheet("""
                        QLabel {
                            background: transparent;
                            color: #ff7979;
                            border-radius: 16px;
                            font-size: 13px;
                            font-weight: 500;
                            border: none;
                        }
                        QLabel:hover {
                            background-color: rgba(255, 121, 121, 0.1);
                        }
                    """)
                    if is_holiday:
                        label.setToolTip(self.holidays[(self.display_date.month, day)])
                else:
                    label.setStyleSheet("""
                        QLabel {
                            background: transparent;
                            color: #e0e0e0;
                            border-radius: 16px;
                            font-size: 13px;
                            font-weight: 500;
                            border: none;
                        }
                        QLabel:hover {
                            background-color: rgba(255, 255, 255, 0.08);
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
        # Create a pixmap with the current day number in Persian digits
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw background circle
        painter.setBrush(QColor(45, 45, 45))
        painter.setPen(QPen(QColor(85, 85, 85), 2))
        painter.drawEllipse(2, 2, 28, 28)

        # Draw day number in Persian digits
        persian_digits = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹']
        day_str = str(self.current_date.day)
        persian_day = ''.join(persian_digits[int(d)] for d in day_str)

        painter.setPen(QColor(255, 255, 255))
        font = QFont("Arial", 10, QFont.Bold)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, persian_day)

        painter.end()

        icon = QIcon(pixmap)
        self.setIcon(icon)

        # Create detailed tooltip with day name and full date
        weekday_names = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه"]
        weekday_name = weekday_names[self.current_date.weekday()]

        # Format: پنجشنبه ۱۴۰۴-۰۳-۱۵
        year_str = ''.join(persian_digits[int(d)] for d in str(self.current_date.year))
        month_str = ''.join(persian_digits[int(d)] for d in f"{self.current_date.month:02d}")
        day_str = ''.join(persian_digits[int(d)] for d in f"{self.current_date.day:02d}")

        tooltip = f"{weekday_name} {year_str}-{month_str}-{day_str}"
        self.setToolTip(tooltip)

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

        exit_action = menu.addAction("خروج")
        exit_action.triggered.connect(QApplication.quit)

        self.setContextMenu(menu)

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:  # Left click
            self.toggle_calendar()

    def toggle_calendar(self):
        if not self.calendar_widget:
            self.calendar_widget = PersianCalendarWidget()

        if self.calendar_widget.isVisible():
            self.calendar_widget.hide()
        else:
            # Position directly above the system tray icon
            self.position_calendar_above_tray()
            self.calendar_widget.show()
            self.calendar_widget.activateWindow()
            self.calendar_widget.raise_()

    def position_calendar_above_tray(self):
        """Position calendar widget directly above the system tray icon"""
        # Get screen geometry
        screen = QApplication.primaryScreen().availableGeometry()

        # Get system tray geometry if possible
        tray_geometry = self.geometry()

        if tray_geometry.isValid():
            # Position directly above the tray icon
            widget_width = self.calendar_widget.width()
            widget_height = self.calendar_widget.height()

            # Center horizontally on the tray icon
            x = tray_geometry.center().x() - widget_width // 2
            # Position above the tray icon
            y = tray_geometry.top() - widget_height - 5

            # Make sure it stays within screen bounds
            if x < 0:
                x = 5
            elif x + widget_width > screen.width():
                x = screen.width() - widget_width - 5

            if y < 0:
                y = tray_geometry.bottom() + 5  # Show below if no space above
        else:
            # Fallback to bottom-right corner if tray geometry is not available
            widget_width = self.calendar_widget.width()
            widget_height = self.calendar_widget.height()

            x = screen.width() - widget_width - 10
            y = screen.height() - widget_height - 50  # Leave space for taskbar

        self.calendar_widget.move(x, y)

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
