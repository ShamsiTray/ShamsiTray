import sys
from PyQt5 import QtWidgets, QtGui, QtCore
import jdatetime

# Persian month names
PERSIAN_MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد",
    "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"
]

# Sample holidays in Persian
HOLIDAYS = {
    1: "نوروز",
    13: "سیزده بدر",
}

class CalendarPopup(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        self.setLayoutDirection(QtCore.Qt.RightToLeft)
        self.setStyleSheet("background-color: #2b2b2b; color: white; border-radius: 8px;")
        self.setFixedSize(240, 280)

        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)

        # Title bar
        self.title_bar = QtWidgets.QHBoxLayout()
        self.title_label = QtWidgets.QLabel("تقویم جلالی")
        self.title_label.setFont(QtGui.QFont("Tahoma", 10, QtGui.QFont.Bold))
        self.title_label.setStyleSheet("color: white;")
        self.title_bar.addWidget(self.title_label)
        self.title_bar.addStretch()

        close_btn = QtWidgets.QPushButton("✕")
        close_btn.setStyleSheet("background-color: transparent; color: red; font-weight: bold;")
        close_btn.setFixedSize(20, 20)
        close_btn.clicked.connect(self.hide)
        self.title_bar.addWidget(close_btn)

        self.main_layout.addLayout(self.title_bar)

        # Grid for calendar
        self.grid = QtWidgets.QGridLayout()
        self.grid.setSpacing(4)
        self.main_layout.addLayout(self.grid)

        self.today = jdatetime.date.today()
        self.current_year = self.today.year
        self.current_month = self.today.month

        self.draw_calendar(self.current_year, self.current_month)

    def draw_calendar(self, year, month):
        while self.grid.count():
            child = self.grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        weekdays = ['جمعه', 'پنجشنبه', 'چهارشنبه', 'سه‌شنبه', 'دوشنبه', 'یک‌شنبه', 'شنبه']
        for i, wd in enumerate(weekdays):
            lbl = QtWidgets.QLabel(wd)
            lbl.setAlignment(QtCore.Qt.AlignCenter)
            lbl.setFont(QtGui.QFont("Tahoma", 9))
            lbl.setStyleSheet("color: white;")
            self.grid.addWidget(lbl, 0, i)

        first_day = jdatetime.date(year, month, 1)
        first_weekday = (first_day.weekday() + 2) % 7

        days_in_month = jdatetime.j_days_in_month[month - 1]
        if month == 12 and jdatetime.j_isleap(year):
            days_in_month += 1

        col = (6 - first_weekday) % 7
        row = 1

        for day in range(1, days_in_month + 1):
            date_obj = jdatetime.date(year, month, day)
            weekday = (date_obj.weekday() + 2) % 7

            btn = QtWidgets.QPushButton(str(day))
            btn.setFixedSize(28, 28)
            btn.setFont(QtGui.QFont("Tahoma", 9, QtGui.QFont.Bold))
            btn.setStyleSheet("border: none;")

            if weekday == 6 or day in HOLIDAYS:
                btn.setStyleSheet("color: red; border: none;")
                btn.setToolTip(HOLIDAYS.get(day, "تعطیل"))
            else:
                btn.setStyleSheet("color: white; border: none;")

            self.grid.addWidget(btn, row, col)

            col -= 1
            if col < 0:
                col = 6
                row += 1
                
    def __init__(self, parent=None):
        super().__init__(parent, QtCore.Qt.WindowStaysOnTopHint)
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.Tool)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setLayoutDirection(QtCore.Qt.RightToLeft)
        self.setStyleSheet("background-color: #1e1e1e; color: white; border-radius: 8px;")
        self.setFixedSize(240, 280)

        self.shadow = QtWidgets.QGraphicsDropShadowEffect()
        self.shadow.setBlurRadius(15)
        self.shadow.setOffset(0, 0)
        self.setGraphicsEffect(self.shadow)

        self.main_layout = QtWidgets.QVBoxLayout()
        self.setLayout(self.main_layout)

        self.title_bar = QtWidgets.QHBoxLayout()
        self.title_bar.setContentsMargins(5, 5, 5, 0)
        self.title_label = QtWidgets.QLabel("تقویم جلالی")
        self.title_label.setFont(QtGui.QFont("Tahoma", 10, QtGui.QFont.Bold))
        self.title_label.setStyleSheet("color: white;")
        self.title_bar.addWidget(self.title_label)
        self.title_bar.addStretch()

        close_btn = QtWidgets.QPushButton("✕")
        close_btn.setStyleSheet("background-color: transparent; color: red; font-weight: bold;")
        close_btn.setFixedSize(20, 20)
        close_btn.clicked.connect(self.hide)
        self.title_bar.addWidget(close_btn)

        self.main_layout.addLayout(self.title_bar)

        self.grid = QtWidgets.QGridLayout()
        self.grid.setSpacing(4)
        self.grid.setContentsMargins(8, 8, 8, 8)

        self.main_layout.addLayout(self.grid)

        self.today = jdatetime.date.today()
        self.current_year = self.today.year
        self.current_month = self.today.month

        self.draw_calendar(self.current_year, self.current_month)

    def draw_calendar(self, year, month):
        # Clear previous grid
        while self.grid.count():
            child = self.grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Persian weekdays right to left
        weekdays = ['جمعه', 'پنجشنبه', 'چهارشنبه', 'سه‌شنبه', 'دوشنبه', 'یک‌شنبه', 'شنبه']
        for i, wd in enumerate(weekdays):
            lbl = QtWidgets.QLabel(wd)
            lbl.setAlignment(QtCore.Qt.AlignCenter)
            lbl.setFont(QtGui.QFont("Tahoma", 9))
            lbl.setStyleSheet("color: white;")
            self.grid.addWidget(lbl, 0, i)

        first_day = jdatetime.date(year, month, 1)
        first_weekday = (first_day.weekday() + 2) % 7

        days_in_month = jdatetime.j_days_in_month[month - 1]
        if month == 12 and jdatetime.j_isleap(year):
            days_in_month += 1

        col = (6 - first_weekday) % 7
        row = 1

        for day in range(1, days_in_month + 1):
            date_obj = jdatetime.date(year, month, day)
            weekday = (date_obj.weekday() + 2) % 7

            btn = QtWidgets.QPushButton(str(day))
            btn.setFixedSize(28, 28)
            btn.setFont(QtGui.QFont("Tahoma", 9, QtGui.QFont.Bold))
            btn.setStyleSheet("border: none;")

            if weekday == 6 or day in HOLIDAYS:
                btn.setStyleSheet("color: red; border: none;")
                btn.setToolTip(HOLIDAYS.get(day, "تعطیل"))
            else:
                btn.setStyleSheet("color: white; border: none;")

            self.grid.addWidget(btn, row, col)

            col -= 1
            if col < 0:
                col = 6
                row += 1

