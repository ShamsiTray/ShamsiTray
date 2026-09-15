"""
UI Helper Functions
-------------------

This module contains utility functions related to creating or manipulating
UI elements, such as dynamically drawing pixmaps or building shared stylesheets.
"""
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPixmap
from PyQt6.QtWidgets import (QApplication, QComboBox, QStyle, QStyleOptionComboBox,
                             QStylePainter)

from config import APP_CONFIG

def create_tray_pixmap(day_str: str, color_hex: str) -> QPixmap:
    """
    Creates a square QPixmap with the given day number drawn in the center.

    This function handles DPI scaling to ensure the icon looks crisp on
    high-resolution displays.
    """
    screen = QApplication.primaryScreen()
    dpi = screen.logicalDotsPerInch() if screen else 96

    # Scale icon size and font size based on system DPI
    icon_size, font_size = (36, 20) if dpi >= 110 else (38, 26)

    pixmap = QPixmap(icon_size, icon_size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    if not painter.isActive():
        return pixmap
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor(color_hex))
    painter.setFont(QFont(APP_CONFIG.FONT_FAMILY, font_size, QFont.Weight.Bold))

    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, day_str)
    painter.end()

    return pixmap

def center_combo_items(combo: QComboBox) -> None:
    """Center every item text of a combo box, both in the dropdown and closed.

    The dropdown rows honor the per-item TextAlignmentRole; the closed combo
    draws its current text centered through ``combo_stylesheet(center_text=
    True)``, so pair this helper with that flag for a fully centered control.
    Call it again whenever the items are repopulated (clear() drops the roles).

    The role MUST combine the horizontal and vertical flags: a horizontal-only
    alignment leaves the popup painting an empty band under the last option
    (the dead-space bug). ``AlignCenter`` is the same as the two OR'd together.
    """
    for i in range(combo.count()):
        combo.setItemData(i, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, Qt.ItemDataRole.TextAlignmentRole)


class DigitsFirstCombo(QComboBox):
    """Combo whose mixed «digits - month» labels always render digits-first.

    Items like «۰۶ - شهریور» are bidi-ambiguous: their visual order depends on
    the base direction of whatever paints them, and the style used for the
    closed field differs per platform/style from the popup's - which is how
    «شهریور - ۰۶» (closed) ever disagreed with «۰۶ - شهریور» (dropdown rows).
    Painting the closed label here with an explicit RTL base pins the
    digits-first order on every platform (an RTL base lays the number at the
    left), and centers it like the dropdown rows. The popup view is pinned to
    the same base in ``showPopup`` so rows can never flip either.
    """

    def paintEvent(self, event):
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        painter = QStylePainter(self)
        # Frame, background and arrow; the label is drawn manually below.
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, opt)
        rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox, opt, QStyle.SubControl.SC_ComboBoxEditField, self)
        palette = APP_CONFIG.get_current_palette()
        enabled = bool(opt.state & QStyle.StateFlag.State_Enabled)
        painter.setLayoutDirection(Qt.LayoutDirection.RightToLeft)  # digits-first bidi base
        painter.setPen(QColor(palette['GREY_COLOR'] if not enabled else palette['TEXT_COLOR']))
        painter.setFont(self.font())
        painter.drawText(rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                         opt.currentText)

    def showPopup(self):
        # Top-level popup windows do not reliably inherit the widget direction
        # on every platform; pin it so the rows render digits-first as well.
        self.view().setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        super().showPopup()

def fit_combo_width(combo: QComboBox, *, font_size: int = 14, bold: bool = False,
                    extra: int = 46, safety: float = 1.12) -> None:
    """Grow a styled combo box so its longest item is never elided.

    Stylesheet fonts are applied after Qt measures ``sizeHint``, so a combo
    with ``AdjustToContents`` plus a QSS ``font-size`` under-measures its own
    text and the closed combo shows ellipses ("بدو...رار"). We measure the
    widest item with the same pixel size the QSS uses and enforce it as a
    minimum width. ``extra`` covers the worst side of the chrome: the closed
    combo's padding + border, or the popup's item padding + vertical scrollbar
    + frame, whichever is larger. A small ``safety`` factor absorbs the
    per-platform font raster differences (a couple of pixels per glyph on
    some Windows DPI settings) that previously elided «همه ماه‌ها» to
    "همه...ه ها" and «۱۴۰۸» to "۱..۸". The popup view inherits the same
    minimum so list rows never clip either. Call this after the items are
    filled and the stylesheet is applied, and again whenever the items are
    repopulated.
    """
    font = QFont(APP_CONFIG.FONT_FAMILY)
    font.setPixelSize(font_size)
    font.setBold(bold)
    metrics = QFontMetrics(font)
    widest = max((metrics.horizontalAdvance(combo.itemText(i))
                  for i in range(combo.count())), default=0)
    if widest > 0:
        min_width = int(widest * safety) + extra
        combo.setMinimumWidth(min_width)
        # The dropdown is as wide as the combo by default; keep it wide enough
        # for item padding plus the scrollbar so no row is ever elided.
        combo.view().setMinimumWidth(min_width)


