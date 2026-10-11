"""
UI Helper Functions
-------------------

This module contains utility functions related to creating or manipulating
UI elements, such as dynamically drawing pixmaps or building shared stylesheets.
"""
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication

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
    scrollbar_style = (
        f"QAbstractItemView::verticalScrollBar {{ border: none; background-color: {palette['SCROLLBAR_GROOVE_COLOR']}; width: {scrollbar_width}px; margin: 0px; border-radius: {scrollbar_width // 2}px; }}"
        f"QAbstractItemView::verticalScrollBar::handle {{ background-color: {palette['SCROLLBAR_HANDLE_COLOR']}; border-radius: {scrollbar_width // 2}px; min-height: 20px; }}"
        f"QAbstractItemView::add-line:vertical, QAbstractItemView::sub-line:vertical {{ height: 0px; }}"
        f"QAbstractItemView::add-page:vertical, QAbstractItemView::sub-page:vertical {{ background: none; }}")
    text_align_rule = " text-align: center;" if center_text else ""
    return (
        f"QComboBox {{ background-color: {palette['INPUT_BG_COLOR']}; color: {palette['TEXT_COLOR']}; border: 1px solid {palette['CALENDAR_BORDER_COLOR']}; border-radius: 8px; padding: {padding}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 14px;{text_align_rule} selection-background-color: {palette['ACCENT_COLOR']}; selection-color: white;}}"
        f"QComboBox:hover, QComboBox:focus, QComboBox::on {{ border: 1px solid {palette['ACCENT_COLOR']}; }}"
        f"QComboBox::drop-down {{ {dropdown_border_rule} }}"
        f"QComboBox QAbstractItemView {{ background-color: {dropdown_color}; color: {palette['TEXT_COLOR']}; selection-background-color: {palette['ACCENT_COLOR']}; border: 1px solid {palette[dropdown_border_key]}; border-radius: 8px; outline: none;}}"
        f"QComboBox QAbstractItemView::item {{ background-color: transparent; padding: 5px 10px; min-height: 25px; border: none; }}"
        f"QComboBox QAbstractItemView::item:hover {{ background-color: {palette['HOVER_BG']}; border-radius: 4px; }}"
        f"QComboBox QAbstractItemView::item:selected {{ background-color: {palette['ACCENT_COLOR']}; color: white; border-radius: 4px; }}"
        f"QComboBox QAbstractItemView::item:selected:hover {{background-color: {palette['ACCENT_COLOR']}; color: white; }}" + scrollbar_style)