"""
Base Frameless Window
---------------------

This module provides `BaseFramelessWindow`, a reusable base class for all
frameless windows in the application (e.g., Calendar, Tutorial, Converter).

It handles common functionality such as:
- A custom-painted rounded-rectangle background.
- Mouse events for dragging the frameless window.
- Translucent background and stay-on-top hints.
"""
from typing import Optional

from PyQt5.QtCore import QPoint, QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPainterPath
from PyQt5.QtWidgets import QApplication, QWidget

from config import APP_CONFIG


class BaseFramelessWindow(QWidget):
    """A base class for frameless windows with custom drag and paint logic."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._drag_position: Optional[QPoint] = None
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        radius = APP_CONFIG.CALENDAR_BORDER_RADIUS_PX
        path.addRoundedRect(QRectF(self.rect()), radius, radius)
        
        # Fill background and draw border within the rounded shape
        painter.fillPath(path, QColor(APP_CONFIG.current_palette['BACKGROUND_COLOR']))
        painter.setPen(QColor(APP_CONFIG.current_palette['CALENDAR_BORDER_COLOR']))
        painter.drawPath(path)
        
        # Clip subsequent painting operations to the rounded shape
        painter.setClipPath(path)
        super().paintEvent(event)

    def mousePressEvent(self, event):
        # Allow dragging only from the top part of the window.
        if event.button() == Qt.LeftButton and event.y() < APP_CONFIG.DRAGGABLE_AREA_HEIGHT:
            self._drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_position is not None:
            new_pos = event.globalPos() - self._drag_position
            screen_geometry = QApplication.screenAt(event.globalPos()).availableGeometry()
            
            # Clamp the new position to stay within the available screen area.
            min_x, max_x = screen_geometry.left(), screen_geometry.right() - self.width()
            clamped_x = max(min_x, min(new_pos.x(), max_x))

            min_y, max_y = screen_geometry.top(), screen_geometry.bottom() - 50 # Buffer for taskbar
            clamped_y = max(min_y, min(new_pos.y(), max_y))

            self.move(clamped_x, clamped_y)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_position = None
        event.accept()
