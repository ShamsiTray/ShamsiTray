import sys
from PyQt5 import QtWidgets, QtGui, QtCore
import jdatetime

# Sample holiday data: day -> holiday name
HOLIDAYS = {
    13: "Nature Day (Sizdah Be-dar)",
    1: "New Year's Day (Nowruz)",
}

class CalendarPopup(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, QtCore.Qt.WindowStaysOnTopHint)
        self.setWindowTitle("Jalili Calendar")
        self.resize(220, 250)
        self.layout = QtWidgets.QGridLayout()
        self.setLayout(self.layout)

        self.today = jdatetime.date.today()
        self.current_year = self.today.year
        self.current_month = self.today.month

        self.draw_calendar(self.current_year, self.current_month)

    def draw_calendar(self, year, month):
        # Clear previous widgets
        for i in reversed(range(self.layout.count())):
            widget = self.layout.itemAt(i).widget()
            if widget is not None:
                widget.deleteLater()

        # Weekday names
        week_days = ['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج']  # Sat - Fri in Persian
        for i, wd in enumerate(week_days):
            lbl = QtWidgets.QLabel(wd)
            lbl.setAlignment(QtCore.Qt.AlignCenter)
            self.layout.addWidget(lbl, 0, i)

        # First day of month weekday (0=Monday, Jalili week starts Saturday)
        first_day = jdatetime.date(year, month, 1)
        first_weekday = (first_day.weekday() + 2) % 7  # adjust to Saturday=0

        # Number of days in month
        days_in_month = jdatetime.j_days_in_month[month - 1]
        if month == 12 and jdatetime.j_isleap(year):
            days_in_month += 1

        row = 1
        col = first_weekday

        for day in range(1, days_in_month + 1):
            btn = QtWidgets.QPushButton(str(day))
            btn.setFixedSize(25, 25)
            btn.setFlat(True)

            # Color coding Fridays and holidays in red
            # Friday is weekday 6 in this adjusted scale
            date_obj = jdatetime.date(year, month, day)
            weekday = (date_obj.weekday() + 2) % 7
            if weekday == 6 or day in HOLIDAYS:
                btn.setStyleSheet("color: red; font-weight: bold;")
                btn.clicked.connect(lambda checked, d=day: self.show_event(d))
            else:
                btn.setStyleSheet("color: white;")

            self.layout.addWidget(btn, row, col)
            col += 1
            if col > 6:
                col = 0
                row += 1

    def show_event(self, day):
        if day in HOLIDAYS:
            QtWidgets.QMessageBox.information(self, "Holiday Info", f"{day} {HOLIDAYS[day]}")
        else:
            QtWidgets.QMessageBox.information(self, "Info", "No event for this day.")

class TrayApp(QtWidgets.QApplication):
    def __init__(self, argv):
        super().__init__(argv)

        # Create tray icon
        self.tray = QtWidgets.QSystemTrayIcon()
        self.update_icon()

        self.tray.setToolTip(self.get_tooltip())
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()

        # Create calendar popup (hidden by default)
        self.popup = CalendarPopup()

        # Timer to update tray icon every minute
        timer = QtCore.QTimer(self)
        timer.timeout.connect(self.update_icon)
        timer.start(60000)

    def get_tooltip(self):
        today = jdatetime.date.today()
        month_names = [
            "Farvardin", "Ordibehesht", "Khordad", "Tir", "Mordad",
            "Shahrivar", "Mehr", "Aban", "Azar", "Dey", "Bahman", "Esfand"
        ]
        return f"{today.day} {month_names[today.month -1]} {today.year}"

    def update_icon(self):
        # Create a pixmap with day number
        today = jdatetime.date.today()
        pixmap = QtGui.QPixmap(32, 32)
        pixmap.fill(QtCore.Qt.transparent)

        painter = QtGui.QPainter(pixmap)
        font = QtGui.QFont("Arial", 14, QtGui.QFont.Bold)
        painter.setFont(font)

        # Determine color: red if holiday or Friday, else white
        weekday = (today.weekday() + 2) % 7
        if weekday == 6 or today.day in HOLIDAYS:
            painter.setPen(QtGui.QColor("red"))
        else:
            painter.setPen(QtGui.QColor("white"))

        painter.drawText(pixmap.rect(), QtCore.Qt.AlignCenter, str(today.day))
        painter.end()

        self.tray.setIcon(QtGui.QIcon(pixmap))
        self.tray.setToolTip(self.get_tooltip())

    def on_tray_activated(self, reason):
        if reason == QtWidgets.QSystemTrayIcon.Trigger:  # Left click
            if self.popup.isVisible():
                self.popup.hide()
            else:
                # Show popup near the tray icon
                self.popup.move(QtGui.QCursor.pos())
                self.popup.show()
                self.popup.raise_()
                self.popup.activateWindow()

if __name__ == "__main__":
    app = TrayApp(sys.argv)
    sys.exit(app.exec())
