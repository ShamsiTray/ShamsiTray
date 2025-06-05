import sys
import jdatetime
from PyQt5 import QtWidgets, QtGui, QtCore


class CalendarPopup(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.Popup)
        self.setStyleSheet("background-color: #121212; color: white;")
        self.setLayoutDirection(QtCore.Qt.RightToLeft)
        self.setWindowTitle("تقویم")
        self.resize(300, 200)

        layout = QtWidgets.QVBoxLayout(self)
        label = QtWidgets.QLabel("نمایش تقویم (نمونه)")
        label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(label)

        self.drag_position = None

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & QtCore.Qt.LeftButton and self.drag_position:
            self.move(event.globalPos() - self.drag_position)
            event.accept()


class PersianTrayApp(QtWidgets.QSystemTrayIcon):
    def __init__(self, app):
        self.app = app
        today = jdatetime.date.today()
        day_str = str(today.day)

        icon = self.generate_day_icon(day_str)
        super().__init__(icon, app)

        self.setToolTip(f"امروز: {today}")

        self.popup = CalendarPopup()
        self.activated.connect(self.icon_clicked)

        menu = QtWidgets.QMenu()
        quit_action = menu.addAction("خروج")
        quit_action.triggered.connect(app.quit)
        self.setContextMenu(menu)

        self.show()

    def icon_clicked(self, reason):
        if reason == QtWidgets.QSystemTrayIcon.Trigger:
            self.show_popup_near_tray()

    def show_popup_near_tray(self):
        screen_geometry = QtWidgets.QApplication.primaryScreen().availableGeometry()
        cursor_pos = QtGui.QCursor.pos()

        self.popup.adjustSize()
        popup_size = self.popup.size()

        x = min(cursor_pos.x(), screen_geometry.width() - popup_size.width())
        y = min(cursor_pos.y(), screen_geometry.height() - popup_size.height())

        self.popup.move(x, y)
        self.popup.show()

    def generate_day_icon(self, text):
        pixmap = QtGui.QPixmap(64, 64)
        pixmap.fill(QtCore.Qt.transparent)

        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtCore.Qt.red)
        painter.setFont(QtGui.QFont("Tahoma", 30, QtGui.QFont.Bold))
        painter.drawText(pixmap.rect(), QtCore.Qt.AlignCenter, text)
        painter.end()

        return QtGui.QIcon(pixmap)


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    tray = PersianTrayApp(app)

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