def accent_button_stylesheet(palette: dict, *, padding: str = "8px 18px", font_size: Optional[int] = None) -> str:
    """Shared primary (accent) button style: lightens on hover, darkens on press,
    dimmed when disabled."""
    base = QColor(palette['ACCENT_COLOR'])
    font_rule = f" font-size: {font_size}px;" if font_size else ""
    return (
        f"QPushButton {{ background-color: {base.name()}; color: white; border: none; border-radius: 8px; padding: {padding};{font_rule} font-family: '{APP_CONFIG.FONT_FAMILY}'; font-weight: bold; }}"
        f"QPushButton:hover {{ background-color: {base.lighter(110).name()}; }}"
        f"QPushButton:pressed {{ background-color: {base.darker(120).name()}; }}"
        f"QPushButton:disabled {{ background-color: {base.darker(150).name()}; color: rgba(255, 255, 255, 110); }}")


def ghost_button_stylesheet(palette: dict, *, padding: str = "8px 18px") -> str:
    """Shared neutral outline button (accent on hover) for secondary actions.

    Destructive actions keep ``danger_button_stylesheet``; import/export and
    similar low-emphasis buttons use this so red never implies "click me".
    """
    return (
        f"QPushButton {{ background-color: transparent; color: {palette['TEXT_COLOR']}; border: 1px solid {palette['CALENDAR_BORDER_COLOR']}; border-radius: 8px; padding: {padding}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-weight: bold; }}"
        f"QPushButton:hover {{ border-color: {palette['ACCENT_COLOR']}; color: {palette['ACCENT_COLOR']}; }}"
        f"QPushButton:pressed {{ background-color: {palette['HOVER_BG']}; }}")


def danger_button_stylesheet(palette: dict) -> str:
    """Shared destructive (holiday-red) button style for cancel/delete actions."""
    base = QColor(palette['HOLIDAY_COLOR'])
    return (
        f"QPushButton {{ background-color: {base.darker(120).name()}; color: white; border: none; border-radius: 8px; padding: 8px 18px; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-weight: bold; }}"
        f"QPushButton:hover {{ background-color: {base.darker(110).name()}; }}"
        f"QPushButton:pressed {{ background-color: {base.darker(140).name()}; }}")


def _scrollbar_rules(palette: dict, *, width: int, selector: str, min_handle: int) -> str:
    """Core rounded-scrollbar rules shared by every scrollbar in the app.

    ``selector`` is ``QScrollBar`` for plain scroll areas and
    ``QAbstractItemView::verticalScrollBar`` for combo-box popups. The groove
    is painted with ``SCROLLBAR_GROOVE_COLOR`` so the track reads as one round
    pill, the handle is a rounded bar that lights up in the accent color on
    hover and press, and the corner arrow buttons are removed entirely.
    """
    radius = width // 2
    return (
        f"{selector}:vertical {{ border: none; background-color: {palette['SCROLLBAR_GROOVE_COLOR']}; width: {width}px; margin: 0px; border-radius: {radius}px; }}"
        f"{selector}::handle:vertical {{ background-color: {palette['SCROLLBAR_HANDLE_COLOR']}; border-radius: {radius}px; min-height: {min_handle}px; }}"
        f"{selector}::handle:vertical:hover {{ background-color: {palette['ACCENT_COLOR']}; }}"
        f"{selector}::handle:vertical:pressed {{ background-color: {palette['ACCENT_COLOR']}; }}"
        f"{selector}::add-line:vertical, {selector}::sub-line:vertical {{ height: 0px; }}"
        f"{selector}::add-page:vertical, {selector}::sub-page:vertical {{ background: none; }}")


def scrollbar_stylesheet(palette: dict, *, width: int = 10) -> str:
    """Shared vertical QScrollBar style for the scroll areas of the tool windows.

    Same round pill look the combo-box popups already used (grooved round
    track, rounded handle) plus the accent-color hover reaction that every
    scrollbar in the app now shares.
    """
    return _scrollbar_rules(palette, width=width, selector="QScrollBar", min_handle=24)


def line_edit_stylesheet(palette: dict, *, padding: str = "8px", center_text: bool = False) -> str:
    """Shared single-line input style: accent border on hover/focus, greyed
    out while disabled (e.g. the event date-picker's year field for recurring
    events, which need no year). The disabled state dims the text, the border
    and the fill so the field clearly reads as "not editable"."""
    align_rule = " text-align: center;" if center_text else ""
    return (
        f"QLineEdit {{ background-color: {palette['INPUT_BG_COLOR']}; color: {palette['TEXT_COLOR']}; border: 1px solid {palette['CALENDAR_BORDER_COLOR']}; border-radius: 8px; padding: {padding};{align_rule} font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 14px; selection-background-color: {palette['ACCENT_COLOR']}; selection-color: white; }}"
        f"QLineEdit:hover {{ border: 1px solid {palette['ACCENT_COLOR']}; }}"
        f"QLineEdit:focus {{ border: 1px solid {palette['ACCENT_COLOR']}; }}"
        f"QLineEdit:disabled {{ background-color: {palette['SCROLLBAR_GROOVE_COLOR']}; color: {palette['GREY_COLOR']}; border: 1px solid {palette['CALENDAR_BORDER_COLOR']}; }}")


