"""
UI Helper Functions
-------------------

This module contains utility functions related to creating or manipulating
UI elements, such as dynamically drawing pixmaps.
"""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt5.QtWidgets import QApplication

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
    pixmap.fill(Qt.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    
    painter.setPen(QColor(color_hex))
    painter.setFont(QFont(APP_CONFIG.FONT_FAMILY, font_size, QFont.Bold))
    
    # Draw text centered in the pixmap rectangle
    painter.drawText(pixmap.rect(), Qt.AlignCenter, day_str)
    painter.end()
    
    return pixmap
