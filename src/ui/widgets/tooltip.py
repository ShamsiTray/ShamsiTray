"""
Custom Tooltip Widget
--------------------

This module provides `CustomTooltip`, a custom-rendered tooltip that bypasses
Qt6's native tooltip rendering. This fixes the issue where native tooltips on
Windows ignore border-radius styling and appear as rectangles with sharp corners.
"""
from PyQt6.QtCore import Qt, QPoint, QTimer
from PyQt6.QtWidgets import QLabel, QWidget, QVBoxLayout, QApplication

from config import APP_CONFIG

class CustomTooltip(QWidget):
    """A custom tooltip widget that bypasses Qt6's native tooltip rendering."""

    _instance = None

    def __init__(self):
        super().__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel()
        self._label.setTextFormat(Qt.TextFormat.RichText)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self._label)

        # One reusable auto-hide timer for the copy confirmations. Restarting a
        # single shot gives every copy its own full window; separate
        # QTimer.singleShot calls cannot be cancelled, so an earlier one could
        # cut a later copy short or hide an unrelated tooltip (a holiday, say)
        # mid-display.
        self._auto_hide_timer = QTimer(self)
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(self.hide)

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = CustomTooltip()
        return cls._instance

    def flash_tooltip(self, text: str, global_pos: QPoint, duration_ms: int = 600):
        """Show a transient confirmation (e.g. «کپی شد») that hides itself.

        Restarting the single shot on every call is the point: two copies in a
        row never shorten each other's feedback window.
        """
        self.show_tooltip(text, global_pos)
        self._auto_hide_timer.start(duration_ms)

    def show_tooltip(self, text: str, global_pos: QPoint):
        # An explicit show must never be auto-hidden by a flash still counting
        # down - a holiday or event tooltip arriving right after a copy would
        # vanish mid-read.
        self._auto_hide_timer.stop()
        if not text:
            self.hide()
            return

        palette = APP_CONFIG.get_current_palette()
        self._label.setStyleSheet(f"QLabel {{background-color: {palette['BACKGROUND_COLOR']}; color: {palette['TEXT_COLOR']}; border: 1px solid {palette['CALENDAR_BORDER_COLOR']}; border-radius: 8px; padding: 6px 10px; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 13px; font-weight: bold;}}")

        self._label.setText(text)
        self.adjustSize()

        screen = QApplication.screenAt(global_pos)
        if screen:
            screen_geo = screen.availableGeometry()
            x = global_pos.x() + 4
            y = global_pos.y() + 12

            if x + self.width() > screen_geo.right():
                x = global_pos.x() - self.width() - 8
            if y + self.height() > screen_geo.bottom():
                y = global_pos.y() - self.height() - 8

            self.move(x, y)
        else:
            self.move(global_pos + QPoint(16, 16))

        self.show()
        self.raise_()
