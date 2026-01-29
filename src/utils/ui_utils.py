"""
UI Helper Functions
-------------------

This module contains utility functions related to creating or manipulating
UI elements, such as dynamically drawing pixmaps.
"""
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap, QStandardItemModel
from PyQt6.QtWidgets import QApplication, QComboBox

from config import APP_CONFIG

import time

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

def apply_combo_style(combo: QComboBox) -> None:
    """
    Applies a centered, and stable toggle behavior to a QComboBox.
    """
    combo.setEditable(True)
    
    line_edit = combo.lineEdit()
    line_edit.setReadOnly(True)
    line_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
    line_edit.setCursor(Qt.CursorShape.PointingHandCursor)
    combo.view().viewport().setCursor(Qt.CursorShape.PointingHandCursor)
    combo.view().setMouseTracking(True)
    line_edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    combo.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

    model = QStandardItemModel()
    combo.setModel(model)

    combo._last_close_time = 0
    original_hide = combo.hidePopup

    def patched_hide_popup():
        combo._last_close_time = time.time()
        original_hide()

    combo.hidePopup = patched_hide_popup
    
    line_edit.installEventFilter(combo)
    
    def custom_event_filter(obj, event):
        if obj == combo.lineEdit() and event.type() == QEvent.Type.MouseButtonPress:
            if event.button() != Qt.MouseButton.LeftButton:
                    return True
            if time.time() - getattr(combo, '_last_close_time', 0) < 0.2:
                return True
            if not combo.view().isVisible():
                combo.showPopup()
            return True
        
        if event.type() == QEvent.Type.MouseButtonDblClick:
             return True
            
        if event.type() == QEvent.Type.MouseMove:
            return True

        return False

    combo.eventFilter = custom_event_filter
