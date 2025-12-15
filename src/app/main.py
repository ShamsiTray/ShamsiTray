"""
Main entry point for the ShamsiTray application.
"""

import ctypes
import sys

from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from config import APP_CONFIG
from utils import load_fonts, setup_logging, verify_assets
from ui.windows.tutorial_window import TutorialWindow
from core.tray_controller import SystemTrayController

logger = setup_logging(__name__)

def run_app():
    """Initializes and runs the ShamsiTray application."""
    try:
        verify_assets()
    except FileNotFoundError as e:
        QMessageBox.critical(None, "خطا در فایل‌های برنامه", str(e))
        sys.exit(1)

    # Set a unique AppUserModelID for Windows to handle taskbar icon correctly
    if sys.platform == 'win32':
        myappid = f"{APP_CONFIG.COMPANY_NAME}.{APP_CONFIG.APP_NAME}.1"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    try:
        load_fonts()
    except (RuntimeError, FileNotFoundError) as e:
        QMessageBox.critical(None, "خطای فونت", str(e))
        sys.exit(1)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "خطا", "هیچ System Tray در این سیستم یافت نشد.")
        sys.exit(1)

    tray_icon = SystemTrayController()
    tray_icon.show()

    settings = QSettings(APP_CONFIG.COMPANY_NAME, APP_CONFIG.APP_NAME)
    if not settings.value(APP_CONFIG.TUTORIAL_SHOWN_SETTING_KEY, False, type=bool):
        logger.info("First run: Showing tutorial.")
        tutorial = TutorialWindow()
        tutorial.setPalette(app.palette())
        tutorial.update_styles()
        tutorial.show()
        screen_center = QApplication.primaryScreen().availableGeometry().center()
        tutorial.move(screen_center - tutorial.rect().center())
        settings.setValue(APP_CONFIG.TUTORIAL_SHOWN_SETTING_KEY, True)

    sys.exit(app.exec_())