def error_line_edit_stylesheet(palette: dict, *, padding: str = "8px", center_text: bool = False) -> str:
    """The shared line-edit style with the invalid-input (holiday-red) look.

    Appended over ``line_edit_stylesheet`` so the border and text turn holiday
    red - and stay red on hover/focus. Revert to a normal year input by
    applying the plain ``line_edit_stylesheet`` again.
    """
    red = palette['HOLIDAY_COLOR']
    return (line_edit_stylesheet(palette, padding=padding, center_text=center_text)
            + f"QLineEdit {{ border: 1px solid {red}; color: {red}; }}"
              f"QLineEdit:hover, QLineEdit:focus {{ border: 1px solid {red}; }}")


def window_title_button_stylesheets(palette: dict) -> tuple[str, str]:
    """Shared (close, minimize) caption-button styles used by the frameless windows."""
    close_style = (
        f"QPushButton {{ background-color: transparent; border: 1px solid {palette['CALENDAR_BORDER_COLOR']}; border-radius: 8px; color: {palette['TEXT_COLOR']}; font-size: 13px; }}"
        f"QPushButton:hover {{ background-color: #E81123; border-color: #E81123; color: white; }}"
        f"QPushButton:pressed {{ background-color: #C50F1F; border-color: #C50F1F; color: white; }}")
    minimize_style = (
        f"QPushButton {{ background-color: transparent; border: 1px solid {palette['CALENDAR_BORDER_COLOR']}; border-radius: 8px; color: {palette['TEXT_COLOR']}; font-size: 13px; }}"
        f"QPushButton:hover {{ background-color: {palette['HOVER_BG']}; }}"
        f"QPushButton:pressed {{ background-color: {palette['HOVER_BG']}; }}")
    return close_style, minimize_style


def combo_stylesheet(
    palette: dict,
    *,
    padding: str = "8px 5px",
    center_text: bool = False,
    dropdown_bg: Optional[str] = None,
    dropdown_border_key: str = 'CALENDAR_BORDER_COLOR',
    scrollbar_width: int = 10,
    zero_drop_down: bool = True,
) -> str:
    """
    Builds the shared QComboBox stylesheet used by the converter and the
    go-to-date popup. Parameters cover the small per-window visual differences.
    """
    dropdown_color = dropdown_bg if dropdown_bg is not None else palette['INPUT_BG_COLOR']
    dropdown_border_rule = "border: 0px; width: 0px; height: 0px;" if zero_drop_down else "border: 0px;"
    # Same round scrollbar as the scroll areas (shared rules), including the
    # accent-color hover so every scrollbar in the app reacts identically.
    scrollbar_style = _scrollbar_rules(
        palette, width=scrollbar_width,
        selector="QAbstractItemView::verticalScrollBar", min_handle=20)
    text_align_rule = " text-align: center;" if center_text else ""
    return (
        f"QComboBox {{ background-color: {palette['INPUT_BG_COLOR']}; color: {palette['TEXT_COLOR']}; border: 1px solid {palette['CALENDAR_BORDER_COLOR']}; border-radius: 8px; padding: {padding}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 14px;{text_align_rule} selection-background-color: {palette['ACCENT_COLOR']}; selection-color: white;}}"
        f"QComboBox:hover, QComboBox:focus, QComboBox::on {{ border: 1px solid {palette['ACCENT_COLOR']}; }}"
        f"QComboBox:disabled {{ background-color: {palette['SCROLLBAR_GROOVE_COLOR']}; color: {palette['GREY_COLOR']}; border: 1px solid {palette['CALENDAR_BORDER_COLOR']}; }}"
        f"QComboBox::drop-down {{ {dropdown_border_rule} }}"
        f"QComboBox QAbstractItemView {{ background-color: {dropdown_color}; color: {palette['TEXT_COLOR']}; selection-background-color: {palette['ACCENT_COLOR']}; border: 1px solid {palette[dropdown_border_key]}; border-radius: 8px; outline: none;}}"
        f"QComboBox QAbstractItemView::item {{ background-color: transparent; padding: 5px 10px; min-height: 25px; border: none; }}"
        f"QComboBox QAbstractItemView::item:hover {{ background-color: {palette['HOVER_BG']}; border-radius: 4px; }}"
        f"QComboBox QAbstractItemView::item:selected {{ background-color: {palette['ACCENT_COLOR']}; color: white; border-radius: 4px; }}"
        f"QComboBox QAbstractItemView::item:selected:hover {{background-color: {palette['ACCENT_COLOR']}; color: white; }}" + scrollbar_style)
