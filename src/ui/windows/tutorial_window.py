"""
Tutorial Window
---------------

This module defines the `TutorialWindow`, which is displayed on the first
launch of the application. It provides a brief, user-friendly guide on
how to pin the application to the taskbar for easy access.
"""
import os
import sys
from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QMovie, QColor
from PyQt5.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from config import APP_CONFIG
from utils.logging_setup import setup_logging
from .base_window import BaseFramelessWindow

logger = setup_logging(__name__)

try:
    import win32con
    import win32gui
    WIN32_AVAILABLE = True
except ImportError:
    logger.warning("win32api not available. Window style modifications will be skipped.")
    WIN32_AVAILABLE = False


class TutorialWindow(BaseFramelessWindow):
    """A window to display a first-time tutorial for the app."""
    tutorial_closed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Welcome Guide")
        self.setFixedSize(500, 400)
        self._setup_ui()
        self.update_styles()
        self._apply_windows_styles()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        self.message_label = QLabel(
            "برای دسترسی آسان، می‌توانید آیکون برنامه را از بخش آیکون‌های پنهان ویندوز، به نوار وظیفه اصلی بکشید."
        )
        self.message_label.setWordWrap(True)
        self.message_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.message_label)
        
        self.gif_label = QLabel()
        self.gif_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.gif_label, alignment=Qt.AlignCenter)
        self._load_gif()
        
        main_layout.addStretch(1)
        self.close_button = QPushButton("بستن آموزش")
        self.close_button.clicked.connect(self._close_tutorial)
        main_layout.addWidget(self.close_button)

    def _load_gif(self):
        """
        Loads and starts the tutorial GIF.
        Falls back to text if the file is missing or invalid.
        """
        gif_path = str(APP_CONFIG.TUTORIAL_GIF_PATH)
        if not os.path.exists(gif_path):
            logger.error(f"Tutorial GIF not found: {gif_path}")
            self.gif_label.setText("GIF file not found.")
            return
            
        self.movie = QMovie(gif_path)
        if self.movie.isValid():
            self.gif_label.setMovie(self.movie)
            self.movie.setCacheMode(QMovie.CacheAll)
            self.movie.setSpeed(100)
            self.movie.start()
        else:
            logger.warning(f"Failed to load GIF from {gif_path}.")

    def update_styles(self):
        palette = APP_CONFIG.get_current_palette()
        self.message_label.setFont(QFont(APP_CONFIG.FONT_FAMILY, 12))
        self.message_label.setStyleSheet(f"color: {palette['TEXT_COLOR']};")
        self.close_button.setFixedHeight(50)
        self.close_button.setStyleSheet(
            f"QPushButton {{ background-color: {palette['ACCENT_COLOR']}; color: white; border: none; border-radius: 8px; font-size: 16px; font-weight: bold; font-family: '{APP_CONFIG.FONT_FAMILY}'; }}"
            f"QPushButton:hover {{ background-color: {QColor(palette['ACCENT_COLOR']).darker(120).name()}; }}"
        )

    def _close_tutorial(self):
        if hasattr(self, "movie") and self.movie:
            self.movie.stop()
            self.movie.deleteLater()
            self.movie = None
        self.tutorial_closed.emit()
        self.close()

    def _apply_windows_styles(self):
        if sys.platform == "win32" and WIN32_AVAILABLE:
            try:
                hwnd = self.winId().__int__()
                style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
                style |= win32con.WS_MINIMIZEBOX | win32con.WS_SYSMENU
                win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
            except Exception as e:
                logger.warning(f"Could not set Windows styles for tutorial: {e}")
