"""
Main Application Initialization
-------------------------------

This module contains the primary `main` function that initializes and runs the
PyQt5 application. It sets up the application instance, handles asset verification,
loads necessary resources like fonts, and launches the system tray icon controller.
"""
import sys
import ctypes

from PyQt5.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon
from PyQt5.QtCore import Qt, QSettings

from config import APP_CONFIG
from utils.assets import verify_assets, load_fonts
from utils.logging_setup import setup_logging
from core.tray_controller import SystemTrayIcon
from ui.windows.tutorial_window import TutorialWindow

logger = setup_logging(__name__)

def main():
    """Initializes and runs the ShamsiTray application."""
    try:
        verify_assets()
    except FileNotFoundError as e:
        # We need a temporary QApplication to show the error message if assets are missing.
        temp_app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "Application File Error", str(e))
        sys.exit(1)

    # Set the AppUserModelID for Windows to ensure the icon is displayed correctly in the taskbar.
    if sys.platform == 'win32':
        myappid = f"{APP_CONFIG.COMPANY_NAME}.{APP_CONFIG.APP_NAME}.1"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    # Configure high-DPI scaling for better visuals on modern displays.
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    # The application should not exit when the last window is closed, as it lives in the system tray.
    app.setQuitOnLastWindowClosed(False)

    try:
        load_fonts()
    except (RuntimeError, FileNotFoundError) as e:
        QMessageBox.critical(None, "Font Error", str(e))
        sys.exit(1)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "Error", "No system tray was found on this system.")
        sys.exit(1)

    tray_icon = SystemTrayIcon()
    tray_icon.show()

    # Check if this is the first time the application is running to show the tutorial.
    settings = QSettings(APP_CONFIG.COMPANY_NAME, APP_CONFIG.APP_NAME)
    if not settings.value(APP_CONFIG.TUTORIAL_SHOWN_SETTING_KEY, False, type=bool):
        logger.info("First run: Showing tutorial.")
        tutorial = TutorialWindow()
        tray_icon.tutorial_window = tutorial
        tutorial.show()
        
        # Safely center the tutorial window on the primary screen.
        screen = QApplication.primaryScreen()
        if screen:
            screen_center = screen.availableGeometry().center()
            tutorial.move(screen_center - tutorial.rect().center())
        
        settings.setValue(APP_CONFIG.TUTORIAL_SHOWN_SETTING_KEY, True)

    sys.exit(app.exec_())
