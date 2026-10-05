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
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QMouseEvent, QPainter, QPainterPath
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QMenu, QWidget

from config import APP_CONFIG
from utils.ui_helpers import nudge_popup_inside_work_area

# The day-cell menu's item box, shared by the QSS rules in
# calendar_day_cell._menu_stylesheet and by CenteredTextMenu's painter so the
# native rows and the painted text cannot drift apart: the same 15px/6px inner
# box MenuActionWidget uses as its layout margins (hence the same 34px row
# height), and the same 12px arrow box CenteredTextMenu paints its submenu
# indicator into. These values ARE the menu's existing conventions.
MENU_ITEM_PADDING_H = 15
MENU_ITEM_PADDING_V = 6
SUBMENU_ARROW_SIZE = 12


def paint_device_snapped_hairline(painter: QPainter, rect: QRect, color: QColor,
                                  dpr: float, horizontal: bool = True) -> None:
    """Draw one divider line the way a native 1px separator renders on a
    well-aligned position: ``ceil(dpr)`` full device rows (or columns), snapped
    to the device-pixel grid.

    Qt hands child paint offsets over as integer *logical* points, which are then
    scaled by the (possibly fractional) device pixel ratio with each clip edge
    rounded independently. At Windows scale factors like 125% / 150% that lands a
    1px line on a fractional device row, so its ink is split across one or two
    physical rows in a ratio that depends on its position - which is why some
    dividers looked thinner than others.

    Painting from the menu's own paintEvent avoids that: a top-level window's
    device origin is always an integer number of physical pixels, so every line
    can be placed deterministically and they all come out identical (one crisp
    row at 100%, two solid rows at 125% / 150%, ...).

    Shared by ``TrayMenu`` and ``CenteredTextMenu`` so the tray menu and the
    calendar's day menu (and its submenu) render their dividers the same way.
    """
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


class HoverWidget(QWidget):
    """Base widget for menu items that handles hover effects."""
    triggered = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._is_hovered = False
        self.setMouseTracking(True)
        self.setStyleSheet("background-color: transparent; border-radius: 6px;")

    def paintEvent(self, event):
        # Disabled items show no hover feedback, like native menus.
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
    """Widget for the theme row in the context menu.

    One row, three states: the click cycles the preference
    system → light → dark → system (the controller owns the cycle; this
    widget only reads the current preference back and labels it, so
    «هماهنگ با سیستم» is visible and reachable again after any pin).
    """
    _DISPLAY = (
        ("system", "FA_DESKTOP", "تم برنامه: هماهنگ با سیستم"),
        ("light", "FA_SUN_SOLID", "تم برنامه: روشن"),
        ("dark", "FA_MOON_SOLID", "تم برنامه: تاریک"),
    )

    def __init__(self, theme_choice_getter, parent: Optional[QWidget] = None):
        super().__init__("", parent)
        self.theme_choice_getter = theme_choice_getter
        layout = self.layout()
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
        choice = self.theme_choice_getter()
        for value, glyph_name, text in self._DISPLAY:
            if choice == value:
                icon = getattr(APP_CONFIG.FAS, glyph_name)
                break
        else:
            # An unknown preference reads as "system", but the row still
            # labels whatever it cannot resolve defensively.
            icon, text = APP_CONFIG.FAS.FA_DESKTOP, self._DISPLAY[0][2]
        self.icon_label.setText(icon)
        self.label.setText(text)
        color = APP_CONFIG.current_palette['TEXT_COLOR']
        self.icon_label.setStyleSheet(f"color: {color}; background: transparent;")
        self._update_style()

