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

from PyQt6.QtCore import QLockFile, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon

from config import APP_CONFIG
from utils.asset_loader import verify_assets, load_fonts
from utils.json_settings import JsonSettings
from utils.logger import install_qt_message_handler, setup_logging
from utils.settings_migration import migrate_from_registry
from core.app_controller import SystemTrayIcon
from ui.widgets.confirm_dialog import ConfirmDialog
from ui.windows.tutorial_window import TutorialWindow

logger = setup_logging(__name__)

def main():
    """Initialize and run the ShamsiTray application."""

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    # Route Qt's own diagnostics into the rotating log and drop the two
    # known-benign internals warnings (QSslSocket teardown, QSS font resolve)
    # that kept popping up as stderr noise after normal operations.
    install_qt_message_handler()

    logger.info(f"Starting {APP_CONFIG.APP_NAME} v{APP_CONFIG.APP_VERSION}")

    try:
        verify_assets()
    except FileNotFoundError as e:
        ConfirmDialog.notify(None, "خطای فایل‌های برنامه", str(e),
                             danger=True, glyph=APP_CONFIG.FAS.FA_CIRCLE_EXCLAMATION)
        sys.exit(1)

    if sys.platform == 'win32':
        try:
            # Stable AppUserModelID: Microsoft's AppUserModelID guidance says the
            # version segment is only for apps that must coexist as separate
            # taskbar entities, and should be omitted otherwise so an upgrade
            # keeps the same identity (pinning, jump lists). A version-qualified
            # ID here reset taskbar identity on every release.
            myappid = f"{APP_CONFIG.COMPANY_NAME}.{APP_CONFIG.APP_NAME}"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
            logger.debug("Windows AppUserModelID set successfully")
        except Exception as e:
            logger.warning(f"Failed to set Windows AppUserModelID: {e}")

    try:
        load_fonts()
    except (RuntimeError, FileNotFoundError) as e:
        ConfirmDialog.notify(None, "خطای فونت", str(e),
                             danger=True, glyph=APP_CONFIG.FAS.FA_CIRCLE_EXCLAMATION)
        sys.exit(1)

    # Give every widget a concrete default font. Without this, widgets that
    # never get an explicit font inherit one with pointSize -1, and Qt emits
    # "QFont::setPointSize: Point size <= 0 (-1)" while re-resolving fonts
    # under Windows fractional DPI scaling (e.g. 125%).
    app.setFont(QFont(APP_CONFIG.FONT_FAMILY, 10))

    if not QSystemTrayIcon.isSystemTrayAvailable():
        ConfirmDialog.notify(None, "خطا", "ناحیه اعلان (System Tray) در این سیستم پیدا نشد.",
                             danger=True, glyph=APP_CONFIG.FAS.FA_CIRCLE_EXCLAMATION)
        sys.exit(1)

    # Single-instance guard, acquired BEFORE any user-state work: without it, the
    # installer's auto-run plus a manual launch produce two tray icons racing on
    # the same settings and events files. The lock must also cover the one-time
    # registry->JSON migration, which is exactly the kind of stateful step two
    # near-simultaneous launches could both run before either acquired a later
    # lock. The lock lives in the user-data dir and auto-heals when a crashed
    # process leaves it behind (QLockFile tests staleness itself).
    APP_CONFIG.ensure_user_data_dirs()
    lock = QLockFile(str(APP_CONFIG.USER_DATA_DIR / "app.lock"))
    # The lock guards the app for its whole runtime, so it must never expire by
    # age: Qt documents that a resource protected indefinitely should always
    # call setStaleLockTime(0). Zero only turns the timestamp expiry off - a
    # lock whose owner is gone is still detected and healed through the pid
    # check, so a crashed instance does not block the next launch.
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        if lock.error() != QLockFile.LockError.LockFailedError:
            # A lock failure other than contention has a cause of its own: an
            # unwritable data dir (PermissionError) or a full disk
            # (UnknownError) fails the lock with no other instance around, and
            # reporting that as "already running" while exiting 0 would make
            # the launch look fine while nothing actually started.
            logger.error(f"Cannot acquire the single-instance lock ({lock.error().name}); exiting.")
            ConfirmDialog.notify(None, "خطای اجرا",
                                 "برنامه نتوانست قفل اجرا را ایجاد کند. دسترسی به پوشه داده‌ها را بررسی کنید.",
                                 glyph=APP_CONFIG.FAS.FA_CIRCLE_EXCLAMATION,
                                 danger=True)
            sys.exit(1)
        logger.warning("Another ShamsiTray instance is already running; exiting.")
        ConfirmDialog.notify(None, "اجرای برنامه",
                             "یک نسخه دیگر از برنامه در حال اجرا است.",
                             glyph=APP_CONFIG.FAS.FA_CIRCLE_INFO)
        sys.exit(0)

    settings = JsonSettings()
    migrate_from_registry(settings)

    tray_icon = SystemTrayIcon(settings=settings)
    tray_icon.show()
    logger.info("System tray icon initialized")

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
