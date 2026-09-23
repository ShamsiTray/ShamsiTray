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
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath
from PyQt6.QtWidgets import QWidget

from config import APP_CONFIG
from utils.ui_helpers import FramelessDragMixin

class BaseFramelessWindow(FramelessDragMixin, QWidget):
    """A base class for frameless windows with custom drag and paint logic.

    Subclasses set ``TASKBAR_ICON = True`` to opt into a real top-level window
    type: plain ``Qt.WindowType.Tool`` windows never get a taskbar entry, so a
    minimized tool window could previously never be brought back. The calendar
    popup and tutorial keep the Tool behaviour (a taskbar button for a quick
    popup would be noise); the converter and the other tool windows show in
    the taskbar like the converter always did.

    Dragging comes from ``FramelessDragMixin`` - including the Qt mouse-event
    routing: the top ``DRAGGABLE_AREA_HEIGHT`` pixels act as the grab strip, and
    the window keeps its historical vertical clamp (only the top 50 px must stay
    above the screen's bottom edge).
    """
    TASKBAR_ICON = False
    drag_strip_height = APP_CONFIG.DRAGGABLE_AREA_HEIGHT
    drag_bottom_keep_visible = 50

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
