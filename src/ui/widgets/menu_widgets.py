"""
Custom Menu Widgets
-------------------

This module contains a set of custom QWidgets designed to be used as actions
in a QMenu. This allows for more complex and better-styled menu items than
the default QAction, such as items with icons, hover effects, and custom text.
"""
import math
from typing import Optional

from PyQt6.QtCore import QRect, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPainterPath
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QMenu, QWidget

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

    def hideEvent(self, event):
        # A hidden menu never sends leaveEvent, so without this the hover
        # background survives the close and re-appears on the previously
        # hovered item the next time the menu opens.
        self._is_hovered = False
        super().hideEvent(event)

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

class TrayMenu(QMenu):
    """QMenu that paints its own divider lines on the device-pixel grid.

    Native QMenu::separator lines (and any 1px child widget) sit at fractional
    device positions: Qt passes child paint offsets as integer *logical*
    points which are then scaled by the (fractional) device pixel ratio, and
    each clip edge is rounded independently. With Qt's PassThrough DPI policy
    on Windows scale factors like 125% / 150%, that makes dividers at
    different heights get their one logical pixel of ink split across one or
    two physical rows in different ratios, so some look thinner than others.

    Painting every line from this menu's own paintEvent avoids the problem:
    a top-level window's device origin is always an integer number of physical
    pixels, so each line can be placed deterministically. Every divider is
    drawn exactly the way a native separator renders on a well-aligned
    position at the current scale factor: ``ceil(dpr)`` full-coverage device
    rows at 100% scale, two solid rows at 125% / 150%, and so on - and now
    every divider gets that same look, identically, at any scale.

    Divider spacing comes from native separator actions (kept invisible via
    the QMenu::separator stylesheet rule), painted by this menu.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._divider_actions = []

    def add_divider(self):
        """Add a divider row and remember it for device-snapped painting."""
        action = self.addSeparator()
        self._divider_actions.append(action)
        return action

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        color = QColor(APP_CONFIG.get_current_palette()['MENU_BORDER_COLOR'])

        for action in self._divider_actions:
            rect = self.actionGeometry(action)
            if rect.isValid() and rect.height() > 0:
                self._paint_hairline(painter, rect, True, color)

    def _paint_hairline(self, painter: QPainter, rect: QRect, horizontal: bool, color: QColor):
        """Draw one divider line the way a native 1px separator renders on a
        well-aligned position: ``ceil(dpr)`` full device rows (or columns),
        snapped to the device-pixel grid. Deterministic, so every divider in
        the menu renders with the same thickness at every position and scale
        (one crisp pixel at 100%, two solid rows at 125% / 150%, ...)."""
        dpr = self.devicePixelRatioF() or 1.0
        rows = max(1, math.ceil(dpr - 1e-6))

        if horizontal:
            x0 = round(rect.left() * dpr) / dpr
            x1 = round((rect.left() + rect.width()) * dpr) / dpr
            center_y = rect.top() + rect.height() / 2.0
            top = round(center_y * dpr - rows / 2.0)
            painter.fillRect(QRectF(x0, top / dpr, x1 - x0, rows / dpr), color)
        else:
            y0 = round(rect.top() * dpr) / dpr
            y1 = round((rect.top() + rect.height()) * dpr) / dpr
            center_x = rect.left() + rect.width() / 2.0
            left = round(center_x * dpr - rows / 2.0)
            painter.fillRect(QRectF(left / dpr, y0, rows / dpr, y1 - y0), color)
