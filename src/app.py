"""
Main Application Initialization
-------------------------------

This module contains the primary `main` function that initializes and runs the
PyQt5 application. It sets up the application instance, handles asset verification,
loads necessary resources like fonts, and launches the system tray icon controller.
"""
import sys
import ctypes

from PyQt6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon
from PyQt6.QtCore import Qt, QSettings

from config import APP_CONFIG
from utils.assets import verify_assets, load_fonts
from utils.logging_setup import setup_logging
from core.tray_controller import SystemTrayIcon
from ui.windows.tutorial_window import TutorialWindow

logger = setup_logging(__name__)

def main():
    """Initializes and runs the ShamsiTray application."""
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    try:
        verify_assets()
    except FileNotFoundError as e:
        QMessageBox.critical(None, "Application File Error", str(e))
        sys.exit(1)


    if sys.platform == 'win32':
        try:
            myappid = f"{APP_CONFIG.COMPANY_NAME}.{APP_CONFIG.APP_NAME}.1"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception as e:
            logger.warning(f"Failed to set AppUserModelID: {e}")

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

    settings = QSettings(APP_CONFIG.COMPANY_NAME, APP_CONFIG.APP_NAME)
    if not settings.value(APP_CONFIG.TUTORIAL_SHOWN_SETTING_KEY, False, type=bool):
        logger.info("First run: Showing tutorial.")
        tutorial = TutorialWindow()
        tray_icon.tutorial_window = tutorial
        tutorial.show()
        
        screen = QApplication.primaryScreen()
        if screen:
            screen_center = screen.availableGeometry().center()
            tutorial.move(screen_center - tutorial.rect().center())
        
        settings.setValue(APP_CONFIG.TUTORIAL_SHOWN_SETTING_KEY, True)

    sys.exit(app.exec())