class TrayMenu(QMenu):
    """QMenu that paints its own divider lines on the device-pixel grid.

    Native QMenu::separator lines sit at fractional device positions, so at
    Windows scale factors like 125% / 150% a divider's one logical pixel of ink
    is split across one or two physical rows in a ratio that depends on where it
    sits - which is why some dividers used to look thinner than others. Painting
    every line from this menu's own paintEvent avoids that; see
    ``paint_device_snapped_hairline`` for the mechanism, which CenteredTextMenu
    shares so the calendar's day menu renders its dividers identically.

    Divider spacing comes from native separator actions (kept invisible via the
    QMenu::separator stylesheet rule), painted by this menu.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._divider_actions = []

    def add_divider(self):
        """Add a divider row and remember it for device-snapped painting."""
        action = self.addSeparator()
        self._divider_actions.append(action)
        return action

    def showEvent(self, event):
        super().showEvent(event)
        # The tray icon lives on the screen edge, so Qt places this menu flush
        # against it; nudge it back inside now that it has a real geometry.
        nudge_popup_inside_work_area(self)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        color = QColor(APP_CONFIG.get_current_palette()['MENU_BORDER_COLOR'])

        for action in self._divider_actions:
            rect = self.actionGeometry(action)
            if rect.isValid() and rect.height() > 0:
                self._paint_hairline(painter, rect, True, color)

    def _paint_hairline(self, painter: QPainter, rect: QRect, horizontal: bool, color: QColor):
        """Draw one divider line on the device-pixel grid (see the module helper)."""
        paint_device_snapped_hairline(painter, rect, color,
                                      self.devicePixelRatioF() or 1.0, horizontal)


class CenteredTextMenu(QMenu):
    """QMenu whose NATIVE rows draw their text horizontally centered.

    Why a painter rather than QSS or a QProxyStyle: Qt's stylesheet engine has no
    ``text-align`` for ``QMenu::item``, and once any ``QMenu::item`` rule matches,
    ``QStyleSheetStyle`` paints ``CE_MenuItem`` (background, hover, arrow AND
    glyphs) entirely itself - a ``QProxyStyle.drawControl(CE_MenuItem)`` override
    never fires for a styled menu. Reimplementing the whole item painting in a
    style was rejected as disproportionate.

    So the work is split: the shared stylesheet still paints the frame, item box
    and hover, but its item text is ``color: transparent``, and this class paints
    the glyphs afterwards, centered in the item's content rect (the same 15px/6px
    box the QSS padding defines). Separator lines are painted here too, on the
    device-pixel grid via ``paint_device_snapped_hairline``, so the day menu's
    dividers match the tray menu's instead of being drawn by QSS.

    Rows that open a submenu also get their indicator from this painter. Handing
    the arrow back to the style primitives via bare ``QMenu::right-arrow`` /
    ``::left-arrow`` rules proved undrawable in the wild (some platform styles
    render no visible primitive for them, and any primitive they do draw picks
    its own color, not the palette's), so the arrow is painted here: a small
    triangle centered in the row's TRAILING padding gutter, in the text colors.
    Because it lives entirely inside that 15px gutter, the caption can center in
    the FULL content rect like every other row.

    Behavior is untouched by construction: no mouse handling, no hover state, no
    custom rows - hover-to-open, hover background, keyboard navigation, RTL
    mirroring and submenu opening/closing are all still Qt's own.
    """

    def paintEvent(self, event):
        super().paintEvent(event)  # QSS paints frame, boxes, hover, separators
        painter = QPainter(self)
        painter.setFont(self.font())  # the QSS-applied menu font
        palette = APP_CONFIG.get_current_palette()
        rtl = self.layoutDirection() == Qt.LayoutDirection.RightToLeft
        align = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        metrics = QFontMetrics(painter.font())
        for action in self.actions():
            if action.isSeparator():
                # Painted here rather than by QSS so the line lands on the
                # device-pixel grid: the stylesheet keeps the separator row's
                # height for spacing but draws nothing, exactly like TrayMenu.
                paint_device_snapped_hairline(
                    painter, self.actionGeometry(action),
                    QColor(palette["MENU_BORDER_COLOR"]),
                    self.devicePixelRatioF() or 1.0)
                continue
            text = action.text()
            if not text:
                # A QWidgetAction row paints itself. Its geometry is deliberately
                # NOT queried: actionGeometry() consults the row's widget, and a
                # row whose widget is already gone must never be touched (a
                # repaint of a leaked menu would otherwise dereference freed
                # memory). Only separators and text rows are measured here.
                continue
            color = QColor(palette["TEXT_COLOR"] if action.isEnabled()
                           else palette["GREY_COLOR"])
            geo = self.actionGeometry(action)
            zone = geo.adjusted(
                MENU_ITEM_PADDING_H, MENU_ITEM_PADDING_V,
                -MENU_ITEM_PADDING_H, -MENU_ITEM_PADDING_V)
            if action.menu() is not None:
                self._paint_submenu_arrow(painter, geo, rtl, color)
                zone.adjust(4, 0, 4, 0)
                if metrics.horizontalAdvance(text) > zone.width():
                    # Overflow safety net for unnaturally narrow menus: the
                    # caption cannot fit beside the arrow, so fall back to the
                    # arrow-aware zone and clip to it - glyphs can never reach
                    # the gutter, but stay as visible as the space allows.
                    if rtl:
                        zone.setLeft(zone.left() + SUBMENU_ARROW_SIZE)
                    else:
                        zone.setRight(zone.right() - SUBMENU_ARROW_SIZE)
                    painter.save()
                    painter.setClipRect(zone)
                    painter.setPen(color)
                    painter.drawText(zone, align, text)
                    painter.restore()
                    continue
            painter.setPen(color)
            painter.drawText(zone, align, text)

    def _paint_submenu_arrow(self, painter: QPainter, row: QRect, rtl: bool,
                             color: QColor):
        """The submenu indicator: a small triangle centered in the row's trailing
        padding gutter (left edge under RTL, right edge under LTR), vertically
        centered in the row and painted in the row's own text color."""
        half = SUBMENU_ARROW_SIZE / 3.0  # an 8x8 triangle in the 12px arrow box
        row_f = QRectF(row)
        center_y = row_f.center().y()
        gutter_center_x = (row_f.left() + MENU_ITEM_PADDING_H / 2.0 if rtl
                           else row_f.right() - MENU_ITEM_PADDING_H / 2.0)
        path = QPainterPath()
        if rtl:  # points left, toward the trailing edge the popup opens from
            path.moveTo(gutter_center_x - half, center_y)
            path.lineTo(gutter_center_x + half, center_y - half)
            path.lineTo(gutter_center_x + half, center_y + half)
        else:
            path.moveTo(gutter_center_x + half, center_y)
            path.lineTo(gutter_center_x - half, center_y - half)
            path.lineTo(gutter_center_x - half, center_y + half)
        path.closeSubpath()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPath(path)
        painter.restore()
