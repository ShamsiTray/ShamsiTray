"""
Base Frameless Window
---------------------

This module provides `BaseFramelessWindow`, a reusable base class for all
frameless windows in the application (e.g., Calendar, Tutorial, Converter).

It handles common functionality such as:
- A custom-painted rounded-rectangle background.
- Mouse events for dragging the frameless window.
- Translucent background.
- A taskbar presence for tool windows (see ``TASKBAR_ICON``).
"""
from typing import Optional

from PyQt6.QtCore import QPoint, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath
from PyQt6.QtWidgets import QApplication, QWidget

from config import APP_CONFIG

class BaseFramelessWindow(QWidget):
    """A base class for frameless windows with custom drag and paint logic.

    Subclasses set ``TASKBAR_ICON = True`` to opt into a real top-level window
    type: plain ``Qt.WindowType.Tool`` windows never get a taskbar entry, so a
    minimized tool window could previously never be brought back. The calendar
    popup and tutorial keep the Tool behaviour (a taskbar button for a quick
    popup would be noise); the converter and the other tool windows show in
    the taskbar like the converter always did.
    """
    TASKBAR_ICON = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._drag_position: Optional[QPoint] = None
        if self.TASKBAR_ICON:
            self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
            if APP_CONFIG.ICON_PATH.exists():
                self.setWindowIcon(QIcon(str(APP_CONFIG.ICON_PATH)))
        else:
            self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, event):
        if self.rect().isEmpty():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = APP_CONFIG.CALENDAR_BORDER_RADIUS_PX
        path.addRoundedRect(rect, radius, radius)
        painter.fillPath(path, QColor(APP_CONFIG.current_palette['BACKGROUND_COLOR']))
        painter.setPen(QColor(APP_CONFIG.current_palette['CALENDAR_BORDER_COLOR']))
        painter.drawPath(path)
        painter.setClipPath(path)
        super().paintEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < APP_CONFIG.DRAGGABLE_AREA_HEIGHT:
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_position is not None:
            new_pos = event.globalPosition().toPoint() - self._drag_position
            screen = QApplication.screenAt(event.globalPosition().toPoint())
            if screen is None:
                return
            screen_geometry = screen.availableGeometry()
            min_x, max_x = screen_geometry.left(), screen_geometry.right() - self.width()
            clamped_x = max(min_x, min(new_pos.x(), max_x))
            min_y, max_y = screen_geometry.top(), screen_geometry.bottom() - 50 # Prevents dragging windows fully off-screen at the bottom
            clamped_y = max(min_y, min(new_pos.y(), max_y))
            self.move(clamped_x, clamped_y)
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag_position is not None:
            self._drag_position = None
            event.accept()
            return
        super().mouseReleaseEvent(event)