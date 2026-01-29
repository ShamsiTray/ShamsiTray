"""
Event Input Widget
------------------

This module provides `EventInputWidget`, an overlay panel used within the
calendar window for adding or editing user events. It includes a text area,
a checkbox for yearly recurrence, and save/cancel buttons.
"""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QTextOption
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

from config import APP_CONFIG
from .custom_checkbox import CustomCheckbox


class RTLTextEdit(QTextEdit):
    """A QTextEdit with right-to-left layout and placeholder text support."""
    def __init__(self, placeholder_text=""):
        super().__init__()
        self.placeholder_text = placeholder_text
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self.textChanged.connect(self.viewport().update)
    
    def paintEvent(self, event):
        super().paintEvent(event)
        # QTextEdit does not support placeholders in RTL reliably, so we manually draw it when the document is empty.
        if not self.toPlainText() and self.placeholder_text:
            painter = QPainter(self.viewport())
            painter.setPen(QColor(128, 128, 128))
            rect = self.viewport().rect()
            rect.adjust(5, 5, -5, -5)
            painter.drawText(rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop, self.placeholder_text)

class EventInputWidget(QWidget):
    """An integrated widget for adding or editing a user event."""
    # Arguments:
    # text (str): event description
    # is_yearly (bool): whether the event repeats every year
    # remove_after_finish (bool): auto-remove after date passes
    saved = pyqtSignal(str, bool, bool)
    canceled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)
        
        self.title_label = QLabel("افزودن/ویرایش رویداد")
        main_layout.addWidget(self.title_label)
        
        self.text_edit = RTLTextEdit("رویداد خود را وارد کنید")
        text_option = QTextOption()
        text_option.setTextDirection(Qt.LayoutDirection.RightToLeft)
        self.text_edit.document().setDefaultTextOption(text_option)
        main_layout.addWidget(self.text_edit)

        checkbox_container_layout = QVBoxLayout()
        self.yearly_checkbox = CustomCheckbox("رویداد سالانه (تکرار هر سال)")
        self.remove_after_finish_checkbox = CustomCheckbox("حذف پس از گذشت تاریخ")
        
        checkbox_container_layout.addWidget(self.yearly_checkbox)
        checkbox_container_layout.addWidget(self.remove_after_finish_checkbox)
        main_layout.addLayout(checkbox_container_layout)
        main_layout.addStretch()

        button_layout = QHBoxLayout()
        self.save_button = QPushButton("ذخیره")
        self.cancel_button = QPushButton("لغو")
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)
        main_layout.addLayout(button_layout)

        self.save_button.clicked.connect(self._on_save)
        self.cancel_button.clicked.connect(self.canceled)
        self.yearly_checkbox.toggled.connect(self._on_yearly_toggled)
        
        self.update_styles()

    def update_styles(self):
        palette = APP_CONFIG.get_current_palette()
        self.setStyleSheet(f"EventInputWidget {{background-color: {palette['BACKGROUND_COLOR']}; border: 1px solid {palette['MENU_BORDER_COLOR']}; border-radius: 15px;}}")
        
        self.title_label.setStyleSheet(f"color: {palette['TEXT_COLOR']}; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 16px; font-weight: bold; border: none;")
        self.text_edit.setStyleSheet(
            f"QTextEdit {{color: {palette['TEXT_COLOR']}; border: 1px solid {palette['MENU_BORDER_COLOR']}; border-radius: 8px; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-size: 14px; selection-background-color: {palette['ACCENT_COLOR']}; selection-color: white; }}"
            f"QTextEdit:focus {{border-color: {palette['ACCENT_COLOR']};}}")
        self.text_edit.viewport().setStyleSheet(f"background-color: {palette['INPUT_BG_COLOR']}; border-radius: 8px")
        self.yearly_checkbox.update_visuals()
        self.remove_after_finish_checkbox.update_visuals()
        
        cancel_button_style = (
            f"QPushButton {{ background-color: {QColor(palette['HOLIDAY_COLOR']).darker(120).name()}; color: white; border: none; border-radius: 8px; padding: 8px 18px; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {QColor(palette['HOLIDAY_COLOR']).darker(110).name()}; }}"
            f"QPushButton:pressed {{ background-color: {QColor(palette['HOLIDAY_COLOR']).darker(140).name()}; }}")
        self.cancel_button.setStyleSheet(cancel_button_style)
        
        save_button_style = (
            f"QPushButton {{ background-color: {palette['ACCENT_COLOR']}; color: white; border: none; border-radius: 8px; padding: 8px 18px; font-family: '{APP_CONFIG.FONT_FAMILY}'; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {QColor(palette['ACCENT_COLOR']).lighter(110).name()}; }}"
            f"QPushButton:pressed {{ background-color: {QColor(palette['ACCENT_COLOR']).darker(120).name()}; }}")
        self.save_button.setStyleSheet(save_button_style)

    def set_data(self, text, is_yearly, remove_after_finish):
        self.text_edit.setText(text)
        self.yearly_checkbox.setChecked(is_yearly)
        self.remove_after_finish_checkbox.setChecked(remove_after_finish)
        self.remove_after_finish_checkbox.setEnabled(not is_yearly)

    def _on_yearly_toggled(self, is_checked):
        # Yearly events cannot be auto-removed
        self.remove_after_finish_checkbox.setEnabled(not is_checked)
        if is_checked:
            self.remove_after_finish_checkbox.setChecked(False)

    def _on_save(self):
        text = self.text_edit.toPlainText().strip()
        if not text:
            return
        self.saved.emit(self.text_edit.toPlainText().strip(), self.yearly_checkbox.isChecked(), self.remove_after_finish_checkbox.isChecked())