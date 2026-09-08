"""
Custom Menu Widgets
-------------------

This module contains a set of custom QWidgets designed to be used as actions
in a QMenu. This allows for more complex and better-styled menu items than
the default QAction, such as items with icons, hover effects, and custom text.
"""
from typing import Optional

from PyQt6.QtCore import Qt, QRectF, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPainterPath
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from config import APP_CONFIG

class HoverWidget(QWidget):
    """Base widget for menu items that handles hover effects."""
    triggered = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._is_hovered = False
        self.setMouseTracking(True)
        self.setStyleSheet("background-color: transparent; border-radius: 6px;")

    def paintEvent(self, event):
        # Draw a rounded hover background only when the widget is enabled.
        # Disabled items must not show hover feedback to match native menu behavior.
        if self._is_hovered and self.isEnabled():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()), 6, 6)
            painter.fillPath(path, QColor(*APP_CONFIG.current_palette["MENU_HOVER_COLOR"]))
        super().paintEvent(event)
        
    def enterEvent(self, event):
        self._is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.triggered.emit()
            event.accept()
            return
        super().mousePressEvent(event)

class MenuActionWidget(HoverWidget):
    """Custom widget for a simple text-based menu action."""
    def __init__(self, text: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 6, 15, 6)
        self.label = QLabel(text)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()
        layout.addWidget(self.label)
        layout.addStretch()
        self._update_style()

    def setEnabled(self, enabled: bool):
        # Re-apply styles on enable/disable because this widget uses custom rendering instead of native QAction styling.
        super().setEnabled(enabled)
        self._update_style()

    def _update_style(self):
        palette = APP_CONFIG.get_current_palette()
        text_color = palette['TEXT_COLOR'] if self.isEnabled() else palette['GREY_COLOR']
        self.label.setStyleSheet(f"color: {text_color}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 14px; font-weight: bold; background: transparent; border: none;")

class ThemeToggleActionWidget(MenuActionWidget):
    """Widget for the 'App Theme' toggle in the context menu."""
    def __init__(self, current_theme_getter, parent: Optional[QWidget] = None):
        super().__init__("", parent)
        self.current_theme_getter = current_theme_getter
        layout = self.layout()
        # Replace MenuActionWidget's default layout content with icon + label because this action requires dynamic text and an icon.
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.icon_label = QLabel()
        self.icon_label.setFont(QFont(APP_CONFIG.FONT_AWESOME_FAMILY, 14))
        self.icon_label.setFixedWidth(22)
        self.label = QLabel("") 
        layout.addStretch()
        layout.addWidget(self.icon_label)
        layout.addSpacing(-7)
        layout.addWidget(self.label)
        layout.addStretch()
        self.update_display()

    def update_display(self):
        theme = self.current_theme_getter()
        icon = APP_CONFIG.FAS.FA_MOON_SOLID if theme == APP_CONFIG.Theme.DARK else APP_CONFIG.FAS.FA_SUN_SOLID
        text = "تم برنامه: تاریک" if theme == APP_CONFIG.Theme.DARK else "تم برنامه: روشن"
        self.icon_label.setText(icon)
        self.label.setText(text)
        color = APP_CONFIG.current_palette['TEXT_COLOR']
        self.icon_label.setStyleSheet(f"color: {color}; background: transparent;")
        self._update_style()

class EventsActionWidget(QWidget):
    """'رویدادها' section for the tray menu with import/export child buttons."""
    import_triggered = pyqtSignal()
    export_triggered = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumWidth(210)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(0)

        self.header_label = QLabel("رویدادها")
        self.header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.header_label.setFixedHeight(28)
        layout.addWidget(self.header_label)

        self.h_divider = QFrame()
        self.h_divider.setFrameShape(QFrame.Shape.HLine)
        self.h_divider.setFixedHeight(1)
        layout.addWidget(self.h_divider)

        buttons_row = QHBoxLayout()
        buttons_row.setContentsMargins(0, 0, 0, 0)
        buttons_row.setSpacing(0)
        self.import_button = MenuActionWidget("وارد کردن")
        self.import_button.setFixedHeight(34)
        self.export_button = MenuActionWidget("خروجی گرفتن")
        self.export_button.setFixedHeight(34)
        self.v_divider = QFrame()
        self.v_divider.setFrameShape(QFrame.Shape.VLine)
        self.v_divider.setFixedWidth(1)
        buttons_row.addWidget(self.import_button)
        buttons_row.addWidget(self.v_divider)
        buttons_row.addWidget(self.export_button)
        layout.addLayout(buttons_row)

        self.import_button.triggered.connect(self.import_triggered)
        self.export_button.triggered.connect(self.export_triggered)
        self.update_styles()

    def update_styles(self):
        palette = APP_CONFIG.get_current_palette()
        self.header_label.setStyleSheet(
            f"color: {palette['GREY_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 14px; font-weight: bold; background: transparent; border: none;")
        divider_style = f"color: {palette['MENU_BORDER_COLOR']}; background-color: {palette['MENU_BORDER_COLOR']}; border: none;"
        self.h_divider.setStyleSheet(divider_style)
        self.v_divider.setStyleSheet(divider_style)