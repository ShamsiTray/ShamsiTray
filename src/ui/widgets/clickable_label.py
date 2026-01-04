"""
Clickable Label Widget
----------------------

This module provides `ClickableLabel`, a QLabel subclass that emits signals
for left-clicks and context menu requests. It's used for the calendar day
cells to handle date selection and event management.
"""
from typing import Optional

import jdatetime
from PyQt6.QtCore import QTimer, pyqtSignal, Qt
from PyQt6.QtGui import QContextMenuEvent, QMouseEvent
from PyQt6.QtWidgets import QLabel, QMenu, QWidget, QWidgetAction

from config import APP_CONFIG
from .menu_widgets import MenuActionWidget


class ClickableLabel(QLabel):
    """A QLabel that emits signals for clicks and context menu actions."""
    clicked = pyqtSignal(object)
    add_event_requested = pyqtSignal(object)
    remove_event_requested = pyqtSignal(object)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.jalali_date: Optional[jdatetime.date] = None
        self.has_user_event = False

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.jalali_date)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent):
        if not self.jalali_date or not self.text():
            return

        menu = QMenu(self)
        palette = APP_CONFIG.get_current_palette()
        menu.setStyleSheet(
            f"QMenu {{ background-color: {palette['BACKGROUND_COLOR']}; border: 1px solid {palette['MENU_BORDER_COLOR']}; border-radius: 8px; padding: 5px; color: {palette['TEXT_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-weight: bold; }}"
            f"QMenu::item:disabled {{ color: {palette['GREY_COLOR']}; }}"
            f"QMenu::item:selected {{ background-color: {palette['HOVER_BG']}; }}"
            f"QMenu::separator {{ height: 1px; background-color: {palette['MENU_BORDER_COLOR']}; margin: 5px 0px; }}"
        )

        add_action_text = "ویرایش رویداد" if self.has_user_event else "افزودن رویداد"
        add_event_widget = MenuActionWidget(add_action_text, menu)
        add_action = QWidgetAction(menu)
        add_action.setDefaultWidget(add_event_widget)
        menu.addAction(add_action)

        menu.addSeparator()

        remove_event_widget = MenuActionWidget("حذف رویداد", menu)
        remove_action = QWidgetAction(menu)
        remove_action.setDefaultWidget(remove_event_widget)
        menu.addAction(remove_action)
        remove_action.setEnabled(self.has_user_event)
        remove_event_widget.setEnabled(self.has_user_event)

        add_event_widget.triggered.connect(lambda: self._trigger_add_event_and_close_menu(menu, self.jalali_date))
        remove_event_widget.triggered.connect(lambda: self._trigger_remove_event_and_close_menu(menu, self.jalali_date))

        menu.exec(self.mapToGlobal(event.pos()))

    def _trigger_add_event_and_close_menu(self, menu: QMenu, jdate: jdatetime.date):
        menu.close()
            # Delay emission slightly to ensure the context menu fully closes before opening any new dialogs or widgets.
        QTimer.singleShot(50, lambda: self.add_event_requested.emit(jdate))

    def _trigger_remove_event_and_close_menu(self, menu: QMenu, jdate: jdatetime.date):
        menu.close()
        QTimer.singleShot(50, lambda: self.remove_event_requested.emit(jdate))