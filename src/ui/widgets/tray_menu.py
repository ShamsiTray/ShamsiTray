"""
Tray Menu Builder
-----------------

The tray context menu's composition: one builder assembles the menu the
controller shows (row order, separators, the checkbox rows and the
«close, then open» deferral so a tray click can still open nested dialogs).
It sits beside the row widgets in menu_widgets.py, while the state those
rows drive keeps its controller-side owner (the ``_toggle_*`` callbacks).

The builder reaches the controller's own methods - including the private
toggles - by design: it is the composition layer for exactly those
callbacks, the same localized reach the event manager takes on controller
state through ``event_service``.
"""
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QWidgetAction

from config import APP_CONFIG
from ui.widgets.checkbox import IconCheckboxActionWidget
from ui.widgets.menu_widgets import MenuActionWidget, ThemeToggleActionWidget, TrayMenu


def close_menu_then(tray, callback):
    """Close the popup menu, then run callback once it has fully dismissed.
    Windows refuses to show modal dialogs (e.g. native file dialogs) while a
    popup menu is still tracking, so dialogs must be opened after the close."""
    menu = tray.contextMenu()
    if menu:
        menu.close()
    QTimer.singleShot(50, callback)


def add_menu_action(tray, menu, text, slot):
    action = QWidgetAction(tray)
    widget = MenuActionWidget(text, parent=menu)
    widget.triggered.connect(slot)
    action.setDefaultWidget(widget)
    menu.addAction(action)


def add_theme_toggle_action(tray, menu):
    """The theme row: one click advances system → light → dark → system,
    and the row reads back the current preference, so «هماهنگ با سیستم» is
    reachable again after any pin."""
    action = QWidgetAction(tray)
    widget = ThemeToggleActionWidget(lambda: tray._theme_choice(), parent=menu)
    widget.triggered.connect(tray._cycle_theme_choice)
    action.setDefaultWidget(widget)
    menu.addAction(action)


def add_startup_action(tray, menu):
    if not sys.platform.startswith('win'):
        return
    action = QWidgetAction(tray)
    widget = IconCheckboxActionWidget("راه اندازی همراه با سیستم", tray.is_open_at_login, parent=menu)
    widget.toggled.connect(tray._toggle_open_at_boot)
    action.setDefaultWidget(widget)
    menu.addAction(action)


def add_always_on_top_action(tray, menu):
    action = QWidgetAction(tray)
    widget = IconCheckboxActionWidget("تقویم همیشه در بالا", tray.always_on_top, parent=menu)
    widget.toggled.connect(tray._toggle_always_on_top)
    action.setDefaultWidget(widget)
    menu.addAction(action)


def add_auto_check_action(tray, menu):
    """The tray toggle for the automatic update check.

    The row sits right above the manual «بررسی بروزرسانی» action it
    complements. Like the other checkbox rows, the widget keeps the menu
    open on click and paints its own new state.
    """
    action = QWidgetAction(tray)
    widget = IconCheckboxActionWidget("بررسی خودکار بروزرسانی", tray._auto_check_enabled(), parent=menu)
    widget.toggled.connect(tray._toggle_auto_update_check)
    action.setDefaultWidget(widget)
    menu.addAction(action)


def build_tray_menu(tray):
    """Compose the tray context menu; row order and separators live here."""
    menu = TrayMenu()
    palette = APP_CONFIG.get_current_palette()
    # Separator rows only provide spacing; TrayMenu paints the actual divider
    # lines with the same thickness everywhere: ceil(scale) full device rows,
    # matching how a native separator renders on a well-aligned position.
    menu.setStyleSheet(
        f"QMenu {{ background-color: {palette['BACKGROUND_COLOR']}; border: 1px solid {palette['MENU_BORDER_COLOR']}; border-radius: 8px; padding: 5px; }}"
        f"QMenu::separator {{ height: 11px; background-color: transparent; }}"
    )
    add_menu_action(tray, menu, "تبدیل تاریخ",
                    lambda: close_menu_then(tray, tray._open_date_converter))
    menu.add_divider()
    add_theme_toggle_action(tray, menu)
    menu.add_divider()
    add_startup_action(tray, menu)
    menu.add_divider()
    add_always_on_top_action(tray, menu)
    menu.add_divider()
    add_menu_action(tray, menu, "مدیریت رویدادها",
                    lambda: close_menu_then(tray, tray._open_event_manager))
    menu.add_divider()
    add_menu_action(tray, menu, "مشاهده تعطیلات",
                    lambda: close_menu_then(tray, tray._open_holiday_viewer))
    menu.add_divider()
    add_auto_check_action(tray, menu)
    menu.add_divider()
    add_menu_action(tray, menu, "بررسی بروزرسانی",
                    lambda: close_menu_then(tray, lambda: tray._check_for_updates(manual=True)))
    menu.add_divider()
    add_menu_action(tray, menu, "خروج", QApplication.quit)
    return menu
