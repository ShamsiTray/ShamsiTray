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
from PyQt6.QtGui import QContextMenuEvent, QMouseEvent, QCursor
from PyQt6.QtWidgets import QLabel, QMenu, QWidget, QWidgetAction

from config import APP_CONFIG
from .menu_widgets import MenuActionWidget
from .custom_tooltip import CustomTooltip


class ClickableLabel(QLabel):
    """A QLabel that emits signals for clicks and context menu actions."""
    clicked = pyqtSignal(object)
    add_event_requested = pyqtSignal(object)
    remove_event_requested = pyqtSignal(object)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.jalali_date: Optional[jdatetime.date] = None
        self.has_user_event = False
        self._tooltip_text = ""
        self._tooltip_timer = QTimer(self)
        self._tooltip_timer.setSingleShot(True)
        self._tooltip_timer.timeout.connect(self._show_custom_tooltip)
        self._context_menu_open = False

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.jalali_date)
        super().mousePressEvent(event)

    def setToolTip(self, text: str):
        self._tooltip_text = text
        
    def enterEvent(self, event):
        super().enterEvent(event)
        if self._tooltip_text and not self._context_menu_open:
            self._tooltip_timer.start(500)
            
    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._tooltip_timer.stop()
        CustomTooltip.instance().hide()
        
    def _show_custom_tooltip(self):
        if self._tooltip_text and self.underMouse() and not self._context_menu_open:
            palette = APP_CONFIG.get_current_palette()
            global_pos = QCursor.pos()
            CustomTooltip.instance().show_tooltip(self._tooltip_text, global_pos, palette)

    def contextMenuEvent(self, event: QContextMenuEvent):
        if not self.jalali_date or not self.text():
            return
        
        self._context_menu_open = True
        CustomTooltip.instance().hide()

        menu = QMenu(self)
        palette = APP_CONFIG.get_current_palette()
        p = palette
        menu.setStyleSheet(
            f"QMenu {{ background-color: {p['BACKGROUND_COLOR']}; border: 1px solid {p['MENU_BORDER_COLOR']}; border-radius: 8px; padding: 5px; color: {p['TEXT_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-weight: bold; }}"
            f"QMenu::item:disabled {{ color: {p['GREY_COLOR']}; }}"
            f"QMenu::item:selected {{ background-color: {p['HOVER_BG']}; }}"
            f"QMenu::separator {{ height: 1px; background-color: {p['MENU_BORDER_COLOR']}; margin: 5px 0px; }}"
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

        self._context_menu_open = False
        self.setAttribute(Qt.WidgetAttribute.WA_UnderMouse, False)
        self.update()
        
    def _trigger_add_event_and_close_menu(self, menu: QMenu, jdate: jdatetime.date):
        menu.close()
            # Delay emission slightly to ensure the context menu fully closes before opening any new dialogs or widgets.
        QTimer.singleShot(50, lambda: self.add_event_requested.emit(jdate))

    def _trigger_remove_event_and_close_menu(self, menu: QMenu, jdate: jdatetime.date):
        menu.close()
        QTimer.singleShot(50, lambda: self.remove_event_requested.emit(jdate))