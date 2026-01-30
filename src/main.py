"""
Main Application Entry Point
-----------------------------

This module contains the primary entry point that initializes and runs the
ShamsiTray application. It sets up the application instance, handles asset
verification, loads necessary resources like fonts, and launches the system
tray icon controller.
"""
import ctypes
import sys

from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from config import APP_CONFIG
from utils.asset_loader import verify_assets, load_fonts
from utils.logger import setup_logging
from core.system_tray import SystemTrayIcon
from ui.windows.tutorial_window import TutorialWindow

logger = setup_logging(__name__)

def main():
    """Initialize and run the ShamsiTray application."""

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    logger.info(f"Starting {APP_CONFIG.APP_NAME} v{APP_CONFIG.APP_VERSION}")
    
    try:
        verify_assets()
    except FileNotFoundError as e:
        QMessageBox.critical(None, "Application File Error", str(e))
        sys.exit(1)
    
    if sys.platform == 'win32':
        try:
            myappid = f"{APP_CONFIG.COMPANY_NAME}.{APP_CONFIG.APP_NAME}.1"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
            logger.debug("Windows AppUserModelID set successfully")
        except Exception as e:
            logger.warning(f"Failed to set Windows AppUserModelID: {e}")
    
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
    logger.info("System tray icon initialized")
    
    settings = QSettings(APP_CONFIG.COMPANY_NAME, APP_CONFIG.APP_NAME)
    if not settings.value(APP_CONFIG.TUTORIAL_SHOWN_SETTING_KEY, False, type=bool):
        logger.info("First run detected: Showing tutorial window")
        
        tutorial = TutorialWindow()
        tray_icon.tutorial_window = tutorial
        tutorial.setPalette(app.palette())
        tutorial.update_styles()
        tutorial.show()
        screen = QApplication.primaryScreen()
        if screen:
            screen_center = screen.availableGeometry().center()
            tutorial.move(screen_center - tutorial.rect().center())
        settings.setValue(APP_CONFIG.TUTORIAL_SHOWN_SETTING_KEY, True)
        logger.debug("Tutorial window displayed and marked as shown")
    
    logger.info("Application initialization complete, entering main loop")
    sys.exit(app.exec())

if __name__ == "__main__":
    main()