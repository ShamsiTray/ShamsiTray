"""
Window Chrome
-------------

Shared "window furniture" for the frameless windows: a caption row with
close/minimize buttons and the Windows style tweak that restores native
minimize/sysmenu behaviour on frameless top-level windows. Every tool window
(date converter, tutorial, event manager, holiday viewer) reuses it from here.
"""
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton

from config import APP_CONFIG
from utils.logger import setup_logging
from utils.ui_helpers import window_title_button_stylesheets

logger = setup_logging(__name__)

try:
    import win32con
    import win32gui
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False


class WindowTitleBar(QHBoxLayout):
    """Caption row with FontAwesome close/minimize buttons and an optional title.

    Buttons are added on the left edge (mirrored to the right edge under the
    windows' RTL layout direction), matching the existing converter window.
    """

    def __init__(self, on_close, on_minimize=None, title: str = ""):
        super().__init__()
        self.exit_button = QPushButton(APP_CONFIG.FAS.FA_XMARK)
        self.minimize_button = QPushButton(APP_CONFIG.FAS.FA_MINUS)
        for button in (self.exit_button, self.minimize_button):
            button.setFont(QFont(APP_CONFIG.FONT_AWESOME_FAMILY, 10))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.addWidget(self.exit_button, alignment=Qt.AlignmentFlag.AlignTop)
        self.addWidget(self.minimize_button, alignment=Qt.AlignmentFlag.AlignTop)
        if title:
            title_label = QLabel(title)
            title_label.setObjectName("WindowTitleLabel")
            title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.addWidget(title_label, 1)
            self._title_label = title_label
        else:
            self.addStretch(1)
            self._title_label = None
        self.exit_button.clicked.connect(on_close)
        if on_minimize is not None:
            self.minimize_button.clicked.connect(on_minimize)
        else:
            self.minimize_button.hide()

    def update_styles(self):
        palette = APP_CONFIG.get_current_palette()
        close_style, minimize_style = window_title_button_stylesheets(palette)
        self.exit_button.setFixedSize(30, 30)
        self.minimize_button.setFixedSize(30, 30)
        self.exit_button.setStyleSheet(close_style)
        self.minimize_button.setStyleSheet(minimize_style)
        if self._title_label is not None:
            self._title_label.setStyleSheet(
                f"color: {palette['TEXT_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; "
                f"font-size: 16px; font-weight: bold; background: transparent; border: none;")


def apply_windows_styles(window) -> None:
    """Restore native minimize/sysmenu behaviour for a frameless top-level window.

    No-op off Windows or when pywin32 is unavailable (tests, other platforms).
    """
    if sys.platform != "win32" or not WIN32_AVAILABLE:
        return
    try:
        hwnd = window.winId().__int__()
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        style |= win32con.WS_MINIMIZEBOX | win32con.WS_SYSMENU
        win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
        win32gui.SetWindowPos(hwnd, None, 0, 0, 0, 0,
                              win32con.SWP_FRAMECHANGED | win32con.SWP_NOMOVE |
                              win32con.SWP_NOSIZE | win32con.SWP_NOZORDER)
    except Exception as e:
        logger.warning(f"Could not apply Windows window styles: {e}")
