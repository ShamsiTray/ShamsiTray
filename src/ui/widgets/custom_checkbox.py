"""
Custom Checkbox Widgets
-----------------------

This module provides custom checkbox widgets that use FontAwesome icons
instead of native controls, allowing for consistent styling across platforms
and themes.
"""
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QMouseEvent
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from config import APP_CONFIG
from .menu_widgets import HoverWidget


class CustomCheckbox(QWidget):
    """A custom checkbox widget using a FontAwesome icon and a label."""
    toggled = pyqtSignal(bool)

    def __init__(self, text: str, is_checked: bool = False, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._is_checked = is_checked
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4) 
        self.icon_label = QLabel()
        fa_font = QFont(APP_CONFIG.FONT_AWESOME_FAMILY, 14)
        self.icon_label.setFont(fa_font)
        self.icon_label.setFixedWidth(22)
        self.text_label = QLabel(text)
        layout.addWidget(self.text_label)
        layout.addWidget(self.icon_label)
        layout.addStretch()
        self.update_visuals()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            new_state = not self._is_checked
            self.setChecked(new_state)
            self.toggled.emit(new_state)
        super().mousePressEvent(event)

    def isChecked(self) -> bool:
        return self._is_checked

    def setChecked(self, checked: bool):
        if self._is_checked != checked:
            self._is_checked = checked
            self.update_visuals()

    def update_visuals(self):
        palette = APP_CONFIG.get_current_palette()
        icon = APP_CONFIG.FAS.FA_SQUARE_CHECK_SOLID if self._is_checked else APP_CONFIG.FAS.FA_SQUARE_REGULAR
        icon_color = palette['ACCENT_COLOR'] if self._is_checked else palette['TEXT_COLOR']
        
        self.icon_label.setText(icon)
        self.icon_label.setStyleSheet(f"color: {icon_color}; background: transparent;")
        self.text_label.setStyleSheet(f"color: {palette['TEXT_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 13px; font-weight: bold; background: transparent;")

class IconCheckboxActionWidget(HoverWidget):
    """A context menu checkbox using FontAwesome icons."""
    toggled = pyqtSignal(bool)

    def __init__(self, text: str, is_checked: bool, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._is_checked = is_checked
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(8)
        self.icon_label = QLabel()
        self.icon_label.setFont(QFont(APP_CONFIG.FONT_AWESOME_FAMILY, 14))
        self.icon_label.setFixedWidth(22)
        self.text_label = QLabel(text)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label)
        layout.addStretch()
        self.update_visuals()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            new_state = not self._is_checked
            self.setChecked(new_state)
            self.toggled.emit(new_state)
            self.update_visuals()
        super().mousePressEvent(event)


    def setChecked(self, checked: bool):
        if self._is_checked != checked:
            self._is_checked = checked
            self.update_visuals()

    def update_visuals(self):
        icon = APP_CONFIG.FAS.FA_SQUARE_CHECK_SOLID if self._is_checked else APP_CONFIG.FAS.FA_SQUARE_REGULAR
        self.icon_label.setText(icon)
        color = APP_CONFIG.current_palette['TEXT_COLOR']
        self.icon_label.setStyleSheet(f"color: {color}; background: transparent;")
        self.text_label.setStyleSheet(f"color: {color}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 14px; font-weight: bold; background: transparent;")