class TrayApp(QtWidgets.QApplication):
    def __init__(self, argv):
        super().__init__(argv)
        self.setQuitOnLastWindowClosed(False)

        self.tray = QtWidgets.QSystemTrayIcon()
        self.tray.setIcon(self.get_icon())
        self.tray.setToolTip(self.get_tooltip())
        self.tray.activated.connect(self.on_click)
        self.tray.show()

        self.popup = CalendarPopup()

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(60000)  # every 60s

    def get_tooltip(self):
        today = jdatetime.date.today()
        return f"{today.day} {PERSIAN_MONTHS[today.month -1]} {today.year}"

    def get_icon(self):
        today = jdatetime.date.today()
        weekday = (today.weekday() + 2) % 7

        pixmap = QtGui.QPixmap(32, 32)
        pixmap.fill(QtCore.Qt.transparent)

        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setFont(QtGui.QFont("Tahoma", 16, QtGui.QFont.Bold))

        if weekday == 6 or today.day in HOLIDAYS:
            painter.setPen(QtGui.QColor("red"))
        else:
            painter.setPen(QtGui.QColor("white"))

        painter.drawText(pixmap.rect(), QtCore.Qt.AlignCenter, str(today.day))
        painter.end()

        return QtGui.QIcon(pixmap)

    def refresh(self):
        self.tray.setIcon(self.get_icon())
        self.tray.setToolTip(self.get_tooltip())

    def on_click(self, reason):
        if reason == QtWidgets.QSystemTrayIcon.Trigger:
            if self.popup.isVisible():
                self.popup.hide()
            else:
                self.popup.move(QtGui.QCursor.pos())
                self.popup.show()
                self.popup.raise_()
                self.popup.activateWindow()

if __name__ == "__main__":
    app = TrayApp(sys.argv)
    sys.exit(app.exec())
